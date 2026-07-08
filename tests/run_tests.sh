#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Test runner script for iris
# Uses virtual environment from project root (.venv)

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="$PROJECT_ROOT/.venv"

echo -e "${GREEN}IRIS Test Runner${NC}"
echo "================================"
echo ""

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}Error: Virtual environment not found at $VENV_PATH${NC}"
    echo ""
    echo "Please run ./deploy.sh from the project root first to create the virtual environment."
    echo ""
    echo "Usage:"
    echo "  cd .."
    echo "  ./deploy.sh"
    exit 1
fi

# Activate virtual environment
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source "$VENV_PATH/Scripts/activate"
else
    source "$VENV_PATH/bin/activate"
fi

echo -e "${GREEN}✓ Virtual environment activated: $VENV_PATH${NC}"
echo ""

# Function to check AWS credentials (for integration tests)
check_aws_credentials() {
    if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_PROFILE:-}" ] && [ ! -f ~/.aws/credentials ]; then
        echo -e "${YELLOW}⚠ AWS credentials not configured${NC}"
        echo -e "${YELLOW}Integration tests will be skipped${NC}"
        echo ""
        echo "To configure AWS:"
        echo "  1. aws configure"
        echo "  2. Set AWS_PROFILE environment variable"
        echo "  3. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
        echo ""
        return 1
    fi
    return 0
}

# Parse command line arguments
TEST_TYPE="${1:-all}"

case "$TEST_TYPE" in
    unit)
        echo -e "${YELLOW}Running unit tests only (no AWS required)...${NC}"
        cd "$PROJECT_ROOT"
        pytest tests/unit/ -v
        ;;
    integration)
        if ! check_aws_credentials; then
            echo -e "${RED}Cannot run integration tests without AWS credentials${NC}"
            exit 1
        fi
        echo -e "${YELLOW}Running integration tests (requires AWS)...${NC}"
        cd "$PROJECT_ROOT"
        pytest tests/integration/ -v
        ;;
    e2e)
        if ! check_aws_credentials; then
            echo -e "${RED}Cannot run E2E tests without AWS credentials${NC}"
            exit 1
        fi
        echo -e "${YELLOW}Running E2E deployment tests...${NC}"
        cd "$PROJECT_ROOT"
        ./tests/e2e/test_deployment_e2e.sh
        ;;
    fast)
        echo -e "${YELLOW}Running fast tests (unit + no slow)...${NC}"
        cd "$PROJECT_ROOT"
        pytest tests/unit/ -m "not slow" -v
        ;;
    coverage)
        echo -e "${YELLOW}Running tests with coverage report...${NC}"
        cd "$PROJECT_ROOT"
        pytest --cov=iris --cov=backend --cov=infra --cov-report=html:tests/htmlcov --cov-report=term -v
        echo -e "${GREEN}Coverage report generated in tests/htmlcov/index.html${NC}"
        ;;
    ci)
        echo -e "${YELLOW}Running CI test suite...${NC}"
        cd "$PROJECT_ROOT"
        pytest tests/unit/ --junitxml=tests/test-results.xml --cov=iris --cov=backend --cov=infra --cov-report=xml:tests/coverage.xml -v
        ;;
    all)
        echo -e "${YELLOW}Running all tests...${NC}"
        cd "$PROJECT_ROOT"

        # Run unit tests first (fast)
        echo -e "${BLUE}1. Unit tests...${NC}"
        pytest tests/unit/ -v

        # Run integration tests if AWS is configured
        if check_aws_credentials; then
            echo -e "${BLUE}2. Integration tests...${NC}"
            pytest tests/integration/ -v

            echo -e "${BLUE}3. E2E tests...${NC}"
            ./tests/e2e/test_deployment_e2e.sh
        else
            echo -e "${YELLOW}Skipping integration and E2E tests (no AWS credentials)${NC}"
        fi
        ;;
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo ""
        echo "Usage: $0 [test_type]"
        echo ""
        echo "Test types:"
        echo "  unit        - Run unit tests only (fast, no AWS)"
        echo "  integration - Run integration tests (requires AWS)"
        echo "  e2e         - Run E2E deployment tests (requires AWS)"
        echo "  fast        - Run fast tests (unit, no slow)"
        echo "  coverage    - Run tests with coverage report"
        echo "  ci          - Run CI test suite"
        echo "  all         - Run all tests (default)"
        echo ""
        echo "Examples:"
        echo "  $0 unit        # Quick validation during development"
        echo "  $0 all         # Full test suite"
        exit 1
        ;;
esac

echo -e "${GREEN}Tests completed successfully!${NC}"
