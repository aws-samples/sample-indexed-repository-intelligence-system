# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
LLM-based artifact summarization producing ArtifactOverview JSON objects.

Follows the same parallel ThreadPoolExecutor pattern as
:func:`summarize_files` in ``iris/summarize/file_summarizer.py``,
but uses an artifact-specific prompt and schema.
"""

import json
import logging
import re
import threading

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore.config import Config
from tqdm import tqdm

from ..utils import load_default_config
from ..utils.bedrock import call_bedrock
from . import FORMAT_NAMES, ArtifactOverview, ExtractionResult

logger = logging.getLogger(__name__)

_SYSTEM_MESSAGE = (
    "You are an expert document analyst. Analyze the provided artifact content "
    "and produce a structured JSON summary following the given schema. "
    "Output ONLY the JSON wrapped in triple backticks (```json ... ```)."
)

_STATIC_PROMPT_TEMPLATE = f"""\
<task>
Analyze the given project artifact and generate a structured summary in JSON format.
</task>

<instructions>
1. The artifact metadata is provided in <artifact_metadata>...</artifact_metadata>.
2. The extracted content is provided in <artifact_content>...</artifact_content>.
3. Produce a JSON object with these fields:
   - "purpose": A one-sentence description of the artifact's purpose.
   - "source_material_type": The type of source material (e.g., presentations, readouts, design_docs).
   - "project_phase": The project phase (e.g., pre-project, during-project, post-project, unclassified).
   - "file_format": The file format (one of: {", ".join(FORMAT_NAMES)}).
   - "key_topics": A list of 3-8 key topics covered in the artifact.
   - "related_artifacts": A list of related artifact file paths mentioned or implied (empty list if none).
   - "summary": A 2-4 sentence summary of the artifact's content.
4. The output JSON should be wrapped in triple backticks (including the word `json`).
5. Don't output anything else other than the JSON wrapped within triple backticks.
</instructions>
"""


def _build_dynamic_message(
    extraction_result: ExtractionResult, max_file_size: int
) -> str:
    """Build the dynamic portion of the LLM prompt for a single artifact."""
    content = extraction_result.content
    if len(content) > max_file_size:
        logger.warning(
            "Truncating content for %s from %d to %d chars",
            extraction_result.file_path,
            len(content),
            max_file_size,
        )
        content = content[:max_file_size]

    return (
        f"<artifact_metadata>\n"
        f"file_path: {extraction_result.file_path}\n"
        f"file_format: {extraction_result.file_format}\n"
        f"project_phase: {extraction_result.project_phase}\n"
        f"source_material_type: {extraction_result.source_material_type}\n"
        f"</artifact_metadata>\n\n"
        f"<artifact_content>\n{content}\n</artifact_content>"
    )


def _parse_llm_response(response: str) -> dict:
    """Extract JSON from an LLM response wrapped in triple backticks."""
    pattern = r"```json\s*(.*?)\s*```"
    match = re.search(pattern, response, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON block found in LLM response")
    return json.loads(match.group(1))


def _fallback_overview(extraction_result: ExtractionResult) -> ArtifactOverview:
    """Produce a metadata-only fallback when LLM summarization fails."""
    return ArtifactOverview(
        purpose=f"Artifact: {extraction_result.file_path}",
        source_material_type=extraction_result.source_material_type,
        project_phase=extraction_result.project_phase,
        file_format=extraction_result.file_format,
        key_topics=[],
        related_artifacts=[],
        summary=f"Summarization failed for {extraction_result.file_path}.",
    )


def summarize_artifact(
    extraction_result: ExtractionResult,
    model_config: dict,
    max_file_size: int = 30_000_000,
) -> ArtifactOverview:
    """Summarize a single artifact via LLM.

    Truncates content exceeding *max_file_size*. Retries once on
    unparsable response; falls back to metadata-only summary on second
    failure.
    """
    model_id = model_config["model_id"]
    region = model_config["region"]
    boto3_config = Config(
        region_name=region,
        read_timeout=300,
        retries={"mode": "standard", "max_attempts": 5},
    )
    bedrock_client = boto3.client("bedrock-runtime", config=boto3_config)

    dynamic_message = _build_dynamic_message(extraction_result, max_file_size)

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            response = call_bedrock(
                static_message=_STATIC_PROMPT_TEMPLATE,
                dynamic_message=dynamic_message,
                system_message=_SYSTEM_MESSAGE,
                model_id=model_id,
                bedrock_client=bedrock_client,
                maxTokens=4096,
            )
            parsed = _parse_llm_response(response)
            return ArtifactOverview.from_dict(parsed)
        except Exception as exc:
            if attempt < max_attempts:
                logger.warning(
                    "Summarization attempt %d failed for %s: %s — retrying",
                    attempt,
                    extraction_result.file_path,
                    exc,
                )
            else:
                logger.error(
                    "Summarization failed for %s after %d attempts: %s — using fallback",
                    extraction_result.file_path,
                    max_attempts,
                    exc,
                )
                return _fallback_overview(extraction_result)

    # Should not reach here, but just in case
    return _fallback_overview(extraction_result)


def summarize_artifacts(
    extraction_results: list[ExtractionResult],
    output_dir: str | Path,
    model_config: dict | None = None,
    max_file_size: int = 30_000_000,
    max_workers: int = 4,
) -> dict[str, ArtifactOverview]:
    """Summarize multiple artifacts in parallel using ThreadPoolExecutor.

    Follows the same thread-pool pattern as :func:`summarize_files`.
    Saves each summary + hash atomically. Writes ``artifact_overview.json``
    to *output_dir*.

    Returns a dict mapping ``file_path`` → :class:`ArtifactOverview`.
    """
    if not extraction_results:
        return {}

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if model_config is None:
        config = load_default_config()
        models = config["model_configuration"]["file_summarizer"]["models"]
        model_config = models[0]  # Use first model for artifact summarization

    # Only summarize successful extractions
    to_summarize = [r for r in extraction_results if r.success and r.content]
    if not to_summarize:
        return {}

    results: dict[str, ArtifactOverview] = {}
    lock = threading.Lock()

    # Load existing overview for atomic updates
    overview_path = out / "artifact_overview.json"
    if overview_path.exists():
        try:
            existing = json.loads(overview_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}

    def _worker(er: ExtractionResult) -> None:
        overview = summarize_artifact(er, model_config, max_file_size)
        with lock:
            results[er.file_path] = overview
            # Atomic save: update overview on disk after each summary
            existing[er.file_path] = overview.to_dict()
            overview_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, er): er for er in to_summarize}
        with tqdm(
            total=len(to_summarize), desc="📝 Summarizing artifacts", unit="file"
        ) as pbar:
            for future in as_completed(futures):
                er = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    logger.error(
                        "Unexpected error summarizing %s: %s", er.file_path, exc
                    )
                    with lock:
                        fallback = _fallback_overview(er)
                        results[er.file_path] = fallback
                        existing[er.file_path] = fallback.to_dict()
                        overview_path.write_text(
                            json.dumps(existing, indent=2), encoding="utf-8"
                        )
                pbar.update(1)

    logger.info("Summarized %d artifacts → %s", len(results), overview_path)
    return results
