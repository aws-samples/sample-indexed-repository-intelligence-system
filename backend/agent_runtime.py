# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Amazon Bedrock AgentCore Runtime entrypoint for IRIS.

This is the deployed backend for IRIS on AgentCore Runtime, implementing the
AgentCore ``HTTP`` protocol contract:

- ``POST /invocations`` — single request/response (SSE streaming for chat).
- ``GET /ping``         — health check (provided automatically by the harness).

Transport / session model
--------------------------
AgentCore Runtime gives each ``runtimeSessionId`` its own isolated microVM, so a
per-session Strands ``Agent`` can live in process for the life of that microVM.
We keep a small ``session_id -> Agent`` cache so multi-turn conversations reuse
the same agent (and therefore the same in-memory conversation history), matching
the behavior of the old in-memory ``SessionManager`` without the WebSocket
lifecycle, TTL, or rate-limiter machinery (the Runtime handles session
lifecycle and isolation).

Event contract
--------------
The streamed events use the SAME envelope shape the frontend already parses in
``handleWebSocketMessage`` (``irisService.js``): ``status``, ``stream_chunk``,
``tool_use``, ``complete``, ``error``. The AgentCore harness serializes each
yielded dict as an SSE ``data: {json}`` frame automatically, so this module
yields plain dicts and never formats SSE by hand.
"""

import logging
import os
import uuid
from typing import Any, AsyncGenerator, Dict, Optional

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

try:
    from .create_backend_agent import create_backend_agent, setup_codebase
    from .security_utils import get_safe_error_type, sanitize_for_log
except ImportError:  # allow running as a plain script (local dev / container CMD)
    from create_backend_agent import create_backend_agent, setup_codebase
    from security_utils import get_safe_error_type, sanitize_for_log

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _build_middleware() -> Optional[list]:
    """Local-dev CORS only.

    In the deployed Runtime the browser calls the AgentCore data-plane endpoint
    (``bedrock-agentcore.{region}.amazonaws.com``), which handles CORS itself — this
    app never sees those requests cross-origin. For local dev the React dev server
    (``:3000``) calls this app (``:8080``) directly, which IS cross-origin, so we
    enable CORS only when ``CORS_ORIGINS`` is set. Absent that env var, no CORS
    middleware is attached (inert in production).
    """
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return None
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins or "*" in origins:
        # Refuse wildcard: browsers reject it with credentials anyway, and it's
        # never appropriate for a token-bearing endpoint.
        return None
    return [
        Middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization",
                           "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"],
        )
    ]


app = BedrockAgentCoreApp(middleware=_build_middleware())

# session_id -> Agent. One microVM serves one runtimeSessionId, so this cache
# normally holds a single entry; the dict simply tolerates a session id changing
# within the same microVM (e.g. local dev with multiple sessions).
_agents: Dict[str, Any] = {}

# Fallback session id used when no runtime session header is present (e.g. local
# `curl` testing). Kept stable for the process so local multi-turn works.
_LOCAL_SESSION_ID = "local-dev-session"


def _get_agent(session_id: str):
    """Return the per-session Strands agent, creating it on first use."""
    agent = _agents.get(session_id)
    if agent is None:
        log.info("Creating agent for session %s", sanitize_for_log(session_id))
        agent = create_backend_agent()
        _agents[session_id] = agent
    return agent


def _resolve_session_id(context: Any) -> str:
    """Pick the session id from the AgentCore request context, with a local fallback."""
    session_id = getattr(context, "session_id", None) if context else None
    return session_id or _LOCAL_SESSION_ID


async def _stream_chat(prompt: str, agent) -> AsyncGenerator[Dict[str, Any], None]:
    """Reshape Strands ``stream_async`` events into IRIS's frontend event envelope."""
    message_id = str(uuid.uuid4())

    # Initial status (matches old "processing" status event).
    yield {
        "type": "status",
        "message_id": message_id,
        "data": {"status": "processing", "message": "Processing your request..."},
    }

    announced_tools: set = set()

    async for event in agent.stream_async(prompt):
        # Streaming text tokens.
        if "data" in event:
            yield {
                "type": "stream_chunk",
                "message_id": message_id,
                "data": {"chunk_type": "text", "content": event["data"]},
            }

        # Tool invocation start — announce each tool once (matches old tool_use event).
        if "current_tool_use" in event:
            tool = event["current_tool_use"]
            tool_id = tool.get("toolUseId")
            if tool_id and tool_id not in announced_tools:
                announced_tools.add(tool_id)
                yield {
                    "type": "tool_use",
                    "message_id": message_id,
                    "data": {
                        "tool_name": tool.get("name"),
                        "tool_id": tool_id,
                    },
                }

        # Final result — signal completion. A guardrail stop is logged like before.
        if "result" in event:
            result = event["result"]
            stop_reason = getattr(result, "stop_reason", None) or (
                result.get("stop_reason") if isinstance(result, dict) else None
            )
            if stop_reason == "guardrail_intervened":
                log.warning("Bedrock Guardrail intervened — prompt or response blocked")
            yield {
                "type": "complete",
                "message_id": message_id,
                "data": {"status": "completed"},
            }


@app.entrypoint
async def invoke(payload: Dict[str, Any], context: Any) -> AsyncGenerator[Dict[str, Any], None]:
    """AgentCore Runtime entrypoint.

    Chat is the default action and streams SSE events. A small set of non-chat
    actions return a single JSON-ish event for parity with the old auxiliary
    HTTP endpoints (``/config``, ``/codebase-info``).

    Payload shapes:
        {"prompt": "..."}                      -> chat (also accepts "message")
        {"action": "config"}                   -> setup_codebase()
        {"action": "codebase_info"}            -> codebase info (best-effort)
    """
    session_id = _resolve_session_id(context)
    action = payload.get("action")

    # --- Non-chat actions (parity with old read-only HTTP endpoints) ---
    if action == "config":
        yield {"type": "config", "data": setup_codebase()}
        return

    if action == "codebase_info":
        yield {"type": "codebase_info", "data": _codebase_info()}
        return

    if action == "generate_context":
        yield {"type": "generate_context", "data": _generate_context()}
        return

    # --- Default: chat ---
    prompt = payload.get("prompt") or payload.get("message") or ""
    if not str(prompt).strip():
        yield {"type": "error", "data": {"error": "Empty message"}}
        return

    try:
        agent = _get_agent(session_id)
        async for event in _stream_chat(str(prompt), agent):
            yield event
    except Exception as e:  # noqa: BLE001 — surface a safe error to the client
        log.error(
            "Error processing invocation for session %s: %s - %s",
            sanitize_for_log(session_id),
            get_safe_error_type(e),
            sanitize_for_log(e),
        )
        yield {"type": "error", "data": {"error": "Error processing query"}}


def _codebase_info() -> Dict[str, Any]:
    """Best-effort codebase info, mirroring the old /codebase-info endpoint's core fields."""
    try:
        from pathlib import Path

        from iris.file_system.file_management import validate_tree
        from iris.utils.utils import construct_output_dir, load_default_config
        from iris.utils.codebase_stats import get_codebase_evaluation_stats

        config = load_default_config()
        codebase_dir = config.get("codebase_dir")
        if not codebase_dir or not Path(codebase_dir).exists():
            return {"status": "no_codebase", "error": "No codebase loaded yet"}

        files_result = validate_tree(codebase_dir=codebase_dir)
        output_dir = construct_output_dir(codebase_dir=codebase_dir)
        evaluation_stats = get_codebase_evaluation_stats(output_dir)
        return {
            "status": "success",
            "codebase_dir": codebase_dir,
            "total_files": files_result.total_files,
            "tree_display": files_result.tree_display,
            "tree_structure": files_result.tree_structure,
            "evaluation": {
                "last_evaluation": evaluation_stats.get("last_evaluation"),
                "evaluated_files": evaluation_stats.get("evaluated_files", 0),
                "evaluation_coverage": evaluation_stats.get("evaluation_coverage", 0.0),
            },
        }
    except Exception as e:  # noqa: BLE001
        log.error("Error getting codebase info: %s", get_safe_error_type(e))
        return {"status": "error", "error": "Failed to retrieve codebase information"}


def _generate_context() -> Dict[str, Any]:
    """Re-index the configured codebase, mirroring the old /generate-context endpoint.

    Note: this is a long, Bedrock-fan-out job. On the deployed Runtime, indexing is
    normally done offline/at packaging time; this action exists for parity with the
    local UI's refresh button. Long invocations are supported by the Runtime.
    """
    try:
        from iris.generate_context import generate_context
        from iris.utils.utils import (
            construct_output_dir,
            get_ignore_patterns,
            load_default_config,
        )

        config = load_default_config()
        codebase_dir = config.get("codebase_dir")
        if not codebase_dir:
            return {"status": "error", "error": "No codebase directory configured"}

        output_dir = construct_output_dir(codebase_dir=codebase_dir)
        ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)
        result = generate_context(
            codebase_dir=codebase_dir,
            output_dir=str(output_dir),
            ignore_patterns=ignore_patterns,
            additional_context=None,
        )
        return {
            "status": result.status,
            "message": (
                "Context generated successfully"
                if result.status == "success"
                else "Context generation failed"
            ),
            "processed_files": getattr(result, "processed_files", []),
        }
    except Exception as e:  # noqa: BLE001
        log.error("Error generating context: %s", get_safe_error_type(e))
        return {"status": "error", "error": "Failed to generate context"}


if __name__ == "__main__":
    # Local dev / container entrypoint. The harness binds 0.0.0.0 when it detects
    # a container (via /.dockerenv or DOCKER_CONTAINER), else 127.0.0.1.
    port = int(os.getenv("PORT", "8080"))
    log.info("Starting IRIS AgentCore Runtime on port %d...", port)
    app.run(port=port)
