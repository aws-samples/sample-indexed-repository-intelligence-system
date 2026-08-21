#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Test MCP server integration with IRIS.
"""

import pytest
from iris.agents.mcp_tools import load_mcp_tools, build_mcp_prompt
from iris.utils.utils import load_default_config


class TestMCPConfiguration:
    """Test MCP server configuration."""

    def test_mcp_configuration_exists(self):
        """Test that the optional mcp_servers config, if present, is well-formed.

        MCP integration is an optional feature that is disabled by default, so
        an active config.yaml may legitimately omit mcp_servers entirely. When
        the section is present it must be a mapping of server-name -> config.
        """
        config = load_default_config()
        mcp_config = config.get("mcp_servers", {})

        assert isinstance(mcp_config, dict), "mcp_servers should be a mapping"

    def test_mcp_server_structure(self):
        """Test that MCP server configs have required fields."""
        config = load_default_config()
        mcp_config = config.get("mcp_servers", {})

        for name, cfg in mcp_config.items():
            assert "enabled" in cfg, f"Server {name} missing 'enabled' field"
            assert "command" in cfg, f"Server {name} missing 'command' field"
            assert "args" in cfg, f"Server {name} missing 'args' field"
            assert isinstance(
                cfg["args"], list
            ), f"Server {name} 'args' should be a list"


class TestMCPToolsLoading:
    """Test MCP tools loading functionality."""

    def test_load_mcp_tools_with_no_enabled_servers(self):
        """Test that load_mcp_tools returns empty list when no servers enabled."""
        config = {
            "mcp_servers": {
                "test_server": {"enabled": False, "command": "uvx", "args": ["test"]}
            }
        }

        tools = load_mcp_tools(config)
        assert tools == [], "Should return empty list when no servers enabled"

    def test_load_mcp_tools_with_no_config(self):
        """Test that load_mcp_tools handles missing config gracefully."""
        config = {}
        tools = load_mcp_tools(config)
        assert tools == [], "Should return empty list when no mcp_servers config"


class TestMCPPromptBuilding:
    """Test dynamic MCP prompt building."""

    def test_build_mcp_prompt_with_no_servers(self):
        """Test prompt building with no MCP servers."""
        config = {}
        prompt = build_mcp_prompt(config)
        assert prompt == "", "Should return empty string when no servers configured"

    def test_build_mcp_prompt_with_disabled_servers(self):
        """Test prompt building with disabled servers."""
        config = {
            "mcp_servers": {
                "aws_documentation": {"enabled": False},
                "agentcore_docs": {"enabled": False},
            }
        }
        prompt = build_mcp_prompt(config)
        assert prompt == "", "Should return empty string when all servers disabled"

    def test_build_mcp_prompt_with_enabled_servers(self):
        """Test prompt building with enabled servers."""
        config = {
            "mcp_servers": {
                "aws_documentation": {"enabled": True},
                "agentcore_docs": {"enabled": False},
            }
        }
        prompt = build_mcp_prompt(config)
        assert prompt != "", "Should return prompt when servers enabled"
        assert "<mcp_tools_capability>" in prompt, "Should contain capability tags"
        assert "AWS Documentation" in prompt, "Should mention enabled server"
        assert "AgentCore" not in prompt, "Should not mention disabled server"


class TestMCPEnabledToolsConfig:
    """Test MCP enabled tools configuration."""

    def test_config_has_mcp_enabled_tools(self):
        """Test that config includes mcp_enabled_tools."""
        config = load_default_config()
        assert "mcp_enabled_tools" in config, "Config should have mcp_enabled_tools"

    def test_mcp_enabled_tools_is_list(self):
        """Test that mcp_enabled_tools is a list."""
        config = load_default_config()
        tools = config.get("mcp_enabled_tools", [])
        assert isinstance(tools, list), "mcp_enabled_tools should be a list"

    def test_mcp_enabled_tools_contains_valid_names(self):
        """Test that all entries in mcp_enabled_tools are valid tool names."""
        valid_tools = {
            "all",
            "codebase_artifact_context",
            "codebase_artifact_query",
        }
        config = load_default_config()
        tools = config.get("mcp_enabled_tools", [])
        for tool in tools:
            assert tool in valid_tools, f"Unknown tool '{tool}' in mcp_enabled_tools"


@pytest.mark.integration
class TestMCPLiveIntegration:
    """Live integration tests - only run when MCP servers are enabled."""

    def test_mcp_tools_loading_live(self):
        """Test loading MCP tools from actual config (skipped if none enabled)."""
        config = load_default_config()
        mcp_config = config.get("mcp_servers", {})
        enabled_count = sum(
            1 for cfg in mcp_config.values() if cfg.get("enabled", False)
        )

        if enabled_count == 0:
            pytest.skip("No MCP servers enabled in config.yaml")

        tools = load_mcp_tools(config)
        assert len(tools) > 0, f"Expected {enabled_count} MCP clients, got {len(tools)}"
