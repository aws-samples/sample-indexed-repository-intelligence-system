# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Strands tool for retrieving project artifact content.

Analogous to :func:`file_retrieval_agent` but loads per-artifact
extracted files and artifact overview instead of source code files.

Identifies only the relevant artifacts for a given query (using the same
structured-output Bedrock identifier used for codebase files) to avoid
context window overflow from loading all artifacts at once.
"""

import json
import logging
from pathlib import Path

from strands import tool, ToolContext

from .utils import create_bedrock_agent, build_user_message, RelevantFiles
from ..artifacts.knowledge_base import load_extracted_artifact
from ..utils.utils import load_default_config, construct_output_dir
from ..summarize.utils import load_prompts

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = load_default_config()
_DEFAULT_PROMPTS = load_prompts()

# Maximum characters of artifact content to return (conservative limit
# to leave room for codebase context and conversation history).
_MAX_ARTIFACT_CONTEXT_CHARS = _DEFAULT_CONFIG.get("context_window_size", 200_000) * 2


def _load_artifact_overview(output_dir: Path) -> dict:
    """Load ``artifact_overview.json`` from *output_dir*, returning {} on failure."""
    path = output_dir / "artifact_overview.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load artifact overview: %s", exc)
        return {}


def _identify_relevant_artifacts(query: str, overview: dict, config: dict) -> list[str]:
    """Identify artifact paths relevant to *query* using a structured-output agent.

    Mirrors :func:`iris.agents.utils.identify_relevant_files` but operates on the
    artifact overview dict directly (artifact summaries do not carry the
    ``imported_files`` key that the codebase overview reducer assumes).

    Returns a list of artifact paths ranked by relevance; empty on failure.
    """
    artifact_identifier_agent = create_bedrock_agent(
        system_message=_DEFAULT_PROMPTS["file_identifier_system_message"],
        model_config=config["model_configuration"]["file_identifier"],
        structured_output_model=RelevantFiles,
        enable_prompt_caching=config.get("enable_prompt_caching", False),
        guardrail_config=(
            {
                "guardrail_id": config.get("guardrail_id"),
                "guardrail_version": config.get("guardrail_version"),
            }
            if config.get("guardrail_id")
            else None
        ),
    )

    message = build_user_message(
        query=query,
        codebase_overview=overview,
        additional_context="",
        mode="identify",
        enable_cache_point=config.get("enable_prompt_caching", False),
    )

    try:
        result = artifact_identifier_agent(message)
        identified = result.structured_output.file_paths
        logger.debug("Identified artifacts: %s", identified)
    except Exception as exc:
        logger.error("Failed to identify artifacts: %s", exc, exc_info=True)
        identified = []

    return identified


@tool(context=True)
def artifact_retrieval_agent(query: str, tool_context: ToolContext) -> str:
    """Retrieve project artifact content relevant to the query.

    This tool identifies the most relevant artifacts for the query, then
    loads only those per-artifact extracted files. This avoids context
    window overflow from loading all artifacts at once.

    Process:
    1. Load ``artifact_overview.json`` to get the full artifact index.
    2. Identify only the artifacts relevant to the query.
    3. Load per-artifact ``.md`` files for the selected artifacts.
    4. Fall back to the ``ArtifactOverview`` summary if the per-artifact
       file is not found.

    Args:
        query: Natural language question about project artifacts.

    Returns:
        Formatted context string with relevant artifact content and metadata.
    """
    config = _DEFAULT_CONFIG
    output_dir = Path(construct_output_dir())
    logger.info("artifact_retrieval_agent: looking for artifacts in %s", output_dir)
    overview = _load_artifact_overview(output_dir)

    if not overview:
        if output_dir.exists():
            files = list(output_dir.iterdir())
            logger.info(
                "Output dir exists with %d items: %s",
                len(files),
                [f.name for f in files[:20]],
            )
        else:
            logger.info("Output dir does NOT exist: %s", output_dir)
        return (
            "No artifact index found. Please run artifact indexing first "
            "(e.g., `iris prepare --artifact` CLI command or "
            "`codebase_artifact_context` MCP tool)."
        )

    # Identify relevant artifacts
    identified = _identify_relevant_artifacts(query, overview, config)

    # Only include paths that are actually in the artifact overview
    relevant_paths: list[str] = [path for path in identified if path in overview]

    if not relevant_paths:
        # Fallback: return just the overview summaries (compact)
        logger.info("No relevant artifacts identified, returning overview summaries")
        sections = [
            "## Project Artifacts Overview\n",
            f"Query: {query}\n",
            f"Total indexed artifacts: {len(overview)}\n",
        ]
        for artifact_path, summary in overview.items():
            purpose = summary.get("purpose", "")
            topics = ", ".join(summary.get("key_topics", []))
            sections.append(f"- **{artifact_path}**: {purpose}")
            if topics:
                sections[-1] += f" (topics: {topics})"
        return "\n".join(sections)

    logger.info(
        "Identified %d relevant artifacts: %s",
        len(relevant_paths),
        relevant_paths[:5],
    )

    # Load only the relevant artifacts, respecting context size limit
    sections: list[str] = []
    sections.append("## Project Artifacts Context\n")
    sections.append(f"Query: {query}\n")
    sections.append(
        f"Relevant artifacts: {len(relevant_paths)} of {len(overview)} total\n"
    )

    total_chars = 0
    loaded_count = 0

    for artifact_path in relevant_paths:
        summary = overview.get(artifact_path, {})

        # Try loading the full extracted content
        content = load_extracted_artifact(artifact_path, output_dir)

        if content:
            # Check if adding this would exceed the limit
            if total_chars + len(content) > _MAX_ARTIFACT_CONTEXT_CHARS:
                # Use summary instead of full content
                logger.info(
                    "Truncating to summary for %s (would exceed context limit)",
                    artifact_path,
                )
                content = _format_summary(artifact_path, summary)
            total_chars += len(content)
            sections.append(f"### Artifact: {artifact_path}")
            sections.append(content)
            loaded_count += 1
        else:
            # Fallback to overview summary
            fallback = _format_summary(artifact_path, summary)
            total_chars += len(fallback)
            sections.append(fallback)
            loaded_count += 1

        sections.append("---")

    logger.info(
        "Loaded %d artifacts, total context: %d chars", loaded_count, total_chars
    )
    return "\n\n".join(sections)


def _format_summary(artifact_path: str, summary: dict) -> str:
    """Format an artifact overview entry as a compact summary string."""
    phase = summary.get("project_phase", "unknown")
    mat_type = summary.get("source_material_type", "unknown")
    fmt = summary.get("file_format", "unknown")
    purpose = summary.get("purpose", "")
    topics = ", ".join(summary.get("key_topics", []))
    summ = summary.get("summary", "")

    lines = [
        f"### Artifact: {artifact_path}",
        f"Phase: {phase} | Type: {mat_type} | Format: {fmt}",
    ]
    if purpose:
        lines.append(f"Purpose: {purpose}")
    if topics:
        lines.append(f"Key topics: {topics}")
    if summ:
        lines.append(f"Summary: {summ}")
    return "\n".join(lines)
