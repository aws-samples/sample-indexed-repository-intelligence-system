# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Test MCP tool name extraction and valid tool set."""

import pytest
from iris.agents.mcp_tools import get_mcp_tool_names


class MockTool:
    """Mock tool with name attribute."""

    def __init__(self, name):
        self.name = name


class MockMCPProvider:
    """Mock MCP provider with tools."""

    def __init__(self, tools):
        self.tools = tools


class TestGetMCPToolNames:
    """Test get_mcp_tool_names function."""

    def test_extract_tool_names_from_objects(self):
        """Test extracting tool names from tool objects."""
        tool1 = MockTool("search_docs")
        tool2 = MockTool("fetch_doc")
        provider = MockMCPProvider([tool1, tool2])

        names = get_mcp_tool_names([provider])
        assert names == ["search_docs", "fetch_doc"]

    def test_extract_tool_names_from_dicts(self):
        """Test extracting tool names from dict-based tools."""
        tools = [{"name": "aws_docs_search"}, {"name": "aws_docs_read"}]
        provider = MockMCPProvider(tools)

        names = get_mcp_tool_names([provider])
        assert names == ["aws_docs_search", "aws_docs_read"]

    def test_multiple_providers(self):
        """Test extracting names from multiple providers."""
        provider1 = MockMCPProvider([MockTool("tool1"), MockTool("tool2")])
        provider2 = MockMCPProvider([MockTool("tool3")])

        names = get_mcp_tool_names([provider1, provider2])
        assert names == ["tool1", "tool2", "tool3"]

    def test_empty_providers(self):
        """Test with no providers."""
        names = get_mcp_tool_names([])
        assert names == []

    def test_provider_without_tools(self):
        """Test provider without tools attribute."""

        class NoToolsProvider:
            pass

        names = get_mcp_tool_names([NoToolsProvider()])
        assert names == []


@pytest.mark.unit
class TestMCPValidToolSet:
    """Test that the MCP server's valid tool set is correct."""

    def test_valid_tools_includes_all_expected(self):
        """Test that the valid_tools set in get_enabled_tools includes all tool names."""
        try:
            from iris_mcp.mcp_server import get_enabled_tools
            from unittest.mock import patch

            expected_tools = {
                "all",
                "codebase_artifact_context",
                "codebase_artifact_query",
            }

            # Return all expected tools from config to verify none are filtered
            with patch(
                "iris.utils.utils.load_default_config",
                return_value={"mcp_enabled_tools": list(expected_tools)},
            ):
                result = get_enabled_tools()
                assert set(result) == expected_tools
        except ImportError:
            pytest.skip("MCP dependencies not installed")

    def test_codebase_artifact_query_is_valid(self):
        """Test that codebase_artifact_query is recognized as a valid tool."""
        try:
            from iris_mcp.mcp_server import get_enabled_tools
            from unittest.mock import patch

            with patch(
                "iris.utils.utils.load_default_config",
                return_value={"mcp_enabled_tools": ["codebase_artifact_query"]},
            ):
                result = get_enabled_tools()
                assert "codebase_artifact_query" in result
        except ImportError:
            pytest.skip("MCP dependencies not installed")
