# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
WebSocket Server for IRIS Chatbot

This module implements a FastAPI WebSocket server that:
1. Accepts WebSocket connections
2. Creates/manages sessions using SessionManager
3. Handles message processing with AI agents
4. Manages connection lifecycle (connect, message, disconnect)
"""

import json
import logging
import os
import time
import uuid
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from .session_manager import session_manager
    from .auth import authenticate_websocket_token, cognito_auth
    from .security_utils import (
        sanitize_for_log,
        get_safe_error_type,
    )
except ImportError:
    from session_manager import session_manager
    from auth import authenticate_websocket_token, cognito_auth
    from security_utils import (
        sanitize_for_log,
        get_safe_error_type,
    )

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class WebSocketMessage(BaseModel):
    """WebSocket message structure - matches your mock backend format"""

    type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
    message_id: str = None


# Create FastAPI application
app = FastAPI(title="IRIS WebSocket Server")

# Add CORS middleware to allow React frontend connections
_cors_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
_cors_origins = [o.strip() for o in _cors_origins if o.strip()]

# Security: reject wildcard origin when credentials are enabled — browsers
# will refuse the response anyway, but failing loudly at startup is clearer.
if "*" in _cors_origins:
    raise RuntimeError(
        "CORS_ORIGINS contains '*' which is incompatible with allow_credentials=True. "
        "Set explicit origins instead (e.g. 'http://localhost:3000')."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    """Add security headers to all HTTP responses"""
    response = await call_next(request)

    # Security headers as per threat protection requirements
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["Cache-Control"] = "no-store, no-cache"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' wss: https:; frame-ancestors 'none';"
    )

    return response


def _require_auth_for_endpoint(request: Request) -> None:
    """Verify that the caller is authorized for sensitive HTTP endpoints.

    In anonymous mode the check is a no-op (local dev).  Otherwise the
    request must carry a valid Bearer token in the Authorization header.
    """
    if cognito_auth.allow_anonymous:
        return  # local dev — allow without token

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header required")

    user = authenticate_websocket_token(auth_header)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


class ConnectionManager:
    """
    Manages active WebSocket connections.

    This class maps WebSocket connections to session IDs and handles
    the connection lifecycle.
    """

    def __init__(self):
        # Map WebSocket connections to session IDs
        self.active_connections: Dict[WebSocket, str] = {}
        # Track authenticated connections
        self.authenticated_connections: set = set()

    async def connect(self, websocket: WebSocket) -> str:
        """
        Accept a new WebSocket connection and create a session.
        Authentication will happen via the first message (secure approach).

        Args:
            websocket: The WebSocket connection

        Returns:
            str: The session ID for this connection
        """
        await websocket.accept()

        try:
            # Generate session ID first
            session_id = str(uuid.uuid4())

            # Map this WebSocket to the session ID immediately
            self.active_connections[websocket] = session_id

            log.info(
                f"WebSocket connected (unauthenticated). Session: {session_id}, Active connections: {len(self.active_connections)}"
            )

            # Send connection confirmation BEFORE creating agent (which takes time)
            welcome_message = WebSocketMessage(
                type="welcome",
                data={
                    "message": "Connected to IRIS Assistant",
                    "session_id": session_id,
                    "client_id": session_id,
                    "status": "initializing",
                },
                message_id=str(uuid.uuid4()),
            )
            await websocket.send_text(welcome_message.model_dump_json())

            # Now create session with agent (this takes time but client knows we're alive)
            session_manager.create_session_with_id(session_id, None)
            _rate_limiters[session_id] = _TokenBucket(
                _RATE_LIMIT_RATE, _RATE_LIMIT_BURST
            )

            # Auto-authenticate in anonymous mode so chat messages are not blocked
            if cognito_auth.allow_anonymous and not cognito_auth.enabled:
                self.authenticated_connections.add(websocket)
                log.info(
                    f"Auto-authenticated anonymous connection. Session: {session_id}"
                )

            # Send ready message
            ready_message = WebSocketMessage(
                type="ready",
                data={
                    "message": "Agent initialized and ready",
                    "session_id": session_id,
                },
                message_id=str(uuid.uuid4()),
            )
            await websocket.send_text(ready_message.model_dump_json())

            return session_id

        except Exception as e:
            # Handle any session creation errors and send to frontend
            # Sanitize error for logging to prevent log injection
            safe_error = sanitize_for_log(e)
            error_type = get_safe_error_type(e)
            log.error(f"Failed to create session: {error_type} - {safe_error}")

            # Send generic error message to frontend (don't leak details)
            error_message = WebSocketMessage(
                type="error",
                data={"error": "Failed to create session"},
                message_id=str(uuid.uuid4()),
            )

            await websocket.send_text(error_message.model_dump_json())
            raise e

    def disconnect(self, websocket: WebSocket):
        """
        Handle WebSocket disconnection and cleanup session.

        Args:
            websocket: The WebSocket connection that disconnected
        """
        if websocket in self.active_connections:
            session_id = self.active_connections[websocket]

            # Remove from active connections
            del self.active_connections[websocket]

            # Remove from authenticated connections if present
            self.authenticated_connections.discard(websocket)

            # Clean up session in session manager
            session_manager.remove_session(session_id)
            _rate_limiters.pop(session_id, None)

            log.info(
                f"WebSocket disconnected. Session: {session_id}, Remaining connections: {len(self.active_connections)}"
            )
        else:
            log.warning("Attempted to disconnect unknown WebSocket")

    def get_session_id(self, websocket: WebSocket) -> str:
        """Get the session ID for a WebSocket connection"""
        return self.active_connections.get(websocket)


# Global connection manager instance
connection_manager = ConnectionManager()


class _TokenBucket:
    """Simple token-bucket rate limiter for a single session."""

    def __init__(self, rate: float, capacity: float):
        self._rate = rate  # tokens added per second
        self._capacity = capacity  # max tokens (burst)
        self._tokens = capacity
        self._last = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


# Per-session rate limiters: 10 messages/minute = ~0.167 tokens/sec, burst 10
_rate_limiters: Dict[str, _TokenBucket] = {}
_RATE_LIMIT_RATE = 10 / 60  # tokens per second
_RATE_LIMIT_BURST = 10  # max burst


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint that handles the complete connection lifecycle.

    This function:
    1. Accepts the connection and creates a session
    2. Listens for messages and processes them
    3. Handles disconnection gracefully
    """
    session_id = None

    # Origin allowlist — HTTP CORS does not apply to WebSocket upgrades, so
    # browser-origin enforcement happens here. Non-browser clients omit the
    # header; allow that path only when running in anonymous/dev mode.
    origin = websocket.headers.get("origin")
    if origin is None:
        if not cognito_auth.allow_anonymous:
            log.warning("Rejecting WS upgrade: missing Origin header")
            await websocket.close(code=1008)
            return
    elif origin not in _cors_origins:
        log.warning(
            f"Rejecting WS upgrade: origin not allowed: {sanitize_for_log(origin)}"
        )
        await websocket.close(code=1008)
        return

    try:
        # Step 1: Accept connection and create session
        session_id = await connection_manager.connect(websocket)

        # Step 2: Listen for messages
        while True:
            # Wait for message from client
            data = await websocket.receive_text()

            try:
                # Parse JSON message
                message = json.loads(data)
                log.info(
                    f"Received message from session {session_id}: {message.get('type', 'unknown')}"
                )

                # Process the message (now sends responses directly via websocket)
                await process_message(session_id, message, websocket)

            except json.JSONDecodeError:
                # Handle invalid JSON using structured format
                error_message = WebSocketMessage(
                    type="error",
                    data={"error": "Invalid JSON format"},
                    message_id=str(uuid.uuid4()),
                )
                await websocket.send_text(error_message.model_dump_json())

            except Exception as e:
                # Handle processing errors using structured format
                safe_error = sanitize_for_log(e)
                error_type = get_safe_error_type(e)
                log.error(
                    f"Error processing message for session {session_id}: {error_type} - {safe_error}"
                )
                error_message = WebSocketMessage(
                    type="error",
                    data={"error": "Processing error occurred"},
                    message_id=str(uuid.uuid4()),
                )
                await websocket.send_text(error_message.model_dump_json())

    except WebSocketDisconnect:
        # Step 3: Handle graceful disconnection
        log.info(f"WebSocket disconnected gracefully for session: {session_id}")

    except Exception as e:
        # Handle unexpected errors
        safe_error = sanitize_for_log(e)
        error_type = get_safe_error_type(e)
        log.error(
            f"Unexpected error in WebSocket connection for session {session_id}: {error_type} - {safe_error}"
        )

    finally:
        # Always clean up the connection
        connection_manager.disconnect(websocket)


async def process_message(
    session_id: str, message: Dict[str, Any], websocket: WebSocket
) -> None:
    """
    Process a message from the client using the AI agent.

    Args:
        session_id: The session ID
        message: The message from the client
        websocket: The WebSocket connection to send responses
    """
    try:
        # Get the session from our session manager
        session = session_manager.get_session(session_id)
        if not session:
            error_message = WebSocketMessage(
                type="error",
                data={"error": "Session not found"},
                message_id=str(uuid.uuid4()),
            )
            await websocket.send_text(error_message.model_dump_json())
            return

        message_type = message.get("type")

        if message_type == "authenticate":
            # Handle JWT authentication (secure approach)
            token = message.get("token")
            user_info = authenticate_websocket_token(token)

            if user_info:
                # Authentication successful
                connection_manager.authenticated_connections.add(websocket)

                # Update session with user info
                session.user_info = user_info

                log.info(
                    f"WebSocket authenticated for user: {user_info.get('email', 'unknown')}"
                )

                # Send success response
                auth_success_message = WebSocketMessage(
                    type="auth_success",
                    data={"message": "Authentication successful"},
                    message_id=str(uuid.uuid4()),
                )
                await websocket.send_text(auth_success_message.model_dump_json())
            else:
                # Authentication failed
                log.warning(
                    f"WebSocket authentication failed for session: {session_id}"
                )

                auth_error_message = WebSocketMessage(
                    type="auth_error",
                    data={"error": "Invalid token"},
                    message_id=str(uuid.uuid4()),
                )
                await websocket.send_text(auth_error_message.model_dump_json())

                # Close connection after auth failure
                await websocket.close(code=1008, reason="Authentication failed")

        elif message_type == "chat":
            # Check if authentication is required and user is authenticated.
            # When Cognito is configured (enabled=True), require auth.
            # When Cognito is not configured, require auth UNLESS allow_anonymous is set.
            auth_required = cognito_auth.enabled or not cognito_auth.allow_anonymous
            if (
                auth_required
                and websocket not in connection_manager.authenticated_connections
            ):
                error_message = WebSocketMessage(
                    type="error",
                    data={"error": "Authentication required before sending messages"},
                    message_id=str(uuid.uuid4()),
                )
                await websocket.send_text(error_message.model_dump_json())
                return

            # Enforce per-session rate limit before processing chat messages
            limiter = _rate_limiters.get(session_id)
            if limiter and not limiter.consume():
                await websocket.send_text(
                    WebSocketMessage(
                        type="error",
                        data={"error": "Rate limit exceeded. Please slow down."},
                        message_id=str(uuid.uuid4()),
                    ).model_dump_json()
                )
                return

            # Handle chat messages (matches your mock backend format)
            user_message = message.get("message", "")

            if not user_message.strip():
                error_message = WebSocketMessage(
                    type="error",
                    data={"error": "Empty message"},
                    message_id=str(uuid.uuid4()),
                )
                await websocket.send_text(error_message.model_dump_json())
                return

            # Use the streaming process query method
            await stream_process_query(user_message, session.agent, websocket)

        elif message_type == "ping":
            # Handle ping/keepalive (always allowed)
            pong_message = WebSocketMessage(
                type="pong",
                data={"timestamp": datetime.now().isoformat()},
                message_id=str(uuid.uuid4()),
            )
            await websocket.send_text(pong_message.model_dump_json())

        else:
            error_message = WebSocketMessage(
                type="error",
                data={"error": f"Unknown message type: {message_type}"},
                message_id=str(uuid.uuid4()),
            )
            await websocket.send_text(error_message.model_dump_json())

    except Exception as e:
        safe_error = sanitize_for_log(e)
        error_type = get_safe_error_type(e)
        log.error(
            f"Error in process_message for session {session_id}: {error_type} - {safe_error}"
        )
        error_message = WebSocketMessage(
            type="error",
            data={"error": "Internal processing error"},
            message_id=str(uuid.uuid4()),
        )
        await websocket.send_text(error_message.model_dump_json())


async def stream_process_query(query: str, agent, websocket: WebSocket):
    """
    Process query with streaming and send updates via WebSocket.
    """
    try:
        message_id = str(uuid.uuid4())

        # Send initial status
        await websocket.send_text(
            WebSocketMessage(
                type="status",
                data={"status": "processing", "message": "Processing your request..."},
                message_id=message_id,
            ).model_dump_json()
        )

        # Stream the response using the agent
        async for chunk in stream_text(agent, query):
            if chunk["type"] == "text":
                # Send streaming text
                await websocket.send_text(
                    WebSocketMessage(
                        type="stream_chunk",
                        data={"chunk_type": "text", "content": chunk["data"]},
                        message_id=message_id,
                    ).model_dump_json()
                )

            elif chunk["type"] == "tool":
                # Send tool use notification
                await websocket.send_text(
                    WebSocketMessage(
                        type="tool_use",
                        data={
                            "tool_name": chunk["name"],
                            "tool_id": chunk.get("toolUseId"),
                        },
                        message_id=message_id,
                    ).model_dump_json()
                )

            elif chunk["type"] == "final":
                # Send completion
                await websocket.send_text(
                    WebSocketMessage(
                        type="complete",
                        data={"status": "completed"},
                        message_id=message_id,
                    ).model_dump_json()
                )

    except Exception as e:
        safe_error = sanitize_for_log(e)
        error_type = get_safe_error_type(e)
        log.error(f"Error processing query: {error_type} - {safe_error}")
        await websocket.send_text(
            WebSocketMessage(
                type="error", data={"error": "Error processing query"}
            ).model_dump_json()
        )


async def stream_text(agent, prompt: str, **kwargs):
    """
    Stream text from agent with proper event handling.
    """
    try:
        async for event in agent.stream_async(prompt):
            # Handle text streaming
            if "data" in event:
                yield {"type": "text", "data": event["data"]}

            # Handle tool use streaming
            if "current_tool_use" in event:
                tool = event["current_tool_use"]
                yield {
                    "type": "tool",
                    "toolUseId": tool.get("toolUseId"),
                    "name": tool.get("name"),
                    "input": tool.get("input"),
                }

            # Handle tool results
            if "tool_result" in event:
                yield {"type": "tool_result", "data": event["tool_result"]}

            # Handle final result - this ends the stream
            if "result" in event:
                # Check if guardrail intervened
                result = event["result"]
                stop_reason = getattr(result, "stop_reason", None) or (
                    result.get("stop_reason") if isinstance(result, dict) else None
                )
                if stop_reason == "guardrail_intervened":
                    log.warning(
                        "Bedrock Guardrail intervened — prompt or response blocked"
                    )
                yield {"type": "final", "result": result}
                # break  # Exit the loop when we get the final result

            # Handle completion - send once
            # Note: 'complete' signals end of event loop CYCLE, not necessarily final
            if event.get("complete", False):
                # This can fire multiple times during multi-turn reasoning
                # Only use for logging, not for breaking
                log.debug("Event loop cycle completed")

        # Stream naturally completed - telemetry spans close properly
        log.debug("stream_async completed naturally")
    except Exception as e:
        safe_error = sanitize_for_log(e)
        error_type = get_safe_error_type(e)
        log.error(f"Error in stream_text: {error_type} - {safe_error}")
        raise


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint — returns minimal info to avoid leaking internal state."""
    return {"status": "healthy"}


# Config endpoint for frontend
@app.get("/config")
@app.get("/api/config")
async def get_config(request: Request):
    """Get configuration for frontend"""
    _require_auth_for_endpoint(request)
    try:
        from .create_backend_agent import setup_codebase

        codebase_info = setup_codebase()
        return codebase_info
    except ImportError:
        from create_backend_agent import setup_codebase

        codebase_info = setup_codebase()
        return codebase_info
    except Exception as e:
        safe_error = sanitize_for_log(e)
        error_type = get_safe_error_type(e)
        log.error(f"Error getting config: {error_type} - {safe_error}")
        return {
            "codebase_dir": "/app/codebase",
            "output_dir": "/app/output",
            "status": "error",
            "error": "Configuration error occurred",
        }


# New endpoint for detailed codebase information
@app.get("/codebase-info")
@app.get("/api/codebase-info")
async def get_codebase_info(request: Request):
    """Get detailed codebase information including file tree and statistics"""
    _require_auth_for_endpoint(request)
    try:
        from iris.file_system.file_management import validate_tree
        from iris.utils.utils import (
            load_default_config,
            construct_output_dir,
        )
        from iris.utils.codebase_stats import get_codebase_evaluation_stats

        config = load_default_config()
        codebase_dir = config.get("codebase_dir")

        if not codebase_dir:
            return {"status": "error", "error": "No codebase directory configured"}

        # Check if directory exists before calling validate_tree (which uses sys.exit for CLI)
        if not Path(codebase_dir).exists():
            log.info(f"Codebase directory not found: {codebase_dir}")
            return {"status": "no_codebase", "error": "No codebase loaded yet"}

        # Get file tree and validation info
        files_result = validate_tree(codebase_dir=codebase_dir)

        # Get output directory for evaluation stats
        output_dir = construct_output_dir(codebase_dir=codebase_dir)

        # Get evaluation statistics including last evaluation timestamp
        evaluation_stats = get_codebase_evaluation_stats(output_dir)

        return {
            "status": "success",
            "codebase_dir": codebase_dir,
            "total_files": files_result.total_files,
            "has_changed": files_result.has_changed,
            "tree_display": files_result.tree_display,
            "tree_structure": files_result.tree_structure,
            "change_details": (
                files_result.change_details if files_result.has_changed else None
            ),
            "files_to_process": (
                files_result.files_to_process if files_result.has_changed else []
            ),
            "evaluation": {
                "last_evaluation": evaluation_stats.get("last_evaluation"),
                "evaluated_files": evaluation_stats.get("evaluated_files", 0),
                "evaluation_coverage": evaluation_stats.get("evaluation_coverage", 0.0),
            },
        }

    except FileNotFoundError as e:
        log.info(f"Codebase directory not found: {e}")
        return {"status": "no_codebase", "error": "No codebase loaded yet"}
    except Exception as e:
        safe_error = sanitize_for_log(e)
        error_type = get_safe_error_type(e)
        log.error(f"Error getting codebase info: {error_type} - {safe_error}")
        return {"status": "error", "error": "Failed to retrieve codebase information"}


# New endpoint for generating/refreshing context
@app.post("/generate-context")
async def generate_context_endpoint(request: Request):
    """Generate or refresh codebase context"""
    _require_auth_for_endpoint(request)
    try:
        from iris.generate_context import generate_context
        from iris.utils.utils import (
            load_default_config,
            construct_output_dir,
            get_ignore_patterns,
        )

        config = load_default_config()
        codebase_dir = config.get("codebase_dir")

        if not codebase_dir:
            return {"status": "error", "error": "No codebase directory configured"}

        output_dir = construct_output_dir(codebase_dir=codebase_dir)
        ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)

        # Generate context
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

    except Exception as e:
        safe_error = sanitize_for_log(e)
        error_type = get_safe_error_type(e)
        log.error(f"Error generating context: {error_type} - {safe_error}")
        return {"status": "error", "error": "Failed to generate context"}


# New endpoint for tree validation
@app.post("/validate-tree")
async def validate_tree_endpoint(request: Request):
    """Validate the current file tree"""
    _require_auth_for_endpoint(request)
    try:
        from iris.file_system.file_management import validate_tree
        from iris.utils.utils import load_default_config

        config = load_default_config()
        codebase_dir = config.get("codebase_dir")

        if not codebase_dir:
            return {"status": "error", "error": "No codebase directory configured"}

        # Validate tree
        files_result = validate_tree(codebase_dir=codebase_dir)

        return {
            "status": "success",
            "has_changed": files_result.has_changed,
            "total_files": files_result.total_files,
            "tree_display": files_result.tree_display,
            "change_details": (
                files_result.change_details if files_result.has_changed else None
            ),
            "files_to_process": (
                files_result.files_to_process if files_result.has_changed else []
            ),
        }

    except Exception as e:
        safe_error = sanitize_for_log(e)
        error_type = get_safe_error_type(e)
        log.error(f"Error validating tree: {error_type} - {safe_error}")
        return {"status": "error", "error": "Failed to validate file tree"}


# Session info endpoint (for debugging — only available when ENABLE_DEBUG_ENDPOINTS=true)
if os.getenv("ENABLE_DEBUG_ENDPOINTS", "false").lower() == "true":

    @app.get("/sessions")
    async def get_sessions(request: Request):
        """Get information about active sessions"""
        _require_auth_for_endpoint(request)
        return {
            "sessions": session_manager.list_sessions(),
            "total_count": session_manager.get_active_session_count(),
        }


if __name__ == "__main__":
    import uvicorn

    log.info("Starting IRIS WebSocket Server...")
    # binding to 0.0.0.0 is safe in ECS - container network is isolated and only accessible via ALB/service mesh within VPC
    uvicorn.run(
        "websocket_server:app",
        host="0.0.0.0",  # nosec B104: binding to 0.0.0.0 is safe in ECS - container network is isolated
        port=8000,
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level="info",
    )
