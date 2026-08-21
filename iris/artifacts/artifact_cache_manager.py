# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Artifact cache manager for hash-based change detection.

Mirrors the :class:`CodebaseCacheManager` pattern for artifact-specific
files (``artifact_file_hashes.json`` and ``artifact_overview.json``).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import ArtifactOverview

logger = logging.getLogger(__name__)

ARTIFACT_HASHES_FILE = "artifact_file_hashes.json"
ARTIFACT_OVERVIEW_FILE = "artifact_overview.json"


class ArtifactCacheManager:
    """Manages artifact cache files for incremental indexing.

    Provides change detection, cache validation, and cleanup operations
    analogous to :class:`CodebaseCacheManager`.
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self._hashes: Optional[Dict[str, str]] = None
        self._overview: Optional[Dict[str, dict]] = None
        self._needs_kb_rebuild: bool = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_state(self) -> None:
        """Load hashes and overview from disk.

        Handles corrupted JSON gracefully — treats as empty cache.
        Validates overview entries on load, logging warnings for
        non-conforming entries.
        """
        self._hashes = self._load_json(ARTIFACT_HASHES_FILE, default={})
        raw_overview = self._load_json(ARTIFACT_OVERVIEW_FILE, default={})

        # Validate overview entries
        self._overview = {}
        for path, entry in raw_overview.items():
            try:
                ArtifactOverview.from_dict(entry)
                self._overview[path] = entry
            except (KeyError, TypeError) as exc:
                logger.warning(
                    "Invalid artifact overview entry for '%s': %s — skipped",
                    path,
                    exc,
                )

    def _load_json(self, filename: str, default: Any = None) -> Any:
        """Load a JSON file from output_dir, returning *default* on failure."""
        path = self.output_dir / filename
        if not path.exists():
            return default if default is not None else {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Corrupted cache file %s: %s — treating as empty.", path, exc
            )
            return default if default is not None else {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def hashes(self) -> Dict[str, str]:
        """Artifact file hashes, loading from disk if needed."""
        if self._hashes is None:
            self.load_state()
        if self._hashes is None:
            raise ValueError("Could not load artifact hashes")
        return self._hashes

    @property
    def overview(self) -> Dict[str, dict]:
        """Artifact overview, loading from disk if needed."""
        if self._overview is None:
            self.load_state()
        if self._overview is None:
            raise ValueError("Could not load artifact overview")
        return self._overview

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    def has_changed(self, current_hashes: Dict[str, str]) -> Dict[str, Any]:
        """Compare *current_hashes* against stored hashes.

        Returns a dict with:
        - ``has_changed`` (bool)
        - ``new_files`` (list)
        - ``modified_files`` (list)
        - ``deleted_files`` (list)
        - ``changed_files`` (list) — new + modified (excludes deleted)
        """
        if not self.hashes:
            return {
                "has_changed": bool(current_hashes),
                "changed_files": list(current_hashes.keys()),
                "new_files": list(current_hashes.keys()),
                "deleted_files": [],
                "modified_files": [],
            }

        current_keys = set(current_hashes.keys())
        existing_keys = set(self.hashes.keys())
        overview_keys = set(self.overview.keys())

        new_files = list(current_keys - existing_keys)
        deleted_files = list(existing_keys - current_keys)

        # Orphaned overview entries
        orphaned = list(overview_keys - current_keys - set(deleted_files))
        # Hashes without overview (corruption)
        null_hashes = list(existing_keys - overview_keys)

        files_to_remove = set(deleted_files + orphaned + null_hashes)
        if files_to_remove:
            self.remove_deleted_artifacts(files_to_remove)
            if orphaned:
                logger.info("Cleaned up %d orphaned overview entries", len(orphaned))
            if null_hashes:
                logger.info("Cleaned up %d orphaned hash entries", len(null_hashes))

        # Recompute common after cleanup (removed entries are no longer in self.hashes)
        common = current_keys & set(self.hashes.keys())
        modified_files = [fp for fp in common if current_hashes[fp] != self.hashes[fp]]

        changed_files = new_files + modified_files
        has_any = bool(new_files or deleted_files or modified_files)

        return {
            "has_changed": has_any,
            "changed_files": changed_files,
            "new_files": new_files,
            "deleted_files": deleted_files,
            "modified_files": modified_files,
        }

    def get_files_to_process(self, current_hashes: Dict[str, str]) -> List[str]:
        """Return files needing indexing (new + modified + corrupted cache)."""
        changes = self.has_changed(current_hashes)
        corrupted = self._get_invalid_cache_entries()
        return list(set(changes["changed_files"]) | set(corrupted))

    def _get_invalid_cache_entries(self) -> List[str]:
        """Find hashed files missing or invalid in the overview."""
        invalid: set[str] = set()
        hashed = set(self.hashes.keys())
        overview_keys = set(self.overview.keys())

        # Hashes without overview
        invalid.update(hashed - overview_keys)

        # Invalid overview entries
        for fp, entry in self.overview.items():
            if not entry or not isinstance(entry, dict):
                invalid.add(fp)

        return list(invalid)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def remove_deleted_artifacts(self, deleted_files: set | list) -> None:
        """Remove *deleted_files* from hashes and overview, persist changes.

        Sets the KB rebuild flag so the orchestrator knows to regenerate
        ``knowledge_base.md``.
        """
        if not deleted_files:
            return

        for fp in deleted_files:
            self.hashes.pop(fp, None)
            self.overview.pop(fp, None)

        self._save_json(ARTIFACT_HASHES_FILE, self.hashes)
        self._save_json(ARTIFACT_OVERVIEW_FILE, self.overview)
        self._needs_kb_rebuild = True

        logger.info(
            "Removed %d deleted/orphaned artifacts from cache.", len(deleted_files)
        )

    def save_hashes(self, hashes: Dict[str, str]) -> None:
        """Persist artifact file hashes and update internal cache."""
        self._save_json(ARTIFACT_HASHES_FILE, hashes)
        self._hashes = hashes

    def save_overview(self, overview: Dict[str, dict]) -> None:
        """Persist artifact overview and update internal cache."""
        self._save_json(ARTIFACT_OVERVIEW_FILE, overview)
        self._overview = overview

    def needs_kb_rebuild(self) -> bool:
        """Whether the knowledge base needs rebuilding due to deletions."""
        return self._needs_kb_rebuild

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_json(self, filename: str, data: Any) -> None:
        """Write *data* as JSON to *filename* in output_dir."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / filename
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_cache_empty(self) -> bool:
        """Check if cache is empty (first run)."""
        return len(self.hashes) == 0 and len(self.overview) == 0
