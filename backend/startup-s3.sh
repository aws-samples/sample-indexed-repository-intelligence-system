#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

echo "🚀 Starting IRIS with S3 support..."

# Create base directories
mkdir -p /app/codebase_data /app/codebase_data/output

# Download and extract files from S3 if environment variables are set
if [ -n "$S3_BUCKET" ]; then
    echo "📦 Downloading from S3 bucket: $S3_BUCKET"

    # Set up S3 paths for default user
    if [ -n "$S3_PREFIX" ]; then
        CODEBASE_KEY="$S3_PREFIX/default/codebase/"
        REPRESENTATION_KEY="$S3_PREFIX/default/codebase_representation/"
    else
        CODEBASE_KEY="default/codebase/"
        REPRESENTATION_KEY="default/codebase_representation/"
    fi

    # Download codebase zip
    echo "📥 Downloading codebase..."
    # If multiple zip files exist in the S3 bucket, choose the latest uploaded one.
    CODEBASE_FILE=$(aws s3 ls "s3://$S3_BUCKET/$CODEBASE_KEY" | grep ".zip" | sort -k1,2 | tail -n 1 | awk '{print $4}')
    if [ -n "$CODEBASE_FILE" ]; then
        # Extract codebase name from filename (remove .zip) and strip unsafe chars
        CODEBASE_NAME="${CODEBASE_FILE%.zip}"
        CODEBASE_NAME=$(echo "$CODEBASE_NAME" | tr -cd 'a-zA-Z0-9_-')

        aws s3 cp "s3://$S3_BUCKET/$CODEBASE_KEY$CODEBASE_FILE" /tmp/codebase.zip
        if [ -f /tmp/codebase.zip ]; then
            # Extract to temp directory first to see structure
            mkdir -p /tmp/codebase_extract
            python -c "import zipfile; zipfile.ZipFile('/tmp/codebase.zip').extractall('/tmp/codebase_extract/')"

            # Create target directory
            mkdir -p "/app/codebase_data/codebase/$CODEBASE_NAME"

            # Move contents to target (handles both flat and nested structures)
            if [ -d "/tmp/codebase_extract/$CODEBASE_NAME" ]; then
                # Zip contains the codebase directory - move its contents
                mv "/tmp/codebase_extract/$CODEBASE_NAME"/* "/app/codebase_data/codebase/$CODEBASE_NAME/"
            else
                # Zip contains files directly - move all contents
                mv /tmp/codebase_extract/* "/app/codebase_data/codebase/$CODEBASE_NAME/"
            fi

            rm -rf /tmp/codebase_extract /tmp/codebase.zip
            echo "✅ Codebase extracted to /app/codebase_data/codebase/$CODEBASE_NAME/"
        fi
    fi

    # Download representation zip
    echo "📥 Downloading representation..."
    REPRESENTATION_FILE=$(aws s3 ls "s3://$S3_BUCKET/$REPRESENTATION_KEY" | grep "_representation.zip" | sort -k1,2 | tail -n 1 | awk '{print $4}')
    if [ -n "$REPRESENTATION_FILE" ]; then
        # Use the same codebase name from above for consistency
        if [ -z "$CODEBASE_NAME" ]; then
            # Fallback: extract from representation filename if codebase wasn't found
            CODEBASE_NAME="${REPRESENTATION_FILE%_representation.zip}"
            CODEBASE_NAME=$(echo "$CODEBASE_NAME" | tr -cd 'a-zA-Z0-9_-')
        fi

        aws s3 cp "s3://$S3_BUCKET/$REPRESENTATION_KEY$REPRESENTATION_FILE" /tmp/representation.zip
        if [ -f /tmp/representation.zip ]; then
            # Create target directory and extract directly
            mkdir -p "/app/codebase_data/output/$CODEBASE_NAME"
            python -c "import zipfile; zipfile.ZipFile('/tmp/representation.zip').extractall('/app/codebase_data/output/$CODEBASE_NAME/')"
            chmod -R u+w "/app/codebase_data/output/$CODEBASE_NAME"

            rm -f /tmp/representation.zip
            echo "✅ Representation extracted to /app/codebase_data/output/$CODEBASE_NAME/"
        fi
    fi
else
    echo "❌ S3_BUCKET not set. This container requires S3 configuration."
    echo "Please set S3_BUCKET environment variable."
    exit 1
fi

echo "📁 Extraction complete. Starting WebSocket server..."
exec /app/iris/.venv/bin/python websocket_server.py
