# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Orchestrator for artifact discovery, extraction, storage, and summarization.

Analogous to :func:`generate_context` for the codebase pipeline.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .artifacts.artifact_cache_manager import ArtifactCacheManager
from .artifacts.artifact_discovery import discover_artifacts
from .artifacts.artifact_file_management import save_artifact_state_files
from .artifacts.artifact_extractors import extract_artifacts_parallel
from .artifacts.knowledge_base import (
    build_knowledge_base,
    save_extracted_artifact,
)
from .artifacts.artifact_summarizer import summarize_artifacts
from .file_system.file_utils import hash_file_content
from .artifacts.knowledge_base import load_extracted_artifact
from .artifacts import ExtractionResult

logger = logging.getLogger(__name__)

_ARTIFACT_PROCESSING_CONFIG_DEFAULTS = {
    "artifact_max_file_size": 30_000_000,
    "artifact_video_max_file_size": 300_000_000,
    "artifact_ocr_enabled": False,
    "artifact_ocr_provider": "llm",
    "artifact_ocr_max_pages": 50,
    "artifact_transcription_enabled": False,
    "artifact_transcribe_s3_bucket": "",
}


def _artifact_processing_config_fingerprint(config: dict) -> str:
    settings = {
        key: config.get(key, default)
        for key, default in _ARTIFACT_PROCESSING_CONFIG_DEFAULTS.items()
    }
    payload = json.dumps(settings, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ArtifactContextResult(BaseModel):
    """Result of artifact context generation."""

    status: Literal["update_complete", "no_op", "error"]
    message: str = ""
    processed_artifacts: list[str] | None = None
    knowledge_base_path: str | None = None
    knowledge_base_size: int | None = None
    total_artifacts: int | None = None


def generate_artifact_context(
    artifact_dir: str | Path,
    output_dir: str | Path,
    config: dict | None = None,
    verbose: bool = False,
    force: bool = False,
) -> ArtifactContextResult:
    """Orchestrate the full artifact indexing pipeline.

    Steps:
    1. Discover artifacts in *artifact_dir*
    2. Compute file hashes and detect changes via :class:`ArtifactCacheManager`
    3. Extract content from changed files in parallel
    4. Save per-artifact ``.md`` files under ``extracted_artifacts/``
    5. Optionally rebuild ``knowledge_base.md``
    6. Summarize changed artifacts via LLM
    7. Return :class:`ArtifactContextResult`

    Returns a ``no_op`` result when no artifacts have changed.
    Handles missing/empty *artifact_dir* gracefully.
    """
    config = config or {}
    artifact_path = Path(artifact_dir)
    out_path = Path(output_dir)

    max_file_size = config.get("artifact_max_file_size", 30_000_000)
    video_max_file_size = config.get("artifact_video_max_file_size", 300_000_000)
    max_workers = config.get("artifact_max_workers", 4)
    generate_kb = config.get("artifact_generate_knowledge_base", True)
    ocr_enabled = config.get("artifact_ocr_enabled", False)
    ocr_max_pages = config.get("artifact_ocr_max_pages", 50)
    ocr_provider = config.get("artifact_ocr_provider", "llm")

    # Resolve model config for LLM-based OCR and video frame analysis
    # (reuses file_summarizer model)
    llm_model_config = None
    try:
        models = (
            config.get("model_configuration", {})
            .get("file_summarizer", {})
            .get("models", [])
        )
        if models:
            llm_model_config = models[0]
    except Exception:
        pass  # Will be resolved lazily inside the extractor

    # Build transcription config dict from individual config fields
    transcription_config = {
        "artifact_transcription_enabled": config.get(
            "artifact_transcription_enabled", False
        ),
        "artifact_transcribe_s3_bucket": config.get(
            "artifact_transcribe_s3_bucket", ""
        ),
    }

    if verbose:
        print("🔍 Artifact Context Generation")
        print(f"📂 Artifacts: {artifact_path}")
        print(f"💾 Output: {out_path}")

    try:
        # Step 1: Discover artifacts
        artifacts = discover_artifacts(artifact_path)
        if not artifacts:
            msg = f"No supported artifacts found in {artifact_path}"
            if verbose:
                print(f"⚠️  {msg}")
            return ArtifactContextResult(status="no_op", message=msg)

        if verbose:
            print(f"📄 Discovered {len(artifacts)} artifacts")

        # Persist the artifact tree and path list alongside the codebase
        # equivalents (tree.txt / file_paths.txt).
        save_artifact_state_files(
            artifact_dir=artifact_path,
            output_dir=out_path,
            artifact_paths=[a.file_path for a in artifacts],
        )

        # Step 2: Compute hashes and detect changes
        current_hashes = {}
        for art in artifacts:
            current_hashes[art.file_path] = hash_file_content(art.absolute_path)

        cache = ArtifactCacheManager(out_path)
        changes = cache.has_changed(current_hashes)
        artifact_processing_fingerprint = _artifact_processing_config_fingerprint(config)
        artifact_processing_config_changed = cache.processing_config_has_changed(
            artifact_processing_fingerprint
        )

        if (
            not force
            and not artifact_processing_config_changed
            and not changes["has_changed"]
        ):
            msg = "All artifacts are up to date, no processing needed."
            if verbose:
                print(f"✅ {msg}")
            return ArtifactContextResult(
                status="no_op",
                message=msg,
                total_artifacts=len(artifacts),
            )

        files_to_process = (
            list(current_hashes)
            if force or artifact_processing_config_changed
            else changes["changed_files"]
        )
        if verbose:
            print(f"🔄 Processing {len(files_to_process)} changed artifacts")
            if changes["new_files"]:
                print(f"   New: {len(changes['new_files'])}")
            if changes["modified_files"]:
                print(f"   Modified: {len(changes['modified_files'])}")
            if changes["deleted_files"]:
                print(f"   Deleted: {len(changes['deleted_files'])}")

        # Step 3: Extract content from changed artifacts
        artifacts_to_extract = [
            a for a in artifacts if a.file_path in set(files_to_process)
        ]
        extraction_results = extract_artifacts_parallel(
            artifacts_to_extract,
            max_file_size=max_file_size,
            video_max_file_size=video_max_file_size,
            transcription_config=transcription_config,
            max_workers=max_workers,
            ocr_enabled=ocr_enabled,
            ocr_max_pages=ocr_max_pages,
            ocr_provider=ocr_provider,
            ocr_model_config=llm_model_config,
        )

        successful = [r for r in extraction_results if r.success]
        if verbose:
            print(f"📝 Extracted {len(successful)}/{len(extraction_results)} artifacts")

        # Step 4: Save per-artifact .md files
        for result in successful:
            save_extracted_artifact(result, out_path)

        # Step 5: Optionally rebuild knowledge base
        kb_path_str = None
        kb_size = None
        if generate_kb and (successful or cache.needs_kb_rebuild()):
            # For a full KB rebuild we need ALL successful extractions,
            # not just the changed ones. Load existing + merge new.
            all_results = _collect_all_extraction_results(
                artifacts, extraction_results, out_path
            )
            kb_path, kb_size = build_knowledge_base(all_results, out_path)
            kb_path_str = str(kb_path)
            if verbose:
                print(f"📚 Knowledge base: {kb_size} characters")

        # Step 6: Summarize changed artifacts
        if successful:
            summarize_artifacts(
                successful,
                output_dir=out_path,
                max_file_size=max_file_size,
                max_workers=max_workers,
            )

        # Step 7: Save updated hashes and artifact processing settings
        cache.save_hashes(current_hashes)
        cache.save_processing_config_fingerprint(artifact_processing_fingerprint)

        processed = [r.file_path for r in successful]
        msg = f"Successfully processed {len(processed)} artifacts."
        if verbose:
            print(f"✅ {msg}")

        return ArtifactContextResult(
            status="update_complete",
            message=msg,
            processed_artifacts=processed,
            knowledge_base_path=kb_path_str,
            knowledge_base_size=kb_size,
            total_artifacts=len(artifacts),
        )

    except Exception as exc:
        logger.error("Artifact context generation failed: %s", exc, exc_info=True)
        msg = f"Artifact context generation error: {exc}"
        if verbose:
            print(f"❌ {msg}")
        return ArtifactContextResult(status="error", message=msg)


def _collect_all_extraction_results(
    all_artifacts,
    new_results: list,
    output_dir: Path,
) -> list:
    """Collect extraction results for ALL artifacts (existing + newly extracted).

    For artifacts that were just extracted, use the new results.
    For unchanged artifacts, load from their per-artifact .md files.
    """
    new_by_path = {r.file_path: r for r in new_results if r.success}
    all_results = []

    for art in all_artifacts:
        if art.file_path in new_by_path:
            all_results.append(new_by_path[art.file_path])
        else:
            # Load from existing per-artifact file
            content = load_extracted_artifact(art.file_path, output_dir)
            if content:
                all_results.append(
                    ExtractionResult(
                        file_path=art.file_path,
                        content=content,
                        file_format=art.file_format,
                        project_phase=art.project_phase,
                        source_material_type=art.source_material_type,
                        success=True,
                    )
                )

    return all_results
