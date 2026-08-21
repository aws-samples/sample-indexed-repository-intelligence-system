# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tests for MCP server.
"""

import inspect
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.mark.unit
class TestMCPServer:
    """Test MCP server module."""

    def test_mcp_server_exists(self):
        """Test MCP server file exists."""
        mcp_path = Path(__file__).parent.parent.parent / "iris_mcp" / "mcp_server.py"
        assert mcp_path.exists()

    def test_mcp_server_imports(self):
        """Test MCP server can be imported."""
        try:
            import iris_mcp.mcp_server

            assert hasattr(iris_mcp.mcp_server, "__file__")
        except ImportError as e:
            pytest.skip(f"MCP dependencies not installed: {e}")

    def test_mcp_init_exists(self):
        """Test MCP __init__.py exists."""
        init_path = Path(__file__).parent.parent.parent / "iris_mcp" / "__init__.py"
        assert init_path.exists()

    def test_mcp_server_has_tools(self):
        """Test MCP server defines all expected tool functions."""
        try:
            import iris_mcp.mcp_server as mcp_module

            assert hasattr(mcp_module, "codebase_artifact_context")
            assert hasattr(mcp_module, "codebase_artifact_query")
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_mcp_server_has_utility_functions(self):
        """Test MCP server defines utility functions."""
        try:
            import iris_mcp.mcp_server as mcp_module

            assert hasattr(mcp_module, "get_enabled_tools")
            assert hasattr(mcp_module, "is_tool_enabled")
            assert hasattr(mcp_module, "validate_codebase_path")
        except ImportError:
            pytest.skip("MCP dependencies not installed")


@pytest.mark.unit
class TestValidateCodebasePath:
    """Test validate_codebase_path function."""

    def test_valid_directory(self, temp_dir):
        """Test validation with a valid directory."""
        try:
            from iris_mcp.mcp_server import validate_codebase_path

            result = validate_codebase_path(str(temp_dir))
            assert result == temp_dir.resolve()
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_nonexistent_path(self):
        """Test validation with a nonexistent path."""
        try:
            from iris_mcp.mcp_server import validate_codebase_path

            with pytest.raises(ValueError, match="Path does not exist"):
                validate_codebase_path("/nonexistent/path/abc123")
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_file_path_not_directory(self, temp_dir):
        """Test validation with a file path instead of directory."""
        try:
            from iris_mcp.mcp_server import validate_codebase_path

            file_path = temp_dir / "test.txt"
            file_path.write_text("test")
            with pytest.raises(ValueError, match="not a directory"):
                validate_codebase_path(str(file_path))
        except ImportError:
            pytest.skip("MCP dependencies not installed")


@pytest.mark.unit
class TestGetEnabledTools:
    """Test get_enabled_tools function."""

    def test_default_returns_all(self):
        """Test that default config returns all tools."""
        try:
            from iris_mcp.mcp_server import get_enabled_tools

            with patch(
                "iris.utils.utils.load_default_config",
                return_value={"mcp_enabled_tools": ["all"]},
            ):
                result = get_enabled_tools()
                assert result == ["all"]
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_specific_tools(self):
        """Test with specific tools enabled."""
        try:
            from iris_mcp.mcp_server import get_enabled_tools

            with patch(
                "iris.utils.utils.load_default_config",
                return_value={
                    "mcp_enabled_tools": [
                        "codebase_artifact_context",
                        "codebase_artifact_query",
                    ]
                },
            ):
                result = get_enabled_tools()
                assert "codebase_artifact_context" in result
                assert "codebase_artifact_query" in result
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_invalid_tools_filtered(self):
        """Test that invalid tool names are filtered out."""
        try:
            from iris_mcp.mcp_server import get_enabled_tools

            with patch(
                "iris.utils.utils.load_default_config",
                return_value={
                    "mcp_enabled_tools": ["codebase_artifact_context", "invalid_tool"]
                },
            ):
                result = get_enabled_tools()
                assert "codebase_artifact_context" in result
                assert "invalid_tool" not in result
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_config_load_failure_returns_all(self):
        """Test fallback to all when config loading fails."""
        try:
            from iris_mcp.mcp_server import get_enabled_tools

            with patch(
                "iris.utils.utils.load_default_config",
                side_effect=Exception("config error"),
            ):
                result = get_enabled_tools()
                assert result == ["all"]
        except ImportError:
            pytest.skip("MCP dependencies not installed")


@pytest.mark.unit
class TestIsToolEnabled:
    """Test is_tool_enabled function."""

    def test_all_enables_everything(self):
        """Test that 'all' enables any tool."""
        try:
            from iris_mcp.mcp_server import is_tool_enabled

            assert is_tool_enabled("codebase_artifact_context", ["all"]) is True
            assert is_tool_enabled("codebase_artifact_query", ["all"]) is True
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_specific_tool_enabled(self):
        """Test specific tool check."""
        try:
            from iris_mcp.mcp_server import is_tool_enabled

            enabled = ["codebase_artifact_context"]
            assert is_tool_enabled("codebase_artifact_context", enabled) is True
            assert is_tool_enabled("codebase_artifact_query", enabled) is False
        except ImportError:
            pytest.skip("MCP dependencies not installed")


@pytest.mark.integration
class TestMCPTools:
    """Test MCP tool functionality."""

    def test_codebase_artifact_context_is_async(self):
        """Test codebase_artifact_context is an async function."""
        try:
            from iris_mcp.mcp_server import codebase_artifact_context

            assert callable(codebase_artifact_context)
            assert inspect.iscoroutinefunction(codebase_artifact_context)
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_codebase_artifact_query_is_async(self):
        """Test codebase_artifact_query is an async function."""
        try:
            from iris_mcp.mcp_server import codebase_artifact_query

            assert callable(codebase_artifact_query)
            assert inspect.iscoroutinefunction(codebase_artifact_query)
        except ImportError:
            pytest.skip("MCP dependencies not installed")
