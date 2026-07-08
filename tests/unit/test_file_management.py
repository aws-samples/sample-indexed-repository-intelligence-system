# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Unit tests for file_management - Pydantic models and file analysis logic.
"""

import pytest

from iris.file_system.file_management import (
    FilesToProcessResult,
    get_files_to_process,
)


class TestFilesToProcessResult:
    """Test the Pydantic model for file processing results."""

    def test_valid_result_creation(self):
        """Test creating a valid FilesToProcessResult."""
        result = FilesToProcessResult(
            has_changed=True,
            files_to_process=["file1.py", "file2.py"],
            change_details={
                "new_files": ["file1.py"],
                "modified_files": ["file2.py"],
                "deleted_files": [],
            },
            tree_display="test tree",
            tree_structure={},
            total_files=5,
        )

        assert result.has_changed
        assert result.files_to_process == ["file1.py", "file2.py"]
        assert result.change_details["new_files"] == ["file1.py"]
        assert result.tree_display == "test tree"
        assert result.total_files == 5

    def test_minimal_result_creation(self):
        """Test creating result with minimal required fields."""
        result = FilesToProcessResult(
            has_changed=False,
            files_to_process=[],
            change_details={},
            tree_display="",
            tree_structure={},
            total_files=0,
        )

        assert not result.has_changed
        assert result.files_to_process == []
        assert result.change_details == {}

    def test_result_serialization(self):
        """Test that result can be serialized to dict."""
        result = FilesToProcessResult(
            has_changed=True,
            files_to_process=["test.py"],
            change_details={"new_files": ["test.py"]},
            tree_display="tree",
            tree_structure={},
            total_files=1,
        )

        result_dict = result.model_dump()

        assert result_dict["has_changed"]
        assert result_dict["files_to_process"] == ["test.py"]
        assert result_dict["change_details"]["new_files"] == ["test.py"]


class TestGetFilesToProcess:
    """Test the get_files_to_process function with real file operations."""

    def test_first_run_all_files_new(self, test_codebase, temp_dir):
        """Test first run where all files are new."""
        output_dir = temp_dir / "output"
        ignore_patterns = ["*.pyc", "__pycache__/"]

        result = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        assert isinstance(result, FilesToProcessResult)
        assert result.has_changed
        assert len(result.files_to_process) > 0
        assert result.total_files > 0
        assert result.tree_display is not None

        # All files should be new on first run
        assert len(result.change_details["new_files"]) > 0
        assert len(result.change_details["deleted_files"]) == 0
        assert len(result.change_details["modified_files"]) == 0

    def test_same_result(self, test_codebase, temp_dir):
        """Test second run with no changes."""
        output_dir = temp_dir / "output"
        ignore_patterns = ["*.pyc", "__pycache__/"]

        # First run
        result1 = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        # Second run - no changes
        result2 = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        assert result1 == result2

    def test_file_modification_detected(self, test_codebase, temp_dir):
        """Test that file modifications are detected."""
        output_dir = temp_dir / "output"
        ignore_patterns = ["*.pyc", "__pycache__/"]

        # First run
        result1 = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        # Save the cache state after first run using the utility function
        from iris.file_system.file_utils import generate_hashes
        from iris.summarize.utils import (
            update_and_save_codebase_overview,
        )

        # Generate hashes for the current files and save them
        current_hashes = generate_hashes(test_codebase, result1.files_to_process)
        # Create dummy summaries for the files (Dict[str, dict] format)
        dummy_overviews = {
            file_path: {
                "summary": f"Summary for {file_path}",
                "purpose": f"Purpose of {file_path}",
                "key_functions": [],
            }
            for file_path in result1.files_to_process
        }

        update_and_save_codebase_overview(
            output_folder=output_dir,
            new_overviews=dummy_overviews,
            file_hashes=current_hashes,
        )

        # Modify a file
        main_file = test_codebase / "main.py"
        original_content = main_file.read_text()
        main_file.write_text(original_content + "\n# Modified")

        # Second run - should detect modification
        result2 = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        assert result2.has_changed
        assert len(result2.files_to_process) > 0
        assert "main.py" in result2.change_details["modified_files"]

    def test_new_file_detected(self, test_codebase, temp_dir):
        """Test that new files are detected."""
        output_dir = temp_dir / "output"
        ignore_patterns = ["*.pyc", "__pycache__/"]

        # First run
        get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        # Add a new file
        new_file = test_codebase / "new_file.py"
        new_file.write_text("# New file")

        # Second run - should detect new file
        result2 = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        assert result2.has_changed
        assert len(result2.files_to_process) > 0
        assert "new_file.py" in result2.change_details["new_files"]

    def test_deleted_file_detected(self, test_codebase, temp_dir):
        """Test that deleted files are detected and cleaned up."""
        output_dir = temp_dir / "output"
        ignore_patterns = ["*.pyc", "__pycache__/"]

        # First run
        result1 = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        # Save the cache state after first run using the utility function
        from iris.file_system.file_utils import generate_hashes
        from iris.summarize.utils import (
            update_and_save_codebase_overview,
        )

        # Generate hashes for the current files and save them
        current_hashes = generate_hashes(test_codebase, result1.files_to_process)
        # Create dummy summaries for the files (Dict[str, dict] format)
        dummy_overviews = {
            file_path: {
                "summary": f"Summary for {file_path}",
                "purpose": f"Purpose of {file_path}",
                "key_functions": [],
            }
            for file_path in result1.files_to_process
        }

        update_and_save_codebase_overview(
            output_folder=output_dir,
            new_overviews=dummy_overviews,
            file_hashes=current_hashes,
        )

        # Delete a file
        utils_file = test_codebase / "utils.py"
        utils_file.unlink()

        # Second run - should detect deletion
        result2 = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        assert result2.has_changed
        assert "utils.py" in result2.change_details["deleted_files"]

    def test_ignore_patterns_respected(self, test_codebase, temp_dir):
        """Test that ignore patterns are respected."""
        output_dir = temp_dir / "output"

        # Create files that should be ignored
        (test_codebase / "test.pyc").write_text("compiled")
        (test_codebase / "__pycache__").mkdir()
        (test_codebase / "__pycache__" / "test.pyc").write_text("cached")

        ignore_patterns = ["*.pyc", "__pycache__/"]

        result = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        # Ignored files should not appear in results
        all_files = result.change_details["new_files"]
        assert not any("test.pyc" in f for f in all_files)
        assert not any("__pycache__" in f for f in all_files)

    def test_tree_display_generated(self, test_codebase, temp_dir):
        """Test that tree display is generated."""
        output_dir = temp_dir / "output"
        ignore_patterns = ["*.pyc", "__pycache__/"]

        result = get_files_to_process(
            codebase_dir=test_codebase,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
        )

        assert result.tree_display is not None
        assert len(result.tree_display) > 0
        # Should contain some of our test files
        assert "main.py" in result.tree_display
        assert "utils.py" in result.tree_display

    def test_error_handling_invalid_codebase(self, temp_dir):
        """Test error handling for invalid codebase directory."""
        invalid_codebase = temp_dir / "nonexistent"
        output_dir = temp_dir / "output"
        ignore_patterns = []

        with pytest.raises(RuntimeError, match="Failed to analyze files"):
            get_files_to_process(
                codebase_dir=invalid_codebase,
                output_dir=output_dir,
                ignore_patterns=ignore_patterns,
            )
