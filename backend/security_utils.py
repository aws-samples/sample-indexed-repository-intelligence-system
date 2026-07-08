# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Security utilities for sanitizing user-controlled input in logs and responses.

This module provides functions to prevent log injection attacks by sanitizing
error messages and other user-controlled content before logging or returning
to clients.
"""

import re
from typing import Any


def sanitize_for_log(value: Any, max_length: int = 200) -> str:
    """
    Sanitize a value for safe logging by removing control characters and limiting length.

    This prevents log injection attacks where malicious input could:
    - Inject fake log entries
    - Break log parsing
    - Inject ANSI escape codes
    - Create misleading log entries

    Args:
        value: The value to sanitize (will be converted to string)
        max_length: Maximum length of the sanitized string (default: 200)

    Returns:
        str: Sanitized string safe for logging

    Example:
        >>> sanitize_for_log("Error: \n[FAKE] Admin logged in\nReal error")
        'Error: [NEWLINE][FAKE] Admin logged in[NEWLINE]Real error'
    """
    # Convert to string
    text = str(value)

    # Replace newlines and carriage returns to prevent log injection
    text = text.replace("\n", "[NEWLINE]")
    text = text.replace("\r", "[CR]")

    # Remove or replace other control characters (ASCII 0-31 except tab)
    # Keep tab (0x09) as it's commonly used in logs
    text = re.sub(r"[\x00-\x08\x0B-\x1F\x7F]", "[CTRL]", text)

    # Remove ANSI escape codes that could manipulate terminal output
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "[ANSI]", text)

    # Truncate to max length to prevent log flooding
    if len(text) > max_length:
        text = text[:max_length] + "...[truncated]"

    return text


def sanitize_error_for_client(error: Exception, include_details: bool = False) -> str:
    """
    Sanitize an exception for safe return to client.

    This provides a generic error message by default, with option to include
    sanitized details for debugging (should only be enabled in development).

    Args:
        error: The exception to sanitize
        include_details: Whether to include sanitized error details (default: False)

    Returns:
        str: Safe error message for client

    Example:
        >>> sanitize_error_for_client(ValueError("Bad input"))
        'An error occurred while processing your request'
    """
    if include_details:
        # Sanitize the error message before including it
        error_msg = sanitize_for_log(str(error), max_length=100)
        return f"Error: {error_msg}"
    else:
        # Generic message - don't leak implementation details
        return "An error occurred while processing your request"


def get_safe_error_type(error: Exception) -> str:
    """
    Get a safe representation of the error type for logging.

    Args:
        error: The exception

    Returns:
        str: Safe error type name
    """
    return error.__class__.__name__
