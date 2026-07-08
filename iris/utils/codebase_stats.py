# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Utility functions for calculating codebase-level statistics and metadata.
"""

from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import logging

from ..file_system.file_utils import load_codebase_overview, get_codebase_metadata

log = logging.getLogger(__name__)


def get_codebase_evaluation_timestamp(output_dir: str | Path) -> Optional[str]:
    """
    Get the last evaluation timestamp for the entire codebase.

    This function retrieves the codebase-level evaluation timestamp from the
    codebase_metadata.json file, representing when the codebase was last
    fully evaluated.

    Args:
        output_dir: Directory containing codebase metadata

    Returns:
        ISO 8601 timestamp string of the last evaluation, or None if not found
    """
    try:
        # Get codebase metadata from separate file
        metadata = get_codebase_metadata(output_dir)

        if not metadata:
            log.info(f"No codebase metadata found in {output_dir}")
            return None

        # Return the evaluation timestamp if it exists
        timestamp = metadata.get("evaluation_timestamp")

        if timestamp:
            # Validate the timestamp format
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return timestamp
            except (ValueError, TypeError) as e:
                log.warning(f"Invalid timestamp format in metadata: {timestamp} - {e}")
                return None

        log.info("No evaluation timestamp found in codebase metadata")
        return None

    except Exception as e:
        log.error(f"Error retrieving codebase evaluation timestamp: {e}")
        return None


def get_codebase_evaluation_stats(output_dir: str | Path) -> Dict[str, Any]:
    """
    Get comprehensive evaluation statistics for the codebase.

    Args:
        output_dir: Directory containing codebase overview data

    Returns:
        Dictionary containing evaluation statistics
    """
    try:
        # Load the codebase overview
        overview = load_codebase_overview(output_dir)

        if not overview:
            return {
                "total_files": 0,
                "evaluated_files": 0,
                "last_evaluation": None,
                "evaluation_coverage": 0.0,
            }

        # Count all files
        total_files = len(overview)
        # All files in overview are considered evaluated (they have summaries)
        evaluated_files = total_files

        # Get codebase-level evaluation timestamp from separate metadata file
        last_evaluation = get_codebase_evaluation_timestamp(output_dir)

        # Calculate coverage percentage (100% if we have files in overview)
        coverage = 100.0 if total_files > 0 else 0.0

        return {
            "total_files": total_files,
            "evaluated_files": evaluated_files,
            "last_evaluation": last_evaluation,
            "evaluation_coverage": round(coverage, 2),
        }

    except Exception as e:
        log.error(f"Error calculating codebase evaluation stats: {e}")
        return {
            "total_files": 0,
            "evaluated_files": 0,
            "last_evaluation": None,
            "evaluation_coverage": 0.0,
            "error": str(e),
        }
