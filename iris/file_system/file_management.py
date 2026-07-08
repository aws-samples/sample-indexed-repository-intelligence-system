# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Codebase preparation primitives - change detection, tree generation, file preparation.
"""

import sys
from pathlib import Path
from typing import List
from pydantic import BaseModel

from .cache_manager import CodebaseCacheManager
from .file_utils import (
    collect_files,
    generate_tree_display,
    generate_tree_structure,
    generate_hashes,
)
from ..utils.utils import (
    construct_output_dir,
    get_ignore_patterns,
    load_default_config,
)


class FilesToProcessResult(BaseModel):
    """Result of filesystem analysis and change detection."""

    has_changed: bool
    files_to_process: List[str]
    change_details: dict
    tree_display: str
    tree_structure: dict
    total_files: int


def get_files_to_process(
    codebase_dir: str | Path,
    output_dir: str | Path,
    ignore_patterns: List[str],
) -> FilesToProcessResult:
    """
    Analyze codebase for changes and determine which files need processing.

    Args:
        codebase_dir: Path to codebase
        output_dir: Output directory for state files
        ignore_patterns: Patterns to ignore

    Returns:
        FilesToProcessResult with change analysis and files to process
    """
    try:
        # Step 1: Collect files from the repository that aren't on the ignore list
        file_paths = collect_files(codebase_dir, ignore_patterns)

        # Create file tree for visualization
        tree_display = generate_tree_display(codebase_dir, ignore_patterns)
        tree_structure = generate_tree_structure(codebase_dir, ignore_patterns)

        # Step 2: Write files to disk
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save file paths
        with open(output_path / "file_paths.txt", "w") as f:
            for path in file_paths:
                f.write(f"{path}\n")

        # Save tree display
        with open(output_path / "tree.txt", "w", encoding="utf-8") as f:
            f.write(tree_display)

        # Step 3: Generate hashes for current state
        current_hashes = generate_hashes(codebase_dir, file_paths)

        # Step 4: Use cache manager for all cache operations
        cache = CodebaseCacheManager(output_dir)

        change_result = cache.has_changed(current_hashes)

        # Step 5: Get files needing updates if there are changes
        files_to_process = []
        if change_result["has_changed"]:
            files_to_process = cache.get_files_to_process(current_hashes)

        # Step 7: Return structured result using Pydantic model
        return FilesToProcessResult(
            has_changed=change_result["has_changed"],
            files_to_process=files_to_process,
            change_details=change_result,
            tree_display=tree_display,
            tree_structure=tree_structure,
            total_files=len(file_paths),
        )

    except Exception as e:
        # Re-raise with more context
        raise RuntimeError(f"Failed to analyze files in {codebase_dir}: {e}") from e


def validate_tree(codebase_dir: str | Path | None = None) -> FilesToProcessResult:
    """
    Validate the codebase tree and report the files that would be processed.

    Loads defaults from config when arguments are omitted. Exits the process
    with status 1 if the codebase directory does not exist (CLI-friendly).

    Args:
        codebase_dir: Root directory of codebase (defaults to config)

    Returns:
        FilesToProcessResult describing the current tree and pending changes
    """
    # Load defaults from config if not provided
    config = load_default_config()

    if codebase_dir is None:
        codebase_dir = Path(config["codebase_dir"])

    if not Path(codebase_dir).exists():
        print(f"Code base directory {codebase_dir} doesn't exist.")
        sys.exit(1)

    output_dir = construct_output_dir(codebase_dir=codebase_dir)
    ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)

    files_result: FilesToProcessResult = get_files_to_process(
        codebase_dir=codebase_dir,
        output_dir=output_dir,
        ignore_patterns=ignore_patterns,
    )

    return files_result
