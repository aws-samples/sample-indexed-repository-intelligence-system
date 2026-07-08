# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import logging
import subprocess
from typing import List, Any, Dict, Optional
import logging as stdlib_logging
from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient
from ..summarize.utils import load_prompts
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)


def _create_mcp_transport(command: str, args: list, env: dict):
    """
    Create MCP transport factory with log suppression.

    Args:
        command: Command to execute
        args: Command arguments
        env: Environment variables

    Returns:
        Callable that returns stdio_client context manager
    """

    def transport():
        return stdio_client(
            StdioServerParameters(command=command, args=args, env=env),
            errlog=subprocess.DEVNULL,
        )

    return transport


def get_mcp_tool_names(mcp_tools: List[Any]) -> List[str]:
    """
    Extract tool names from MCP tool providers.

    Args:
        mcp_tools: List of MCP tool provider instances

    Returns:
        List of tool names from all MCP providers
    """
    tool_names = []
    for mcp_provider in mcp_tools:
        # MCPClient has a tools property that contains the tool definitions
        if hasattr(mcp_provider, "tools"):
            for tool in mcp_provider.tools:
                if hasattr(tool, "name"):
                    tool_names.append(tool.name)
                elif isinstance(tool, dict) and "name" in tool:
                    tool_names.append(tool["name"])
    return tool_names


def build_mcp_prompt(config: dict) -> str:
    """
    Build dynamic MCP tools prompt based on enabled servers.

    Args:
        config: Application configuration dictionary

    Returns:
        Formatted prompt text describing available MCP tools
    """
    mcp_servers_config = config.get("mcp_servers", {})
    if not mcp_servers_config:
        return ""

    # Get enabled servers
    enabled_servers = [
        name for name, cfg in mcp_servers_config.items() if cfg.get("enabled", False)
    ]

    if not enabled_servers:
        return ""

    # Load all prompts
    prompts = load_prompts()

    # Build prompt with only enabled servers
    prompt_parts = ["<mcp_tools_capability>"]
    prompt_parts.append(
        "You have access to external MCP (Model Context Protocol) servers that provide additional tools:\n"
    )

    # Add each enabled server's description
    for server_name in enabled_servers:
        prompt_key = f"mcp_{server_name}"
        if prompt_key in prompts:
            prompt_parts.append(prompts[prompt_key])

    # Add common usage instructions
    prompt_parts.append(
        "\nThese tools provide full documentation pages, not just snippets. Use them to:"
    )
    prompt_parts.append("- Answer questions about AWS services and APIs")
    prompt_parts.append("- Provide deployment guidance for agents")
    prompt_parts.append("- Explain AWS best practices and patterns")
    prompt_parts.append(
        "\nWhen querying for AWS-related documentation, select the most relevant MCP server first. Only use other MCP servers when needed."
    )

    prompt_parts.append("\nIMPORTANT SECURITY NOTICE:")
    prompt_parts.append(
        "- NEVER send codebase content, file paths, or project-specific code to MCP servers"
    )
    prompt_parts.append(
        "- NEVER include proprietary information, business logic, or sensitive data in MCP queries"
    )
    prompt_parts.append(
        "- ONLY ask generic questions about documentation, APIs, and best practices"
    )
    prompt_parts.append(
        "- Keep queries focused on general concepts, not specific implementation details from the codebase"
    )
    prompt_parts.append(
        "\nThe tools are automatically available when MCP servers are enabled in the configuration."
    )
    prompt_parts.append("</mcp_tools_capability>")

    return "\n".join(prompt_parts)


def _parse_tool_filters(tool_filters: Optional[Dict]) -> Dict[str, List[str]]:
    """
    Parse tool filters from configuration.

    Args:
        tool_filters: Dictionary with 'allowed' and/or 'rejected' keys

    Returns:
        Dictionary with parsed filters
    """
    if not tool_filters:
        return {}

    parsed = {}

    # Parse allowed filters (can be strings or regex patterns)
    if "allowed" in tool_filters:
        allowed = tool_filters["allowed"]
        if isinstance(allowed, list):
            parsed["allowed"] = allowed
        else:
            parsed["allowed"] = [allowed]

    # Parse rejected filters
    if "rejected" in tool_filters:
        rejected = tool_filters["rejected"]
        if isinstance(rejected, list):
            parsed["rejected"] = rejected
        else:
            parsed["rejected"] = [rejected]

    return parsed


def load_mcp_tools(config: dict) -> List[Any]:
    """
    Load tools from external configured MCP servers with optional filtering.

    Args:
        config: Application configuration dictionary

    Returns:
        List of MCP client tool providers

    Configuration supports:
        - tool_filters: Filter which tools to expose
          - allowed: List of tool names to include (whitelist)
          - rejected: List of tool names to exclude (blacklist)
        - prefix: String prefix to add to all tool names from this server
    """
    mcp_servers_config = config.get("mcp_servers", {})
    if not mcp_servers_config:
        return []

    # Check if any MCP server is enabled
    enabled_servers = {
        name: cfg
        for name, cfg in mcp_servers_config.items()
        if cfg.get("enabled", False)
    }

    if not enabled_servers:
        return []

    # Suppress strands MCP client logging (client-side only)
    stdlib_logging.getLogger("strands.tools.mcp").setLevel(stdlib_logging.ERROR)

    mcp_clients = []
    new_clients_to_init = []  # Track clients that need initialization

    for server_name, server_config in enabled_servers.items():
        try:
            command = server_config.get("command")
            args = server_config.get("args", [])
            env = server_config.get("env", {})
            tool_filters = server_config.get("tool_filters")
            prefix = server_config.get("prefix")

            if not command:
                log.warning(
                    f"Skipping MCP server '{server_name}': no command specified"
                )
                continue

            # Parse tool filters
            parsed_filters = _parse_tool_filters(tool_filters)

            mcp_client_kwargs = {}
            if parsed_filters:
                mcp_client_kwargs["tool_filters"] = parsed_filters
            if prefix:
                mcp_client_kwargs["prefix"] = prefix

            # Create transport factory with stderr suppression
            transport_factory = _create_mcp_transport(command, args, env)

            # Create MCP client with transport factory as first positional argument
            mcp_client = MCPClient(transport_factory, **mcp_client_kwargs)

            mcp_clients.append(mcp_client)

            # Track for parallel initialization
            new_clients_to_init.append((server_name, mcp_client))

            # Log configuration details
            filter_info = ""
            if parsed_filters:
                if "allowed" in parsed_filters:
                    filter_info += f" (allowed: {', '.join(parsed_filters['allowed'])})"
                if "rejected" in parsed_filters:
                    filter_info += (
                        f" (rejected: {', '.join(parsed_filters['rejected'])})"
                    )
            if prefix:
                filter_info += f" (prefix: {prefix})"

            log.info(f"✓ Configured MCP server: {server_name}{filter_info}")

        except Exception as e:
            log.warning(f"Failed to configure MCP server '{server_name}': {e}")
            continue

    # Parallel initialization of new clients for faster startup
    if new_clients_to_init:
        log.info(
            f"Starting parallel initialization of {len(new_clients_to_init)} MCP clients..."
        )

        def init_client(name_client_tuple):
            name, client = name_client_tuple
            try:
                if not client._tool_provider_started:
                    client.start()
                    client._tool_provider_started = True
                    # Pre-fetch tools to cache them
                    client.list_tools_sync()
                    log.info(f"✓ Pre-initialized connection: {name}")
            except Exception as e:
                log.warning(f"Failed to pre-initialize '{name}': {e}")

        try:
            with ThreadPoolExecutor(
                max_workers=min(len(new_clients_to_init), 10)
            ) as executor:
                list(executor.map(init_client, new_clients_to_init))
            log.info("✓ Parallel MCP initialization completed")
        except Exception as e:
            log.warning(f"Error during parallel MCP initialization: {e}")

    return mcp_clients
