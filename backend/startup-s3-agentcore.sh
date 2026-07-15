#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# AgentCore Runtime S3 startup: download the codebase + pre-generated representation
# from S3 (same layout as backend/startup-s3.sh), then launch the AgentCore Runtime
# entrypoint (agent_runtime.py on :8080) instead of the WebSocket server.

echo "🚀 Starting IRIS AgentCore Runtime with S3 support..."

# Create base directories
mkdir -p /app/codebase_data /app/codebase_data/output

if [ -z "$S3_BUCKET" ]; then
    echo "❌ S3_BUCKET not set. This container requires S3 configuration."
    exit 1
fi

echo "📦 Downloading from S3 bucket: $S3_BUCKET"

# Set up S3 paths for default user
if [ -n "$S3_PREFIX" ]; then
    CODEBASE_KEY="$S3_PREFIX/default/codebase/"
    REPRESENTATION_KEY="$S3_PREFIX/default/codebase_representation/"
else
    CODEBASE_KEY="default/codebase/"
    REPRESENTATION_KEY="default/codebase_representation/"
fi

# Download codebase zip (latest uploaded if multiple)
echo "📥 Downloading codebase..."
CODEBASE_FILE=$(aws s3 ls "s3://$S3_BUCKET/$CODEBASE_KEY" | grep ".zip" | sort -k1,2 | tail -n 1 | awk '{print $4}')
if [ -n "$CODEBASE_FILE" ]; then
    CODEBASE_NAME="${CODEBASE_FILE%.zip}"
    CODEBASE_NAME=$(echo "$CODEBASE_NAME" | tr -cd 'a-zA-Z0-9_-')

    aws s3 cp "s3://$S3_BUCKET/$CODEBASE_KEY$CODEBASE_FILE" /tmp/codebase.zip
    if [ -f /tmp/codebase.zip ]; then
        mkdir -p /tmp/codebase_extract
        python -c "import zipfile; zipfile.ZipFile('/tmp/codebase.zip').extractall('/tmp/codebase_extract/')"
        mkdir -p "/app/codebase_data/codebase/$CODEBASE_NAME"
        if [ -d "/tmp/codebase_extract/$CODEBASE_NAME" ]; then
            mv "/tmp/codebase_extract/$CODEBASE_NAME"/* "/app/codebase_data/codebase/$CODEBASE_NAME/"
        else
            mv /tmp/codebase_extract/* "/app/codebase_data/codebase/$CODEBASE_NAME/"
        fi
        rm -rf /tmp/codebase_extract /tmp/codebase.zip
        echo "✅ Codebase extracted to /app/codebase_data/codebase/$CODEBASE_NAME/"
    fi
fi

# Download representation zip (latest uploaded if multiple)
echo "📥 Downloading representation..."
REPRESENTATION_FILE=$(aws s3 ls "s3://$S3_BUCKET/$REPRESENTATION_KEY" | grep "_representation.zip" | sort -k1,2 | tail -n 1 | awk '{print $4}')
if [ -n "$REPRESENTATION_FILE" ]; then
    if [ -z "$CODEBASE_NAME" ]; then
        CODEBASE_NAME="${REPRESENTATION_FILE%_representation.zip}"
        CODEBASE_NAME=$(echo "$CODEBASE_NAME" | tr -cd 'a-zA-Z0-9_-')
    fi

    aws s3 cp "s3://$S3_BUCKET/$REPRESENTATION_KEY$REPRESENTATION_FILE" /tmp/representation.zip
    if [ -f /tmp/representation.zip ]; then
        mkdir -p "/app/codebase_data/output/$CODEBASE_NAME"
        python -c "import zipfile; zipfile.ZipFile('/tmp/representation.zip').extractall('/app/codebase_data/output/$CODEBASE_NAME/')"
        chmod -R u+w "/app/codebase_data/output/$CODEBASE_NAME"
        rm -f /tmp/representation.zip
        echo "✅ Representation extracted to /app/codebase_data/output/$CODEBASE_NAME/"
    fi
fi

echo "📁 Extraction complete. Starting AgentCore Runtime server..."
exec /app/iris/.venv/bin/python agent_runtime.py
