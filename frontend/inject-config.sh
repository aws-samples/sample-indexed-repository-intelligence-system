#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
set -e

# Use environment variables directly from CDK
USER_POOL_ID=${USER_POOL_ID:-""}
USER_POOL_CLIENT_ID=${USER_POOL_CLIENT_ID:-""}
AWS_REGION=${AWS_REGION:-"us-east-1"}

CONFIG_FILE="./dist/runtime-config.js"

echo "🔧 Injecting runtime config:"
echo "   Region: ${AWS_REGION}"
echo "   UserPool: ${USER_POOL_ID:0:10}..."
echo "   ClientId: ${USER_POOL_CLIENT_ID:0:10}..."

# Replace placeholders in the runtime config
sed -i \
    -e "s/REPLACE_WITH_REGION/${AWS_REGION}/g" \
    -e "s/REPLACE_WITH_USER_POOL_ID/${USER_POOL_ID}/g" \
    -e "s/REPLACE_WITH_CLIENT_ID/${USER_POOL_CLIENT_ID}/g" \
    "$CONFIG_FILE"

echo "✅ Runtime config injected"
