# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Use ECR Public Python base image
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm

# Install uv
RUN pip install uv

WORKDIR /app

# Copy entire project
COPY . ./iris
RUN rm -rf ./iris/.venv

# Debug: List what was copied
RUN ls -la /app/iris/

# Create output directory
RUN mkdir -p /app/output

# Copy artifacts from project root codebase_artifacts directory
COPY codebase_artifacts/ /app/iris/codebase_data/

# Extract codebase zip from codebase/ directory
RUN find /app/iris/codebase_data/codebase/ -name "*.zip" -exec python -c "\
import zipfile, os, sys; \
zip_path = sys.argv[1]; \
filename = os.path.basename(zip_path); \
codebase_name = filename.replace('.zip', ''); \
target_dir = f'/app/codebase_data/codebase/{codebase_name}'; \
os.makedirs(target_dir, exist_ok=True); \
zipfile.ZipFile(zip_path).extractall(target_dir) \
" {} \; -exec rm {} \; || echo "No codebase zip files found"
RUN echo "Successfully extracted codebase to /app/codebase_data/codebase/"

# Extract representation zip from codebase_representation/ directory
RUN find /app/iris/codebase_data/codebase_representation/ -name "*_representation.zip" -exec python -c "\
import zipfile, os, sys; \
zip_path = sys.argv[1]; \
filename = os.path.basename(zip_path); \
codebase_name = filename.replace('_representation.zip', ''); \
target_dir = f'/app/codebase_data/output/{codebase_name}'; \
os.makedirs(target_dir, exist_ok=True); \
zipfile.ZipFile(zip_path).extractall(target_dir) \
" {} \; -exec rm {} \; || echo "No representation zip files found"
RUN echo "Successfully extracted representation to /app/codebase_data/output/"

# Change to iris directory for dependency installation
WORKDIR /app/iris

# Delete config.yaml and rename config_docker.yaml to config.yaml
RUN rm -f config.yaml && mv config_docker.yaml config.yaml

# Debug: Verify the config replacement worked
RUN echo "=== CONFIG AFTER REPLACEMENT ===" && head -10 config.yaml

# Install system dependencies and upgrade all packages for security
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    curl \
    git \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install and upgrade specific vulnerable packages to advisory versions to avoid CVE errors
RUN apt-get update && apt-get install -y \
    libpam-modules \
    libpam0g \
    libglib2.0-0 \
    libglib2.0-data \
    gnupg2 \
    libxml2 \
    openssl \
    libssl3 \
    libexpat1 \
    libgnutls30 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Verify installed versions for security compliance
RUN echo "=== SECURITY PACKAGE VERSIONS ===" && \
    dpkg -l | grep -E "(libpam|libglib2.0|gnupg|libxml2|gnutls)" | awk '{print $2, $3}'

# Install dependencies using uv with increased timeout
ENV UV_HTTP_TIMEOUT=300
RUN uv sync --frozen --no-cache

# Upgrade zipp and urllib3 to fix vulnerabilities
RUN uv pip install --system --upgrade zipp "urllib3>=2.2.3"

# Create non-root user with home directory
RUN groupadd -r appuser && useradd -r -g appuser -m appuser
RUN chown -R appuser:appuser /app
USER appuser

# Set environment variables
ENV PYTHONPATH=/app/iris
ENV PYTHONUNBUFFERED=1
ENV DOCKER_ENV=true

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the WebSocket server from the backend directory
WORKDIR /app/iris/backend
CMD ["uv", "run", "python", "websocket_server.py"]
