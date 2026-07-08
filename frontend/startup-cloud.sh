#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# Cloud deployment startup script for React app
# This script fetches runtime configuration from AWS and starts the application

set -e

echo "🚀 Starting IRIS React App (Cloud Mode)"
echo "=================================================="

# Set default values
export DEPLOYMENT_MODE=${DEPLOYMENT_MODE:-cloud}
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
export VITE_AWS_REGION=${VITE_AWS_REGION:-$AWS_DEFAULT_REGION}

echo "📍 Region: $AWS_DEFAULT_REGION"
echo "🔧 Deployment Mode: $DEPLOYMENT_MODE"

# Function to get CloudFormation stack outputs
get_stack_output() {
    local stack_name=$1
    local output_key=$2

    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$AWS_DEFAULT_REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text 2>/dev/null || echo ""
}

# Function to get parameter from Systems Manager Parameter Store
get_parameter() {
    local parameter_name=$1

    aws ssm get-parameter \
        --name "$parameter_name" \
        --region "$AWS_DEFAULT_REGION" \
        --query "Parameter.Value" \
        --output text 2>/dev/null || echo ""
}

# Use environment variables directly from CDK (no CloudFormation fetch needed)
echo "🔍 Using Cognito configuration from environment variables..."
echo "   - USER_POOL_ID: ${USER_POOL_ID:0:15}..."
echo "   - USER_POOL_CLIENT_ID: ${USER_POOL_CLIENT_ID:0:15}..."
echo "   - AWS_REGION: ${AWS_REGION}"

# If CloudFormation outputs are not available, try environment variables
if [ -z "$USER_POOL_ID" ] && [ -n "$VITE_USER_POOL_ID" ]; then
    USER_POOL_ID="$VITE_USER_POOL_ID"
    echo "📝 Using USER_POOL_ID from environment variable"
fi

if [ -z "$USER_POOL_CLIENT_ID" ] && [ -n "$VITE_USER_POOL_CLIENT_ID" ]; then
    USER_POOL_CLIENT_ID="$VITE_USER_POOL_CLIENT_ID"
    echo "📝 Using USER_POOL_CLIENT_ID from environment variable"
fi

# Set runtime environment variables
if [ -n "$USER_POOL_ID" ]; then
    export USER_POOL_ID="$USER_POOL_ID"
    export VITE_USER_POOL_ID="$USER_POOL_ID"
    echo "✅ Cognito User Pool ID: ${USER_POOL_ID:0:10}..."
else
    echo "⚠️  Warning: Cognito User Pool ID not found"
fi

if [ -n "$USER_POOL_CLIENT_ID" ]; then
    export USER_POOL_CLIENT_ID="$USER_POOL_CLIENT_ID"
    export VITE_USER_POOL_CLIENT_ID="$USER_POOL_CLIENT_ID"
    echo "✅ Cognito User Pool Client ID: ${USER_POOL_CLIENT_ID:0:10}..."
else
    echo "⚠️  Warning: Cognito User Pool Client ID not found"
fi

if [ -n "$AUTH_METHOD" ]; then
    export VITE_AUTH_METHOD="$AUTH_METHOD"
    echo "✅ Auth Method: $AUTH_METHOD"
fi

# Display Cognito configuration for debugging
echo "🔍 Cognito Configuration:"
echo "   - Region: ${AWS_DEFAULT_REGION}"
echo "   - User Pool ID: ${USER_POOL_ID:0:15}..."
echo "   - Client ID: ${USER_POOL_CLIENT_ID:0:15}..."

# Load static configuration from .env (copied from .env.cloud during build in cloud mode)
if [ -f ".env" ]; then
    echo "📄 Loading static configuration from .env"
    set -a  # automatically export all variables
    source .env
    set +a
else
    echo "⚠️  Warning: .env file not found"
fi

# Validate required configuration
echo "🔍 Validating configuration..."

REQUIRED_VARS=(
    "VITE_BACKEND_URL"
    "VITE_WEBSOCKET_URL"
    "VITE_AWS_REGION"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "❌ Missing required environment variables:"
    printf '   - %s\n' "${MISSING_VARS[@]}"
    echo "Please check your configuration and try again."
    exit 1
fi

# Display final configuration (without sensitive data)
echo "📋 Final Configuration:"
echo "   - Backend URL: $VITE_BACKEND_URL"
echo "   - WebSocket URL: $VITE_WEBSOCKET_URL"
echo "   - AWS Region: $VITE_AWS_REGION"
echo "   - Auth Method: ${VITE_AUTH_METHOD:-cognito_auth}"
echo "   - Debug Mode: ${VITE_DEBUG_MODE:-false}"

# Health check function
health_check() {
    local max_attempts=30
    local attempt=1

    echo "🏥 Performing health check..."

    while [ "$attempt" -le "$max_attempts" ]; do
        if curl -f -s "http://localhost:${PORT:-3000}" > /dev/null 2>&1; then
            echo "✅ Health check passed (attempt $attempt/$max_attempts)"
            return 0
        fi
        echo "⏳ Health check attempt $attempt/$max_attempts failed, retrying in 2 seconds..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "❌ Health check failed after $max_attempts attempts"
    return 1
}

# Function to handle graceful shutdown
cleanup() {
    echo "🛑 Received shutdown signal, cleaning up..."
    if [ -n "$APP_PID" ]; then
        kill -TERM "$APP_PID" 2>/dev/null || true
        wait "$APP_PID" 2>/dev/null || true
    fi
    echo "✅ Cleanup completed"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm ci --only=production
fi

# Build the application if dist directory doesn't exist
if [ ! -d "dist" ]; then
    echo "🔨 Building application..."
    npm run build
fi

# Inject runtime configuration into built files
echo "🔧 Injecting runtime configuration..."
echo "📍 Current directory: $(pwd)"
echo "📍 Available files: $(ls -la)"
echo "📍 Environment before injection:"
echo "   - USER_POOL_ID: ${USER_POOL_ID:-'NOT SET'}"
echo "   - USER_POOL_CLIENT_ID: ${USER_POOL_CLIENT_ID:-'NOT SET'}"
echo "   - AWS_DEFAULT_REGION: ${AWS_DEFAULT_REGION:-'NOT SET'}"
./inject-config.sh

# Start the application
echo "🚀 Starting React application..."
echo "   - Port: ${PORT:-3000}"
echo "   - Host: ${HOST:-0.0.0.0}"

# Use serve to serve the built application in production
if command -v serve > /dev/null 2>&1; then
    echo "📡 Using 'serve' to serve static files with security headers"
    cd dist && serve -s . -l "${PORT:-3000}" --config serve.json &
    APP_PID=$!
    cd ..
else
    echo "📡 Installing and using 'serve' to serve static files"
    npm install -g serve
    cd dist && serve -s . -l "${PORT:-3000}" --config serve.json &
    APP_PID=$!
    cd ..
fi

# Wait a moment for the server to start
sleep 5

# Perform health check
if health_check; then
    echo "🎉 Application started successfully!"
    echo "🌐 Application is running on http://${HOST:-0.0.0.0}:${PORT:-3000}"
else
    echo "❌ Application failed to start properly"
    exit 1
fi

# Keep the script running and wait for the application process
wait "$APP_PID"
