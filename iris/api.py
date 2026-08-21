# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Public API for iris package.
Exposes codebase indexing and agentic chat functionality for external use.
"""

from .generate_context import generate_context
from .generate_artifact_context import generate_artifact_context
from .artifacts import resolve_artifact_dir
from .agentic_chat import cli_chat
from .utils.utils import (
    construct_output_dir,
    get_ignore_patterns,
    get_additional_context,
    set_config_path,
    load_default_config,
)


def index_codebase_artifacts(config_path: str, mode: str = "both"):
    """
    Unified indexing: index codebase and/or project artifacts.

    Args:
        config_path: Path to config file (required, enables config merge with template)
        mode: What to index — "both" (default), "codebase", or "artifact".

    Returns:
        Dict with codebase_result and/or artifact_result (None when skipped)
    """
    if mode:
        mode = mode.lower()

    if mode not in ("both", "codebase", "artifact"):
        raise ValueError(
            f"Invalid mode '{mode}'. Must be 'both', 'codebase', or 'artifact'."
        )

    set_config_path(config_path)
    config = load_default_config()

    codebase_dir = config.get("codebase_dir")
    if not codebase_dir:
        raise ValueError("codebase_dir must be specified in config file")

    output_dir = construct_output_dir(codebase_dir=codebase_dir)
    ignore_patterns = get_ignore_patterns(codebase_dir)
    additional_context = get_additional_context()

    # Index codebase
    codebase_result = None
    if mode in ("both", "codebase"):
        codebase_result = generate_context(
            codebase_dir=codebase_dir,
            output_dir=output_dir,
            ignore_patterns=ignore_patterns,
            additional_context=additional_context,
            verbose=True,
        )

    # Index artifacts
    artifact_result = None
    if mode in ("both", "artifact"):
        artifact_dir = resolve_artifact_dir(config)
        if artifact_dir:
            artifact_result = generate_artifact_context(
                artifact_dir=artifact_dir,
                output_dir=output_dir,
                config=config,
                verbose=True,
            )

    return {
        "codebase_result": codebase_result,
        "artifact_result": artifact_result,
    }


def chat_with_codebase_artifacts(config_path: str):
    """
    Start an interactive chat session with both codebase and artifact context.

    If artifact_dir is not configured, this behaves as a codebase-only chat session.

    Args:
        config_path: Path to config file (required, enables config merge with template)
    """
    set_config_path(config_path)
    config = load_default_config()
    codebase_dir = config.get("codebase_dir")

    return cli_chat(codebase_dir=codebase_dir, context=None)


__all__ = [
    "index_codebase_artifacts",
    "chat_with_codebase_artifacts",
]
