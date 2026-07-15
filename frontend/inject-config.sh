#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
set -e

# Use environment variables directly from CDK
USER_POOL_ID=${USER_POOL_ID:-""}
USER_POOL_CLIENT_ID=${USER_POOL_CLIENT_ID:-""}
AWS_REGION=${AWS_REGION:-"us-east-1"}
# The Runtime ARN the frontend invokes directly.
AGENT_RUNTIME_ARN=${AGENT_RUNTIME_ARN:-""}

CONFIG_FILE=${CONFIG_FILE:-"./dist/runtime-config.js"}

echo "🔧 Injecting runtime config:"
echo "   Region: ${AWS_REGION}"
echo "   UserPool: ${USER_POOL_ID:0:10}..."
echo "   ClientId: ${USER_POOL_CLIENT_ID:0:10}..."
echo "   AgentRuntimeArn: ${AGENT_RUNTIME_ARN:0:40}..."

# Replace placeholders in the runtime config.
# Use '|' as the delimiter for the ARN because it contains '/' characters.
# BSD sed (macOS) requires an argument to -i; GNU sed (Linux container) does not.
# Detect and call accordingly so this works both on the host (deploy.sh) and in
# the container (startup-cloud.sh).
if sed --version >/dev/null 2>&1; then
    SED_INPLACE=(-i)       # GNU sed
else
    SED_INPLACE=(-i '')    # BSD/macOS sed
fi

sed "${SED_INPLACE[@]}" \
    -e "s/REPLACE_WITH_REGION/${AWS_REGION}/g" \
    -e "s/REPLACE_WITH_USER_POOL_ID/${USER_POOL_ID}/g" \
    -e "s/REPLACE_WITH_CLIENT_ID/${USER_POOL_CLIENT_ID}/g" \
    -e "s|REPLACE_WITH_AGENT_RUNTIME_ARN|${AGENT_RUNTIME_ARN}|g" \
    "$CONFIG_FILE"

echo "✅ Runtime config injected"
