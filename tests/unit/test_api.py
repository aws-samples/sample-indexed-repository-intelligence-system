"""
Tests for iris.api module.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestIndexCodebaseArtifacts:
    """Test index_codebase_artifacts API function."""

    @patch("iris.api.resolve_artifact_dir", return_value="/test/artifacts")
    @patch("iris.api.generate_artifact_context")
    @patch("iris.api.generate_context")
    @patch("iris.api.load_default_config")
    @patch("iris.api.set_config_path")
    @patch("iris.api.get_additional_context", return_value="")
    @patch("iris.api.get_ignore_patterns", return_value=["*.pyc"])
    @patch("iris.api.construct_output_dir", return_value="/mock/output")
    def test_indexes_both_by_default(
        self,
        mock_output,
        mock_ignore,
        mock_ctx,
        mock_set,
        mock_config,
        mock_gen,
        mock_art,
        mock_resolve,
    ):
        """Test that both codebase and artifact indexing run with default mode='both'."""
        from iris.api import index_codebase_artifacts

        mock_config.return_value = {
            "codebase_dir": "/test/code",
            "artifact_dir": "/test/artifacts",
        }
        mock_gen.return_value = MagicMock(status="success")
        mock_art.return_value = MagicMock(status="success")

        result = index_codebase_artifacts("/path/to/config.yaml")

        mock_gen.assert_called_once()
        mock_art.assert_called_once()
        assert result["codebase_result"].status == "success"
        assert result["artifact_result"].status == "success"

    @patch("iris.api.generate_context")
    @patch("iris.api.load_default_config")
    @patch("iris.api.set_config_path")
    @patch("iris.api.get_additional_context", return_value="")
    @patch("iris.api.get_ignore_patterns", return_value=["*.pyc"])
    @patch("iris.api.construct_output_dir", return_value="/mock/output")
    def test_mode_codebase_skips_artifacts(
        self,
        mock_output,
        mock_ignore,
        mock_ctx,
        mock_set,
        mock_config,
        mock_gen,
    ):
        """Test mode='codebase' only indexes codebase, skips artifacts."""
        from iris.api import index_codebase_artifacts

        mock_config.return_value = {
            "codebase_dir": "/test/code",
            "artifact_dir": "/test/artifacts",
        }
        mock_gen.return_value = MagicMock(status="success")

        result = index_codebase_artifacts("/path/to/config.yaml", mode="codebase")

        mock_gen.assert_called_once()
        assert result["codebase_result"].status == "success"
        assert result["artifact_result"] is None

    @patch("iris.api.resolve_artifact_dir", return_value="/test/artifacts")
    @patch("iris.api.generate_artifact_context")
    @patch("iris.api.load_default_config")
    @patch("iris.api.set_config_path")
    @patch("iris.api.get_additional_context", return_value="")
    @patch("iris.api.get_ignore_patterns", return_value=["*.pyc"])
    @patch("iris.api.construct_output_dir", return_value="/mock/output")
    def test_mode_artifact_skips_codebase(
        self,
        mock_output,
        mock_ignore,
        mock_ctx,
        mock_set,
        mock_config,
        mock_art,
        mock_resolve,
    ):
        """Test mode='artifact' only indexes artifacts, skips codebase."""
        from iris.api import index_codebase_artifacts

        mock_config.return_value = {
            "codebase_dir": "/test/code",
            "artifact_dir": "/test/artifacts",
        }
        mock_art.return_value = MagicMock(status="success")

        result = index_codebase_artifacts("/path/to/config.yaml", mode="artifact")

        assert result["codebase_result"] is None
        assert result["artifact_result"].status == "success"

    @patch("iris.api.generate_context")
    @patch("iris.api.load_default_config")
    @patch("iris.api.set_config_path")
    @patch("iris.api.get_additional_context", return_value="")
    @patch("iris.api.get_ignore_patterns", return_value=["*.pyc"])
    @patch("iris.api.construct_output_dir", return_value="/mock/output")
    def test_skips_artifacts_when_no_artifact_dir(
        self,
        mock_output,
        mock_ignore,
        mock_ctx,
        mock_set,
        mock_config,
        mock_gen,
    ):
        """Test that artifact indexing is skipped when artifact_dir is not configured."""
        from iris.api import index_codebase_artifacts

        mock_config.return_value = {"codebase_dir": "/test/code"}
        mock_gen.return_value = MagicMock(status="success")

        result = index_codebase_artifacts("/path/to/config.yaml")

        mock_gen.assert_called_once()
        assert result["codebase_result"].status == "success"
        assert result["artifact_result"] is None

    @patch("iris.api.load_default_config")
    @patch("iris.api.set_config_path")
    def test_raises_without_codebase_dir(self, mock_set, mock_config):
        """Test that missing codebase_dir raises ValueError."""
        from iris.api import index_codebase_artifacts

        mock_config.return_value = {"artifact_dir": "/test/artifacts"}

        with pytest.raises(ValueError, match="codebase_dir must be specified"):
            index_codebase_artifacts("/path/to/config.yaml")

    def test_raises_on_invalid_mode(self):
        """Test that an invalid mode raises ValueError."""
        from iris.api import index_codebase_artifacts

        with pytest.raises(ValueError, match="Invalid mode"):
            index_codebase_artifacts("/path/to/config.yaml", mode="invalid")


@pytest.mark.unit
class TestChatWithCodebaseArtifacts:
    """Test chat_with_codebase_artifacts API function."""

    @patch("iris.api.cli_chat")
    @patch("iris.api.load_default_config")
    @patch("iris.api.set_config_path")
    def test_calls_cli_chat_with_codebase_dir(self, mock_set, mock_config, mock_chat):
        """Test that chat_with_codebase_artifacts calls cli_chat correctly."""
        from iris.api import chat_with_codebase_artifacts

        mock_config.return_value = {"codebase_dir": "/test/code"}
        mock_chat.return_value = None

        chat_with_codebase_artifacts("/path/to/config.yaml")

        mock_set.assert_called_once_with("/path/to/config.yaml")
        mock_chat.assert_called_once_with(codebase_dir="/test/code", context=None)


@pytest.mark.unit
class TestAPIExports:
    """Test that api module exports the expected symbols."""

    def test_all_exports(self):
        """Test __all__ contains expected functions."""
        from iris.api import __all__

        expected = [
            "index_codebase_artifacts",
            "chat_with_codebase_artifacts",
        ]
        for name in expected:
            assert name in __all__, f"{name} should be in __all__"

    def test_index_codebase_artifacts_importable(self):
        """Test index_codebase_artifacts can be imported."""
        from iris.api import index_codebase_artifacts

        assert callable(index_codebase_artifacts)

    def test_chat_with_codebase_artifacts_importable(self):
        """Test chat_with_codebase_artifacts can be imported."""
        from iris.api import chat_with_codebase_artifacts

        assert callable(chat_with_codebase_artifacts)
