# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
MCP Server for IRIS - provides codebase context generation and agentic queries.
"""

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import Field

# Configure logging to stderr (MCP uses stdout for protocol)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Add project root to Python path for imports from iris
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from iris.file_system.file_utils import (  # noqa: E402
    load_codebase_overview,
)
from iris.generate_context import generate_context  # noqa: E402
from iris.agentic_chat import create_agent  # noqa: E402
from iris.utils.utils import (  # noqa: E402
    construct_output_dir,
    get_ignore_patterns,
    set_config_path,
)


@asynccontextmanager
async def lifespan(server: FastMCP):
    logger.info("MCP server starting")
    try:
        yield
    finally:
        logger.info("MCP server shutting down")


mcp = FastMCP("iris", lifespan=lifespan)


def get_enabled_tools():
    """Get list of enabled tools from config."""
    try:
        from iris.utils.utils import load_default_config

        config = load_default_config()
        enabled_tools = config.get("mcp_enabled_tools", ["all"])

        # Validate tool names
        valid_tools = {"all", "codebase_context", "codebase_query"}
        if not isinstance(enabled_tools, list):
            logger.warning(
                f"Invalid mcp_enabled_tools type: {type(enabled_tools)}, using default"
            )
            return ["all"]

        invalid = set(enabled_tools) - valid_tools
        if invalid:
            logger.warning(f"Invalid tools in config: {invalid}, ignoring them")
            enabled_tools = [t for t in enabled_tools if t in valid_tools]

        if not enabled_tools:
            logger.warning("No valid tools enabled, defaulting to 'all'")
            return ["all"]

        return enabled_tools
    except Exception as e:
        logger.warning(f"Failed to load config, enabling all tools: {e}")
        return ["all"]


def is_tool_enabled(tool_name: str, enabled_tools: list) -> bool:
    """Check if a tool is enabled."""
    return "all" in enabled_tools or tool_name in enabled_tools


def validate_codebase_path(path: str) -> Path:
    """Validate and normalize codebase path."""
    try:
        resolved = Path(path).resolve()
    except (ValueError, OSError) as e:
        raise ValueError(f"Invalid path: {path}") from e

    if not resolved.exists():
        raise ValueError(f"Path does not exist: {path}")
    if not resolved.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    return resolved


def validate_file_within_codebase(file_path: str, codebase_root: Path) -> Path:
    """Validate that a file path resolves within the codebase root directory.

    Prevents path traversal attacks (e.g., ../../etc/passwd) by resolving
    symlinks and verifying containment.

    Args:
        file_path: The file path to validate
        codebase_root: The resolved codebase root directory

    Returns:
        The resolved file path

    Raises:
        ValueError: If the path escapes the codebase root
    """
    resolved = Path(file_path).resolve()
    try:
        resolved.relative_to(codebase_root)
    except ValueError:
        raise ValueError(
            f"Path traversal blocked: {file_path} is outside codebase root {codebase_root}"
        )
    return resolved


# Define tool functions but don't register yet
async def codebase_context(
    codebase_dir: str = Field(
        description="Directory to codebase for which iris should be run"
    ),
):
    """
    Generate/update codebase context and provide it to the client.

    This tool:
    1. Generates/updates codebase context using the orchestrator (no-op if unchanged)
    2. Loads the codebase overview into memory
    3. Returns a concise summary (use codebase_query to ask questions)

    Args:
        codebase_dir: The codebase directory (absolute path)

    Returns:
        A concise summary of the generated context
    """
    import asyncio

    try:
        # Validate path
        validated_path = validate_codebase_path(codebase_dir)
        codebase_dir = str(validated_path)

        # Get ignore patterns from config
        ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)

        output_dir = construct_output_dir(codebase_dir=codebase_dir)

        logger.info(f"Generating context for codebase: {codebase_dir}")

        # Run blocking generate_context in a thread to keep event loop responsive
        result = await asyncio.to_thread(
            generate_context,
            codebase_dir=codebase_dir,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
            additional_context="",
            verbose=True,
        )

        if result.status == "error":
            logger.error(f"Context generation failed: {result.message}")
            return f"❌ Error generating codebase context: {result.message}"

        # Load the codebase context into memory
        codebase_ctx = load_codebase_overview(output_dir)

        if not codebase_ctx:
            logger.warning("No codebase context available")
            return "❌ No codebase context available. The codebase may be empty or all files were ignored."

        # Return concise summary to avoid exceeding MCP output limits
        num_files = len(codebase_ctx)
        file_list = list(codebase_ctx.keys())[:20]
        more_files = max(0, num_files - 20)

        logger.info(f"Context generated successfully: {num_files} files")

        context_summary = (
            f"✅ Codebase context generated successfully!\n\n"
            f"**Codebase**: {codebase_dir}\n"
            f"**Files analyzed**: {num_files}\n"
            f"**Files**: {', '.join(file_list)}"
            f"{f' (and {more_files} more)' if more_files > 0 else ''}\n\n"
            f"Context is indexed and ready. Use codebase_query to ask questions about this codebase."
        )

        return context_summary

    except ValueError as e:
        logger.error(f"Path validation error: {e}")
        return f"❌ Invalid path: {str(e)}"
    except Exception as e:
        logger.error(f"Error in codebase_context: {str(e)}", exc_info=True)
        return "❌ An internal error occurred in codebase_context. Check server logs for details."


async def codebase_query(
    query: str = Field(
        description="The question or task to evaluate against the codebase"
    ),
    codebase_dir: str = Field(
        description="Directory to codebase for which iris should be run"
    ),
):
    """
    End-to-end codebase query: runs the IRIS agent and returns its AI response.

    WARNING: This operation can take 30-60+ seconds for large codebases.
    Consider using codebase_context first to pre-generate context.

    This tool:
    1. Requires codebase context to exist (run codebase_context first)
    2. Processes the user query with the IRIS agent (file retrieval, code
       search, and any configured tools)
    3. Returns the AI-generated response

    Args:
        query: The question or task to evaluate against the codebase
        codebase_dir: The codebase directory (absolute path)

    Returns:
        AI-generated response to the query based on codebase analysis
    """
    import asyncio

    agent = None
    try:
        # Validate path
        validated_path = validate_codebase_path(codebase_dir)
        codebase_dir = str(validated_path)

        logger.info(f"Processing query: {query[:100]}...")
        logger.info(f"Codebase: {codebase_dir}")

        # Build the IRIS agent (blocking: boto3 session, prompt/tool loading).
        # Run in a thread to keep the event loop responsive. A fresh agent is
        # created per call since MCP tool invocations are independent.
        logger.info("Creating agent...")
        agent = await asyncio.to_thread(create_agent, codebase_dir=codebase_dir)

        # Stream the response and collect the text chunks.
        logger.info("Generating response...")
        response_parts = []
        async for event in agent.stream_async(query):
            if "data" in event:
                response_parts.append(event["data"])

        logger.info("Response generated successfully")
        return "".join(response_parts)

    except ValueError as e:
        logger.error(f"Path validation error: {e}")
        return f"❌ Invalid path: {str(e)}"
    except Exception as e:
        logger.error(f"Error in codebase_query: {str(e)}", exc_info=True)
        return "❌ An internal error occurred in codebase_query. Check server logs for details."
    finally:
        # Release any MCP tool clients held by the agent's tool registry.
        if agent is not None and hasattr(agent, "tool_registry"):
            try:
                agent.tool_registry.cleanup()
            except Exception as cleanup_err:
                logger.debug(f"Agent cleanup error (ignored): {cleanup_err}")


def main():
    """Entry point for MCP server with config support."""
    parser = argparse.ArgumentParser(description="IRIS MCP Server")
    parser.add_argument("--config", type=str, help="Path to config.yaml file")
    args = parser.parse_args()

    # Set config path globally if provided
    if args.config:
        set_config_path(args.config)
        logger.info(f"Using config: {args.config}")

    # Register tools based on config
    enabled_tools = get_enabled_tools()
    logger.info(f"Enabled tools: {enabled_tools}")

    if is_tool_enabled("codebase_context", enabled_tools):
        mcp.tool()(codebase_context)

    if is_tool_enabled("codebase_query", enabled_tools):
        mcp.tool()(codebase_query)

    try:
        mcp.run()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
