<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# MCP Integration Guide

This guide provides comprehensive information about integrating IRIS with Model Context Protocol (MCP) servers and clients, enabling seamless integration with AI assistants and development tools.

## Table of Contents

- [Overview](#overview)
- [MCP Server Implementation](#mcp-server-implementation)
- [Client Integrations](#client-integrations)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Advanced Features](#advanced-features)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Overview

### What is MCP?

Model Context Protocol (MCP) is a standardized protocol that enables AI assistants to securely connect with external data sources and tools. IRIS implements an MCP server that provides powerful code analysis capabilities to any MCP-compatible client.

### Benefits of MCP Integration

- **Standardized Interface**: Consistent tool interface across different AI clients
- **Secure Access**: Controlled access to codebase analysis capabilities
- **Real-time Analysis**: Live code analysis within your development workflow
- **Extensible**: Easy to add new tools and capabilities
- **IDE Integration**: Direct integration with popular development environments

### Architecture

```
AI Client (Cline/Kiro/etc.) ←→ MCP Protocol ←→ IRIS MCP Server ←→ Code Analysis Engine
```

## MCP Server Implementation

### Server Location

The MCP server is implemented in `iris_mcp/mcp_server.py` and registered as a console entry point (`iris_mcp`) in `pyproject.toml`.

### Available Tools

The server exposes two tools. Both cover the codebase and, when an artifact
directory is configured, project artifacts alongside it.

#### 1. codebase_artifact_query

**Description**: Answers a question using the orchestrator agent, which decides which retrieval tools to invoke — `file_retrieval_agent` for codebase questions, `artifact_retrieval_agent` for artifact questions, or both when the query spans the two. Responses include source attribution. This operation can take 30-60+ seconds for large codebases.

**Parameters**:

- `query` (string, required): The question to evaluate against the codebase and/or project artifacts
- `codebase_dir` (string, required): The codebase directory (absolute path)
- `artifact_dir` (string, optional): The project artifacts directory (absolute path). Falls back to `artifact_dir` in `config.yaml`; leave empty to skip artifact context.

**Usage**:

```json
{
  "name": "codebase_artifact_query",
  "arguments": {
    "query": "What does this codebase do and how is it structured?",
    "codebase_dir": "/path/to/your/codebase"
  }
}
```

**Capabilities**:

- Intelligent file selection based on query relevance
- Comprehensive codebase analysis
- Artifact retrieval when artifacts are indexed
- Context-aware responses with source attribution

#### 2. codebase_artifact_context

**Description**: Generates or updates the codebase index, and the artifact index when an artifact directory is provided or configured. Run this before querying to pre-generate context.

**Parameters**:

- `codebase_dir` (string, required): The codebase directory (absolute path)
- `artifact_dir` (string, optional): The project artifacts directory (absolute path). Falls back to `artifact_dir` in `config.yaml`; leave empty to skip artifact indexing.

**Usage**:

```json
{
  "name": "codebase_artifact_context",
  "arguments": {
    "codebase_dir": "/path/to/your/codebase"
  }
}
```

**Capabilities**:

- Generate comprehensive codebase overview
- Update existing context with file changes
- Index project artifacts by phase when configured
- Provide structured codebase information
- File relationship mapping

### Tool Enablement

Tools can be selectively enabled via the `mcp_enabled_tools` setting in `config.yaml`:

```yaml
# MCP Server: List of tools to enable (default: all)
# Options: "all", "codebase_artifact_context", "codebase_artifact_query"
mcp_enabled_tools:
  - all
```

To enable only a specific tool:

```yaml
mcp_enabled_tools:
  - codebase_artifact_context
```

Both tools index and query project artifacts alongside the codebase. See [artifact-indexing.md](artifact-indexing.md) for details on how artifacts are organized and indexed.

### Server Configuration

The MCP server loads configuration from `config.yaml` (or falls back to `config_template.yaml`) in the project root automatically. No config path needs to be passed — the server resolves it internally via `load_default_config()`.

Key config sections used by the MCP server:

```yaml
# MCP Server: List of tools to enable (default: all)
mcp_enabled_tools:
  - all

# AWS Bedrock model configurations
model_configuration:
  file_summarizer:
    models:
      - model_id: us.anthropic.claude-haiku-4-5-20251001-v1:0
        region: us-west-2
  response_generator:
    model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
    region: us-west-2

# File patterns to ignore
ignore_patterns:
  - "build/"
  - "node_modules/"
  - ".git/"
```

## Client Integrations

### Cline Integration

Cline is a popular AI assistant that supports MCP integration for enhanced development capabilities.

#### Configuration Setup

**Method 1: Using AWS Profile (Recommended)**

Create or edit your Cline MCP configuration file:

```json
{
  "mcpServers": {
    "iris-server": {
      "command": "bash",
      "timeout": 600000,
      "args": ["-c", "source /path/to/your/venv/bin/activate && python /path/to/iris/iris_mcp/mcp_server.py"],
      "env": {
        "AWS_PROFILE": "your-aws-profile-name"
      },
      "alwaysAllow": ["codebase_artifact_query", "codebase_artifact_context"],
      "disabled": false
    }
  }
}
```

**Method 2: Using AWS Access Keys**

```json
{
  "mcpServers": {
    "iris-server": {
      "command": "bash",
      "timeout": 600000,
      "args": ["-c", "source /path/to/your/venv/bin/activate && python /path/to/iris/iris_mcp/mcp_server.py"],
      "env": {
        "AWS_ACCESS_KEY_ID": "<your-access-key-id>",
        "AWS_SECRET_ACCESS_KEY": "<your-secret-access-key>",
        "AWS_SESSION_TOKEN": "<your-session-token>"
      },
      "alwaysAllow": ["codebase_artifact_query", "codebase_artifact_context"],
      "disabled": false
    }
  }
}
```

#### Quick Setup

1. **Install MCP with Cline**:

   Open Cline and use a prompt to install `iris_mcp/mcp_server.py`:

   `Install the IRIS mcp server from iris_mcp/mcp_server.py`

#### Manual Setup Steps

1. **Access MCP Configuration**:

   Open Cline and select MCP from the sidebar.

2. **Configure MCP Servers**:

   Click "Install and Configure MCP Servers".

3. **Add Server Configuration**:

   Add the JSON configuration from above to your MCP settings.

4. **Verify Installation**:

   The server should appear under the "Installed" section.

5. **Test Integration**:

   In Cline, enter:

   ```
   use codebase_artifact_query to analyze: What does this codebase do?
   ```

   You should see the tool run and return a summary of the codebase.

### Kiro Integration

Kiro provides advanced AI assistance with MCP support for development workflows. Both Kiro CLI and Kiro IDE share the same MCP configuration file, so the setup below applies to either.

#### Configuration Setup

**Method 1: Using the Kiro CLI Command**

```bash
kiro-cli mcp add --name iris \
  --command /path/to/your/venv/bin/python \
  --args /path/to/iris/iris_mcp/mcp_server.py
```

**Method 2: Manual Configuration**

Create or edit `~/.kiro/settings/mcp.json` (use `.kiro/settings/mcp.json` in a project for workspace-level scope):

```json
{
  "mcpServers": {
    "iris-server": {
      "command": "bash",
      "timeout": 600000,
      "args": ["-c", "source /path/to/your/venv/bin/activate && python /path/to/iris/iris_mcp/mcp_server.py"],
      "env": {
        "AWS_PROFILE": "your-aws-profile-name"
      },
      "disabled": false
    }
  }
}
```

> **Legacy Amazon Q Developer CLI:** Amazon Q Developer CLI was rebranded to Kiro CLI. If you have not yet migrated, the older client reads the same JSON format from `~/.aws/amazonq/mcp.json`. On upgrading to Kiro CLI this file is migrated automatically to `~/.kiro/settings/mcp.json`.

## Configuration

### Path Configuration

Ensure all paths in your MCP configuration are absolute paths:

```json
{
  "command": "/Users/username/.local/share/uv/python/cpython-3.11.9-macos-aarch64-none/bin/python",
  "args": [
    "/Users/username/projects/iris/iris_mcp/mcp_server.py"
  ]
}
```

### Timeout Configuration

Set appropriate timeouts for complex codebase analysis:

```json
{
  "timeout": 600,
  "alwaysAllow": ["codebase_artifact_query", "codebase_artifact_context"]
}
```

### Security Configuration

For enhanced security, limit tool access:

```json
{
  "alwaysAllow": ["codebase_artifact_query"],
  "disabled": false,
  "autoApprove": []
}
```

## Usage Examples

### Basic Codebase Analysis

```
use codebase_artifact_query to answer: What does this codebase do?
```

**Expected Response**:

- High-level overview of the codebase purpose
- Main components and their functions
- Technology stack and dependencies
- Architecture patterns used

### Specific Feature Analysis

```
use codebase_artifact_query to analyze: How does the authentication system work?
```

**Expected Response**:

- Authentication flow description
- Relevant files and components
- Security considerations
- Integration points

### Code Structure Investigation

```
use codebase_artifact_query to explain: How is the project structured and what are the main modules?
```

**Expected Response**:

- Directory structure overview
- Module descriptions and purposes
- Inter-module dependencies
- Entry points and main workflows

### Debugging Assistance

```
use codebase_artifact_query to help: I'm getting an error in the user login flow. Can you help me understand how it works?
```

**Expected Response**:

- Login flow analysis
- Potential error sources
- Relevant code sections
- Debugging suggestions

### Documentation Generation

```
use codebase_artifact_query to create: Generate documentation for the API endpoints in this codebase
```

**Expected Response**:

- API endpoint documentation
- Request/response formats
- Authentication requirements
- Usage examples

### Context Generation

```
use codebase_artifact_context to generate a comprehensive overview of this codebase
```

**Expected Response**:

- Complete codebase context
- File summaries and relationships
- Directory tree structure
- Technology stack analysis
- Artifact indexing status when an artifact directory is configured

## Advanced Features

### Custom Workflows with .clinerules

Create a `.clinerules` file to define custom workflows:

```markdown
# IRIS Workflow Rules

## Analysis Workflow

When analyzing a new codebase:

1. First use `codebase_artifact_context` to understand the overall structure
2. Then use `codebase_artifact_query` for specific questions
3. Always provide code examples when explaining functionality

## Documentation Workflow

When generating documentation:

1. Use `codebase_artifact_query` to understand the component
2. Generate comprehensive documentation with examples
3. Include usage patterns and best practices

## Debugging Workflow

When debugging issues:

1. Use `codebase_artifact_query` to understand the relevant code flow
2. Identify potential error sources
3. Suggest specific debugging steps and tools
```

### Multi-turn Conversations

The MCP server supports multi-turn conversations for complex analysis:

```
# Turn 1
use codebase_artifact_query to analyze: What are the main components of this system?

# Turn 2 (building on previous context)
use codebase_artifact_query to explain: How do these components interact with each other?

# Turn 3 (continuing the conversation)
use codebase_artifact_query to identify: What are potential scalability bottlenecks in this architecture?
```

## Troubleshooting

### Common Issues

#### 1. MCP Server Not Starting

**Symptoms**:

- "Failed to connect to MCP server" errors
- Server not appearing in client interface
- Timeout errors during startup

**Solutions**:

```bash
# Test MCP server directly
cd /path/to/iris
python iris_mcp/mcp_server.py

# Or via the installed entry point
iris_mcp

# Check Python path
which python
/path/to/your/venv/bin/python --version

# Verify dependencies
pip list | grep -E "(mcp|boto3|pydantic)"

# Check AWS credentials
aws sts get-caller-identity
```

#### 2. AWS Credential Issues

**Symptoms**:

- "Unable to locate credentials" errors
- "Access denied" errors
- Authentication failures

**Solutions**:

```bash
# Verify AWS profile
aws configure list --profile your-profile

# Test Bedrock access
aws bedrock list-foundation-models --region us-west-2 --profile your-profile

# Check environment variables
echo $AWS_PROFILE
echo $AWS_ACCESS_KEY_ID
```

#### 3. Configuration Path Issues

**Symptoms**:

- "Config file not found" errors
- "Codebase directory not found" errors
- Permission denied errors

**Solutions**:

```bash
# Verify config file exists
ls -la /path/to/iris/config.yaml

# Check file permissions
ls -la /path/to/codebase/

# Test with absolute paths
python -c "import os; print(os.path.abspath('config.yaml'))"
```

#### 4. Tool Execution Failures

**Symptoms**:

- Tools not responding
- Timeout errors
- Incomplete responses

**Solutions**:

```bash
# Increase timeout in MCP configuration
{
  "timeout": 900
}

# Check system resources
top
df -h

# Monitor MCP server logs (logs go to stderr)
python iris_mcp/mcp_server.py 2>mcp_server.log &
tail -f mcp_server.log
```

### Debugging Tips

#### 1. Enable Debug Logging

Add to your MCP configuration:

```json
{
  "env": {
    "LOG_LEVEL": "DEBUG",
    "PYTHONUNBUFFERED": "1"
  }
}
```

#### 2. Test MCP Server Independently

```bash
# Run MCP server in standalone mode
cd /path/to/iris
python iris_mcp/mcp_server.py
```

#### 3. Verify Client Configuration

```bash
# Check MCP client configuration
cat ~/.kiro/settings/mcp.json  # For Kiro CLI

# Validate JSON syntax
python -m json.tool ~/.kiro/settings/mcp.json
```

#### 4. Monitor Resource Usage

```bash
# Monitor memory usage
ps aux | grep mcp_server

# Monitor file handles
lsof -p $(pgrep -f mcp_server)

# Check disk space
df -h /path/to/iris
```

### Performance Optimization

#### 1. Model Selection

Use faster models for development:

```yaml
model_configuration:
  response_generator:
    model_id: us.anthropic.claude-haiku-4-5-20251001-v1:0 # Faster model
    region: us-west-2
```

#### 2. Context Window Management

Optimize context window usage:

```yaml
context_window_size: 100000 # Smaller for faster processing
```

## Development

### Adding New Tools

IRIS supports MCP Python SDK `>=1.23,<2.2`. MCP 2.0 and 2.1 expose `MCPServer`; MCP 1.x uses the compatible `FastMCP` implementation, aliased to the same local name:

```python
from mcp import server as mcp_server

if hasattr(mcp_server, "MCPServer"):
    MCPServer = mcp_server.MCPServer
else:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer
from pydantic import Field

mcp = MCPServer("iris", lifespan=lifespan)

# Define the tool function
async def my_new_tool(
    param: str = Field(description="Parameter description"),
):
    """Tool docstring becomes the MCP tool description."""
    # Implement tool logic
    return "result"

# Register conditionally based on mcp_enabled_tools config
if is_tool_enabled("my_new_tool", enabled_tools):
    mcp.tool()(my_new_tool)
```

Remember to add the new tool name to the valid set in `get_enabled_tools()`:

```python
valid_tools = {
    "all",
    "codebase_artifact_context",
    "codebase_artifact_query",
    "my_new_tool",
}
```

### Testing MCP Integration

#### Integration Tests

```bash
# Test the stdio contract with the installed MCP SDK version
.venv/bin/pytest -q tests/integration/test_mcp.py
```

### Custom Client Integration

The server accepts MCP SDK `>=1.23,<2.2` stdio clients. This example uses the MCP 2.x high-level client:

```python
import asyncio
from mcp import Client, StdioServerParameters

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["/path/to/iris/iris_mcp/mcp_server.py"]
    )

    async with Client(server_params) as client:
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools.tools]}")

        result = await client.call_tool(
            "codebase_artifact_query",
            {
                "query": "What does this codebase do?",
                "codebase_dir": "/path/to/your/codebase"
            }
        )
        print(f"Result: {result.content[0].text}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Related Documentation

- [Development Guide](dev-guide.md) - Development setup and workflows
- [Agentic Architecture](agentic-architecture.md) - Detailed architecture overview
- [Deployment Guide](deployment-guide.md) - Deployment instructions
- [Architecture Overview](architecture.md) - High-level system architecture

## External Resources

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [Cline MCP Integration Guide](https://github.com/cline/cline/blob/main/docs/mcp.md)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Strands Framework Documentation](https://strandsagents.com/latest/)
