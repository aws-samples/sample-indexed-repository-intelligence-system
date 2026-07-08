# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Unit tests for file_utils - file operations and utilities.
"""

from pathlib import Path
from iris.file_system.file_utils import (
    collect_files,
    generate_tree_display,
    generate_hashes,
    hash_file_content,
    load_file_hashes,
    save_file_hashes,
    load_codebase_overview,
    save_codebase_overview,
    read_source,
)


class TestCollectFiles:
    """Test file collection functionality."""

    def test_collect_all_files(self, test_codebase):
        """Test collecting all files without ignore patterns."""
        files = collect_files(test_codebase, [])

        assert len(files) > 0
        assert "main.py" in files
        assert "utils.py" in files
        assert "README.md" in files
        assert "config.json" in files
        assert "lib/helper.py" in files

    def test_collect_with_ignore_patterns(self, test_codebase):
        """Test collecting files with ignore patterns."""
        # Create files to ignore
        (test_codebase / "test.pyc").write_text("compiled")
        (test_codebase / ".git").mkdir()
        (test_codebase / ".git" / "config").write_text("git config")

        ignore_patterns = ["*.pyc", ".git/"]
        files = collect_files(test_codebase, ignore_patterns)

        # Should not include ignored files
        assert not any("test.pyc" in f for f in files)
        assert not any(".git" in f for f in files)
        # Should include regular files
        assert "main.py" in files
        assert "utils.py" in files

    def test_collect_empty_directory(self, temp_dir):
        """Test collecting files from empty directory."""
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()

        files = collect_files(empty_dir, [])
        assert files == []


class TestGenerateTreeDisplay:
    """Test tree display generation."""

    def test_generate_tree_basic(self, test_codebase):
        """Test basic tree generation."""
        tree = generate_tree_display(test_codebase, [])

        assert len(tree) > 0
        assert "main.py" in tree
        assert "utils.py" in tree
        assert "lib/" in tree or "lib" in tree
        assert "helper.py" in tree

    def test_generate_tree_with_ignore(self, test_codebase):
        """Test tree generation with ignore patterns."""
        # Create files to ignore
        (test_codebase / "ignored.pyc").write_text("ignored")

        tree = generate_tree_display(test_codebase, ["*.pyc"])

        assert "ignored.pyc" not in tree
        assert "main.py" in tree


class TestGenerateHashes:
    """Test hash generation functionality."""

    def test_generate_hashes_basic(self, test_codebase):
        """Test basic hash generation."""
        files = ["main.py", "utils.py", "README.md"]
        hashes = generate_hashes(test_codebase, files)

        assert len(hashes) == 3
        assert "main.py" in hashes
        assert "utils.py" in hashes
        assert "README.md" in hashes

        # Hashes should be non-empty strings
        for file_hash in hashes.values():
            assert isinstance(file_hash, str)
            assert len(file_hash) > 0

    def test_generate_hashes_nonexistent_file(self, test_codebase):
        """Test hash generation with nonexistent file."""
        files = ["main.py", "nonexistent.py"]
        hashes = generate_hashes(test_codebase, files)

        # Should only include existing files
        assert "main.py" in hashes
        assert "nonexistent.py" not in hashes

    def test_hash_consistency(self, test_codebase):
        """Test that same file produces same hash."""
        hash1 = hash_file_content(test_codebase / "main.py")
        hash2 = hash_file_content(test_codebase / "main.py")

        assert hash1 == hash2
        assert len(hash1) > 0

    def test_hash_changes_with_content(self, test_codebase):
        """Test that hash changes when file content changes."""
        main_file = test_codebase / "main.py"

        # Get original hash
        original_hash = hash_file_content(main_file)

        # Modify file
        original_content = main_file.read_text()
        main_file.write_text(original_content + "\n# Modified")

        # Get new hash
        new_hash = hash_file_content(main_file)

        assert original_hash != new_hash


class TestFileHashPersistence:
    """Test saving and loading file hashes."""

    def test_save_and_load_hashes(self, temp_dir, sample_file_hashes):
        """Test saving and loading file hashes."""
        output_dir = temp_dir / "output"

        # Save hashes
        save_file_hashes(sample_file_hashes, output_dir)

        # Load hashes
        loaded_hashes = load_file_hashes(output_dir)

        assert loaded_hashes == sample_file_hashes

    def test_load_nonexistent_hashes(self, temp_dir):
        """Test loading hashes when file doesn't exist."""
        output_dir = temp_dir / "output"

        hashes = load_file_hashes(output_dir)
        assert hashes == {}

    def test_load_corrupted_hashes(self, temp_dir):
        """Test loading corrupted hash file."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Create corrupted hash file
        hash_file = output_dir / "file_hashes.json"
        hash_file.write_text("invalid json")

        hashes = load_file_hashes(output_dir)
        assert hashes == {}


class TestCodebaseOverviewPersistence:
    """Test saving and loading codebase overview."""

    def test_save_and_load_overview(self, temp_dir, sample_codebase_overview):
        """Test saving and loading codebase overview."""
        output_dir = temp_dir / "output"

        # Save overview
        save_codebase_overview(sample_codebase_overview, output_dir)

        # Load overview
        loaded_overview = load_codebase_overview(output_dir)

        assert loaded_overview == sample_codebase_overview

    def test_load_nonexistent_overview(self, temp_dir):
        """Test loading overview when file doesn't exist."""
        output_dir = temp_dir / "output"

        overview = load_codebase_overview(output_dir)
        assert overview == {}

    def test_save_creates_directory(self, temp_dir):
        """Test that save creates output directory if it doesn't exist."""
        output_dir = temp_dir / "nonexistent" / "output"
        overview = {"test.py": {"summary": "test"}}

        save_codebase_overview(overview, output_dir)

        # Directory should be created
        assert output_dir.exists()

        # File should be saved
        overview_file = output_dir / "codebase_overview.json"
        assert overview_file.exists()


class TestReadSource:
    """Test source file reading functionality."""

    def test_read_python_file(self, test_codebase):
        """Test reading a Python source file."""
        content = read_source(Path("main.py"), test_codebase)

        assert content is not None
        assert "def main():" in content
        assert "Hello, world!" in content

    def test_read_markdown_file(self, test_codebase):
        """Test reading a Markdown file."""
        content = read_source(Path("README.md"), test_codebase)

        assert content is not None
        assert "# Test Project" in content
        assert "Features" in content

    def test_read_json_file(self, test_codebase):
        """Test reading a JSON file."""
        content = read_source(Path("config.json"), test_codebase)

        assert content is not None
        assert "test_project" in content
        assert "version" in content

    def test_read_nonexistent_file(self, test_codebase):
        """Test reading nonexistent file returns None."""
        content = read_source(Path("nonexistent.py"), test_codebase)
        assert content is None

    def test_read_large_file_truncated(self, test_codebase):
        """Test that very large files are handled appropriately."""
        # Create a large file
        large_file = test_codebase / "large.py"
        large_content = "# Large file\n" * 10000  # Should be within limits
        large_file.write_text(large_content)

        content = read_source(Path("large.py"), test_codebase)

        # Should read successfully (not too large for our test)
        assert content is not None
        assert "# Large file" in content

    def test_read_binary_file_handled(self, test_codebase):
        """Test that binary files are handled gracefully."""
        # Create a binary file
        binary_file = test_codebase / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")

        content = read_source(Path("binary.bin"), test_codebase)

        # Should either return content or None, but not crash
        assert content is None or isinstance(content, str)
