# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Artifact discovery with hybrid folder classification.

Recursively discovers all supported files in the artifact directory.
Files in recognized phase/type subfolders are automatically classified;
files elsewhere are tagged as "unclassified".
"""

import logging
from collections import Counter
from pathlib import Path

from . import (
    SUPPORTED_EXTENSIONS,
    KNOWN_PHASES,
    KNOWN_TYPES,
    EXTENSION_TO_EXTRACTOR,
    DiscoveredArtifact,
)

logger = logging.getLogger(__name__)


def _classify_path(relative_path: Path) -> tuple[str, str]:
    """Classify a relative path into (project_phase, source_material_type).

    Checks whether the first two path components match a known
    phase / type combination from RECOMMENDED_FOLDER_MAP.

    Returns ("unclassified", "unclassified") when the path does not
    match the recommended structure.
    """
    parts = relative_path.parts
    if len(parts) < 2:
        return "unclassified", "unclassified"

    phase_candidate = parts[0]
    type_candidate = parts[1]

    if phase_candidate in KNOWN_PHASES and type_candidate in KNOWN_TYPES.get(
        phase_candidate, set()
    ):
        return phase_candidate, type_candidate

    return "unclassified", "unclassified"


def discover_artifacts(artifact_dir: str | Path) -> list[DiscoveredArtifact]:
    """Discover all supported artifacts under *artifact_dir*.

    Uses a hybrid approach:
    1. Recursively traverse *artifact_dir* for files with supported extensions.
    2. For each file, check if its relative path matches a recognised
       ``phase/type/...`` pattern from :data:`RECOMMENDED_FOLDER_MAP`.
    3. Matched files get the recognised phase and type; unmatched files
       get ``project_phase="unclassified"`` and
       ``source_material_type="unclassified"``.

    Returns an empty list (with a warning log) when *artifact_dir* does
    not exist or contains no supported files.
    """
    artifact_path = Path(artifact_dir)

    if not artifact_path.exists():
        logger.warning("Artifact directory does not exist: %s", artifact_path)
        return []

    if not artifact_path.is_dir():
        logger.warning("Artifact path is not a directory: %s", artifact_path)
        return []

    artifacts: list[DiscoveredArtifact] = []

    for file_path in sorted(artifact_path.rglob("*")):
        if not file_path.is_file():
            continue

        # Skip Office temporary/lock files (e.g. ~$document.docx)
        if file_path.name.startswith("~$"):
            logger.debug("Skipping Office temp file: %s", file_path.name)
            continue

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        relative = file_path.relative_to(artifact_path)
        phase, material_type = _classify_path(relative)

        artifacts.append(
            DiscoveredArtifact(
                file_path=str(relative),
                absolute_path=file_path.resolve(),
                project_phase=phase,
                source_material_type=material_type,
                file_format=ext.lstrip("."),
            )
        )

    if not artifacts:
        logger.warning("No supported artifacts found in: %s", artifact_path)

    return artifacts


def collect_unsupported_files(artifact_dir: str | Path) -> list[str]:
    """Return relative paths of files skipped because their extension is unsupported.

    Complements :func:`discover_artifacts`: every regular file under
    *artifact_dir* is either discovered as an artifact or reported here.
    Office temporary/lock files (``~$`` prefix) are excluded from both,
    since they are never user content.

    Useful for telling the user which files were filtered out (for example
    source files such as ``.py`` or ``.js`` that live alongside documents).
    """
    artifact_path = Path(artifact_dir)

    if not artifact_path.is_dir():
        return []

    unsupported: list[str] = []
    for file_path in sorted(artifact_path.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.name.startswith("~$"):
            continue
        if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            continue
        unsupported.append(str(file_path.relative_to(artifact_path)))

    return unsupported


def summarize_unsupported_extensions(
    unsupported_files: list[str],
) -> list[tuple[str, int]]:
    """Summarize *unsupported_files* as ``(extension, count)`` pairs.

    Sorted by descending count, then extension name. Files without a
    suffix are reported as ``"(no extension)"``.
    """
    counts = Counter(
        Path(fp).suffix.lower() or "(no extension)" for fp in unsupported_files
    )
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def get_extractor_for_artifact(artifact: DiscoveredArtifact) -> str:
    """Return the extractor name for *artifact* based on its file extension.

    Extractor selection is independent of folder location or classification.

    Returns one of: ``'pptx'``, ``'docx'``, ``'xlsx'``, ``'docs'``,
    ``'pdf'``, ``'video'``.

    Raises :class:`ValueError` for unsupported extensions (should not
    happen if the artifact was produced by :func:`discover_artifacts`).
    """
    ext = f".{artifact.file_format}"
    try:
        return EXTENSION_TO_EXTRACTOR[ext]
    except KeyError:
        raise ValueError(
            f"No extractor for extension '{ext}' (file: {artifact.file_path})"
        )


def generate_artifact_tree_display(artifact_dir: str | Path) -> str:
    """Generate a visual tree representation of the artifact directory.

    Only includes files with supported extensions and skips Office
    temporary files (``~$`` prefix). The output mirrors the format
    used by generate_tree_display from file_utils.
    """
    root = Path(artifact_dir).resolve()

    if not root.exists() or not root.is_dir():
        return f"{root.name}/ (not found)"

    lines: list[str] = [f"{root.name}/"]

    def _build(current: Path, prefix: str = "") -> None:
        try:
            items = sorted(
                current.iterdir(),
                key=lambda x: (x.is_file(), x.name.lower()),
            )
        except PermissionError:
            lines.append(f"{prefix}+-- [Permission denied]")
            return

        filtered = []
        for item in items:
            if item.name.startswith("~$"):
                continue
            if item.is_dir():
                if any(
                    f.suffix.lower() in SUPPORTED_EXTENSIONS
                    for f in item.rglob("*")
                    if f.is_file() and not f.name.startswith("~$")
                ):
                    filtered.append(item)
            elif item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
                filtered.append(item)

        for i, item in enumerate(filtered):
            is_last = i == len(filtered) - 1
            connector = "`-- " if is_last else "|-- "
            extension = "    " if is_last else "|   "

            lines.append(f"{prefix}{connector}{item.name}")
            if item.is_dir():
                _build(item, prefix + extension)

    _build(root)
    return "\n".join(lines)
