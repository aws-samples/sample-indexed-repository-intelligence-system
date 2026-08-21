# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Artifact indexing package for project artifacts.

Provides data models, constants, and utilities for discovering, extracting,
summarizing, and querying project artifacts (DOCX, PPTX, PDF, MD, TXT, video).
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
import json

# ---------------------------------------------------------------------------
# Supported artifact formats — THE single source of truth
# ---------------------------------------------------------------------------
#
# To add or remove a supported format, edit ARTIFACT_FORMATS below and nothing
# else. Every extension set, extractor lookup, ordering table, and user-facing
# format list in the codebase is derived from it.
#
# Adding an entry also requires a matching extractor: see the dispatch in
# ``artifact_extractors.extract_artifact`` for the recognised extractor names
# (``pptx``, ``docx``, ``xlsx``, ``docs``, ``pdf``, ``video``).


@dataclass(frozen=True)
class ArtifactFormat:
    """One supported artifact format and everything the pipeline needs for it."""

    extension: str  # Lowercase, with leading dot (e.g. ".pptx")
    extractor: str  # Extractor name dispatched on in artifact_extractors
    order: int  # Sort position when assembling knowledge_base.md
    description: str  # Human-readable extractor summary (shown to users/docs)


ARTIFACT_FORMATS: tuple[ArtifactFormat, ...] = (
    ArtifactFormat(".pptx", "pptx", 0, "python-pptx: slide text + speaker notes"),
    ArtifactFormat(".docx", "docx", 1, "python-docx: paragraph text"),
    ArtifactFormat(".xlsx", "xlsx", 2, "openpyxl: all sheets, row-by-row cell data"),
    ArtifactFormat(".md", "docs", 3, "built-in: prefixed with source filename"),
    ArtifactFormat(".txt", "docs", 3, "built-in: prefixed with source filename"),
    ArtifactFormat(
        ".pdf", "pdf", 4, "pdfplumber: text extraction, optional OCR for image pages"
    ),
    ArtifactFormat(".mp4", "video", 5, "AWS Transcribe (optional)"),
    ArtifactFormat(".mov", "video", 5, "AWS Transcribe (optional)"),
    ArtifactFormat(".avi", "video", 5, "AWS Transcribe (optional)"),
    ArtifactFormat(".mkv", "video", 5, "AWS Transcribe (optional)"),
)

# --- Views derived from ARTIFACT_FORMATS (do not edit by hand) --------------

#: Extensions recognised during discovery, e.g. ``{".pptx", ...}``.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    fmt.extension for fmt in ARTIFACT_FORMATS
)

#: Extension → extractor name, e.g. ``{".pptx": "pptx"}``.
EXTENSION_TO_EXTRACTOR: dict[str, str] = {
    fmt.extension: fmt.extractor for fmt in ARTIFACT_FORMATS
}

#: Bare format name → knowledge base sort order, e.g. ``{"pptx": 0}``.
FORMAT_ORDER: dict[str, int] = {
    fmt.extension.lstrip("."): fmt.order for fmt in ARTIFACT_FORMATS
}

#: Bare format names in registry order, e.g. ``("pptx", "docx", ...)``.
FORMAT_NAMES: tuple[str, ...] = tuple(
    fmt.extension.lstrip(".") for fmt in ARTIFACT_FORMATS
)


def format_extension_list() -> str:
    """Return supported extensions as a sorted comma-separated string.

    Convenience for user-facing output (CLI help text, previews, prompts).
    """
    return ", ".join(sorted(SUPPORTED_EXTENSIONS))


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

# Placeholder value shipped in config_template.yaml. Treated as "not configured"
# so that a default config does not enable artifact indexing.
ARTIFACT_DIR_PLACEHOLDER = "/path/to/your/artifacts"


def resolve_artifact_dir(config: dict) -> str | None:
    """Return a usable ``artifact_dir`` from *config*, or None if unusable.

    Artifact indexing is only enabled when ``artifact_dir`` is set to a real,
    existing directory. The template placeholder, blank strings, and paths that
    do not exist all resolve to None so callers can cleanly skip artifacts.

    Args:
        config: Loaded configuration dict.

    Returns:
        The artifact directory as a string, or None when not usable.
    """
    artifact_dir = config.get("artifact_dir")
    if not artifact_dir or not str(artifact_dir).strip():
        return None
    if str(artifact_dir).strip() == ARTIFACT_DIR_PLACEHOLDER:
        return None
    if not Path(artifact_dir).expanduser().is_dir():
        return None
    return str(artifact_dir)


# ---------------------------------------------------------------------------
# Recommended folder structure (used for automatic classification)
# ---------------------------------------------------------------------------
#
# Only the phase and type folder *names* drive classification (see
# ``artifact_discovery._classify_path``). The extension lists are advisory —
# they document what typically belongs in each folder and are not enforced,
# so a .pdf placed in ``presentations/`` is still classified as a
# presentation. Every extension listed here must exist in ARTIFACT_FORMATS.

RECOMMENDED_FOLDER_MAP: dict[str, dict[str, list[str]]] = {
    "pre-project": {
        "readouts": [".docx"],
        "design_docs": [".md", ".txt"],
    },
    "during-project": {
        "presentations": [".pptx"],
        "design_docs": [".md", ".txt"],
        "meetings": [".mp4", ".mov", ".avi", ".mkv", ".md", ".txt"],
        "reports": [".pdf", ".docx", ".xlsx"],
        "technical_docs": [".md", ".txt"],
    },
    "post-project": {
        "readouts": [".pptx", ".docx"],
        "roadmap": [".md", ".docx", ".pdf"],
        "production_readiness": [".md", ".docx", ".pdf"],
        "constraints": [".md", ".docx", ".pdf"],
    },
}

KNOWN_PHASES: set[str] = set(RECOMMENDED_FOLDER_MAP.keys())

KNOWN_TYPES: dict[str, set[str]] = {
    phase: set(types.keys()) for phase, types in RECOMMENDED_FOLDER_MAP.items()
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class DiscoveredArtifact:
    """A single discovered artifact with classification metadata."""

    file_path: str  # Relative path from artifact_dir
    absolute_path: Path  # Absolute path for reading
    project_phase: str  # pre-project | during-project | post-project | unclassified
    source_material_type: str  # presentations | readouts | ... | unclassified
    file_format: str  # Bare extension, one of FORMAT_NAMES (e.g. "pptx")


@dataclass
class ExtractionResult:
    """Result of extracting content from a single artifact."""

    file_path: str
    content: str
    file_format: str
    project_phase: str
    source_material_type: str
    success: bool
    error_message: Optional[str] = None


@dataclass
class ArtifactOverview:
    """Schema-aligned artifact summary produced by the LLM summarizer."""

    purpose: str
    source_material_type: str
    project_phase: str
    file_format: str
    key_topics: list[str] = field(default_factory=list)
    related_artifacts: list[str] = field(default_factory=list)
    summary: str = ""

    # -- serialization helpers ------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for JSON output."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactOverview":
        """Deserialize from a plain dict.

        Raises ``KeyError`` / ``TypeError`` for missing or invalid fields.
        """
        return cls(
            purpose=str(data["purpose"]),
            source_material_type=str(data["source_material_type"]),
            project_phase=str(data["project_phase"]),
            file_format=str(data["file_format"]),
            key_topics=list(data.get("key_topics", [])),
            related_artifacts=list(data.get("related_artifacts", [])),
            summary=str(data.get("summary", "")),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ArtifactOverview":
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# Public API for the package
# ---------------------------------------------------------------------------

__all__ = [
    "ARTIFACT_DIR_PLACEHOLDER",
    "resolve_artifact_dir",
    "ArtifactFormat",
    "ARTIFACT_FORMATS",
    "SUPPORTED_EXTENSIONS",
    "RECOMMENDED_FOLDER_MAP",
    "KNOWN_PHASES",
    "KNOWN_TYPES",
    "EXTENSION_TO_EXTRACTOR",
    "FORMAT_ORDER",
    "FORMAT_NAMES",
    "format_extension_list",
    "DiscoveredArtifact",
    "ExtractionResult",
    "ArtifactOverview",
]
