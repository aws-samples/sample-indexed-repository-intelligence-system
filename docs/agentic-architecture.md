<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Agentic Architecture

IRIS leverages a sophisticated agentic architecture built on the Strands framework to provide intelligent code analysis and interaction capabilities. This document outlines the core architectural components and their interactions.

## Overview

The agentic architecture consists of specialized agents that work together to understand, analyze, and interact with codebases. Each agent has specific responsibilities and tools, enabling modular and efficient processing of user queries.

## Core Components

### 1. Main Agent (Agentic Chat)

**Location**: `iris/agentic_chat.py`

The main orchestrating agent that handles user interactions and coordinates between specialized sub-agents. Key features:

- **Conversation Management**: Uses `DropAndSlideConversationManager` for efficient memory management
- **Tool Coordination**: Orchestrates calls to specialized agents
- **Session Handling**: Manages conversation state and context
- **Streaming Support**: Provides real-time response streaming

**Key Components**:

- `DropAndSlideConversationManager`: Custom conversation manager that drops tool results for specific tools after each turn, then applies sliding window management
- Integration with Strands framework for agent lifecycle management
- Amazon Bedrock model integration for LLM capabilities

### 2. File Retrieval Agent

**Location**: `iris/agents/file_retrieval_agent.py`

Specialized agent responsible for intelligent file discovery and content retrieval.

**Capabilities**:

- **Two-Stage Process**:
  1. **File Identification**: Analyzes codebase overview to identify relevant files
  2. **File Loading**: Loads identified files and generates comprehensive context
- **Context-Aware Selection**: Uses codebase summaries and file relationships
- **Efficient Loading**: Respects context window limits when reading files

**Tool Definition**:

```python
@tool
def file_retrieval_agent(query: str) -> str:
    """
    Return contents helpful for answer questions.

    Performs intelligent file identification and loading based on query analysis.
    """
```

### 3. Code Search Tool

**Location**: `iris/agents/code_search_tool.py`

Fast grep-based search tool for finding patterns across the codebase. Much faster and more accurate than LLM-based file scanning for specific keyword searches.

**Capabilities**:

- **Pattern Search**: Find function definitions, class names, imports, TODOs, etc.
- **Regex Support**: Full regex pattern matching
- **File Filtering**: Search only specific file types (e.g., `*.py`, `*.js`)
- **Context Lines**: Show surrounding lines for each match
- **Config-Aware**: Respects `ignore_patterns` from `config.yaml`

**Tool Definition**:

```python
@tool
def code_search_tool(
    pattern: str,
    case_sensitive: bool = False,
    max_results: int = 50,
    context_lines: int = 2,
    file_pattern: Optional[str] = None,
) -> str:
    """
    Search the codebase for a pattern using grep.

    Fast, accurate keyword search that returns matching lines with file paths
    and line numbers.
    """
```

**Usage Examples**:

- Find function definitions: `pattern="def calculate"`
- Find class definitions: `pattern="^class.*Agent", file_pattern="*.py"`
- Find TODO comments: `pattern="TODO|FIXME"`
- Case-sensitive search: `pattern="Config", case_sensitive=True`

## Architecture Flow

### 1. Context Generation Pipeline

```
User Query → Context Generation → File Analysis → Summarization → Response
```

**Components**:

- **File Management** (`file_system/file_management.py`): Handles file discovery and processing
- **Summarization** (`summarize/file_summarizer.py`): Creates intelligent file summaries
- **Context Generation** (`generate_context.py`): Orchestrates the full pipeline

### 2. Response Generation Pipeline

```
User Query → Orchestrator Agent → Tool Calls (file retrieval / code search) → Streaming Response
```

**Components**:

- **Orchestrator Agent** (`agentic_chat.py`): Strands agent that plans the response and decides which tools to invoke
- **File Retrieval Agent** (`agents/file_retrieval_agent.py`): Identifies and loads relevant files for a query
- **Code Search Tool** (`agents/code_search_tool.py`): Pattern-based search across the codebase
- **Streaming Handler**: Provides real-time response delivery via `agent.stream_async`

### 3. Agent Interaction Flow

```
Main Agent → Tool Selection → Specialized Agent → Tool Execution → Result Integration
```

## Key Design Patterns

### 1. Tool-Based Architecture

Each agent is equipped with specific tools that define its capabilities:

```python
# File Retrieval Agent Tools
- Codebase analysis
- File identification
- Content loading

# Code Search Tool
- Pattern-based grep search
- File type filtering
- Context line display

```

### 2. Conversation Management

**DropAndSlideConversationManager**:

- Drops tool results for specific tools after each turn
- Applies sliding window management for memory efficiency
- Maintains conversation context while managing token limits

### 3. Modular Agent Design

Each agent has a specific responsibility:

- **Separation of Concerns**: File retrieval vs. code search
- **Specialized Tools**: Each agent has tools suited to its purpose
- **Reusable Components**: Shared utilities and configurations

## Configuration and Setup

### Model Configuration

Agents use Amazon Bedrock models with specific configurations:

```yaml
model_configuration:
  file_summarizer:
    models:
      - model_id: us.anthropic.claude-haiku-4-5-20251001-v1:0
        region: us-east-1
  response_generator:
    model_id: us.anthropic.claude-haiku-4-5-20251001-v1:0
    region: us-west-2
```

### Agent Initialization

Agents are initialized with:

- **System Messages**: Define agent behavior and capabilities
- **Model Configuration**: Specify which Amazon Bedrock models to use
- **Tools**: Available functions the agent can call
- **Temperature**: Control response creativity/determinism

## Monitoring and Observability

### Agent Monitor

**Location**: `common/monitoring.py`

Provides comprehensive monitoring capabilities:

- **Performance Tracking**: Monitor agent execution times
- **Tool Usage Analytics**: Track which tools are used most frequently
- **Error Monitoring**: Capture and analyze failures
- **Resource Utilization**: Monitor token usage and API calls

### Logging

Comprehensive logging throughout the architecture:

- **Agent Actions**: Log all agent decisions and tool calls
- **Performance Metrics**: Track response times and resource usage
- **Error Tracking**: Detailed error logs for debugging
- **User Interactions**: Audit trail of user queries and responses

## Integration Points

### 1. Strands Framework Integration

The architecture leverages the Strands framework for:

- **Agent Lifecycle Management**: Creation, execution, and cleanup
- **Tool Registration**: Automatic tool discovery and registration
- **Conversation Management**: Built-in conversation handling
- **Model Integration**: Seamless Amazon Bedrock model integration

### 2. AgentCore Runtime Integration

For real-time applications, the agent is hosted on Amazon Bedrock AgentCore Runtime (`backend/agent_runtime.py`):

- **Session Management**: Each `runtimeSessionId` gets its own isolated microVM and a per-session agent with in-memory conversation history
- **Streaming Responses**: Real-time response delivery over Server-Sent Events
- **Tool Visualization**: Live updates on tool usage
- **Error Handling**: Graceful error recovery and user notification

### 3. MCP Integration

Model Context Protocol integration enables:

- **External Tool Access**: Integration with IDE tools and external systems
- **Standardized Interface**: Consistent tool interface across different clients
- **Extensibility**: Easy addition of new tools and capabilities

## Performance Optimizations

### 1. Parallel Processing

- **Multi-Model Support**: Use multiple models/regions for faster processing
- **Concurrent File Processing**: Process multiple files simultaneously
- **Async Operations**: Non-blocking operations for better responsiveness

### 2. Caching Strategies

- **Prompt Caching**: Cache frequently used prompts
- **File Content Caching**: Cache file summaries and analysis
- **Context Reuse**: Reuse generated context across sessions

### 3. Memory Management

- **Sliding Window**: Manage conversation history efficiently
- **Tool Result Dropping**: Remove large tool results to save memory
- **Context Window Optimization**: Intelligent context size management

## Security Considerations

### 1. File Access Control

- **Path Validation**: Ensure file access is within allowed directories
- **Permission Checking**: Verify read/write permissions before operations
- **Sanitization**: Clean user inputs to prevent injection attacks

### 2. Model Security

- **Credential Management**: Secure handling of AWS credentials
- **Rate Limiting**: Prevent abuse of model APIs
- **Input Validation**: Validate all inputs before processing

### 3. Session Security

- **Session Isolation**: Each session has isolated context
- **Cleanup**: Proper cleanup of session data
- **Audit Logging**: Track all user actions for security auditing

## Future Enhancements

### 1. Additional Agents

Potential new specialized agents:

- **Testing Agent**: Automated test generation and execution
- **Documentation Agent**: Automatic documentation generation
- **Refactoring Agent**: Large-scale code refactoring operations
- **Security Agent**: Security analysis and vulnerability detection

### 2. Enhanced Tool Integration

- **IDE Integration**: Direct integration with popular IDEs
- **Version Control**: Git operations and branch management
- **Build System Integration**: Integration with build tools and CI/CD
- **Database Tools**: Database schema analysis and query generation

### 3. Advanced Analytics

- **Code Quality Metrics**: Automated code quality assessment
- **Performance Analysis**: Code performance optimization suggestions
- **Dependency Analysis**: Advanced dependency tracking and management
- **Technical Debt Detection**: Identify and prioritize technical debt

## Troubleshooting

### Common Issues

1. **Agent Initialization Failures**
   - Check AWS credentials and permissions
   - Verify model availability in specified regions
   - Ensure configuration files are properly formatted

2. **Tool Execution Errors**
   - Check file paths and existence
   - Monitor token limits and context windows

3. **Performance Issues**
   - Review conversation history size
   - Check for memory leaks in long-running sessions
   - Monitor API rate limits and quotas

### Debugging Tips

1. **Enable Verbose Logging**: Set log level to DEBUG for detailed information
2. **Monitor Agent State**: Use the monitoring system to track agent behavior
3. **Test Individual Tools**: Test each tool separately to isolate issues
4. **Check Configuration**: Verify all configuration parameters are correct

## Related Documentation

- [Development Guide](dev-guide.md) - Setup and development workflows
- [Deployment Guide](deployment-guide.md) - Deployment instructions and best practices
- [Architecture Overview](architecture.md) - High-level system architecture
- [MCP Integration](mcp.md) - Model Context Protocol integration details
