# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Test MCP tool name extraction."""

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
