<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Development Guide

This guide provides comprehensive instructions for developers working on IRIS, including setup, development workflows, testing procedures, and contribution guidelines.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Development Workflows](#development-workflows)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Debugging](#debugging)
- [Contributing](#contributing)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before starting development, ensure you have the following installed:

### Required Software

- **Python 3.10+**: Core runtime environment
- **uv** (recommended) or **pip**: Package management
- **AWS CLI**: For AWS service interactions
- **Docker & Docker Compose**: For containerized development
- **Node.js & npm**: For React frontend development
- **AWS CDK CLI**: For infrastructure deployment
- **jq**: For JSON processing in scripts
- **Git**: Version control

### AWS Requirements

- **AWS Account**: With appropriate permissions
- **Amazon Bedrock Access**: Enabled in your target regions
- **IAM Permissions**: For Amazon S3, Amazon Bedrock AgentCore, AWS CloudFormation, Amazon Cognito, and Amazon Bedrock

### Installing uv (recommended)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Alternative: Using pip

If you prefer pip over uv:

```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows
```

## Development Setup

### 1. Clone and Initial Setup

```bash
# Clone the repository
git clone <your-repository-url>
cd <repository-name>   # folder created by the clone

# Install dependencies with uv (recommended)
uv sync

# Or with pip (alternative)
pip install -e .
```

### 2. Configure AWS Credentials

Choose one method for AWS authentication:

```bash
# Method 1: AWS Profile (recommended for development)
export AWS_PROFILE=your-dev-profile

# Method 2: Environment variables
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_SESSION_TOKEN=your-session-token

# Method 3: AWS CLI default profile
aws configure
```

### 3. Quick Development Start

Use the interactive deployment script for quick setup:

```bash
./deploy.sh
# Select option 1: "Local Testing (No Docker)"
```

This will:

- Install dependencies
- Generate codebase summary
- Start backend and frontend servers
- Open the application at `http://localhost:3000/`

### 4. Manual Configuration Setup

Edit `config.yaml` in the root directory before running `deploy.sh`:

```yaml
# Point to a test codebase for development
codebase_dir: /path/to/test/codebase

# Local output directory
output_dir: .iris_cache

# Model configurations - adjust based on availability
model_configuration:
  file_summarizer:
    models:
      - model_id: us.anthropic.claude-haiku-4-5-20251001-v1:0
        region: us-east-1
      - model_id: us.anthropic.claude-haiku-4-5-20251001-v1:0
        region: us-east-2
  response_generator:
    model_id: us.anthropic.claude-haiku-4-5-20251001-v1:0
    region: us-west-2

# Optional additional context
context_file: /path/to/additional/context.txt

# Ignore patterns for file processing
ignore_patterns:
  - "build/"
  - "_build/"
  - "_templates/"
  - "node_modules/"
  - ".git/"
  - "__pycache__/"
```

## Project Structure

Understanding the codebase organization is crucial for effective development:

```
iris/
├── README.md                           # Main documentation
├── config.yaml                         # Configuration file
├── deploy.sh                          # Interactive deployment script
├── pyproject.toml                     # Python project configuration
├── uv.lock                           # Dependency lock file
│
├── iris/             # Core Python package
│   ├── __init__.py
│   ├── cli.py                        # Command-line interface
│   ├── agentic_chat.py              # Main agentic chat functionality
│   ├── generate_context.py          # Context generation orchestrator
│   │
│   ├── agents/                       # Specialized agents
│   │   ├── file_retrieval_agent.py  # File discovery and retrieval
│   │   ├── code_search_tool.py      # Pattern-based code search
│   │   └── utils.py                 # Agent utilities
│   │
│   ├── common/                       # Shared components
│   │   └── monitoring.py            # Agent monitoring
│   │
│   ├── file_system/                 # File system operations
│   │   ├── file_management.py       # File discovery, processing, tree validation
│   │   └── file_utils.py           # File utilities
│   │
│   ├── prompts/                     # LLM prompts
│   │   └── prompts.yaml            # Prompt templates
│   │
│   ├── summarize/                   # File summarization
│   │   ├── file_summarizer.py      # File summarization logic
│   │   └── utils.py                # Summarization utilities
│   │
│   └── utils/                       # General utilities
│       ├── bedrock.py              # Amazon Bedrock utilities
│       ├── logging_setup.py        # Logging configuration
│       └── utils.py                # General utilities
│
├── backend/                          # AgentCore Runtime backend
│   ├── agent_runtime.py            # AgentCore Runtime entrypoint (POST /invocations, GET /ping)
│   ├── create_backend_agent.py     # Agent creation for backend
│   ├── Dockerfile.agentcore        # ARM64 backend container (bake-in mode)
│   ├── Dockerfile.agentcore_s3     # ARM64 backend container (S3 index-pull-at-boot mode)
│   └── scripts/                    # Utility scripts
│       ├── generate_summary.py     # Codebase summary generation
│       ├── create_docker_config.py # Docker configuration
│       └── upload_to_s3.py        # S3 upload utilities
│
├── frontend/                       # React frontend
│   ├── src/                        # React source code
│   ├── package.json               # Node.js dependencies
│   ├── Dockerfile                 # Frontend container
│   ├── runtime-config-dev.js      # Development configuration
│   └── runtime-config-cloud.js    # Cloud configuration
│
├── infra/                             # Infrastructure as Code
│   ├── app.py                      # CDK application entry point
│   ├── stack.py                    # CDK stack definition
│   ├── config.yaml                 # Infrastructure configuration
│   └── lambda/                     # Lambda functions
│
├── mcp_server/                      # MCP server for AI assistants
│   ├── __init__.py
│   └── mcp_server.py              # MCP server implementation
│
├── scripts/                         # Deployment scripts
│   ├── docker-compose.yml         # Docker Compose for local artifacts
│   ├── docker-compose-s3.yml      # Docker Compose for S3 artifacts
│   ├── start-docker.sh            # Start Docker with local artifacts
│   └── start-docker-s3.sh         # Start Docker with S3 artifacts
│
├── streamlit/                       # Legacy Streamlit UI (deprecated)
│   └── app.py                     # Streamlit application
│
├── docs/                            # Documentation
│   ├── agentic-architecture.md     # Agentic architecture details
│   ├── dev-guide.md               # This development guide
│   ├── deployment-guide.md         # Deployment instructions
│   ├── mcp.md                     # MCP integration details
│   ├── architecture.md            # System architecture overview
│   └── images/                    # Documentation images
│
└── tests/                          # Test suite
    └── ...                        # Test files
```

## Development Workflows

### 1. Local Development (No Docker)

This is the fastest way to develop and test changes locally:

#### Quick Start both backend and frontend

Starts both the backend AgentCore Runtime entrypoint and the React app with Vite.

```bash
uv run iris ui
```

#### Run Legacy Streamlit UI

Starts the Streamlit legacy UI. Will be sunset in future versions

```bash
uv run iris streamlit
```

#### Backend Development

```bash
# Generate codebase summary (required first step)
cd backend/
uv run python scripts/generate_summary.py --local
cd ..

# Start the AgentCore Runtime entrypoint
cd backend/
# Allow unauthenticated local access (no Cognito) and enable CORS for the dev server
export ALLOW_ANONYMOUS=true
export CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
uv run python agent_runtime.py
```

The backend will be available at `http://localhost:8080` (`POST /invocations` for chat, `GET /ping` for health).

#### Frontend Development

```bash
# Install dependencies (first time only)
cd frontend/
npm install

# Start development server with hot reloading
npm start
```

The frontend will be available at `http://localhost:3000/` with hot reloading enabled.

#### CLI Development

```bash
# Test CLI commands directly
uv run iris chat --codebase /path/to/test/codebase
uv run iris prepare --codebase /path/to/test/codebase
uv run iris ui
```

### 2. Docker Development

For testing the full containerized environment:

#### Setup Docker Configuration

```bash
cd backend/
uv run python scripts/create_docker_config.py
cd ..
```

#### Local Artifacts Testing

```bash
# Generate artifacts locally
cd backend/
uv run python scripts/generate_summary.py --local
cd ..

# Start Docker environment
./scripts/start-docker.sh --force-build
```

#### S3 Artifacts Testing

```bash
# Test with S3-stored artifacts
./scripts/start-docker-s3.sh --s3-bucket <test-bucket> --s3-prefix <prefix> --force-build
```

Access the application at `http://localhost:3000`.

#### Configure IDE Integration

See [MCP Integration Guide](mcp.md) for detailed setup instructions for Cline, Kiro CLI, and other MCP clients.

## Testing

### 1. Unit Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_specific_module.py

# Run with verbose output
uv run pytest -v
```

### 2. Integration Tests

```bash
# Test CLI functionality
uv run iris prepare --codebase tests/fixtures/sample_codebase
```

## Code Quality

### 1. Code Formatting

```bash
# Format code with black
uv run black iris/ backend/ tests/

# Sort imports with isort
uv run isort iris/ backend/ tests/
```

### 2. Linting

```bash
# Run ruff for linting and checking
uv run ruff check

# Run ruff for formatting
uv run ruff format
```

### 3. Pre-Commit Hooks

Pre-commit hooks automatically run linting checks before each commit to catch issues early. The hooks run the same checks as the GitLab CI/CD pipeline.

#### Installation

**Quick Setup (Recommended)**

Use the provided setup script to install the pre-commit hook:

```bash
# Run the setup script
./setup-hooks.sh

# Create dev virtual environment (separate from CI environment)
uv sync --group dev --python-preference only-managed
```

This will:

1. Copy the pre-commit hook from `.githooks/` to `.git/hooks/`
2. Make it executable
3. Create `.venv_dev` for development (separate from `.venv` used by deploy.sh)
4. Display next steps

**Important: Virtual Environment Separation**

The project uses two separate virtual environments:

- **`.venv_dev`** - Development environment with linting tools (created by `uv sync --group dev`)
- **`.venv`** - CI/Application environment (created by `deploy.sh`)

This separation prevents version conflicts between development and application dependencies.

**Manual Installation**

If you prefer to install manually:

```bash
# Install dev dependencies
uv sync --group dev

# Create hooks directory and copy the hook
mkdir -p .git/hooks
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

**Alternative: Using pre-commit framework**

If you prefer the pre-commit framework (note: this may conflict with git-defender on some systems):

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# (Optional) Run against all files to verify setup
pre-commit run --all-files
```

#### Usage

Once installed, the hooks will run automatically before each commit. If any checks fail, the commit will be blocked until the issues are fixed.

To run checks manually:

```bash
# Using pre-commit framework
pre-commit run --all-files

# Using the bash hook
.githooks/pre-commit
```

#### Checks Performed

The pre-commit hooks run the following checks:

- **Ruff**: Python linting and formatting
- **Codespell**: Spell checking
- **yamllint**: YAML linting
- **Prettier**: JavaScript/TypeScript/JSON/CSS/Markdown formatting
- **ShellCheck**: Shell script linting
- **Private key detection**: Prevents accidental commits of sensitive data
- **Large file detection**: Warns about files over 100MB
- **Trailing whitespace and end-of-file fixes**: Ensures consistent formatting

#### Fixing Issues

```bash
# Fix Ruff formatting issues
ruff format --exclude .venv,node_modules,.ash,dist,build,infra/cdk.out .

# Fix Prettier formatting issues
npx prettier --write "**/*.{js,jsx,ts,tsx,json,css,md,yaml,yml}" --ignore-path .gitignore

# Fix Codespell issues (review typos found)
codespell --skip='.git,.venv,node_modules,*.pyc,.ash,dist,build,package-lock.json, ./infra/*, *.log, ./IAC/cdk.out/*' .
```

#### Skipping Hooks

If you need to skip the pre-commit hooks for a specific commit (not recommended):

```bash
git commit --no-verify
```

#### Dependency Management

All linting packages are managed in `pyproject.toml` under the `[dependency-groups]` section with the `dev` group:

```toml
[dependency-groups]
dev = [
    "isort",
    "ruff",
    "yamllint",
    "codespell",
    "pre-commit",
]
```

Install all dev dependencies:

```bash
uv sync --group dev
# or
pip install -e ".[dev]"
```

## Contributing

### 1. Development Process

1. **Create Feature Branch**:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**: Follow coding standards and add tests

3. **Test Changes**:

   ```bash
   uv run pytest
   uv run black --check .
   ```

4. **Commit Changes**:

   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```

5. **Push and Create PR**:
   ```bash
   git push origin feature/your-feature-name
   # Create pull request through GitLab interface
   ```

### 2. Coding Standards

- **Python**: Follow PEP 8 style guide
- **Type Hints**: Use type hints for all function parameters and return values
- **Docstrings**: Use Google-style docstrings for all functions and classes
- **Error Handling**: Implement proper error handling and logging
- **Testing**: Write tests for all new functionality

### 3. Documentation

- Update relevant documentation for any changes
- Add docstrings to new functions and classes
- Update configuration examples if needed
- Include usage examples for new features

### 4. Performance Considerations

- **Async Operations**: Use async/await for I/O operations
- **Caching**: Implement caching for expensive operations
- **Memory Management**: Be mindful of memory usage in long-running processes
- **Token Limits**: Respect model context windows and token limits

## Troubleshooting

### Common Development Issues

#### 1. Import Errors

```bash
# Ensure package is installed in development mode
uv sync
# or
pip install -e .

# Check Python path
python -c "import sys; print(sys.path)"
```

#### 2. AWS Credential Issues

```bash
# Verify credentials
aws sts get-caller-identity

# Check profile configuration
aws configure list

# Test Amazon Bedrock access
aws bedrock list-foundation-models --region us-west-2
```

#### 3. Docker Issues

```bash
# Rebuild containers
docker-compose build --no-cache

# Check container logs
docker-compose logs agentcore-backend
docker-compose logs react-frontend

# Clean up Docker resources
docker system prune -a
```

#### 4. Frontend Issues

```bash
# Clear npm cache
npm cache clean --force

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Check for port conflicts
lsof -i :3000
lsof -i :5173
```

#### 5. Model Access Issues

```bash
# Check model availability
aws bedrock list-foundation-models --region us-west-2

# Verify model access permissions
aws bedrock get-foundation-model --model-identifier us.anthropic.claude-haiku-4-5-20251001-v1:0 --region us-west-2
```

### Performance Issues

#### 1. Slow Response Times

- Check model region proximity
- Monitor token usage and context window size
- Verify network connectivity to AWS services
- Review conversation history size

#### 2. Memory Issues

- Monitor agent memory usage
- Check for memory leaks in long-running sessions
- Review file processing batch sizes
- Optimize conversation management settings

#### 3. Rate Limiting

- Implement exponential backoff for API calls
- Monitor AWS service quotas
- Use multiple regions for load distribution
- Implement request queuing for high-volume scenarios

### Getting Help

1. **Check Logs**: Always check application logs first
2. **Review Configuration**: Verify all configuration files are correct
3. **Test Components**: Test individual components to isolate issues
4. **Documentation**: Refer to related documentation:
   - [Agentic Architecture](agentic-architecture.md)
   - [Deployment Guide](deployment-guide.md)
   - [MCP Integration](mcp.md)
   - [Architecture Overview](architecture.md)

### Development Tips

1. **Use Virtual Environments**: Always work in isolated environments
2. **Test Early and Often**: Run tests frequently during development
3. **Monitor Resource Usage**: Keep an eye on AWS costs and usage
4. **Version Control**: Commit changes frequently with descriptive messages
5. **Documentation**: Keep documentation updated as you develop

## Related Documentation

- [Agentic Architecture](agentic-architecture.md) - Detailed architecture overview
- [Deployment Guide](deployment-guide.md) - Production deployment instructions
- [MCP Integration](mcp.md) - Model Context Protocol integration
- [Architecture Overview](architecture.md) - High-level system architecture
