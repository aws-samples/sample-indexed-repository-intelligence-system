# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import logging
import json
from pathlib import Path

log = logging.getLogger(__name__)


def load_prompts():
    """Load prompt templates from prompts directory"""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    return {
        "codebase_overview_description": (
            prompts_dir / "codebase_overview_description.txt"
        ).read_text(encoding="utf-8"),
        "codebase_overview_schema": (
            prompts_dir / "codebase_overview_schema.txt"
        ).read_text(encoding="utf-8"),
        "system_message": (prompts_dir / "system_message.txt").read_text(
            encoding="utf-8"
        ),
        "orchestrator_qa_only_system_message": (
            prompts_dir / "orchestrator_qa_only_system_message.txt"
        ).read_text(encoding="utf-8"),
        "file_identifier_system_message": (
            prompts_dir / "file_identifier_system_message.txt"
        ).read_text(encoding="utf-8"),
        "web_search": (prompts_dir / "web_search_prompt.txt").read_text(
            encoding="utf-8"
        ),
        "mcp_aws_documentation": (prompts_dir / "mcp_aws_documentation.txt").read_text(
            encoding="utf-8"
        ),
        "mcp_agentcore_docs": (prompts_dir / "mcp_agentcore_docs.txt").read_text(
            encoding="utf-8"
        ),
        "mcp_strands_agents_docs": (
            prompts_dir / "mcp_strands_agents_docs.txt"
        ).read_text(encoding="utf-8"),
    }


def load_paths(txt_file: str) -> list[str]:
    """
    Read a text file where each line is a file‑system path
    and return a list of paths.
    """
    with open(txt_file, "r") as f:
        paths = [line.strip() for line in f if line.strip()]  # skip blank lines
    return paths


def update_and_save_codebase_overview(
    output_folder, new_overviews=None, file_hashes=None
):
    """
    Update and save codebase overview with new summaries and their corresponding hashes.

    This ensures cache consistency - hashes should only be saved when summaries are successfully created.

    Args:
        output_folder: Path to output directory
        new_overviews: Dict of file_path -> summary to add/update
        file_hashes: Dict of file_path -> hash for the summarized files

    Returns:
        Updated codebase overview dict
    """
    if not isinstance(output_folder, Path):
        output_folder = Path(output_folder)

    if new_overviews is None:
        new_overviews = {}

    if file_hashes is None:
        file_hashes = {}

    # Load existing overview
    codebase_overview_path = output_folder / "codebase_overview.json"
    if codebase_overview_path.exists():
        with open(codebase_overview_path, "r") as f:
            codebase_overview = json.load(f)
    else:
        codebase_overview = {}

    # Load existing hashes
    file_hashes_path = output_folder / "file_hashes.json"
    if file_hashes_path.exists():
        with open(file_hashes_path, "r") as f:
            existing_hashes = json.load(f)
    else:
        existing_hashes = {}

    # Update overview with new summaries
    for file_path, summary in new_overviews.items():
        codebase_overview[file_path] = summary

        # Also update hash if provided
        if file_path in file_hashes:
            existing_hashes[file_path] = file_hashes[file_path]

    # Save both overview and hashes
    with open(codebase_overview_path, "w") as f:
        json.dump(codebase_overview, f, indent=4)

    with open(file_hashes_path, "w") as f:
        json.dump(existing_hashes, f, indent=2)

    return codebase_overview
