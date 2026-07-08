# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Public API for iris package.
Exposes codebase indexing and agentic chat functionality for external use.
"""

from .generate_context import generate_context
from .agentic_chat import cli_chat
from .utils.utils import (
    construct_output_dir,
    get_ignore_patterns,
    get_additional_context,
    set_config_path,
    load_default_config,
)


def index_codebase(config_path: str):
    """
    Index a codebase and generate context.

    Args:
        config_path: Path to config file (required, enables config merge with template)

    Returns:
        Dictionary containing codebase context generation result
    """
    # Set config path for merge
    set_config_path(config_path)

    # Load config to get codebase_dir
    config = load_default_config()
    codebase_dir = config.get("codebase_dir")

    if not codebase_dir:
        raise ValueError("codebase_dir must be specified in config file")

    # All parameters will be read from config
    output_dir = construct_output_dir(codebase_dir)
    ignore_patterns = get_ignore_patterns(codebase_dir)
    additional_context = get_additional_context()

    return generate_context(
        codebase_dir=codebase_dir,
        output_dir=output_dir,
        ignore_patterns=ignore_patterns,
        additional_context=additional_context,
        verbose=True,
    )


def chat_with_codebase(config_path: str):
    """
    Start an interactive agentic chat session with a codebase.

    Args:
        config_path: Path to config file (required, enables config merge with template)
    """
    # Set config path for merge
    set_config_path(config_path)

    # Load config to get codebase_dir
    config = load_default_config()
    codebase_dir = config.get("codebase_dir")

    return cli_chat(codebase_dir=codebase_dir, context=None)


__all__ = ["index_codebase", "chat_with_codebase"]
