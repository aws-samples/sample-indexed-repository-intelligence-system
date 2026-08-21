"""
Unit tests for ArtifactCacheManager - hash-based change detection for artifacts.
"""

from iris.artifacts.artifact_cache_manager import ArtifactCacheManager


class TestArtifactCacheManager:
    """Test the artifact cache manager functionality."""

    def test_empty_cache_initialization(self, output_dir):
        """Test cache manager with empty cache."""
        cache = ArtifactCacheManager(output_dir)

        assert cache.hashes == {}
        assert cache.overview == {}
        assert cache.is_cache_empty()

    def test_has_changed_with_empty_cache(self, output_dir):
        """Test change detection with empty existing cache."""
        cache = ArtifactCacheManager(output_dir)

        current_hashes = {
            "during-project/presentations/week1.pptx": "hash1",
            "pre-project/readouts/kickoff.docx": "hash2",
        }

        result = cache.has_changed(current_hashes)

        assert result["has_changed"]
        assert set(result["new_files"]) == set(current_hashes.keys())
        assert result["deleted_files"] == []
        assert result["modified_files"] == []

    def test_has_changed_no_changes(self, output_dir):
        """Test change detection when no files have changed."""
        cache = ArtifactCacheManager(output_dir)

        hashes = {
            "presentations/week1.pptx": "hash1",
            "readouts/kickoff.docx": "hash2",
        }
        cache._hashes = hashes.copy()
        cache._overview = {k: {"purpose": "test"} for k in hashes}

        result = cache.has_changed(hashes)

        assert not result["has_changed"]
        assert result["new_files"] == []
        assert result["deleted_files"] == []
        assert result["modified_files"] == []
        assert result["changed_files"] == []

    def test_has_changed_with_new_files(self, output_dir):
        """Test change detection with new files added."""
        cache = ArtifactCacheManager(output_dir)

        cache._hashes = {"existing.pptx": "hash1"}
        cache._overview = {"existing.pptx": {"purpose": "test"}}

        current = {"existing.pptx": "hash1", "new.docx": "hash2"}
        result = cache.has_changed(current)

        assert result["has_changed"]
        assert result["new_files"] == ["new.docx"]
        assert result["modified_files"] == []

    def test_has_changed_with_deleted_files(self, output_dir):
        """Test change detection with deleted files."""
        cache = ArtifactCacheManager(output_dir)

        cache._hashes = {"keep.pptx": "hash1", "deleted.docx": "hash2"}
        cache._overview = {
            "keep.pptx": {"purpose": "test"},
            "deleted.docx": {"purpose": "test"},
        }

        current = {"keep.pptx": "hash1"}
        result = cache.has_changed(current)

        assert result["has_changed"]
        assert result["deleted_files"] == ["deleted.docx"]
        assert "deleted.docx" not in cache.hashes

    def test_has_changed_with_modified_files(self, output_dir):
        """Test change detection with modified files."""
        cache = ArtifactCacheManager(output_dir)

        cache._hashes = {"file.pptx": "old_hash"}
        cache._overview = {"file.pptx": {"purpose": "test"}}

        current = {"file.pptx": "new_hash"}
        result = cache.has_changed(current)

        assert result["has_changed"]
        assert result["modified_files"] == ["file.pptx"]
        assert result["changed_files"] == ["file.pptx"]

    def test_has_changed_mixed(self, output_dir):
        """Test change detection with mixed changes."""
        cache = ArtifactCacheManager(output_dir)

        cache._hashes = {
            "unchanged.pptx": "hash1",
            "modified.docx": "old_hash",
            "deleted.pdf": "hash3",
        }
        cache._overview = {
            "unchanged.pptx": {"purpose": "test"},
            "modified.docx": {"purpose": "test"},
            "deleted.pdf": {"purpose": "test"},
        }

        current = {
            "unchanged.pptx": "hash1",
            "modified.docx": "new_hash",
            "new.xlsx": "hash4",
        }
        result = cache.has_changed(current)

        assert result["has_changed"]
        assert result["new_files"] == ["new.xlsx"]
        assert result["modified_files"] == ["modified.docx"]
        assert result["deleted_files"] == ["deleted.pdf"]

    def test_save_and_load_hashes(self, output_dir):
        """Test saving and loading hashes from disk."""
        cache = ArtifactCacheManager(output_dir)

        hashes = {"file1.pptx": "hash1", "file2.docx": "hash2"}
        cache.save_hashes(hashes)

        # Create a new cache instance and load
        cache2 = ArtifactCacheManager(output_dir)
        cache2.load_state()

        assert cache2.hashes == hashes

    def test_save_and_load_overview(self, output_dir):
        """Test saving and loading overview from disk."""
        cache = ArtifactCacheManager(output_dir)

        overview = {
            "file1.pptx": {
                "purpose": "Test presentation",
                "source_material_type": "presentations",
                "project_phase": "during-project",
                "file_format": "pptx",
                "key_topics": ["topic1"],
                "related_artifacts": [],
                "summary": "A test.",
            }
        }
        cache.save_overview(overview)

        cache2 = ArtifactCacheManager(output_dir)
        cache2.load_state()

        assert "file1.pptx" in cache2.overview
        assert cache2.overview["file1.pptx"]["purpose"] == "Test presentation"

    def test_corrupted_json_handled_gracefully(self, output_dir):
        """Test that corrupted cache files are handled gracefully."""
        # Write corrupted JSON
        (output_dir / "artifact_file_hashes.json").write_text("not valid json")
        (output_dir / "artifact_overview.json").write_text("{broken")

        cache = ArtifactCacheManager(output_dir)
        cache.load_state()

        assert cache.hashes == {}
        assert cache.overview == {}

    def test_needs_kb_rebuild_after_deletion(self, output_dir):
        """Test KB rebuild flag is set after artifact deletion."""
        cache = ArtifactCacheManager(output_dir)

        cache._hashes = {"file.pptx": "hash1"}
        cache._overview = {"file.pptx": {"purpose": "test"}}

        assert not cache.needs_kb_rebuild()

        cache.remove_deleted_artifacts(["file.pptx"])

        assert cache.needs_kb_rebuild()
        assert "file.pptx" not in cache.hashes
        assert "file.pptx" not in cache.overview

    def test_get_invalid_cache_entries(self, output_dir):
        """Test detection of invalid/orphaned cache entries."""
        cache = ArtifactCacheManager(output_dir)

        cache._hashes = {
            "valid.pptx": "hash1",
            "orphaned.pptx": "hash2",  # hash but no overview
        }
        cache._overview = {
            "valid.pptx": {
                "purpose": "test",
                "source_material_type": "presentations",
                "project_phase": "during-project",
                "file_format": "pptx",
                "key_topics": [],
                "related_artifacts": [],
                "summary": "",
            },
            "invalid.pptx": None,  # invalid entry
        }

        invalid = cache._get_invalid_cache_entries()

        assert "orphaned.pptx" in invalid
