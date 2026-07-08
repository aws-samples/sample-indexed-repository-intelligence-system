# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Integration tests for file_summarizer - real Amazon Bedrock calls for file summarization.
"""

import pytest
from pathlib import Path
from iris.summarize.file_summarizer import summarize_files


class TestSummarizeFiles:
    """Integration tests for file summarization with real Amazon Bedrock calls."""

    def test_summarize_single_file(self, test_codebase, output_dir):
        """Test summarizing a single file."""
        files_to_summarize = ["main.py"]

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        assert isinstance(results, dict)
        assert "main.py" in results

        # Check result structure
        result = results["main.py"]
        assert isinstance(result, dict)
        # Should have typical summary fields
        assert len(result) > 0

    def test_summarize_multiple_files(self, test_codebase, output_dir):
        """Test summarizing multiple files."""
        files_to_summarize = ["main.py", "utils.py", "README.md"]

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        assert isinstance(results, dict)
        assert len(results) == 3

        for file_path in files_to_summarize:
            assert file_path in results
            assert isinstance(results[file_path], dict)
            assert len(results[file_path]) > 0

    def test_summarize_with_additional_context(self, test_codebase, output_dir):
        """Test summarizing files with additional context."""
        files_to_summarize = ["main.py"]
        additional_context = (
            "This is a test project for demonstrating IRIS functionality."
        )

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context=additional_context,
        )

        assert isinstance(results, dict)
        assert "main.py" in results

        # Result should be influenced by additional context
        result = results["main.py"]
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_summarize_different_file_types(self, test_codebase, output_dir):
        """Test summarizing different types of files."""
        files_to_summarize = ["main.py", "utils.py", "README.md", "config.json"]

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        assert isinstance(results, dict)

        # Should handle different file types
        for file_path in files_to_summarize:
            assert file_path in results
            result = results[file_path]
            assert isinstance(result, dict)
            assert len(result) > 0

    def test_summarize_subdirectory_files(self, test_codebase, output_dir):
        """Test summarizing files in subdirectories."""
        files_to_summarize = ["lib/helper.py"]

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        assert isinstance(results, dict)
        assert "lib/helper.py" in results

        result = results["lib/helper.py"]
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_summarize_empty_file_list(self, test_codebase, output_dir):
        """Test summarizing empty file list."""
        files_to_summarize = []

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        assert isinstance(results, dict)
        assert len(results) == 0

    def test_summarize_nonexistent_file(self, test_codebase, output_dir):
        """Test summarizing nonexistent file."""
        files_to_summarize = ["nonexistent.py"]

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        assert isinstance(results, dict)
        # Should handle nonexistent files gracefully
        # Either skip them or handle the error

    def test_summarize_creates_output_files(self, test_codebase, output_dir):
        """Test that summarization creates expected output files."""
        files_to_summarize = ["main.py"]

        summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        # Should create codebase overview file
        overview_file = Path(output_dir) / "codebase_overview.json"
        assert overview_file.exists()

        # Should create file hashes
        hashes_file = Path(output_dir) / "file_hashes.json"
        assert hashes_file.exists()

    def test_summarize_updates_existing_overview(self, test_codebase, output_dir):
        """Test that summarization updates existing overview."""
        # First summarization
        files_to_summarize = ["main.py"]

        summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        # Second summarization with additional file
        files_to_summarize = ["utils.py"]

        summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        # Should have results for both files in the overview
        overview_file = Path(output_dir) / "codebase_overview.json"
        assert overview_file.exists()

        import json

        with open(overview_file) as f:
            overview = json.load(f)

        # Should contain both files
        assert "main.py" in overview
        assert "utils.py" in overview

    @pytest.mark.slow
    def test_summarize_performance(self, test_codebase, output_dir):
        """Test that summarization completes in reasonable time."""
        import time

        files_to_summarize = ["main.py", "utils.py"]

        start_time = time.time()
        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )
        end_time = time.time()

        # Should complete within reasonable time (adjust as needed)
        assert end_time - start_time < 120  # 2 minutes max for 2 files
        assert isinstance(results, dict)
        assert len(results) == 2

    def test_summarize_parallel_processing(self, test_codebase, output_dir):
        """Test that parallel processing works correctly."""
        # Use multiple files to test parallel processing
        files_to_summarize = ["main.py", "utils.py", "README.md", "lib/helper.py"]

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        assert isinstance(results, dict)
        assert len(results) == len(files_to_summarize)

        # All files should be processed
        for file_path in files_to_summarize:
            assert file_path in results
            assert isinstance(results[file_path], dict)

    def test_summarize_with_custom_models(self, test_codebase, output_dir, test_config):
        """Test summarization with custom model configuration."""
        files_to_summarize = ["main.py"]
        models = test_config["model_configuration"]["file_summarizer"]["models"]

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            models=models,
            additional_context="",
        )

        assert isinstance(results, dict)
        assert "main.py" in results

        result = results["main.py"]
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_summarize_result_structure(self, test_codebase, output_dir):
        """Test that summarization results have expected structure."""
        files_to_summarize = ["main.py"]

        results = summarize_files(
            files_to_summarize=files_to_summarize,
            codebase_dir=test_codebase,
            output_dir=output_dir,
            additional_context="",
        )

        assert isinstance(results, dict)
        assert "main.py" in results

        result = results["main.py"]
        assert isinstance(result, dict)

        # Should have some expected fields (exact structure depends on prompts)
        # At minimum should be a non-empty dict
        assert len(result) > 0

        # Values should be meaningful (not empty strings)
        for key, value in result.items():
            if isinstance(value, str):
                assert len(value.strip()) > 0
