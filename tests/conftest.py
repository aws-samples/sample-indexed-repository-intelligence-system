# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Shared test fixtures and utilities for IRIS tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

# Conftest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def test_codebase(temp_dir):
    """Create a small test codebase with various file types."""
    codebase_dir = temp_dir / "test_codebase"
    codebase_dir.mkdir()

    # Create test files
    (codebase_dir / "main.py").write_text("""
def main():
    print("Hello, world!")
    return calculate_sum(1, 2)

def calculate_sum(a, b):
    return a + b

if __name__ == "__main__":
    main()
""")

    (codebase_dir / "utils.py").write_text("""
import os
from typing import List

def read_config(filename: str) -> dict:
    \"\"\"Read configuration from file.\"\"\"
    with open(filename, 'r') as f:
        return json.load(f)

def process_files(files: List[str]) -> int:
    \"\"\"Process a list of files and return count.\"\"\"
    return len([f for f in files if os.path.exists(f)])
""")

    (codebase_dir / "README.md").write_text("""
# Test Project

This is a test project for IRIS.

## Features
- Main function
- Utility functions
- Configuration handling
""")

    (codebase_dir / "config.json").write_text("""
{
    "name": "test_project",
    "version": "1.0.0",
    "debug": true
}
""")

    # Create subdirectory
    subdir = codebase_dir / "lib"
    subdir.mkdir()
    (subdir / "helper.py").write_text("""
def helper_function():
    \"\"\"A helper function in a subdirectory.\"\"\"
    return "helper"
""")

    return codebase_dir


@pytest.fixture
def test_config():
    """Provide test configuration."""
    return {
        "codebase_dir": "/test/codebase",
        "output_dir": ".iris_test_output",
        "ignore_patterns": ["*.pyc", "__pycache__/", ".git/", "*.tmp"],
        "context_window_size": 100000,
        "model_configuration": {
            "file_summarizer": {
                "models": [
                    {
                        "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                        "region": "us-west-2",
                    }
                ]
            },
        },
    }


@pytest.fixture
def output_dir(temp_dir):
    """Create output directory for tests."""
    output_path = temp_dir / "output"
    output_path.mkdir()
    return output_path


@pytest.fixture
def sample_file_hashes():
    """Sample file hashes for testing."""
    return {"main.py": "abc123", "utils.py": "def456", "README.md": "ghi789"}


@pytest.fixture
def sample_codebase_overview():
    """Sample codebase overview for testing."""
    return {
        "main.py": {
            "purpose": "Main entry point with hello world and sum calculation functions",
            "genai_system": "No",
            "has_bugs": "No bugs",
            "imported_files": [],
            "classes": {},
            "functions": {
                "main": "Main entry point function that prints hello world",
                "calculate_sum": "Function that calculates the sum of two numbers",
            },
            "file_type": "python",
        },
        "utils.py": {
            "purpose": "Utility functions for config and file processing operations",
            "genai_system": "No",
            "has_bugs": "No bugs",
            "imported_files": ["os", "typing"],
            "classes": {},
            "functions": {
                "read_config": "Function that reads configuration from files",
                "process_files": "Function that processes multiple files",
            },
            "file_type": "python",
        },
        "README.md": {
            "purpose": "Project documentation and setup instructions",
            "genai_system": "No",
            "has_bugs": "No bugs",
            "imported_files": [],
            "classes": {},
            "functions": {},
            "file_type": "markdown",
        },
    }
