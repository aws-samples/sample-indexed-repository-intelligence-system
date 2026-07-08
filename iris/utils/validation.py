# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Model access validation for Amazon Bedrock models.
"""

import urllib.parse
from typing import List, Tuple
import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


class ModelAccessError(Exception):
    """Exception raised when required Amazon Bedrock models are not accessible."""

    def __init__(self, missing_models: List[Tuple[str, str]]):
        self.missing_models = missing_models
        model_list = "\n".join(
            [f"  - {model_id} in {region}" for region, model_id in missing_models]
        )
        message = f"Missing access to required models:\n{model_list}\nEnable access in Amazon Bedrock console."
        super().__init__(message)


class CredentialsNotFound(Exception):
    """Exception raised when AWS credentials are not found or invalid."""

    pass


def normalize_model_id(model_id: str) -> str:
    """
    Remove region prefixes from model ID.

    Args:
        model_id: Original model ID that may have region prefix

    Returns:
        Model ID without region prefix
    """
    region_prefixes = ["us.", "eu.", "apac."]
    for prefix in region_prefixes:
        model_id = model_id.removeprefix(prefix)
    return model_id


def check_model_availability(region: str, model_id: str) -> bool:
    """
    Check if a specific model is available in a region.

    Args:
        region: AWS region name
        model_id: Amazon Bedrock model ID (will be normalized automatically)

    Returns:
        True if model is available, False otherwise

    Raises:
        CredentialsNotFound: If AWS credentials not found or invalid
        Exception: If API call fails for other reasons
    """
    # Get AWS credentials
    session = boto3.Session()
    credentials = session.get_credentials()

    if not credentials:
        raise CredentialsNotFound(
            "AWS credentials not found. Please configure AWS credentials."
        )

    # Normalize model ID
    normalized_model_id = normalize_model_id(model_id)

    # Make API call
    encoded_model_id = urllib.parse.quote(normalized_model_id)
    url = f"https://bedrock.{region}.amazonaws.com/foundation-model-availability/{encoded_model_id}"

    request = AWSRequest(method="GET", url=url)
    SigV4Auth(credentials, "bedrock", region).add_auth(request)

    response = requests.get(url, headers=dict(request.headers), timeout=60)

    if response.status_code == 200:
        return response.json()["entitlementAvailability"] == "AVAILABLE"
    elif response.status_code == 403:
        raise CredentialsNotFound(
            f"Invalid AWS credentials or insufficient permissions for {normalized_model_id} in {region}"
        )
    elif response.status_code == 400:
        # Model doesn't exist - treat as not accessible
        return False
    else:
        raise Exception(
            f"Failed to check model availability for {normalized_model_id} in {region}: {response.status_code} - {response.text}"
        )


def validate_llm_model_access(models: list[dict] | dict):
    """
    Validate access to a list of Amazon Bedrock models.

    Args:
        models: List of (region, model_id) tuples to validate

    Returns:
        List of (region, model_id) tuples for models without access

    Raises:
        CredentialsNotFound: If AWS credentials are invalid (fails fast)
        ModelAccessError: If any models are not accessible
    """
    if isinstance(models, dict):
        models = [models]

    missing_models = []

    for model in models:
        region = model["region"]
        model_id = model["model_id"]
        # Let credential errors bubble up immediately - don't hide them
        if not check_model_availability(region, model_id):
            missing_models.append((region, normalize_model_id(model_id)))

    if missing_models:
        raise ModelAccessError(missing_models)
