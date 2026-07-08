#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# Script to start Docker Compose with AWS credentials from your environment
# This keeps credentials secure and out of docker-compose.yml

# Parse arguments
FORCE_BUILD=false
DOCKER_ARGS=()

for arg in "$@"; do
    case $arg in
        --force_build|--force-build)
            FORCE_BUILD=true
            ;;
        *)
            DOCKER_ARGS+=("$arg")
            ;;
    esac
done

echo "🚀 Starting IRIS WebSocket Backend with Docker Compose..."

# Check if AWS credentials are available
if [ -z "$AWS_ACCESS_KEY_ID" ] && [ -z "$AWS_PROFILE" ] && [ ! -f ~/.aws/credentials ]; then
    echo "❌ No AWS credentials found!"
    echo "Please either:"
    echo "  1. Set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
    echo "  2. Set AWS_PROFILE environment variable"
    echo "  3. Configure AWS CLI: aws configure"
    echo "  4. Use AWS SSO: aws sso login"
    exit 1
fi

# Export AWS credentials to make them available to docker-compose
if [ -n "$AWS_ACCESS_KEY_ID" ]; then
    echo "✅ Using AWS credentials from environment variables"
    export AWS_ACCESS_KEY_ID
    export AWS_SECRET_ACCESS_KEY
    export AWS_SESSION_TOKEN
    export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
    export AWS_REGION=${AWS_REGION:-us-east-1}
elif [ -n "$AWS_PROFILE" ]; then
    echo "✅ Fetching temporary credentials from AWS profile: $AWS_PROFILE"

    # Use AWS CLI to get temporary credentials from the profile
    if TEMP_CREDS=$(aws configure export-credentials --profile "$AWS_PROFILE" --format env 2>/dev/null) && [ -n "$TEMP_CREDS" ]; then
        # Export the temporary credentials
        eval "$TEMP_CREDS"
        echo "✅ Successfully fetched temporary credentials"
    else
        echo "⚠️  Failed to fetch credentials with export-credentials, trying sts get-session-token..."

        # Fallback: try to get session token (works for regular IAM users)
        if TEMP_CREDS=$(aws sts get-session-token --profile "$AWS_PROFILE" --output json 2>/dev/null) && [ -n "$TEMP_CREDS" ]; then
            AWS_ACCESS_KEY_ID=$(echo "$TEMP_CREDS" | jq -r '.Credentials.AccessKeyId')
            export AWS_ACCESS_KEY_ID
            AWS_SECRET_ACCESS_KEY=$(echo "$TEMP_CREDS" | jq -r '.Credentials.SecretAccessKey')
            export AWS_SECRET_ACCESS_KEY
            AWS_SESSION_TOKEN=$(echo "$TEMP_CREDS" | jq -r '.Credentials.SessionToken')
            export AWS_SESSION_TOKEN
            echo "✅ Successfully fetched session token"
        else
            echo "❌ Failed to fetch temporary credentials from profile $AWS_PROFILE"
            echo "Please ensure your AWS profile is configured correctly and you have jq installed"
            exit 1
        fi
    fi
    export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
    export AWS_REGION=${AWS_REGION:-us-east-1}
else
    echo "✅ Using AWS credentials from ~/.aws/credentials (default profile)"

    # Try to get credentials from default profile
    if TEMP_CREDS=$(aws configure export-credentials --format env 2>/dev/null) && [ -n "$TEMP_CREDS" ]; then
        eval "$TEMP_CREDS"
        echo "✅ Successfully fetched credentials from default profile"
    fi

    export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
    export AWS_REGION=${AWS_REGION:-us-east-1}
fi

# Start docker-compose with buildx for Mac
echo "🐳 Building and starting containers with buildx for Mac..."
export DOCKER_DEFAULT_PLATFORM=linux/arm64
export DEV_MODE=true
export BUILD_MODE=dev

if [ "$FORCE_BUILD" = true ]; then
    echo "🔨 Force rebuilding with --build..."
    echo "🧹 Clearing Docker build cache..."
    docker builder prune -f
    docker-compose -f scripts/docker-compose.yml build --no-cache
    docker-compose -f scripts/docker-compose.yml up "${DOCKER_ARGS[@]}"
else
    docker-compose -f scripts/docker-compose.yml up "${DOCKER_ARGS[@]}"
fi
