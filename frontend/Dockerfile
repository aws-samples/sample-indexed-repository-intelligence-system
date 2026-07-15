# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
FROM public.ecr.aws/docker/library/node:22-alpine

# Update package index, upgrade all packages, and install required packages in one step
# This ensures optimal dependency resolution and prevents c-ares downgrade
RUN apk update && apk upgrade --no-cache && \
    apk add --no-cache --upgrade \
        c-ares \
        curl \
        bash \
        aws-cli \
        python3 \
        py3-pip \
        'py3-urllib3>=2.6.3-r0' \
        'openssl>=3.5.5-r0' \
        'expat>=2.7.5-r0' \
        'py3-cryptography>=46.0.5-r0' \
        'zlib>=1.3.2-r0'

# Upgrade zipp to fix vulnerabilities
RUN pip3 install --no-cache-dir --break-system-packages --upgrade zipp

# Set working directory
WORKDIR /app

# Accept build mode argument (dev or cloud)
ARG BUILD_MODE=cloud

# Copy package files
COPY package*.json ./

# Install dependencies
RUN if [ "$BUILD_MODE" = "cloud" ]; then \
        npm ci; \
    else \
        npm ci; \
    fi

# Copy source code
COPY . .

# Conditionally copy environment file based on build mode
RUN if [ "$BUILD_MODE" = "dev" ]; then \
        echo "🔧 Dev mode: using .env.development"; \
        cp .env.development .env; \
    else \
        echo "🌩️  Cloud mode: no .env file needed (uses runtime config)"; \
        echo "# Cloud mode - runtime config provides all settings" > .env; \
    fi

# Accept build arguments for configuration
ARG VITE_AWS_REGION=us-east-1
ARG VITE_USER_POOL_ID=REPLACE_WITH_USER_POOL_ID
ARG VITE_USER_POOL_CLIENT_ID=REPLACE_WITH_CLIENT_ID
# Local dev (Docker): browser talks to the AgentCore Runtime entrypoint on :8080.
ARG VITE_LOCAL_AGENT_URL=http://localhost:8080
ARG VITE_AUTH_ENABLED=false
ARG VITE_APP_NAME=IRIS

# Set environment variables for build (Vite needs these at build time)
ENV BUILD_MODE=$BUILD_MODE
ENV NODE_ENV=production
ENV VITE_AWS_REGION=$VITE_AWS_REGION
ENV VITE_USER_POOL_ID=$VITE_USER_POOL_ID
ENV VITE_USER_POOL_CLIENT_ID=$VITE_USER_POOL_CLIENT_ID
ENV VITE_LOCAL_AGENT_URL=$VITE_LOCAL_AGENT_URL
ENV VITE_AUTH_ENABLED=$VITE_AUTH_ENABLED
ENV VITE_APP_NAME=$VITE_APP_NAME

# Build the React app
RUN npm run build

# Copy serve configuration for security headers to dist directory
COPY serve.json dist/

# Copy appropriate runtime config based on build mode
RUN if [ "$BUILD_MODE" = "dev" ]; then \
        echo "🔧 Copying dev runtime config"; \
        cp runtime-config-dev.js dist/runtime-config.js; \
    else \
        echo "🌩️  Copying cloud runtime config template"; \
        cp runtime-config-cloud.js dist/runtime-config.js; \
    fi

# Install serve to run the production build
RUN npm install -g serve

# Make startup scripts executable
RUN chmod +x startup-cloud.sh inject-config.sh

# Create non-root user with home directory
RUN addgroup -g 1001 -S appuser && adduser -S appuser -G appuser -h /home/appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:3000 || exit 1

# Use different startup commands based on build mode
CMD if [ "$BUILD_MODE" = "dev" ]; then \
        echo "🔧 Starting in dev mode"; \
        serve -s dist -l 3000; \
    else \
        echo "🌩️  Starting in cloud mode with runtime configuration"; \
        ./startup-cloud.sh; \
    fi
