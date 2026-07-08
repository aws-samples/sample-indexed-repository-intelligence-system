# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import boto3
import json
import logging
from typing import Dict, List, Optional, Literal, Any
from strands import Agent
from strands.models.bedrock import BedrockModel
from pathlib import Path
from pydantic import BaseModel, Field

from ..file_system.file_utils import handle_notebook, MAX_NOTEBOOK_SIZE
from ..utils.bedrock import extended_ttl_models

log = logging.getLogger(__name__)


def read_multiple_files(
    paths: List[str],
    separator: str = "\n\n-----\n\n",
    header_template: str = "/* PATH: {path} */\n",
    missing: Literal["skip", "warning", "error"] = "warning",
    max_characters: Optional[int] = None,
    codebase_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Read multiple files and return a dictionary with file paths and content.
    Each file's content is prefixed by its file path.

    Args:
      paths: File paths to read.
      separator: Inserted between files' outputs.
      header_template: Format string; {path} is the file path.
      missing: 'skip' to ignore missing files; 'warning' to issue a warning; 'error' to raise.
      max_characters: If set, limit the combined output to this many characters by stopping the addition of new files.
      codebase_dir: If set, append the file path to this codebase dir to create the absolute file path.

    Returns:
      Dictionary with keys:
        - file_paths: List of file paths that were successfully read
        - file_content: Combined string content of all files
    """
    parts: List[str] = []
    read_paths: List[str] = []
    total_char = 0

    for p in paths:
        if codebase_dir:
            fp = Path(codebase_dir) / p
            # Prevent path traversal outside the codebase root
            try:
                fp.resolve().relative_to(Path(codebase_dir).resolve())
            except ValueError:
                log.warning(f"Path traversal blocked in read_multiple_files: {p}")
                continue
        else:
            fp = Path(p)
        if not fp.exists():
            if missing == "error":
                raise FileNotFoundError(str(fp))
            elif missing == "warning":
                log.warning(f"File {fp} doesn't exist.")
            continue

        # Read text (best-effort UTF-8)
        try:
            if fp.suffix == ".ipynb":
                body, size = handle_notebook(fp, MAX_NOTEBOOK_SIZE, True)
            else:
                body = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            body = fp.read_bytes().decode("utf-8", errors="ignore")

        piece = f"{header_template.format(path=str(fp))}{body}"

        if max_characters is not None:
            # Calculate the new total_char if we add this piece
            new_total_char = total_char + len(piece)
            # If adding this piece would exceed the limit, break out of the loop
            if new_total_char > max_characters:
                break
            # Otherwise, add the piece and update the total_char
            total_char = new_total_char

        parts.append(piece)
        read_paths.append(str(fp))

    log.info(f"Loaded contents from {len(read_paths)} files.")
    result = separator.join(parts)
    return {"file_paths": read_paths, "file_content": result}


def load_codebase_overview_context(
    path: str | Path, character_threshold: int
) -> Dict[str, dict]:
    """
    Load existing codebase overview from disk.

    Args:
      path: File path to read.
      character_threshold: If there are no more than this number of files, return the entire codebase overview with all keys. Otherwise, return only the 'purpose' and 'imported_files' keys.
    """

    if not Path(path).exists():
        return {}

    with open(path, "r") as f:
        overview = json.load(f)

    overview_nchar = len(json.dumps(overview, separators=(",", ":")))
    high_level_overview = True if overview_nchar > character_threshold else False

    if high_level_overview:
        high_level_overview = {
            file_path: {
                "purpose": overview[file_path]["purpose"],
                "imported_files": overview[file_path]["imported_files"],
            }
            for file_path in overview
        }
        return high_level_overview
    else:
        return overview


def create_bedrock_agent(
    system_message: str,
    model_config: Dict,
    structured_output_model: Optional[type] = None,
    tools: List[str] = None,
    enable_prompt_caching: bool = False,
    cache_ttl: str = "5m",
    guardrail_config: Optional[Dict] = None,
) -> Agent:
    """
    Create an Amazon Bedrock agent with the given configuration.

    Args:
        system_message: System prompt for the agent
        model_config: Model configuration dict with model_id and region
        structured_output_model: Optional Pydantic model for structured output
        enable_prompt_caching: Whether to enable prompt caching
        cache_ttl: Cache TTL ("5m" or "1h"), only applies if enable_prompt_caching=True
        guardrail_config: Optional dict with guardrail_id and guardrail_version

    Returns:
        Configured Agent instance
    """
    model_id = model_config["model_id"]
    region = model_config.get("region", "us-east-1")

    session = boto3.Session(region_name=region)

    guardrail_kwargs = {}
    if guardrail_config and guardrail_config.get("guardrail_id"):
        guardrail_kwargs["guardrail_id"] = guardrail_config["guardrail_id"]
        guardrail_kwargs["guardrail_version"] = guardrail_config.get(
            "guardrail_version", "DRAFT"
        )
        guardrail_kwargs["guardrail_stream_processing_mode"] = "sync"

    bedrock_model = BedrockModel(
        model_id=model_id,
        boto_session=session,
        **guardrail_kwargs,
    )

    if enable_prompt_caching:
        cache_point = {"type": "default"}
        if cache_ttl == "1h" and model_id in extended_ttl_models:
            cache_point["ttl"] = "1h"
        system_prompt = [{"text": system_message}, {"cachePoint": cache_point}]
        return Agent(
            system_prompt=system_prompt,
            model=bedrock_model,
            structured_output_model=structured_output_model,
            tools=tools,
        )
    else:
        return Agent(
            system_prompt=system_message,
            model=bedrock_model,
            structured_output_model=structured_output_model,
            tools=tools,
        )


def build_user_message(
    query: str,
    codebase_overview: Dict,
    additional_context: str,
    mode: Literal["identify", "respond"],
    file_info: Optional[str] = None,
    enable_cache_point: bool = False,
) -> str:
    """
    Build user message with codebase context.

    Args:
        query: User query
        codebase_overview: Codebase overview dict
        additional_context: Additional context string
        mode: "identify" for file identification, "respond" for response generation
        file_info: File related information to add to the message
        enable_cache_point: If True, structure message to optimize for caching (static parts first)

    Returns:
        Formatted user message string
    """
    # Build message with static parts first for better caching
    message_parts = [
        f"<codebase_overview>\n{json.dumps(codebase_overview, separators=(',', ':'))}\n</codebase_overview>"
    ]

    if additional_context:
        message_parts.append(
            f"<additional_context>\n{additional_context}\n</additional_context>"
        )

    if mode == "identify":
        # For file identifier: include file path list
        message_parts.append(
            f"<file_path_list>\nThe list of all available file paths are:\n{list(codebase_overview.keys())}\n</file_path_list>"
        )
    elif mode == "respond":
        # For response generator: include file content
        if file_info:
            message_parts.append(f"<file_content>\n{file_info}\n</file_content>")
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'identify' or 'respond'.")

    # Dynamic part (query) comes last
    message_parts.append(f"<user_input>\n{query}\n</user_input>")

    return "\n\n".join(message_parts)


class RelevantFiles(BaseModel):
    """Structured response for file identification"""

    file_paths: List[str] = Field(
        description="List of relevant file paths ranked by importance, with the most important files listed first"
    )


def identify_relevant_files(
    query, config, codebase_overview_path, additional_context, system_message
):
    # Pydantic model for structured output
    file_identifier_overview = load_codebase_overview_context(
        codebase_overview_path, config["context_window_size"] * 2
    )

    file_identifier_agent = create_bedrock_agent(
        system_message=system_message,
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

    file_identifier_message = build_user_message(
        query=query,
        codebase_overview=file_identifier_overview,
        additional_context=additional_context,
        mode="identify",
        enable_cache_point=config.get("enable_prompt_caching", False),
    )

    try:
        result = file_identifier_agent(file_identifier_message)
        identified_files = result.structured_output.file_paths
        log.debug(f"Identified files: {identified_files}")
    except Exception as e:
        log.error(f"Failed to identify files: {e}", exc_info=True)
        identified_files = []

    return identified_files
