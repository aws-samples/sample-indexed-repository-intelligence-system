# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Unit tests for CodebaseCacheManager - pure logic testing.
"""

from iris.file_system.cache_manager import CodebaseCacheManager


class TestCodebaseCacheManager:
    """Test the cache manager functionality."""

    def test_empty_cache_initialization(self, output_dir):
        """Test cache manager with empty cache."""
        cache = CodebaseCacheManager(output_dir)

        # Should return empty dicts for new cache
        assert cache.hashes == {}
        assert cache.overview == {}
        assert cache.is_cache_empty()

    def test_has_changed_with_empty_cache(self, output_dir):
        """Test change detection with empty existing cache."""
        cache = CodebaseCacheManager(output_dir)

        current_hashes = {"file1.py": "hash1", "file2.py": "hash2"}

        result = cache.has_changed(current_hashes)

        assert result["has_changed"]
        assert result["new_files"] == ["file1.py", "file2.py"]
        assert result["deleted_files"] == []
        assert result["modified_files"] == []
        assert result["changed_files"] == ["file1.py", "file2.py"]

    def test_has_changed_no_changes(self, output_dir, sample_file_hashes):
        """Test change detection when no files have changed."""
        cache = CodebaseCacheManager(output_dir)

        # Set up existing cache
        cache._hashes = sample_file_hashes.copy()
        cache._overview = {"main.py": {}, "utils.py": {}, "README.md": {}}

        # Same hashes - no changes
        result = cache.has_changed(sample_file_hashes)

        assert not result["has_changed"]  # Should be False when no changes
        assert result["new_files"] == []
        assert result["deleted_files"] == []
        assert result["modified_files"] == []
        assert result["changed_files"] == []

    def test_has_changed_with_new_files(self, output_dir, sample_file_hashes):
        """Test change detection with new files."""
        cache = CodebaseCacheManager(output_dir)

        # Set up existing cache with fewer files
        existing_hashes = {"main.py": "abc123"}
        cache._hashes = existing_hashes
        cache._overview = {"main.py": {}}

        result = cache.has_changed(sample_file_hashes)

        assert result["has_changed"]
        assert set(result["new_files"]) == {"utils.py", "README.md"}
        assert result["deleted_files"] == []
        assert result["modified_files"] == []
        assert set(result["changed_files"]) == {"utils.py", "README.md"}

    def test_has_changed_with_deleted_files(self, output_dir):
        """Test change detection with deleted files."""
        cache = CodebaseCacheManager(output_dir)

        # Set up existing cache with more files
        existing_hashes = {
            "main.py": "abc123",
            "utils.py": "def456",
            "deleted.py": "xyz789",
        }
        cache._hashes = existing_hashes
        cache._overview = {"main.py": {}, "utils.py": {}, "deleted.py": {}}

        current_hashes = {"main.py": "abc123", "utils.py": "def456"}

        result = cache.has_changed(current_hashes)

        assert result["has_changed"]
        assert result["new_files"] == []
        assert result["deleted_files"] == ["deleted.py"]
        assert result["modified_files"] == []
        assert result["changed_files"] == []

    def test_has_changed_with_modified_files(self, output_dir):
        """Test change detection with modified files."""
        cache = CodebaseCacheManager(output_dir)

        # Set up existing cache
        existing_hashes = {"main.py": "abc123", "utils.py": "def456"}
        cache._hashes = existing_hashes
        cache._overview = {"main.py": {}, "utils.py": {}}

        # Modified file has different hash
        current_hashes = {"main.py": "abc123", "utils.py": "modified_hash"}

        result = cache.has_changed(current_hashes)

        assert result["has_changed"]
        assert result["new_files"] == []
        assert result["deleted_files"] == []
        assert result["modified_files"] == ["utils.py"]
        assert result["changed_files"] == ["utils.py"]

    def test_has_changed_mixed_changes(self, output_dir):
        """Test change detection with mixed changes."""
        cache = CodebaseCacheManager(output_dir)

        # Set up existing cache
        existing_hashes = {
            "main.py": "abc123",
            "utils.py": "def456",
            "deleted.py": "xyz789",
        }
        cache._hashes = existing_hashes
        cache._overview = {"main.py": {}, "utils.py": {}, "deleted.py": {}}

        # New file, modified file, deleted file
        current_hashes = {
            "main.py": "abc123",
            "utils.py": "modified_hash",
            "new.py": "new_hash",
        }

        result = cache.has_changed(current_hashes)

        assert result["has_changed"]
        assert result["new_files"] == ["new.py"]
        assert result["deleted_files"] == ["deleted.py"]
        assert result["modified_files"] == ["utils.py"]
        assert set(result["changed_files"]) == {"new.py", "utils.py"}

    def test_has_changed_with_orphaned_hash(self, output_dir):
        """A hash with no overview entry must not crash change detection.

        Regression: cleanup prunes the orphan from self.hashes, so comparing
        against a pre-cleanup key snapshot raised KeyError. The file still
        exists on disk, so it has to come back as new and be re-summarized.
        """
        cache = CodebaseCacheManager(output_dir)

        cache._hashes = {"main.py": "abc123", "orphaned.py": "xyz789"}
        cache._overview = {"main.py": {"summary": "main"}}  # orphaned.py missing

        current_hashes = {"main.py": "abc123", "orphaned.py": "xyz789"}

        result = cache.has_changed(current_hashes)

        assert result["new_files"] == ["orphaned.py"]
        assert result["modified_files"] == []
        assert result["deleted_files"] == []
        assert result["changed_files"] == ["orphaned.py"]
        assert result["has_changed"]

    def test_has_changed_with_empty_overview(self, output_dir):
        """A corrupt/unreadable overview reduces to a full reindex, not a crash.

        Regression: load_codebase_overview returns {} for a corrupt file, which
        made every hashed path an orphan and tripped the KeyError above.
        """
        cache = CodebaseCacheManager(output_dir)

        cache._hashes = {"main.py": "abc123", "utils.py": "def456"}
        cache._overview = {}

        current_hashes = {"main.py": "abc123", "utils.py": "def456"}

        result = cache.has_changed(current_hashes)

        assert set(result["new_files"]) == {"main.py", "utils.py"}
        assert result["modified_files"] == []
        assert set(result["changed_files"]) == {"main.py", "utils.py"}
        assert result["has_changed"]

    def test_remove_deleted_files_from_cache(self, output_dir):
        """Test removal of deleted files from cache."""
        cache = CodebaseCacheManager(output_dir)

        # Set up cache with files
        cache._hashes = {
            "main.py": "abc123",
            "utils.py": "def456",
            "deleted.py": "xyz789",
        }
        cache._overview = {
            "main.py": {"summary": "main"},
            "utils.py": {"summary": "utils"},
            "deleted.py": {"summary": "deleted"},
        }

        # Remove deleted files
        deleted_files = ["deleted.py"]
        cache.remove_deleted_files_from_cache(deleted_files)

        # Check files were removed
        assert "deleted.py" not in cache._hashes
        assert "deleted.py" not in cache._overview
        assert "main.py" in cache._hashes
        assert "utils.py" in cache._hashes

    def test_get_invalid_cache_entries(self, output_dir):
        """Test detection of invalid cache entries."""
        cache = CodebaseCacheManager(output_dir)

        # Set up cache with inconsistencies
        cache._hashes = {
            "main.py": "abc123",
            "utils.py": "def456",
            "orphaned.py": "xyz789",  # Has hash but no overview
        }
        cache._overview = {
            "main.py": {"summary": "main"},
            "utils.py": None,  # Invalid overview entry
            # orphaned.py missing from overview
        }

        invalid_files = cache.get_invalid_cache_entries()

        assert set(invalid_files) == {"orphaned.py", "utils.py"}

    def test_get_files_to_process(self, output_dir):
        """Test getting files that need processing."""
        cache = CodebaseCacheManager(output_dir)

        # Set up cache
        cache._hashes = {"main.py": "abc123"}
        cache._overview = {"main.py": None}  # Corrupt entry

        current_hashes = {
            "main.py": "modified_hash",  # Modified
            "new.py": "new_hash",  # New
        }

        files_to_process = cache.get_files_to_process(current_hashes)

        # Should include new, modified, and corrupt files
        assert set(files_to_process) == {"main.py", "new.py"}

    def test_save_hashes(self, output_dir):
        """Test saving hashes updates internal cache."""
        cache = CodebaseCacheManager(output_dir)

        new_hashes = {"file1.py": "hash1"}
        cache.save_hashes(new_hashes)

        assert cache._hashes == new_hashes

    def test_clear_cache(self, output_dir):
        """Test clearing internal cache."""
        cache = CodebaseCacheManager(output_dir)

        # Set up cache
        cache._hashes = {"file1.py": "hash1"}
        cache._overview = {"file1.py": {}}

        cache.clear_cache()

        assert cache._hashes is None
        assert cache._overview is None
