# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
The config a caller sets with set_config_path() is the one IRIS uses.

`import iris` loads every module before a library or MCP caller can call
set_config_path(), so a module that reads the config at import time keeps the
packaged template instead. These tests set a config after import and check that
model selection, limits and defaults come from it.
"""

import sys

import pytest
import yaml

import iris  # noqa: F401 - loads every module first, as library and MCP callers do
from iris.file_system import file_utils
from iris.summarize import file_summarizer
from iris.utils import utils as iris_utils

USER_MODELS = [{"model_id": "user-model", "region": "user-region-1"}]


@pytest.fixture
def user_config(temp_dir, monkeypatch):
    """A user config with one model-region pair, set after import."""
    config = {
        "codebase_dir": str(temp_dir),
        "max_file_size": 1234,
        "model_configuration": {
            "file_summarizer": {"models": USER_MODELS},
            "file_identifier": {"model_id": "user-ident", "region": "user-region-1"},
        },
    }
    path = temp_dir / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(iris_utils, "_config_path_override", None)
    monkeypatch.setattr(iris_utils, "_cached_config", None)
    iris_utils.set_config_path(path)
    return config


class _Stop(Exception):
    pass


def test_summarizer_uses_the_set_models(user_config, monkeypatch):
    seen = []

    def capture(models):
        seen.append(models)
        raise _Stop()

    monkeypatch.setattr(file_summarizer, "validate_llm_model_access", capture)
    with pytest.raises(_Stop):
        file_summarizer.summarize_files(
            files_to_summarize=["a.py"],
            codebase_dir=user_config["codebase_dir"],
            output_dir=user_config["codebase_dir"],
        )
    assert seen == [USER_MODELS]


def test_user_config_is_merged_over_the_packaged_template(user_config):
    config = iris_utils.load_default_config()
    template = iris_utils.load_template_config()

    assert config["model_configuration"]["file_summarizer"]["models"] == USER_MODELS
    assert config["model_configuration"]["file_identifier"]["model_id"] == "user-ident"
    # Keys the user did not set come from the template.
    assert config["context_window_size"] == template["context_window_size"]
    assert config["max_notebook_size"] == template["max_notebook_size"]


def test_file_limits_follow_the_set_config(user_config):
    assert file_utils.get_max_file_size() == 1234
    template = iris_utils.load_template_config()
    assert file_utils.get_max_notebook_size() == template["max_notebook_size"]
    assert file_utils.get_max_tokens() == template["context_window_size"]


def test_no_module_keeps_a_config_captured_at_import():
    """No loaded IRIS module holds its own copy of the config."""
    held = []
    for name, module in list(sys.modules.items()):
        if module is None or not (name == "iris" or name.startswith("iris.")):
            continue
        if name == "iris.utils.utils":
            continue  # owns the config cache
        for attr, value in vars(module).items():
            if isinstance(value, dict) and (
                "model_configuration" in value
                or {"file_summarizer", "file_identifier"} & set(value)
            ):
                held.append(f"{name}.{attr}")
    assert held == []
