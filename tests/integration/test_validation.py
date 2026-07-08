# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Integration tests for validation module.
"""

import pytest
from iris.utils.validation import (
    ModelAccessError,
    CredentialsNotFound,
    validate_llm_model_access,
    check_model_availability,
)


@pytest.mark.integration
def test_validate_real_models():
    """Test validation with real AWS calls using common models."""
    models = [
        {
            "region": "us-west-2",
            "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        },
        {
            "region": "us-east-1",
            "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        },
    ]

    try:
        validate_llm_model_access(models)

    except ModelAccessError as e:
        pytest.skip(f"Models not accessible: {e.missing_models}")

    except CredentialsNotFound as e:
        pytest.fail(f"Credentials problem: {e}")


@pytest.mark.integration
def test_validate_fake_model():
    """Test validation with a model that doesn't exist."""
    models = [{"region": "us-west-2", "model_id": "fake.model.that.does.not.exist"}]

    try:
        with pytest.raises(ModelAccessError) as exc_info:
            validate_llm_model_access(models)

        assert len(exc_info.value.missing_models) == 1

    except CredentialsNotFound as e:
        pytest.fail(f"Credentials problem: {e}")


@pytest.mark.integration
def test_single_model_check():
    """Test checking a single model directly."""
    try:
        result = check_model_availability(
            "us-west-2", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        assert isinstance(result, bool)

    except CredentialsNotFound as e:
        pytest.fail(f"Credentials problem: {e}")
