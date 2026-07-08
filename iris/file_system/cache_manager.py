# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Codebase cache manager for handling file updates
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

from .file_utils import (
    load_file_hashes,
    load_codebase_overview,
    save_codebase_overview,
    save_file_hashes,
)

log = logging.getLogger(__name__)


class CodebaseCacheManager:
    """
    Manages codebase cache files (hashes and overview).

    Responsible for loading, validating, and updating cache state.
    Provides high-level operations for change detection and cache validation.
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = output_dir
        self._hashes: Optional[Dict[str, str]] = None
        self._overview: Optional[Dict[str, dict]] = None

    def load_state(self):
        """Load both hashes and overview from disk."""
        self._hashes = load_file_hashes(self.output_dir)
        self._overview = load_codebase_overview(self.output_dir)

    @property
    def hashes(self) -> Dict[str, str]:
        """Get file hashes, loading from disk if needed."""
        if self._hashes is None:
            self.load_state()

        if self._hashes is None:
            raise ValueError("Couldn't load hashes")
        return self._hashes

    @property
    def overview(self) -> Dict[str, dict]:
        """Get codebase overview, loading from disk if needed."""
        if self._overview is None:
            self.load_state()

        if self._overview is None:
            raise ValueError("Couldn't load code_overview")
        return self._overview

    def has_changed(
        self,
        current_hashes: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Compare current file hashes against existing hashes to detect changes.

        Performs efficient set-based comparison to identify:
        - New files (in current but not in existing)
        - Deleted files (in existing but not in current)
        - Modified files (same path, different hash)

        Args:
            current_hashes: Current file path -> hash mapping from filesystem scan
            existing_hashes: Previous file path -> hash mapping from disk cache

        Returns:
            Dict containing:
            - 'has_changed' (bool): True if any files were added, deleted, or modified
            - 'changed_files' (list): Files with content changes (new + modified, excludes deleted)
            - 'new_files' (list): Files that exist now but didn't before
            - 'deleted_files' (list): Files that existed before but don't now
            - 'modified_files' (list): Files that exist in both but have different content hashes

        Note:
            - If existing_hashes is empty, all current files are considered "new"
            - changed_files excludes deleted files since they don't need processing
            - Uses set operations for O(n) performance instead of nested loops
        """
        # If no existing hashes, all files are "new"
        if not self.hashes:
            return {
                "has_changed": True,
                "changed_files": list(current_hashes.keys()),
                "new_files": list(current_hashes.keys()),
                "deleted_files": [],
                "modified_files": [],
            }

        # Files in current filesystem
        current_keys = set(current_hashes.keys())

        # Files in existing hashes cache
        existing_keys = set(self.hashes.keys())

        # File in existing overview cache
        overview_keys = set(self.overview.keys())

        # Find new and deleted files
        new_files = list(current_keys - existing_keys)
        deleted_files = list(existing_keys - current_keys)

        # Find null reference summaries (entries in overview but not in current filesystem)
        # These are corrupt/orphaned entries that need cleanup
        null_reference_summaries = list(
            overview_keys - current_keys - set(deleted_files)
        )

        # Find null hashes (entries in hashes but not in overview)
        # These indicate corruption where hashes were saved but summarization failed
        null_hashes = list(existing_keys - overview_keys)

        # Combine deleted files, null references, and null hashes for cleanup
        files_to_remove_from_cache = set(
            deleted_files + null_reference_summaries + null_hashes
        )

        # Silent cleanup with logging
        if files_to_remove_from_cache:
            self.remove_deleted_files_from_cache(files_to_remove_from_cache)
            if null_reference_summaries:
                log.info(
                    f"Cleaned up {len(null_reference_summaries)} orphaned overview entries: {null_reference_summaries}"
                )
            if null_hashes:
                log.info(
                    f"Cleaned up {len(null_hashes)} orphaned hash entries: {null_hashes}"
                )

        # Find modified files (files that exist in both but have different hashes)
        common_files = current_keys & existing_keys
        modified_files = [
            file_path
            for file_path in common_files
            if current_hashes[file_path] != self.hashes[file_path]
        ]

        # All changed files = new + modified (we don't need to summarize deleted files)
        updated_files = new_files + modified_files

        has_any_changes = bool(new_files or deleted_files or modified_files)

        return {
            "has_changed": has_any_changes,
            "changed_files": updated_files,
            "new_files": new_files,
            "deleted_files": deleted_files,
            "modified_files": modified_files,
        }

    def get_invalid_cache_entries(
        self,
    ) -> List[str]:
        """
        Validate that cache is consistent and not corrupt.

        Returns files that have hashes but missing/invalid entries in the
        overview file.
        This shouldn't happen in normal operation - indicates cache corruption.
            - Hashes should always be written alongside overview writes

        Args:
            existing_hashes: Already loaded file hashes
            existing_overview: Already loaded codebase overview

        Returns:
            List of files with cache inconsistencies
        """
        files_needing_overview_generation = set()

        # Files that have hashes but are missing from overview entirely
        hashed_files = set(self.hashes.keys())
        overview_files = set(self.overview.keys())
        missing_from_overview = hashed_files - overview_files
        files_needing_overview_generation.update(missing_from_overview)

        # Files that are in overview but have invalid entries
        files_with_corrupt_overview = [
            file_path
            for file_path, overview in self.overview.items()
            if not overview or not isinstance(overview, dict)
        ]
        files_needing_overview_generation.update(files_with_corrupt_overview)

        return list(files_needing_overview_generation)

    def get_files_to_process(self, current_hashes: Dict[str, str]) -> List[str]:
        """
        Determine which files need updates based on changes and cache
        validation.

        Args:
            current_hashes: Current file hashes from filesystem

        Returns:
            List of files that need updates
        """
        changed_files = self.has_changed(current_hashes)
        corrupted_files = self.get_invalid_cache_entries()

        files_to_process = set()
        files_to_process.update(changed_files["new_files"])
        files_to_process.update(changed_files["modified_files"])
        files_to_process.update(corrupted_files)

        return list(files_to_process)

    def remove_deleted_files_from_cache(self, deleted_files: set | list):
        """
        Remove deleted files from both hash cache and codebase overview.

        This ensures the cache stays consistent when files are deleted from
        the filesystem. Updates both in-memory cache and saves to disk.

        Args:
            deleted_files: List of file paths that have been deleted
        """
        if not deleted_files:
            return  # Nothing to do

        # Remove from hash cache
        for file_path in deleted_files:
            if file_path in self.hashes:
                del self.hashes[file_path]

        # Remove from overview cache
        for file_path in deleted_files:
            if file_path in self.overview:
                del self.overview[file_path]

        # Save updated caches to disk
        if deleted_files:  # Only save if we actually removed something
            log.info(
                f"Removing deleted files from hashes and overview: {self.output_dir}"
            )
            save_file_hashes(self.hashes, self.output_dir)
            save_codebase_overview(self.overview, self.output_dir)

            log.info(
                f"Removed {len(deleted_files)} deleted files from cache: {deleted_files}"
            )

    def save_hashes(self, hashes: Dict[str, str]):
        """
        Save file hashes to disk and update internal cache.

        Args:
            hashes: File hashes to save
        """
        save_file_hashes(hashes, self.output_dir)
        self._hashes = hashes  # Update internal cache

    def clear_cache(self):
        """Clear internal cache, forcing reload on next access."""
        self._hashes = None
        self._overview = None

    def is_cache_empty(self) -> bool:
        """Check if cache is empty (first run)."""
        return len(self.hashes) == 0 and len(self.overview) == 0
