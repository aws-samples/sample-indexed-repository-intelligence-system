# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from pathlib import Path
import yaml


class ConfigNotFound(Exception):
    """Exception raised when config.yaml is not found."""

    pass


# Global config path override for MCP server and library usage through api package
_config_path_override = None
# Cached config to avoid reloading
_cached_config = None


def set_config_path(path: str | Path):
    """Set config path globally (used by MCP server and library API)."""
    global _config_path_override, _cached_config
    _config_path_override = Path(path)
    _cached_config = None  # Clear cache when config path changes


def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries. Override values take precedence.

    Args:
        base: Base configuration dictionary
        override: Override configuration dictionary

    Returns:
        Merged configuration dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_template_config() -> dict:
    """Load the default template config shipped with the package."""
    # Try two locations:
    # 1. Root level (for development/existing setup)
    # 2. Package level (for installed package)
    template_paths = [
        Path(__file__).parent.parent.parent
        / "config_template.yaml",  # Root level (original)
        Path(__file__).parent.parent
        / "pkg_config_template.yaml",  # Package level (renamed)
    ]

    for template_path in template_paths:
        if template_path.exists():
            with open(template_path, "r") as f:
                return yaml.safe_load(f)

    raise ConfigNotFound(
        f"config_template.yaml not found at {template_paths[0]} or {template_paths[1]}"
    )


def load_default_config() -> dict:
    """
    Load config with optional merge support.

    Backward compatible: Loads config.yaml from project root by default.

    New behavior: If set_config_path() was called (e.g., by MCP server or library),
    merges the specified config with base config:
    - Base priority: config.yaml (if exists) > config_template.yaml
    - User config overrides base

    Returns:
        Configuration dictionary
    """
    global _cached_config, _config_path_override

    # Return cached config if available (only for api use)
    if (_cached_config is not None) and (_config_path_override is not None):
        return _cached_config

    # BACKWARD COMPATIBLE: No override set, use original logic
    if _config_path_override is None:
        # Original behavior: load from project root
        default_config_path = Path(__file__).parent.parent.parent / "config.yaml"
        if default_config_path.exists():
            with open(default_config_path, "r") as f:
                _cached_config = yaml.safe_load(f)
                return _cached_config
        else:
            # If no config exists, try to load template as fallback
            try:
                _cached_config = load_template_config()
                return _cached_config
            except ConfigNotFound:
                raise ConfigNotFound(
                    f"config.yaml or config_template.yaml not found at {default_config_path}. "
                    "Please ensure config.yaml exists in the project root directory."
                )

    # NEW BEHAVIOR: Override set - use merge mode
    user_config_path = _config_path_override

    if not user_config_path.exists():
        raise ConfigNotFound(
            f"config.yaml not found at {user_config_path}. "
            "Please ensure the config file exists."
        )

    # Load user config
    with open(user_config_path, "r") as f:
        user_config = yaml.safe_load(f) or {}

    # Determine base config: config.yaml > config_template.yaml
    base_config_path = Path(__file__).parent.parent.parent / "config.yaml"
    template_config_path = Path(__file__).parent.parent / "config_template.yaml"

    if base_config_path.exists():
        # Use config.yaml as base
        with open(base_config_path, "r") as f:
            base_config = yaml.safe_load(f) or {}
    elif template_config_path.exists():
        # Use config_template.yaml as base
        base_config = load_template_config()
    else:
        # No base config, just return user config
        _cached_config = user_config
        return _cached_config

    # Merge: base config + user config overrides
    _cached_config = deep_merge(base_config, user_config)
    return _cached_config


def construct_output_dir(codebase_dir: str | Path | None = None):
    config = load_default_config()
    output_dir_config = config["output_dir"]

    # Convert to Path objects
    codebase_dir = config.get("codebase_dir") or codebase_dir
    if codebase_dir is None:
        raise ValueError(
            "codebase_dir must be provided either in config or as a parameter"
        )
    codebase_path = Path(codebase_dir).resolve()
    output_path = Path(output_dir_config)

    # Get the name of the codebase directory
    codebase_name = codebase_path.name

    # If output_dir is absolute, use it as base and append codebase name
    if output_path.is_absolute():
        return str(output_path / codebase_name)

    # If output_dir is relative, make it relative to codebase_dir and append codebase name
    return str(codebase_path / output_path / codebase_name)


def get_additional_context(filepath: str | None = None) -> str:
    config = load_default_config()
    additional_context = ""

    context_file = config.get("context_file") or filepath
    if context_file:
        context_path = Path(context_file)
        if context_path.exists():
            additional_context = context_path.read_text(encoding="utf-8")
    return additional_context


def get_conversation_history_filename(output_dir: str | Path):
    config = load_default_config()

    return Path(output_dir) / config["conversation_history_filename"]


def get_ignore_patterns(
    codebase_dir: str | Path,
):
    """
    Get ignore patterns from config.
    Will append output directory to ignore patterns to prevent recursive processing
    """

    output_dir = construct_output_dir(codebase_dir=codebase_dir)

    config = load_default_config()
    enhanced_ignore_patterns = config.get("ignore_patterns")

    # Calculate relative path from codebase_dir to output_dir
    codebase_path = Path(codebase_dir).resolve()
    output_path = Path(output_dir).resolve()

    try:
        # If output_dir is inside codebase_dir, get relative path
        relative_output = output_path.relative_to(codebase_path).as_posix()
        enhanced_ignore_patterns.append(str(relative_output) + "/")
        enhanced_ignore_patterns.append(str(relative_output) + "/*")
    except ValueError:
        # output_dir is outside codebase_dir, no need to ignore
        pass

    return enhanced_ignore_patterns
