# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
MCP Server for IRIS - provides codebase context generation and agentic queries.
"""

import argparse
import json
import logging
import sys
from contextlib import asynccontextmanager, contextmanager
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


@contextmanager
def _suppress_stdout():
    """Temporarily redirect stdout to stderr to prevent print() from corrupting MCP protocol."""
    old = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = old


from iris.file_system.file_utils import (  # noqa: E402
    load_codebase_overview,
)
from iris.artifacts import resolve_artifact_dir  # noqa: E402
from iris.generate_artifact_context import (  # noqa: E402
    generate_artifact_context,
)
from iris.generate_context import generate_context  # noqa: E402
from iris.agentic_chat import create_agent  # noqa: E402
from iris.utils.utils import (  # noqa: E402
    construct_output_dir,
    get_ignore_patterns,
    load_default_config,
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
        valid_tools = {
            "all",
            "codebase_artifact_context",
            "codebase_artifact_query",
        }
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
async def codebase_artifact_context(
    codebase_dir: str = Field(description="Directory to the codebase to index"),
    artifact_dir: str = Field(
        default="",
        description="Directory containing project artifacts organized by phase (optional — falls back to artifact_dir in config, empty to skip artifact indexing)",
    ),
):
    """
    Unified indexing tool: generates/updates both codebase and artifact indexes.

    1. Runs codebase indexing via generate_context() (always)
    2. Loads and returns the codebase overview
    3. If artifact_dir is provided (or configured), runs artifact indexing via
       generate_artifact_context()

    Args:
        codebase_dir: The codebase directory (absolute path)
        artifact_dir: The project artifacts directory (absolute path, optional — falls back to config)

    Returns:
        Status summary with codebase overview and artifact indexing results
    """
    import asyncio

    with _suppress_stdout():
        try:
            validated_path = validate_codebase_path(codebase_dir)
            codebase_dir = str(validated_path)

            ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)
            output_dir = construct_output_dir(codebase_dir=codebase_dir)

            logger.info(f"Generating codebase context for: {codebase_dir}")
            codebase_result = await asyncio.to_thread(
                generate_context,
                codebase_dir=codebase_dir,
                output_dir=output_dir,
                ignore_patterns=ignore_patterns,
                additional_context="",
                verbose=True,
            )

            if codebase_result.status == "error":
                return f"❌ Codebase indexing failed: {codebase_result.message}"

            codebase_overview = load_codebase_overview(output_dir)
            num_files = len(codebase_overview) if codebase_overview else 0

            summary_parts = [
                f"✅ Codebase indexed: {num_files} files from {codebase_dir}",
            ]

            # Resolve artifact_dir: parameter > config > skip
            effective_artifact_dir = artifact_dir
            if not effective_artifact_dir:
                try:
                    effective_artifact_dir = (
                        resolve_artifact_dir(load_default_config()) or ""
                    )
                except Exception:
                    effective_artifact_dir = ""

            # Optionally index artifacts
            if effective_artifact_dir:
                try:
                    validated_artifact = Path(effective_artifact_dir).resolve()
                    if not validated_artifact.exists():
                        summary_parts.append(
                            f"⚠️ Artifact directory not found: {effective_artifact_dir}, skipping"
                        )
                    else:
                        config = {}
                        try:
                            config = load_default_config()
                        except Exception:
                            pass

                        artifact_result = await asyncio.to_thread(
                            generate_artifact_context,
                            artifact_dir=str(validated_artifact),
                            output_dir=output_dir,
                            config=config,
                            verbose=True,
                        )

                        if artifact_result.status == "error":
                            summary_parts.append(
                                f"⚠️ Artifact indexing error: {artifact_result.message}"
                            )
                        elif artifact_result.status == "no_op":
                            summary_parts.append(
                                f"✅ Artifacts up to date ({artifact_result.total_artifacts or 0} total)"
                            )
                        else:
                            count = len(artifact_result.processed_artifacts or [])
                            summary_parts.append(
                                f"✅ Artifacts indexed: {count} processed, "
                                f"{artifact_result.total_artifacts or 0} total"
                            )
                except Exception as e:
                    summary_parts.append(f"⚠️ Artifact indexing skipped: {e}")
            else:
                summary_parts.append(
                    "ℹ️ No artifact_dir provided or configured, skipping artifact indexing"
                )

            if codebase_overview:
                summary_parts.append(f"\n{json.dumps(codebase_overview, indent=2)}")

            return "\n".join(summary_parts)

        except ValueError as e:
            logger.error(f"Path validation error: {e}")
            return f"❌ Invalid path: {str(e)}"
        except Exception as e:
            logger.error(f"Error in codebase_artifact_context: {str(e)}", exc_info=True)
            return "❌ An internal error occurred in codebase_artifact_context. Check server logs for details."


async def codebase_artifact_query(
    query: str = Field(
        description="The question to evaluate against the codebase and/or project artifacts"
    ),
    codebase_dir: str = Field(description="Directory to codebase"),
    artifact_dir: str = Field(
        default="",
        description="Directory containing project artifacts organized by phase (optional — falls back to artifact_dir in config, empty to skip artifact context)",
    ),
):
    """
    Unified query tool: uses the orchestrator agent with retrieval tools
    to answer questions about the codebase and/or project artifacts.

    The orchestrator agent decides which retrieval tools to invoke:
    - file_retrieval_agent for codebase questions
    - artifact_retrieval_agent for artifact questions (when available)
    - both when the query spans codebase and artifacts

    Args:
        query: The question about the codebase and/or project artifacts
        codebase_dir: The codebase directory (absolute path)
        artifact_dir: The project artifacts directory (absolute path, optional — falls back to config)

    Returns:
        AI-generated response with source attribution
    """
    import asyncio

    agent = None
    with _suppress_stdout():
        try:
            validated_path = validate_codebase_path(codebase_dir)
            codebase_dir = str(validated_path)

            logger.info(f"Processing query: {query[:100]}...")
            logger.info(f"Codebase: {codebase_dir}")

            # create_agent() automatically includes artifact_retrieval_agent
            # when artifact_dir is configured or artifact_overview.json exists
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
            logger.error(f"Error in codebase_artifact_query: {str(e)}", exc_info=True)
            return "❌ An internal error occurred in codebase_artifact_query. Check server logs for details."
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

    if is_tool_enabled("codebase_artifact_context", enabled_tools):
        mcp.tool()(codebase_artifact_context)

    if is_tool_enabled("codebase_artifact_query", enabled_tools):
        mcp.tool()(codebase_artifact_query)

    try:
        mcp.run()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
