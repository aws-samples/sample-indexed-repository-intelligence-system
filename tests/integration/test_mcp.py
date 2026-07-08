# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tests for MCP server.
"""

import pytest
from pathlib import Path


@pytest.mark.unit
class TestMCPServer:
    """Test MCP server module."""

    def test_mcp_server_exists(self):
        """Test MCP server file exists."""
        mcp_path = (
            Path(__file__).parent.parent.parent / "iris_mcp" / "mcp_server.py"
        )
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
        init_path = (
            Path(__file__).parent.parent.parent / "iris_mcp" / "__init__.py"
        )
        assert init_path.exists()

    def test_mcp_server_has_tools(self):
        """Test MCP server defines tools."""
        try:
            import iris_mcp.mcp_server as mcp_module

            # Check for tool functions
            assert hasattr(mcp_module, "codebase_context")
            assert hasattr(mcp_module, "codebase_query")
        except ImportError:
            pytest.skip("MCP dependencies not installed")


@pytest.mark.integration
class TestMCPTools:
    """Test MCP tool functionality."""

    def test_get_codebase_context_tool(self, test_codebase, output_dir):
        """Test codebase_context tool can be imported."""
        try:
            from iris_mcp.mcp_server import codebase_context

            # Verify it's a callable async function
            import inspect

            assert callable(codebase_context)
            assert inspect.iscoroutinefunction(codebase_context)
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_codebase_query_tool(self, test_codebase, output_dir):
        """Test codebase_query tool can be imported."""
        try:
            from iris_mcp.mcp_server import codebase_query

            # Verify it's a callable async function
            import inspect

            assert callable(codebase_query)
            assert inspect.iscoroutinefunction(codebase_query)
        except ImportError:
            pytest.skip("MCP dependencies not installed")
