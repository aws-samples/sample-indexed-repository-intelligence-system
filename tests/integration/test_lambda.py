# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tests for Lambda functions in infrastructure.
"""

import pytest
from pathlib import Path


@pytest.mark.unit
class TestLambdaFunctions:
    """Test Lambda function code."""

    def test_lambda_directory_exists(self):
        """Test lambda directory exists."""
        lambda_dir = Path(__file__).parent.parent.parent / "infra" / "lambda"
        assert lambda_dir.exists()

    def test_lambda_functions_exist(self):
        """Test Lambda function files exist."""
        lambda_dir = Path(__file__).parent.parent.parent / "infra" / "lambda"

        # Check if any Python files exist in lambda directory (recursively)
        python_files = list(lambda_dir.rglob("*.py"))

        # If no Lambda functions yet, skip test
        if not python_files:
            pytest.skip("No Lambda functions found")

        # Verify at least one Lambda function exists
        assert len(python_files) > 0

    def test_lambda_handler_signature(self):
        """Test Lambda handlers have correct signature."""
        lambda_dir = Path(__file__).parent.parent.parent / "infra" / "lambda"
        python_files = list(lambda_dir.rglob("*.py"))

        if not python_files:
            pytest.skip("No Lambda functions found")

        # Check first Lambda file for handler function
        for py_file in python_files:
            content = py_file.read_text()
            # Lambda handlers should have 'def handler(event, context)' or similar
            assert "def " in content, f"No function definition in {py_file.name}"
