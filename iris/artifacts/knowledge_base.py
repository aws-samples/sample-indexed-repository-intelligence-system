# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Per-artifact file storage and optional knowledge base assembly.

Each artifact's extracted text is stored as an individual ``.md`` file under
``extracted_artifacts/``, mirroring the artifact's relative path.  This is the
**primary retrieval source** at query time.

An optional assembled ``knowledge_base.md`` can be generated for human review
and report generation — it is NOT the primary retrieval source.
"""

import logging
from pathlib import Path

from . import FORMAT_ORDER, ExtractionResult

logger = logging.getLogger(__name__)

EXTRACTED_ARTIFACTS_DIR = "extracted_artifacts"


def _artifact_md_path(artifact_file_path: str, output_dir: Path) -> Path:
    """Compute the ``.md`` storage path for a given artifact relative path.

    Appends ``.md`` to the full filename (preserving the original extension)
    to avoid collisions when two artifacts share the same stem but differ
    in format (e.g. ``report.pdf`` → ``report.pdf.md``,
    ``report.docx`` → ``report.docx.md``).
    """
    rel = Path(artifact_file_path)
    md_name = rel.parent / (rel.name + ".md")
    return output_dir / EXTRACTED_ARTIFACTS_DIR / md_name


def save_extracted_artifact(
    extraction_result: ExtractionResult,
    output_dir: str | Path,
) -> Path:
    """Save a single artifact's extracted text as an individual ``.md`` file.

    The file is placed under ``extracted_artifacts/`` mirroring the artifact's
    relative path.  For example::

        extracted_artifacts/pre-project/readouts/kickoff_readout.md

    Each file includes a YAML-style metadata header followed by the extracted
    content.

    Returns the path to the saved file.
    """
    out = Path(output_dir)
    dest = _artifact_md_path(extraction_result.file_path, out)
    dest.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "---\n"
        f"source: {extraction_result.file_path}\n"
        f"project_phase: {extraction_result.project_phase}\n"
        f"source_material_type: {extraction_result.source_material_type}\n"
        f"file_format: {extraction_result.file_format}\n"
        "---\n\n"
    )

    dest.write_text(header + extraction_result.content, encoding="utf-8")
    logger.debug("Saved extracted artifact: %s", dest)
    return dest


def load_extracted_artifact(
    artifact_file_path: str,
    output_dir: str | Path,
) -> str | None:
    """Load a single artifact's extracted text from its per-artifact ``.md`` file.

    Returns ``None`` if the file does not exist.
    """
    dest = _artifact_md_path(artifact_file_path, Path(output_dir))
    if not dest.exists():
        return None
    return dest.read_text(encoding="utf-8")


def build_knowledge_base(
    extraction_results: list[ExtractionResult],
    output_dir: str | Path,
    client: str = "",
    project: str = "",
) -> tuple[Path, int]:
    """Assemble all extracted content into ``knowledge_base.md``.

    This is an **optional convenience output** for human review and report
    generation.  Per-artifact files under ``extracted_artifacts/`` are the
    primary retrieval source at query time.

    Content is organized by ``project_phase`` then
    ``source_material_type``, separated by Markdown horizontal rules
    (``---``).  Within each section, results are ordered by extractor type:
    PPTX → DOCX → XLSX → Docs → PDF → Video.

    Creates an empty ``knowledge_base.md`` with a warning comment when no
    successful extraction results are provided.

    Returns ``(path_to_knowledge_base, total_character_count)``.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    kb_path = out / "knowledge_base.md"

    # Filter to successful extractions only
    successful = [r for r in extraction_results if r.success and r.content]

    if not successful:
        kb_path.write_text(
            "<!-- knowledge_base.md: no content extracted -->\n",
            encoding="utf-8",
        )
        logger.warning("Knowledge base is empty — no successful extractions.")
        return kb_path, 0

    # Sort: by format order, then by file_path for stability
    successful.sort(key=lambda r: (FORMAT_ORDER.get(r.file_format, 99), r.file_path))

    # Group by phase → type
    from collections import OrderedDict

    grouped: dict[str, dict[str, list[ExtractionResult]]] = OrderedDict()
    for r in successful:
        phase = r.project_phase
        mat_type = r.source_material_type
        grouped.setdefault(phase, OrderedDict()).setdefault(mat_type, []).append(r)

    # Build markdown
    lines: list[str] = []
    header = "# Knowledge Base"
    if client or project:
        header += f"\n## Client: {client} | Project: {project}"
    lines.append(header)
    lines.append("")

    for phase, types in grouped.items():
        lines.append(f"## {phase.replace('-', ' ').title()}")
        lines.append("")
        for mat_type, results in types.items():
            lines.append(f"### {mat_type.replace('_', ' ').title()}")
            lines.append("")
            for r in results:
                lines.append(r.content)
                lines.append("")
                lines.append("---")
                lines.append("")

    content = "\n".join(lines)
    kb_path.write_text(content, encoding="utf-8")

    total_chars = len(content)
    logger.info("Knowledge base written: %s (%d characters)", kb_path, total_chars)
    return kb_path, total_chars
