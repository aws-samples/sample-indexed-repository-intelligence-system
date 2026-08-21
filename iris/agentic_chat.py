# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import boto3
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Iterable
from strands import Agent
from strands.models import BedrockModel
from strands.agent.conversation_manager import SlidingWindowConversationManager
from .summarize.utils import load_prompts
from .generate_context import generate_context
from .utils.bedrock import create_session_with_assumed_role, extended_ttl_models
from .utils.logging_setup import configure_logging
from .utils.utils import (
    construct_output_dir,
    get_additional_context,
    load_default_config,
    get_ignore_patterns,
)
from .common.monitoring import AgentMonitor
from .agents.file_retrieval_agent import file_retrieval_agent
from .agents.web_search_tool import web_search
from .agents.code_search_tool import code_search_tool
from .agents.mcp_tools import load_mcp_tools, build_mcp_prompt, get_mcp_tool_names
from .agents.artifact_retrieval_agent import artifact_retrieval_agent
from .generate_artifact_context import generate_artifact_context
from .artifacts import resolve_artifact_dir
from .artifacts.artifact_discovery import generate_artifact_tree_display

log = logging.getLogger(__name__)


class DropAndSlideConversationManager(SlidingWindowConversationManager):
    """
    Drops tool results for specific tools after each turn,
    then applies SlidingWindow management.
    """

    def __init__(
        self,
        tools_to_drop: Iterable[str],
        **kwargs: Any,  # pass window_size, should_truncate_results, etc.
    ):
        super().__init__(**kwargs)
        self.tools_to_drop = set(tools_to_drop)

    def apply_management(self, agent, **kwargs):
        # 1) Remove results from the specified tools (keep a tiny breadcrumb)
        to_drop_ids = set()
        new_msgs = []

        for msg in agent.messages:
            role = msg.get("role")
            content = msg.get("content", [])

            if role == "assistant":
                tool_uses = [
                    cb for cb in content if isinstance(cb, dict) and "toolUse" in cb
                ]
                matching = [
                    cb
                    for cb in tool_uses
                    if cb["toolUse"]["name"] in self.tools_to_drop
                ]
                if matching:
                    for cb in matching:
                        to_drop_ids.add(cb["toolUse"]["toolUseId"])

                    # Keep non-matching content blocks
                    kept_content = [
                        cb
                        for cb in content
                        if not (
                            isinstance(cb, dict)
                            and "toolUse" in cb
                            and cb["toolUse"]["name"] in self.tools_to_drop
                        )
                    ]

                    # Add breadcrumb
                    kept_content.append(
                        {
                            "text": f"[{', '.join([cb['toolUse']['name'] for cb in matching])} used; output discarded]"
                        }
                    )

                    new_msgs.append(
                        {
                            "role": "assistant",
                            "content": kept_content,
                        }
                    )
                    continue

            if role == "user":
                kept = []
                for cb in content:
                    if isinstance(cb, dict) and "toolResult" in cb:
                        if cb["toolResult"].get("toolUseId") in to_drop_ids:
                            # drop this toolResult block
                            continue
                    kept.append(cb)
                if kept:
                    new_msgs.append({"role": "user", "content": kept})
                # if nothing left, drop the whole message
                continue

            new_msgs.append(msg)

        agent.messages = new_msgs

        # 2) Now apply SlidingWindow behavior (windowing, overflow trimming, truncation)
        super().apply_management(agent, **kwargs)


def create_agent(
    codebase_dir=None,
    include_monitoring=False,
    configure_logs=False,
    console_log_level=logging.INFO,
):
    """
    Create a configured Agent instance for IRIS.

    This centralized function is used by both CLI and WebSocket backends
    to ensure consistency and avoid code duplication.

    Args:
        codebase_dir: Directory containing the codebase to analyze
        include_monitoring: Whether to include monitoring hooks
        configure_logs: Whether to configure logging (default: False)
        console_log_level: Console logging level if configure_logs is True (default: INFO)

    Returns:
        Agent: Configured agent instance
    """

    config = load_default_config()
    os.environ["BYPASS_TOOL_CONSENT"] = str(config.get("bypass_tool_consent", False))
    model_configuration = config["model_configuration"]["orchestrator"]
    model_id = model_configuration["model_id"]
    region = model_configuration["region"]

    # Create a custom boto3 session
    if config.get("use_super_profile", False):
        session = create_session_with_assumed_role(model_configuration["ROLE_ARN"])
    else:
        session = boto3.Session(region_name=region)

    # Create a Bedrock model instance
    guardrail_kwargs = {}
    if config.get("guardrail_id"):
        guardrail_kwargs["guardrail_id"] = config["guardrail_id"]
        guardrail_kwargs["guardrail_version"] = (
            config.get("guardrail_version") or "DRAFT"
        )
        guardrail_kwargs["guardrail_stream_processing_mode"] = "sync"
        guardrail_kwargs["guardrail_trace"] = "enabled"
        log.info(f"Bedrock Guardrail enabled: {config['guardrail_id']}")

    bedrock_model = BedrockModel(
        model_id=model_id,
        max_tokens=32768,
        boto_session=session,
        **guardrail_kwargs,
    )

    codebase_dir = codebase_dir or config["codebase_dir"]
    output_folder = construct_output_dir(codebase_dir=codebase_dir)

    # Configure logging if requested, or if monitoring needs it
    monitoring_enabled = include_monitoring or config.get("include_monitoring", False)
    if configure_logs or monitoring_enabled:
        log_level = console_log_level if configure_logs else logging.INFO
        configure_logging(Path(output_folder), console_level=log_level)

    tools = [file_retrieval_agent, code_search_tool]
    system_message = load_prompts()["orchestrator_qa_only_system_message"]

    # Add artifact_retrieval_agent if artifact_dir is usable OR
    # pre-computed artifact data exists in the output directory (Docker/S3 deployments
    # may not have artifact_dir set but still have pre-indexed artifact data).
    artifact_dir = resolve_artifact_dir(config)
    has_precomputed_artifacts = Path(output_folder, "artifact_overview.json").exists()
    artifact_enabled = bool(artifact_dir) or has_precomputed_artifacts
    if artifact_enabled:
        tools.append(artifact_retrieval_agent)

    if config.get("web_search", False):
        tools.append(web_search)
        system_message += "\n\n" + load_prompts()["web_search"]

    # Add artifact context instructions when artifacts are available
    if artifact_enabled:
        system_message += (
            "\n\nYou also have access to project artifacts (documents, "
            "presentations, reports, meeting notes, readouts) via the "
            "artifact_retrieval_agent tool. When answering questions about "
            "project context, project history, or non-code materials, "
            "use this tool. Always attribute information to its source "
            "(codebase or artifact)."
        )

    # Load MCP server tools if configured
    mcp_tools = load_mcp_tools(config)
    mcp_tool_names = []
    if mcp_tools:
        tools.extend(mcp_tools)

        # Build dynamic MCP prompt based on enabled servers
        mcp_prompt = build_mcp_prompt(config)
        if mcp_prompt:
            system_message += "\n\n" + mcp_prompt

        # Collect MCP tool names for conversation manager
        mcp_tool_names = get_mcp_tool_names(mcp_tools)

        log.info(f"✓ Loaded {len(mcp_tools)} MCP tool providers from external servers")

    # Build tools to drop list (file_retrieval_agent + artifact_retrieval_agent + all MCP tools)
    tools_to_drop = ["file_retrieval_agent"] + mcp_tool_names
    if artifact_enabled:
        tools_to_drop.append("artifact_retrieval_agent")

    # Create hooks
    hooks = []
    if monitoring_enabled:
        monitor = AgentMonitor(
            log_level=logging.INFO,
            enable_detailed_logging=True,
            include_debug_tool_output=True,
            console_truncate_length=500,
        )
        hooks.append(monitor)

    if config.get("enable_prompt_caching", False):
        cache_point = {"type": "default"}
        cache_ttl = config.get("cache_ttl", "5m")
        if cache_ttl == "1h" and model_id in extended_ttl_models:
            cache_point["ttl"] = "1h"
        system_prompt = [{"text": system_message}, {"cachePoint": cache_point}]
        agent = Agent(
            system_prompt=system_prompt,
            tools=tools,
            model=bedrock_model,
            hooks=hooks,
            conversation_manager=DropAndSlideConversationManager(
                tools_to_drop=tuple(tools_to_drop)
            ),
        )
    else:
        agent = Agent(
            system_prompt=system_message,
            tools=tools,
            model=bedrock_model,
            hooks=hooks,
            conversation_manager=DropAndSlideConversationManager(
                tools_to_drop=tuple(tools_to_drop)
            ),
        )

    agent.state.set("codebase_dir", codebase_dir)

    log.debug("Agent created successfully")
    return agent


def cli_chat(codebase_dir, context=None):
    """
    Interactive CLI chat interface using the centralized agent creation.
    """
    # Setup for CLI interaction
    config = load_default_config()
    codebase_dir = codebase_dir or config["codebase_dir"]
    output_folder = construct_output_dir(codebase_dir=codebase_dir)

    # Configure logging with WARNING level for clean chat output
    configure_logging(Path(output_folder), console_level=logging.WARNING)

    # Create agent using the centralized function
    agent = create_agent(codebase_dir=codebase_dir)

    # Setup signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print("\n\nAborted!")
        # Cleanup agent and MCP clients
        try:
            if hasattr(agent, "tool_registry"):
                agent.tool_registry.cleanup()
        except Exception as e:
            log.debug(f"Cleanup error (can be ignored): {e}")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)
    additional_context = get_additional_context(filepath=context)

    # Prepare artifact context if configured (no-op if artifact_dir absent)
    artifact_dir = resolve_artifact_dir(config)
    if artifact_dir:
        try:
            # Display artifact folder structure (mirrors codebase tree display)
            artifact_tree = generate_artifact_tree_display(artifact_dir)
            print("\n📂 Artifact directory tree:")
            print(artifact_tree)
            print()

            artifact_result = generate_artifact_context(
                artifact_dir=artifact_dir,
                output_dir=str(output_folder),
                config=config,
                verbose=True,
            )
            log.info("Artifact context: %s", artifact_result.status)
        except Exception as e:
            log.warning(
                "Artifact context preparation failed: %s — proceeding without artifacts.",
                e,
            )

    print("\n🔍 What would you like to know about the codebase?")
    while True:
        prompt = input("\n> ")

        if prompt.strip().lower() in {"/quit"}:
            break

        if not prompt.strip():
            print("⚠️  Please enter a question.")
            continue

        generate_context(
            codebase_dir=codebase_dir,
            output_dir=str(output_folder),
            ignore_patterns=ignore_patterns,
            additional_context=additional_context,
        )

        agent(prompt)
