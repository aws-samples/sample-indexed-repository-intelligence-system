# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Artifact preparation primitives - change detection, tree generation.

Mirrors :mod:`iris.file_system.file_management` for project artifacts.
Where the codebase pipeline writes ``file_paths.txt`` and ``tree.txt``,
this module writes ``artifact_file_paths.txt`` and ``artifact_tree.txt``
into the same cache directory.
"""

from pathlib import Path
from typing import List, Tuple
from pydantic import BaseModel

from . import resolve_artifact_dir
from .artifact_cache_manager import ArtifactCacheManager
from .artifact_discovery import (
    collect_unsupported_files,
    discover_artifacts,
    generate_artifact_tree_display,
    summarize_unsupported_extensions,
)
from ..file_system.file_utils import hash_file_content
from ..utils.utils import construct_output_dir, load_default_config

ARTIFACT_PATHS_FILE = "artifact_file_paths.txt"
ARTIFACT_TREE_FILE = "artifact_tree.txt"


class ArtifactsToProcessResult(BaseModel):
    """Result of artifact filesystem analysis and change detection."""

    artifact_dir: str
    has_changed: bool
    artifacts_to_process: List[str]
    change_details: dict
    tree_display: str
    artifact_paths: List[str]
    total_artifacts: int
    filtered_out_files: List[str]
    filtered_out_extensions: List[Tuple[str, int]]


def save_artifact_state_files(
    artifact_dir: str | Path,
    output_dir: str | Path,
    artifact_paths: List[str],
) -> str:
    """Write ``artifact_file_paths.txt`` and ``artifact_tree.txt`` to *output_dir*.

    Mirrors the ``file_paths.txt`` / ``tree.txt`` pair written by the codebase
    pipeline. Both files cover supported artifacts only.

    Args:
        artifact_dir: Path to the project artifacts directory
        output_dir: IRIS cache directory for this codebase
        artifact_paths: Relative paths of discovered artifacts

    Returns:
        The generated tree display string.
    """
    tree_display = generate_artifact_tree_display(artifact_dir)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with open(output_path / ARTIFACT_PATHS_FILE, "w", encoding="utf-8") as f:
        for path in artifact_paths:
            f.write(f"{path}\n")

    with open(output_path / ARTIFACT_TREE_FILE, "w", encoding="utf-8") as f:
        f.write(tree_display)

    return tree_display


def get_artifacts_to_process(
    artifact_dir: str | Path,
    output_dir: str | Path,
) -> ArtifactsToProcessResult:
    """
    Analyze the artifact directory for changes and determine what needs processing.

    Only files with supported extensions are considered artifacts; everything
    else is reported through ``filtered_out_files`` so callers can tell the
    user what was excluded.

    Args:
        artifact_dir: Path to the project artifacts directory
        output_dir: Output directory for state files (the IRIS cache directory)

    Returns:
        ArtifactsToProcessResult with change analysis and artifacts to process
    """
    try:
        # Step 1: Discover supported artifacts and note what was filtered out
        artifacts = discover_artifacts(artifact_dir)
        artifact_paths = [a.file_path for a in artifacts]

        filtered_out = collect_unsupported_files(artifact_dir)

        # Step 2: Write state files to disk
        tree_display = save_artifact_state_files(
            artifact_dir=artifact_dir,
            output_dir=output_dir,
            artifact_paths=artifact_paths,
        )

        # Step 3: Generate hashes for current state
        current_hashes = {
            a.file_path: hash_file_content(a.absolute_path) for a in artifacts
        }

        # Step 4: Use cache manager for all cache operations
        cache = ArtifactCacheManager(output_dir)
        change_result = cache.has_changed(current_hashes)

        # Step 5: Get artifacts needing updates if there are changes
        artifacts_to_process: List[str] = []
        if change_result["has_changed"]:
            artifacts_to_process = cache.get_files_to_process(current_hashes)

        return ArtifactsToProcessResult(
            artifact_dir=str(Path(artifact_dir).resolve()),
            has_changed=change_result["has_changed"],
            artifacts_to_process=artifacts_to_process,
            change_details=change_result,
            tree_display=tree_display,
            artifact_paths=artifact_paths,
            total_artifacts=len(artifacts),
            filtered_out_files=filtered_out,
            filtered_out_extensions=summarize_unsupported_extensions(filtered_out),
        )

    except Exception as e:
        # Re-raise with more context
        raise RuntimeError(f"Failed to analyze artifacts in {artifact_dir}: {e}") from e


def validate_artifact_tree(
    artifact_dir: str | Path | None = None,
    codebase_dir: str | Path | None = None,
) -> ArtifactsToProcessResult | None:
    """
    Validate the artifact tree and report the artifacts that would be processed.

    Loads defaults from config when arguments are omitted. Unlike
    :func:`iris.file_system.file_management.validate_tree`, a missing or
    unconfigured artifact directory is not an error: artifact indexing is
    optional, so this returns ``None`` instead of exiting.

    Args:
        artifact_dir: Project artifacts directory (defaults to config)
        codebase_dir: Codebase directory, used to locate the cache directory
            (defaults to config)

    Returns:
        ArtifactsToProcessResult, or None when no usable artifact_dir is set
    """
    config = load_default_config()

    if artifact_dir is None:
        artifact_dir = resolve_artifact_dir(config)
        if artifact_dir is None:
            return None
    elif not Path(artifact_dir).expanduser().is_dir():
        return None

    if codebase_dir is None:
        codebase_dir = config.get("codebase_dir", ".")

    # The artifact cache lives next to the codebase cache, so a usable
    # codebase_dir is required to locate it.
    if not Path(codebase_dir).expanduser().exists():
        raise RuntimeError(
            f"Cannot locate the IRIS cache: codebase directory '{codebase_dir}' "
            "does not exist. Set codebase_dir in config.yaml."
        )

    output_dir = construct_output_dir(codebase_dir=codebase_dir)

    return get_artifacts_to_process(
        artifact_dir=Path(artifact_dir).expanduser(),
        output_dir=output_dir,
    )
