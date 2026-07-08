#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# Script to start Docker Compose with S3 support (frontend + backend)
# Usage: ./scripts/start-docker-s3.sh --s3-bucket <bucket> [--s3-prefix <prefix>] [--force-build]

S3_BUCKET=""
S3_PREFIX=""
FORCE_BUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --s3-bucket)
            S3_BUCKET="$2"
            shift 2
            ;;
        --s3-prefix)
            S3_PREFIX="$2"
            shift 2
            ;;
        --force-build)
            FORCE_BUILD=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --s3-bucket <bucket> [--s3-prefix <prefix>] [--force-build]"
            exit 1
            ;;
    esac
done

if [ -z "$S3_BUCKET" ]; then
    echo "Error: --s3-bucket is required"
    echo "Usage: $0 --s3-bucket <bucket> [--s3-prefix <prefix>] [--force-build]"
    echo "Example: $0 --s3-bucket my-bucket --s3-prefix my-prefix"
    echo "Example: $0 --s3-bucket my-bucket --force-build"
    exit 1
fi

echo "🚀 Starting IRIS with S3 support (Frontend + Backend)..."
echo "📦 S3 Bucket: $S3_BUCKET"
if [ -n "$S3_PREFIX" ] && [ "$S3_PREFIX" != "" ]; then
    echo "📁 S3 Prefix: $S3_PREFIX"
else
    echo "📁 S3 Prefix: (none)"
    S3_PREFIX=""
fi

# Export S3 variables
export S3_BUCKET
export S3_PREFIX

# Check AWS credentials
if [ -z "$AWS_ACCESS_KEY_ID" ] && [ -z "$AWS_PROFILE" ] && [ ! -f ~/.aws/credentials ]; then
    echo "❌ No AWS credentials found!"
    echo "Please set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or AWS_PROFILE"
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
export DEV_MODE=true
export BUILD_MODE=dev

echo "🐳 Starting containers with S3 support..."

if [ "$FORCE_BUILD" = true ]; then
    echo "🔨 Force rebuilding with --build..."
    echo "🧹 Clearing Docker build cache..."
    docker builder prune -f
    docker-compose -f scripts/docker-compose-s3.yml build --no-cache
    docker-compose -f scripts/docker-compose-s3.yml up
else
    docker-compose -f scripts/docker-compose-s3.yml up
fi
