<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# MCP Server Integration

IRIS can connect to external MCP (Model Context Protocol) servers to extend the agent's capabilities with additional tools and knowledge sources.

## Overview

MCP servers provide standardized access to external services and documentation. IRIS integrates with AWS-provided MCP servers to give the agent access to:

- **AWS Documentation**: Comprehensive AWS service documentation, APIs, and best practices
- **Amazon Bedrock AgentCore Documentation**: Deployment guides, runtime management, and AgentCore features
- **Strands Agents Documentation**: Strands SDK documentation, examples, and API references

## Configuration

MCP servers are configured in `config.yaml`. By default, all three AWS MCP servers are **disabled** (`enabled: false`). Enable them by setting `enabled: true`:

```yaml
mcp_servers:
  aws_documentation:
    enabled: false # Set to true to enable
    command: "uvx"
    args: ["awslabs.aws-documentation-mcp-server@latest"]
    env:
      FASTMCP_LOG_LEVEL: "ERROR"
    tool_filters:
      allowed: ["search_documentation", "read_documentation", "recommend"]
      rejected: ["get_available_services"]
    prefix: "aws_docs"

  agentcore_docs:
    enabled: false # Set to true to enable
    command: "uvx"
    args: ["awslabs.amazon-bedrock-agentcore-mcp-server@latest"]
    env:
      FASTMCP_LOG_LEVEL: "ERROR"
    tool_filters:
      allowed: ["search_agentcore_docs", "fetch_agentcore_doc"]
      rejected: ["manage_agentcore_runtime"]

  strands_agents_docs:
    enabled: false # Set to true to enable
    command: "uvx"
    args: ["strands-agents-mcp-server@latest"]
    env:
      FASTMCP_LOG_LEVEL: "ERROR"
    tool_filters:
      allowed: ["search_docs", "fetch_doc"]
    prefix: "strands"
```

### Configuration Options

- `enabled`: Boolean to enable/disable the MCP server
- `command`: Command to launch the MCP server (typically `uvx`)
- `args`: Arguments passed to the command
- `env`: Environment variables for the MCP server process
- `tool_filters` (optional): Control which tools are exposed
  - `allowed`: List of tool names to include (whitelist)
  - `rejected`: List of tool names to exclude (blacklist)
- `prefix` (optional): String prefix added to all tool names

## Tool Filtering

### Whitelist (Recommended)

Only expose specific tools:

```yaml
tool_filters:
  allowed: ["search_documentation", "fetch_documentation"]
```

### Blacklist

Exclude specific tools:

```yaml
tool_filters:
  rejected: ["get_recommendations"]
```

### Combined

Apply both (rejected is applied after allowed):

```yaml
tool_filters:
  allowed:
    ["search_agentcore_docs", "fetch_agentcore_doc", "manage_agentcore_runtime"]
  rejected: ["manage_agentcore_runtime"]
```

### Tool Name Prefixing

Prevent conflicts when using multiple MCP servers:

```yaml
prefix: "aws_docs"
# Tools become: aws_docs_search_documentation, aws_docs_fetch_documentation
```

## Available MCP Servers

### AWS Documentation MCP Server

**Package**: `awslabs.aws-documentation-mcp-server@latest`

**Available Tools**:

- `search_documentation`: Search AWS documentation
- `read_documentation`: Retrieve complete documentation pages
- `recommend`: Get related documentation
- `get_available_services`: List available AWS services (excluded by default)

**Use Cases**: AWS services, APIs, best practices

### Amazon Bedrock AgentCore Documentation MCP Server

**Package**: `awslabs.amazon-bedrock-agentcore-mcp-server@latest`

**Available Tools**:

- `search_agentcore_docs`: Search Amazon Bedrock AgentCore documentation
- `fetch_agentcore_doc`: Retrieve full documentation pages
- `manage_agentcore_runtime`: Deployment and runtime guides (excluded by default)

**Use Cases**: Agent deployment, memory management, gateway configuration

### Strands Agents Documentation MCP Server

**Package**: `strands-agents-mcp-server@latest`

**Available Tools**:

- `search_docs`: TF-IDF based search with Markdown-aware scoring
- `fetch_doc`: Fetch full document content on-demand

**Use Cases**: Strands SDK documentation, agent patterns, framework features

## Usage

Once enabled in `config.yaml`, MCP tools are automatically available to the agent:

```bash
# Uses AWS Documentation MCP (requires enabled: true)
"What is AWS Lambda and how do I use it?"

# Uses AgentCore MCP (requires enabled: true)
"How do I deploy this agent to AgentCore?"
```

**Note**: All three AWS MCP servers are disabled by default. Set `enabled: true` in your `config.yaml` to use them.

## Testing

Test your MCP configuration:

```bash
# From the repository root
python -m pytest tests/integration/test_mcp_tool_integration.py
```

## Prerequisites

- Python 3.10+
- `uvx` tool: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Internet connection

## Troubleshooting

**Connection Timeouts**: Verify internet connectivity and `uvx` installation

**Tools Not Available**: Check `enabled: true` in config.yaml and run the test above

**Slow Response**: MCP servers initialize on first use (a few seconds)

## Architecture

```
IRIS Agent
├── Native Tools (file_retrieval, code_search)
├── MCP Client (AWS Docs) → AWS Docs MCP Server
├── MCP Client (AgentCore) → AgentCore MCP Server
└── MCP Client (Strands) → Strands Agents MCP Server
```

## Memory Management

To prevent long MCP documentation responses from consuming conversation memory, the system automatically:

1. **Drops MCP tool results** after each turn - The tool use and result are replaced with a breadcrumb like `[aws_docs_search_documentation used; output discarded]`
2. **Keeps only enabled tools** - Only MCP tools that are enabled in `config.yaml` (`enabled: true`) are added to the drop list
3. **Preserves agent reasoning** - The agent still sees that it used the tool and can reference the information in its response

This ensures:

- Long AWS documentation doesn't accumulate in conversation history
- Context window remains available for actual code and conversation
- Costs stay low by not re-sending large documentation on every turn
- Agent can still use the information to answer questions

The memory management is handled automatically by `DropAndSlideConversationManager` which:

- Drops specified tool results (file_retrieval_agent + all enabled MCP tools)
- Applies sliding window management for conversation length
- Truncates results when needed

**Note**: By default, all three AWS MCP servers are disabled, so no MCP tool results will be dropped until you enable them.

## Related Documentation

- [MCP Protocol](https://modelcontextprotocol.io/)
- [AWS MCP Servers](https://awslabs.github.io/mcp/)
- [Strands MCP Integration](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/mcp-tools/)
