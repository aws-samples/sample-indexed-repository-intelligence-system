#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# End-to-end deployment testing script
# Tests the deployment workflows from deploy.sh

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Deployment Workflow Tests${NC}"
echo "================================"
echo ""

# Test 1: Prerequisites check
echo "Test 1: Checking prerequisites..."
if command -v aws &> /dev/null; then
    echo -e "${GREEN}✓ AWS CLI found${NC}"
else
    echo -e "${RED}✗ AWS CLI not found${NC}"
    exit 1
fi

if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Docker found${NC}"
else
    echo -e "${YELLOW}⚠ Docker not found (optional)${NC}"
fi

if command -v python3 &> /dev/null; then
    echo -e "${GREEN}✓ Python found${NC}"
else
    echo -e "${RED}✗ Python not found${NC}"
    exit 1
fi

echo ""

# Test 2: Configuration files
echo "Test 2: Validating configuration files..."
if [ -f "config.yaml" ]; then
    echo -e "${GREEN}✓ config.yaml exists${NC}"
else
    echo -e "${RED}✗ config.yaml missing${NC}"
    exit 1
fi

if [ -f "infra/config.yaml" ]; then
    echo -e "${GREEN}✓ infra/config.yaml exists${NC}"
else
    echo -e "${RED}✗ infra/config.yaml missing${NC}"
    exit 1
fi

echo ""

# Test 3: Backend scripts
echo "Test 3: Testing backend scripts..."
if python backend/scripts/generate_summary.py --help &> /dev/null; then
    echo -e "${GREEN}✓ generate_summary.py works${NC}"
else
    echo -e "${RED}✗ generate_summary.py failed${NC}"
    exit 1
fi

if python backend/scripts/show_project_tree.py &> /dev/null; then
    echo -e "${GREEN}✓ show_project_tree.py works${NC}"
else
    echo -e "${RED}✗ show_project_tree.py failed${NC}"
    exit 1
fi

echo ""

# Test 4: Docker builds (if Docker available)
if command -v docker &> /dev/null; then
    if [ -d "codebase_artifacts" ]; then
        echo "Test 4: Testing Docker builds..."

        echo "  Building backend..."
        if docker build -f backend/Dockerfile -t test-backend . &> /dev/null; then
            echo -e "${GREEN}✓ Backend Docker build successful${NC}"
        else
            echo -e "${RED}✗ Backend Docker build failed${NC}"
            exit 1
        fi

        echo "  Building frontend..."
        if docker build -f frontend/Dockerfile -t test-frontend frontend/ &> /dev/null; then
            echo -e "${GREEN}✓ Frontend Docker build successful${NC}"
        else
            echo -e "${RED}✗ Frontend Docker build failed${NC}"
            exit 1
        fi
    else
        echo "Test 4: Skipping Docker tests (codebase_artifacts not present)"
    fi
else
    echo "Test 4: Skipping Docker tests (Docker not available)"
fi

echo ""

# Test 5: CDK synthesis (if CDK available)
if command -v cdk &> /dev/null; then
    echo "Test 5: Testing CDK synthesis..."
    cd infra
    # Set default region if not already set
    export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
    if cdk synth --no-lookups &> /dev/null; then
        echo -e "${GREEN}✓ CDK synthesis successful${NC}"
    else
        echo -e "${RED}✗ CDK synthesis failed${NC}"
        echo "Run 'cd infra && cdk synth --no-lookups' to see detailed error"
        cd ..
        exit 1
    fi
    cd ..
else
    echo "Test 5: Skipping CDK test (CDK not available)"
fi

echo ""
echo -e "${GREEN}All deployment tests passed!${NC}"
echo ""
echo "Note: These tests validate deployment components."
echo "Full deployment testing requires:"
echo "  - AWS credentials configured"
echo "  - S3 bucket for artifacts"
echo "  - Manual testing of deploy.sh workflows"
