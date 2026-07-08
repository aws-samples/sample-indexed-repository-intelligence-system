# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Orchestrator for codebase preparation and summarization.
"""

from typing import List, Literal
from pathlib import Path
import logging
from pydantic import BaseModel

from .file_system.file_management import get_files_to_process, FilesToProcessResult
from .file_system.file_utils import update_codebase_metadata
from .summarize.file_summarizer import summarize_files
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class ContextGenerationResult(BaseModel):
    """Result of orchestration."""

    status: Literal["update_complete", "no_op", "error"]
    message: str = ""
    processed_files: list[str] | None = None
    file_change_details: dict | None = None
    tree_display: str | None = None
    total_files: int | None = None


def generate_context(
    codebase_dir: str | Path,
    output_dir: str | Path,
    ignore_patterns: List[str],
    additional_context: str = "",
    verbose: bool = False,
) -> ContextGenerationResult:
    """
    Orchestrate the full pipeline: preparation + summarization.
    Is a no op if there are no new files to generate context for.

    Args:
        codebase_dir: Path to codebase
        output_dir: Output directory
        ignore_patterns: Patterns to ignore
        additional_context: Optional context for summarization
        verbose: Show progress messages and status updates

    Returns:
        ContextGenerationResult with completion status
    """
    if verbose:
        print("🚀 IRIS Context Generation")
        print(f"📂 Codebase: {codebase_dir}")
        print(f"💾 Output: {output_dir}")
        print(
            f"🚫 Ignoring: {', '.join(ignore_patterns[:3])}{'...' if len(ignore_patterns) > 3 else ''}"
        )
        if additional_context:
            print("📝 Additional context provided")
        print()
        print("🔄 Starting context generation...")

    try:
        # Step 3: Analyze files for changes
        files_result: FilesToProcessResult = get_files_to_process(
            codebase_dir=codebase_dir,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        if files_result.has_changed:
            change_details = files_result.change_details
            log.info("-" * 25)
            log.info("Changes detected:")
            log.info(f"  New files: {len(change_details['new_files'])}")
            log.info(f"  Modified files: {len(change_details['modified_files'])}")
            log.info(f"  Deleted files: {len(change_details['deleted_files'])}")
            log.info(f"  Files to process: {len(files_result.files_to_process)}")
            log.info("-" * 25)

            print(f"📝 Found changes in {len(files_result.files_to_process)} files")
        else:
            log.debug(
                "\n"
                + "-" * 25
                + "\nNo changes detected - codebase context is up to date\n"
                + "-" * 25
            )

        # Step 4: Process files if needed
        if files_result.files_to_process:
            log.info(
                f"Starting summarization of {len(files_result.files_to_process)} files..."
            )

            _ = summarize_files(
                files_to_summarize=files_result.files_to_process,
                codebase_dir=codebase_dir,
                output_dir=output_dir,
                additional_context=additional_context,
            )

            result = ContextGenerationResult(
                status="update_complete",
                message=f"Successfully processed {len(files_result.files_to_process)} files.",
                processed_files=files_result.files_to_process,
                file_change_details=files_result.change_details,
                tree_display=files_result.tree_display,
                total_files=files_result.total_files,
            )

            log.info(result.message)

            if verbose and result.processed_files:
                print(f"✅ {result.message}")
                print("📋 Processed files:")
                for file_path in result.processed_files:
                    print(f"   • {file_path}")
                print("\n🎉 Context generation complete!")
                print(f"📁 Results saved to: {output_dir}")
        else:
            result = ContextGenerationResult(
                status="no_op",
                message="All files are up to date, no context generation updates needed.",
            )

            if verbose:
                print(f"✅ {result.message}")

        # Update codebase-level evaluation timestamp after each evaluation
        update_codebase_metadata(
            output_dir, {"evaluation_timestamp": datetime.now(timezone.utc).isoformat()}
        )
        return result

    except Exception as e:
        log.error(e, exc_info=True)
        result = ContextGenerationResult(
            status="error", message=f"Context Generation error: {e}"
        )

        if verbose:
            print(f"❌ Context generation failed: {result.message}")

        return result
