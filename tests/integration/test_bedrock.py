# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tests for bedrock utility functions.
"""

import pytest
import boto3
from botocore.config import Config
from iris.utils.bedrock import call_bedrock


class TestCallBedrock:
    """Tests for call_bedrock function."""

    def test_call_bedrock_with_none_content_reproduces_bug(self):
        """Test that reproduces the actual bug when file content is 'None'."""
        # Create real bedrock client
        boto3_config = Config(
            region_name="us-west-2",
            read_timeout=300,
            retries={"mode": "standard", "max_attempts": 3},
        )
        bedrock_client = boto3.client("bedrock-runtime", config=boto3_config)

        # Simulate the exact scenario from file_summarizer when read_source returns None
        static_message = """
<task>
Analyze the given file and generate a codebase overview in JSON format.
</task>

<instructions>
1. The path of the file to be analyzed is provided in <file_path>...</file_path>.
2. The content of the file to analyzed is provided in <file_content>...</file_content>.
3. The output JSON should be wrapped in triple backticks (including the word `json`).
</instructions>
        """

        # This is what happens when read_source returns None
        none_str = None
        dynamic_message = f"""
<file_path>
test_file.py
</file_path>

<file_content>
{none_str}
</file_content>
        """

        system_message = "You are a helpful assistant that analyzes code files."
        model_id = (
            "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # Prompt caching model
        )

        # This should reproduce the ParamValidationError about cachePoint
        try:
            response = call_bedrock(
                static_message=static_message,
                dynamic_message=dynamic_message,
                system_message=system_message,
                model_id=model_id,
                bedrock_client=bedrock_client,
                maxTokens=32768,
            )

            # If we get here, the bug might be fixed or not reproducible
            print(f"Unexpected success: {response}")

        except Exception as e:
            # This should be the ParamValidationError we're trying to reproduce
            print(f"Error reproduced: {type(e).__name__}: {e}")

            # Check if it's the specific error we're looking for
            if "cachePoint" in str(e) and "Parameter validation failed" in str(e):
                pytest.fail(f"Bug reproduced! The error is: {e}")
            else:
                # Some other error - re-raise it
                raise

    def test_call_bedrock_with_empty_content(self):
        """Test call_bedrock with empty file content (should work fine)."""
        boto3_config = Config(
            region_name="us-west-2",
            read_timeout=300,
            retries={"mode": "standard", "max_attempts": 3},
        )
        bedrock_client = boto3.client("bedrock-runtime", config=boto3_config)

        static_message = """
<task>
Analyze the given file and generate a codebase overview in JSON format.
</task>
        """

        # Empty content (not "None" string)
        empty_str = ""
        dynamic_message = f"""
<file_path>
empty_file.py
</file_path>

<file_content>
{empty_str}
</file_content>
        """

        system_message = "You are a helpful assistant."
        model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

        # This should work fine
        response = call_bedrock(
            static_message=static_message,
            dynamic_message=dynamic_message,
            system_message=system_message,
            model_id=model_id,
            bedrock_client=bedrock_client,
            maxTokens=1000,
        )

        # Should get a valid response
        assert isinstance(response, str)
        assert len(response) > 0
