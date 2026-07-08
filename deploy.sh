#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# IRIS Interactive Deployment Script
# This script provides an interactive menu for local testing and cloud deployment
#
# Note: For Windows users, run this script using:
#   - Git Bash (recommended)
#   - WSL (Windows Subsystem for Linux)
#   - Cygwin

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to print colored output
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_prompt() {
    echo -e "${MAGENTA}👤 $1${NC}"
}

print_header() {
    echo ""
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==========================================${NC}"
    echo ""
}

# Function to detect if virtual environment exists
detect_venv() {
    if [ -d ".venv" ] || [ -d "venv" ]; then
        return 0  # Virtual environment exists
    else
        return 1  # No virtual environment found
    fi
}

# Function to setup virtual environment, install dependencies and setup directories
run_installation() {
    print_header "Virtual Environment Installation/Setup"

    # Check if virtual environment already exists
    if detect_venv; then
        if [ -d ".venv" ]; then
            print_success "Virtual environment (.venv) already exists - skipping installation"
        else
            print_success "Virtual environment (venv) already exists - skipping installation"
        fi
        print_info "After installation, you can use the 'iris' CLI tool directly. Activate virtual environment and run 'iris chat' to start."
        return 0
    fi

    # Ask user for package manager preference
    print_info "No virtual environment detected. Setting up dependencies..."
    echo ""
    echo "Choose package manager:"
    echo "1. uv (Recommended - faster)"
    echo "2. pip (Standard)"
    echo ""

    while true; do
        read -r -p "Select option [1-2]: " pkg_choice
        case $pkg_choice in
            1)
                setup_with_uv
                break
                ;;
            2)
                setup_with_pip
                break
                ;;
            *)
                print_error "Invalid option. Please select 1 or 2."
                ;;
        esac
    done

    echo ""
    print_success "Installation complete!"
    echo ""

    # Configure directories after installation
    configure_directories

    print_info "You can now use the 'iris' CLI tool:"
    echo ""
    echo "1. First, run below command to activate virtual environment:"
    echo ""
    print_info "  - source .venv/bin/activate (Linux/Mac)"
    print_info "  - .venv/Scripts/activate (Windows)"
    echo ""
    echo "2. Then use available iris commands:"
    echo ""
    echo "  iris chat               - Interactive chat with file editing"
    echo "  iris ui                 - Launch ReAct UI"
    echo "  iris streamlit          - Launch legacy Streamlit UI"
    echo "  iris prepare            - Generate/update codebase context"
    echo ""
    echo "  Command options:"
    echo "  --codebase, -c <path>         - Specify codebase directory"
    echo "  --skip-validation             - Skip tree validation confirmation"
    echo ""
    print_info "If you need more deployment options with UI besides iris CLI, continue with the menu below."
    print_info "Otherwise, choose option 6 in the menu to exit."
}

# Function to setup with uv
setup_with_uv() {
    print_info "Setting up with uv..."

    # Check if uv is installed
    if ! command -v uv &> /dev/null; then
        print_warning "uv not found. Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh

        # Source the shell profile to make uv available
        if [ -f "$HOME/.bashrc" ]; then
            source "$HOME/.bashrc"
        elif [ -f "$HOME/.zshrc" ]; then
            source "$HOME/.zshrc"
        fi

        # Check if uv is now available
        if ! command -v uv &> /dev/null; then
            print_error "Failed to install uv. Please install manually or choose pip option."
            return 1
        fi
        print_success "uv installed successfully"
    fi

    print_info "Syncing dependencies with uv..."
    if ! uv sync; then
        print_error "Failed to install dependencies with uv"
        return 1
    fi
    print_success "Dependencies installed successfully with uv"
}

# Function to setup with pip
setup_with_pip() {
    print_info "Setting up with pip..."

    # Determine Python command
    local python_cmd="python3"
    if ! command -v python3 &> /dev/null; then
        if command -v python &> /dev/null; then
            python_cmd="python"
        else
            print_error "Python not found. Please install Python 3.10+."
            return 1
        fi
    fi

    print_info "Creating virtual environment..."
    if ! $python_cmd -m venv .venv; then
        print_error "Failed to create virtual environment"
        return 1
    fi

    print_success "Virtual environment created"

    # Activate virtual environment and install
    print_info "Installing package with pip..."
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        if ! .venv/Scripts/python.exe -m pip install -e .; then
            print_error "Failed to install package with pip"
            return 1
        fi
    else
        source .venv/bin/activate
        if ! pip install -e .; then
            print_error "Failed to install package with pip"
            return 1
        fi
    fi
    print_success "Package installed successfully with pip"
}

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"

    local all_good=true

    # Check AWS CLI
    if command -v aws &> /dev/null; then
        print_success "AWS CLI found"
    else
        print_error "AWS CLI not found. Please install it first."
        all_good=false
    fi

    # Check Docker (not needed for deploy option 1)
    if command -v docker &> /dev/null; then
        print_success "Docker found"
    else
        print_warning "Docker not found. Required for Docker-based testing."
        print_info "Here are two options: \n - Docker Desktop: Install and Run it. \n - Colima: You can install it using Homebrew with 'brew install colima docker docker-buildx docker-compose', 'mkdir -p ~/.docker/cli-plugins', 'ln -sfn $(brew --prefix)/opt/docker-buildx/bin/docker-buildx ~/.docker/cli-plugins/docker-buildx' and then start it with 'colima start'"
    fi

    # Check Python
    if command -v python3 &> /dev/null || command -v python &> /dev/null; then
        print_success "Python found"
    else
        print_error "Python not found. Please install Python 3.10+."
        all_good=false
    fi

    # Check Node.js
    if command -v node &> /dev/null; then
        print_success "Node.js found"
    else
        print_warning "Node.js not found. Required for local frontend development."
    fi

    # Check uv (optional but recommended)
    if command -v uv &> /dev/null; then
        print_success "uv found (recommended)"
    else
        print_info "uv not found (optional). Using regular Python."
    fi

    # Check jq (required for AWS credential handling)
    if command -v jq &> /dev/null; then
        print_success "jq found"
    else
        print_warning "jq not found. Required for AWS credential handling."
        read -r -p "Install jq now? [Y/n]: " -r
        REPLY=${REPLY:-Y}
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                brew install jq
            elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
                sudo apt-get install -y jq || sudo yum install -y jq
            else
                print_error "Please install jq manually: https://jqlang.github.io/jq/download/"
                all_good=false
            fi
        else
            all_good=false
        fi
    fi

    if [ "$all_good" = false ]; then
        print_error "Some required prerequisites are missing. Please install them first."
        exit 1
    fi

    echo ""
}

# Function to validate and setup AWS credentials (matches start-docker.sh approach)
validate_aws_credentials() {
    print_info "Checking AWS credentials..."

    if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_PROFILE:-}" ] && [ ! -f ~/.aws/credentials ]; then
        print_error "No AWS credentials found!"
        echo "Please either:"
        echo "  1. Set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
        echo "  2. Set AWS_PROFILE environment variable"
        echo "  3. Configure AWS CLI: aws configure"
        echo "  4. Use AWS SSO: aws sso login"
        return 1
    fi

    # Export AWS credentials to make them available (same as start-docker.sh)
    if [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
        print_success "Using AWS credentials from environment variables"
        export AWS_ACCESS_KEY_ID
        export AWS_SECRET_ACCESS_KEY
        export AWS_SESSION_TOKEN
        export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
        export AWS_REGION=${AWS_REGION:-us-east-1}
    elif [ -n "${AWS_PROFILE:-}" ]; then
        print_success "Using AWS profile: $AWS_PROFILE"

        # Try to export credentials from the profile
        TEMP_CREDS=$(aws configure export-credentials --profile "$AWS_PROFILE" --format env 2>/dev/null || true)

        if [ -n "${TEMP_CREDS:-}" ]; then
            eval "$TEMP_CREDS"
            print_success "Successfully exported credentials"
        else
            print_warning "Could not export credentials, will use profile directly"
        fi

        export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
        export AWS_REGION=${AWS_REGION:-us-east-1}
    else
        print_success "Using AWS credentials from ~/.aws/credentials (default profile)"

        # Try to get credentials from default profile
        TEMP_CREDS=$(aws configure export-credentials --format env 2>/dev/null || true)

        if [ -n "${TEMP_CREDS:-}" ]; then
            eval "$TEMP_CREDS"
            print_success "Successfully fetched credentials from default profile"
        fi

        export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
        export AWS_REGION=${AWS_REGION:-us-east-1}
    fi

    return 0
}

# Function to update infra config with S3 bucket
update_infra_config() {
    local bucket_name=$1
    local config_file="$SCRIPT_DIR/infra/config.yaml"

    if [ ! -f "$config_file" ]; then
        print_error "infra/config.yaml not found"
        return 1
    fi

    # Use sed to update the bucket name
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/bucket: \".*\"/bucket: \"$bucket_name\"/" "$config_file"
    else
        # Linux
        sed -i "s/bucket: \".*\"/bucket: \"$bucket_name\"/" "$config_file"
    fi

    print_success "Updated infra/config.yaml with bucket: $bucket_name"
}

# Function to update codebase_dir in config.yaml
update_codebase_dir() {
    local codebase_dir=$1
    local config_file="$SCRIPT_DIR/config.yaml"

    if [ ! -f "$config_file" ]; then
        print_error "config.yaml not found"
        return 1
    fi

    # Use sed to update the codebase_dir
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|^codebase_dir: .*|codebase_dir: $codebase_dir|" "$config_file"
    else
        # Linux
        sed -i "s|^codebase_dir: .*|codebase_dir: $codebase_dir|" "$config_file"
    fi

    print_success "Updated config.yaml with codebase_dir: $codebase_dir"
}

# Function to update output_dir in config.yaml
update_output_dir() {
    local output_dir=$1
    local config_file="$SCRIPT_DIR/config.yaml"

    if [ ! -f "$config_file" ]; then
        print_error "config.yaml not found"
        return 1
    fi

    # Use sed to update the output_dir
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|^output_dir: .*|output_dir: $output_dir|" "$config_file"
    else
        # Linux
        sed -i "s|^output_dir: .*|output_dir: $output_dir|" "$config_file"
    fi

    print_success "Updated config.yaml with output_dir: $output_dir"
}

# Function to configure codebase and output directories
configure_directories() {
    print_header "Directory Configuration"

    # Read current directories from config.yaml
    local current_codebase_dir=""
    local current_output_dir=""

    if [ -f "$SCRIPT_DIR/config.yaml" ]; then
        current_codebase_dir=$(grep "^codebase_dir:" "$SCRIPT_DIR/config.yaml" | sed 's/codebase_dir: //')
        current_output_dir=$(grep "^output_dir:" "$SCRIPT_DIR/config.yaml" | sed 's/output_dir: //')
    fi

    # Configure codebase directory
    if [ -n "$current_codebase_dir" ]; then
        print_info "Current codebase directory: $current_codebase_dir"

        while true; do
            print_prompt "Keep current codebase directory? [Y/n]: "
            read -r reply
            reply=${reply:-Y}
            case $reply in
                [Yy]* )
                    # Validate current codebase directory exists
                    if [ -d "$current_codebase_dir" ]; then
                        print_success "Codebase directory exists: $current_codebase_dir"
                        print_info "Keeping current codebase directory: $current_codebase_dir"
                    else
                        print_error "Current codebase directory does not exist: $current_codebase_dir"
                        return 1
                    fi
                    break
                    ;;
                [Nn]* )
                    read -r -p "Enter new codebase directory path [$current_codebase_dir]: " new_codebase_dir
                    new_codebase_dir=${new_codebase_dir:-$current_codebase_dir}
                    if [ -n "$new_codebase_dir" ]; then
                        # Validate codebase directory exists
                        if [ -d "$new_codebase_dir" ]; then
                            print_success "Codebase directory exists: $new_codebase_dir"
                            update_codebase_dir "$new_codebase_dir"
                        else
                            print_error "Codebase directory does not exist: $new_codebase_dir"
                            return 1
                        fi
                    fi
                    break
                    ;;
                * )
                    print_error "Please answer y or n."
                    ;;
            esac
        done
    else
        read -r -p "Enter codebase directory path: " new_codebase_dir
        if [ -n "$new_codebase_dir" ]; then
            # Validate codebase directory exists
            if [ -d "$new_codebase_dir" ]; then
                print_success "Codebase directory exists: $new_codebase_dir"
                update_codebase_dir "$new_codebase_dir"
            else
                print_error "Codebase directory does not exist: $new_codebase_dir"
                return 1
            fi
        fi
    fi

    echo ""

    # Configure output directory
    if [ -n "$current_output_dir" ]; then
        print_info "Current output directory: $current_output_dir"

        while true; do
            print_prompt "Keep current output directory? [Y/n]: "
            read -r reply
            reply=${reply:-Y}
            case $reply in
                [Yy]* )
                    # Validate/create current output directory
                    if [ ! -d "$current_output_dir" ]; then
                        print_info "Output directory does not exist. Creating: $current_output_dir"
                        if mkdir -p "$current_output_dir"; then
                            print_success "Output directory created: $current_output_dir"
                        else
                            print_error "Failed to create output directory: $current_output_dir"
                            return 1
                        fi
                    else
                        print_success "Output directory exists: $current_output_dir"
                    fi
                    print_info "Keeping current output directory: $current_output_dir"
                    break
                    ;;
                [Nn]* )
                    read -r -p "Enter new output directory path [$current_output_dir]: " new_output_dir
                    new_output_dir=${new_output_dir:-$current_output_dir}
                    if [ -n "$new_output_dir" ]; then
                        # Create output directory if it doesn't exist
                        if [ ! -d "$new_output_dir" ]; then
                            print_info "Output directory does not exist. Creating: $new_output_dir"
                            if mkdir -p "$new_output_dir"; then
                                print_success "Output directory created: $new_output_dir"
                            else
                                print_error "Failed to create output directory: $new_output_dir"
                                return 1
                            fi
                        else
                            print_success "Output directory exists: $new_output_dir"
                        fi
                        update_output_dir "$new_output_dir"
                    fi
                    break
                    ;;
                * )
                    print_error "Please answer y or n."
                    ;;
            esac
        done
    else
        read -r -p "Enter output directory path: " new_output_dir
        if [ -n "$new_output_dir" ]; then
            # Create output directory if it doesn't exist
            if [ ! -d "$new_output_dir" ]; then
                print_info "Output directory does not exist. Creating: $new_output_dir"
                if mkdir -p "$new_output_dir"; then
                    print_success "Output directory created: $new_output_dir"
                else
                    print_error "Failed to create output directory: $new_output_dir"
                    return 1
                fi
            else
                print_success "Output directory exists: $new_output_dir"
            fi
            update_output_dir "$new_output_dir"
        fi
    fi

    echo ""
}

# Function to update app name in infra config
update_app_name() {
    local app_name=$1
    local config_file="$SCRIPT_DIR/infra/config.yaml"

    if [ ! -f "$config_file" ]; then
        print_error "infra/config.yaml not found"
        return 1
    fi

    # Use sed to update the app name
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/^app_name: \".*\"/app_name: \"$app_name\"/" "$config_file"
    else
        # Linux
        sed -i "s/^app_name: \".*\"/app_name: \"$app_name\"/" "$config_file"
    fi

    print_success "Updated infra/config.yaml with app_name: $app_name"
}

# Function to update React app name in runtime config files
update_react_app_name() {
    local app_name=$1
    local dev_config="$SCRIPT_DIR/frontend/runtime-config-dev.js"
    local cloud_config="$SCRIPT_DIR/frontend/runtime-config-cloud.js"

    # Escape special characters for sed
    local escaped_app_name
    escaped_app_name=$(printf '%s\n' "$app_name" | sed "s/[[\.*^\$()+?{|]/\\\\&/g")

    # Update development config
    if [ -f "$dev_config" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/appName: '[^']*'/appName: '$escaped_app_name'/" "$dev_config"
        else
            # Linux
            sed -i "s/appName: '[^']*'/appName: '$escaped_app_name'/" "$dev_config"
        fi
        print_success "Updated $dev_config with app name: $app_name"
    else
        print_warning "Development config file not found: $dev_config"
    fi

    # Update cloud config
    if [ -f "$cloud_config" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/appName: '[^']*'/appName: '$escaped_app_name'/" "$cloud_config"
        else
            # Linux
            sed -i "s/appName: '[^']*'/appName: '$escaped_app_name'/" "$cloud_config"
        fi
        print_success "Updated $cloud_config with app name: $app_name"
    else
        print_warning "Cloud config file not found: $cloud_config"
    fi
}

# Function to setup S3 bucket
setup_s3_bucket() {
    # Read current bucket from infra config if it exists
    local current_bucket=""
    local current_kms_key=""
    if [ -f "$SCRIPT_DIR/infra/config.yaml" ]; then
        current_bucket=$(grep -A 2 "^codebase_artifacts:" "$SCRIPT_DIR/infra/config.yaml" | grep "bucket:" | sed 's/.*bucket: "\(.*\)".*/\1/' | tr -d '"')
        current_kms_key=$(grep -A 3 "^codebase_artifacts:" "$SCRIPT_DIR/infra/config.yaml" | grep "kms_key_arn:" | sed 's/.*kms_key_arn: "\(.*\)".*/\1/' | tr -d '"')
    fi

    # Check if bucket is placeholder or a real value
    if [ -n "${current_bucket:-}" ] && [ "$current_bucket" != "<placeholder>" ]; then
        print_info "Current S3 bucket: $current_bucket" >&2

        while true; do
            print_prompt "Keep current S3 bucket? [Y/n]: " >&2
            read -r reply
            reply=${reply:-Y}
            case $reply in
                [Yy]* )
                    bucket_name="$current_bucket"
                    print_info "Keeping current S3 bucket: $current_bucket" >&2
                    break
                    ;;
                [Nn]* )
                    read -r -p "Enter new S3 bucket name [$current_bucket]: " bucket_name >&2
                    bucket_name=${bucket_name:-$current_bucket}
                    break
                    ;;
                * )
                    print_error "Please answer y or n." >&2
                    ;;
            esac
        done
    else
        # No bucket configured or placeholder value - ask for input
        read -r -p "Enter S3 bucket name: " bucket_name >&2
    fi

    if [ -z "${bucket_name:-}" ]; then
        print_error "S3 bucket name is required" >&2
        return 1
    fi

    print_info "Checking if bucket exists..." >&2

    if aws s3 ls "s3://$bucket_name" 2>/dev/null 1>&2; then
        print_success "Bucket '$bucket_name' exists" >&2

        # Ask about KMS for existing bucket
        if [ -n "$current_kms_key" ]; then
            print_info "Current KMS Key ARN: $current_kms_key" >&2
            read -r -p "Keep current KMS key? [Y/n]: " keep_kms >&2
            keep_kms=${keep_kms:-Y}
            if [[ ! $keep_kms =~ ^[Yy]$ ]]; then
                read -r -p "Enter new KMS Key ARN (leave empty for default S3 encryption): " kms_key_arn >&2
                if [ -n "$kms_key_arn" ]; then
                    # Update config with new KMS key
                    local config_file="$SCRIPT_DIR/infra/config.yaml"
                    if [[ "$OSTYPE" == "darwin"* ]]; then
                        sed -i '' "s|kms_key_arn: \".*\"|kms_key_arn: \"$kms_key_arn\"|" "$config_file"
                    else
                        sed -i "s|kms_key_arn: \".*\"|kms_key_arn: \"$kms_key_arn\"|" "$config_file"
                    fi
                    print_success "Updated infra/config.yaml with KMS key ARN" >&2
                fi
            fi
        else
            read -r -p "Use Customer Managed KMS Key for encryption? [y/N]: " use_kms >&2
            use_kms=${use_kms:-N}
            if [[ $use_kms =~ ^[Yy]$ ]]; then
                read -r -p "Enter KMS Key ARN: " kms_key_arn >&2
                if [ -n "$kms_key_arn" ]; then
                    # Update config with KMS key
                    local config_file="$SCRIPT_DIR/infra/config.yaml"
                    if [[ "$OSTYPE" == "darwin"* ]]; then
                        sed -i '' "s|kms_key_arn: \".*\"|kms_key_arn: \"$kms_key_arn\"|" "$config_file"
                    else
                        sed -i "s|kms_key_arn: \".*\"|kms_key_arn: \"$kms_key_arn\"|" "$config_file"
                    fi
                    print_success "Updated infra/config.yaml with KMS key ARN" >&2
                fi
            fi
        fi
    else
        print_warning "Bucket '$bucket_name' does not exist" >&2
        read -r -p "Create bucket '$bucket_name'? [Y/n]: " -r >&2
        REPLY=${REPLY:-Y}
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            read -r -e -p "Enter AWS region for bucket [us-east-1]: " bucket_region >&2
            bucket_region=${bucket_region:-us-east-1}

            # Ask about KMS encryption once for all buckets
            print_info "Configure encryption for S3 buckets" >&2
            read -r -p "Use Customer Managed KMS Key? [y/N]: " use_kms >&2
            use_kms=${use_kms:-N}

            local kms_key_arn=""
            if [[ $use_kms =~ ^[Yy]$ ]]; then
                read -r -p "Enter KMS Key ARN: " kms_key_arn >&2
                if [ -n "$kms_key_arn" ]; then
                    print_info "Will use KMS key for all S3 buckets" >&2

                    # Update infra config with KMS key ARN
                    local config_file="$SCRIPT_DIR/infra/config.yaml"
                    if [[ "$OSTYPE" == "darwin"* ]]; then
                        sed -i '' "s|kms_key_arn: \".*\"|kms_key_arn: \"$kms_key_arn\"|" "$config_file"
                    else
                        sed -i "s|kms_key_arn: \".*\"|kms_key_arn: \"$kms_key_arn\"|" "$config_file"
                    fi
                    print_success "Updated infra/config.yaml with KMS key ARN" >&2
                fi
            else
                print_info "Will use default S3 encryption (SSE-S3)" >&2
            fi

            if [ "$bucket_region" = "us-east-1" ]; then
                if aws s3 mb "s3://$bucket_name" >&2; then
                    print_success "Bucket created successfully" >&2

                    # Enable KMS encryption if provided
                    if [ -n "$kms_key_arn" ]; then
                        print_info "Enabling KMS encryption with customer managed key..." >&2
                        aws s3api put-bucket-encryption \
                            --bucket "$bucket_name" \
                            --server-side-encryption-configuration "{\"Rules\":[{\"ApplyServerSideEncryptionByDefault\":{\"SSEAlgorithm\":\"aws:kms\",\"KMSMasterKeyID\":\"$kms_key_arn\"},\"BucketKeyEnabled\":true}]}" >&2
                        print_success "KMS encryption enabled" >&2
                    fi

                    # Enable server access logging
                    local log_bucket="${bucket_name}-access-logs"
                    print_info "Creating access logs bucket: $log_bucket" >&2
                    if aws s3 mb "s3://$log_bucket" >&2; then
                        print_success "Access logs bucket created" >&2

                        # Enable logging on the main bucket
                        print_info "Enabling server access logging..." >&2
                        aws s3api put-bucket-logging \
                            --bucket "$bucket_name" \
                            --bucket-logging-status "{\"LoggingEnabled\":{\"TargetBucket\":\"$log_bucket\",\"TargetPrefix\":\"access-logs/\"}}" >&2
                        print_success "Server access logging enabled" >&2
                    else
                        print_warning "Failed to create access logs bucket - skipping logging configuration" >&2
                    fi
                else
                    print_error "Failed to create bucket" >&2
                    return 1
                fi
            else
                if aws s3 mb "s3://$bucket_name" --region "$bucket_region" >&2; then
                    print_success "Bucket created successfully" >&2

                    # Enable KMS encryption if provided
                    if [ -n "$kms_key_arn" ]; then
                        print_info "Enabling KMS encryption with customer managed key..." >&2
                        aws s3api put-bucket-encryption \
                            --bucket "$bucket_name" \
                            --server-side-encryption-configuration "{\"Rules\":[{\"ApplyServerSideEncryptionByDefault\":{\"SSEAlgorithm\":\"aws:kms\",\"KMSMasterKeyID\":\"$kms_key_arn\"},\"BucketKeyEnabled\":true}]}" \
                            --region "$bucket_region" >&2
                        print_success "KMS encryption enabled" >&2
                    fi

                    # Enable server access logging
                    local log_bucket="${bucket_name}-access-logs"
                    print_info "Creating access logs bucket: $log_bucket" >&2
                    if aws s3 mb "s3://$log_bucket" --region "$bucket_region" >&2; then
                        print_success "Access logs bucket created" >&2

                        # Enable logging on the main bucket
                        print_info "Enabling server access logging..." >&2
                        aws s3api put-bucket-logging \
                            --bucket "$bucket_name" \
                            --bucket-logging-status "{\"LoggingEnabled\":{\"TargetBucket\":\"$log_bucket\",\"TargetPrefix\":\"access-logs/\"}}" \
                            --region "$bucket_region" >&2
                        print_success "Server access logging enabled" >&2
                    else
                        print_warning "Failed to create access logs bucket - skipping logging configuration" >&2
                    fi
                else
                    print_error "Failed to create bucket" >&2
                    return 1
                fi
            fi
        else
            print_error "S3 bucket is required for deployment" >&2
            return 1
        fi
    fi

    # Update infra config (send output to stderr)
    update_infra_config "$bucket_name" >&2

    # Output only the bucket name to stdout
    printf "%s" "$bucket_name"
}

# Common function to configure directories and generate Docker config
configure_directories_and_generate_docker_config() {
    print_header "Directory Configuration"

    # Read current directories from config.yaml
    local current_codebase_dir=""
    local current_output_dir=""

    if [ -f "$SCRIPT_DIR/config.yaml" ]; then
        current_codebase_dir=$(grep "^codebase_dir:" "$SCRIPT_DIR/config.yaml" | sed 's/codebase_dir: //')
        current_output_dir=$(grep "^output_dir:" "$SCRIPT_DIR/config.yaml" | sed 's/output_dir: //')
    fi

    # Configure codebase directory
    if [ -n "$current_codebase_dir" ]; then
        print_info "Current codebase directory: $current_codebase_dir"

        while true; do
            print_prompt "Keep current codebase directory? [Y/n]: "
            read -r reply
            reply=${reply:-Y}
            case $reply in
                [Yy]* )
                    # Validate current codebase directory exists
                    if [ -d "$current_codebase_dir" ]; then
                        print_success "Codebase directory exists: $current_codebase_dir"
                        print_info "Keeping current codebase directory: $current_codebase_dir"
                    else
                        print_error "Current codebase directory does not exist: $current_codebase_dir"
                        return 1
                    fi
                    break
                    ;;
                [Nn]* )
                    read -r -p "Enter new codebase directory path [$current_codebase_dir]: " new_codebase_dir
                    new_codebase_dir=${new_codebase_dir:-$current_codebase_dir}
                    if [ -n "$new_codebase_dir" ]; then
                        # Validate codebase directory exists
                        if [ -d "$new_codebase_dir" ]; then
                            print_success "Codebase directory exists: $new_codebase_dir"
                            update_codebase_dir "$new_codebase_dir"
                        else
                            print_error "Codebase directory does not exist: $new_codebase_dir"
                            return 1
                        fi
                    fi
                    break
                    ;;
                * )
                    print_error "Please answer y or n."
                    ;;
            esac
        done
    else
        read -r -p "Enter codebase directory path: " new_codebase_dir
        if [ -n "$new_codebase_dir" ]; then
            # Validate codebase directory exists
            if [ -d "$new_codebase_dir" ]; then
                print_success "Codebase directory exists: $new_codebase_dir"
                update_codebase_dir "$new_codebase_dir"
            else
                print_error "Codebase directory does not exist: $new_codebase_dir"
                return 1
            fi
        fi
    fi

    echo ""

    # Configure output directory
    if [ -n "$current_output_dir" ]; then
        print_info "Current output directory: $current_output_dir"

        while true; do
            print_prompt "Keep current output directory? [Y/n]: "
            read -r reply
            reply=${reply:-Y}
            case $reply in
                [Yy]* )
                    # Validate/create current output directory
                    if [ ! -d "$current_output_dir" ]; then
                        print_info "Output directory does not exist. Creating: $current_output_dir"
                        if mkdir -p "$current_output_dir"; then
                            print_success "Output directory created: $current_output_dir"
                        else
                            print_error "Failed to create output directory: $current_output_dir"
                            return 1
                        fi
                    else
                        print_success "Output directory exists: $current_output_dir"
                    fi
                    print_info "Keeping current output directory: $current_output_dir"
                    break
                    ;;
                [Nn]* )
                    read -r -p "Enter new output directory path [$current_output_dir]: " new_output_dir
                    new_output_dir=${new_output_dir:-$current_output_dir}
                    if [ -n "$new_output_dir" ]; then
                        # Create output directory if it doesn't exist
                        if [ ! -d "$new_output_dir" ]; then
                            print_info "Output directory does not exist. Creating: $new_output_dir"
                            if mkdir -p "$new_output_dir"; then
                                print_success "Output directory created: $new_output_dir"
                            else
                                print_error "Failed to create output directory: $new_output_dir"
                                return 1
                            fi
                        else
                            print_success "Output directory exists: $new_output_dir"
                        fi
                        update_output_dir "$new_output_dir"
                    fi
                    break
                    ;;
                * )
                    print_error "Please answer y or n."
                    ;;
            esac
        done
    else
        read -r -p "Enter output directory path: " new_output_dir
        if [ -n "$new_output_dir" ]; then
            # Create output directory if it doesn't exist
            if [ ! -d "$new_output_dir" ]; then
                print_info "Output directory does not exist. Creating: $new_output_dir"
                if mkdir -p "$new_output_dir"; then
                    print_success "Output directory created: $new_output_dir"
                else
                    print_error "Failed to create output directory: $new_output_dir"
                    return 1
                fi
            else
                print_success "Output directory exists: $new_output_dir"
            fi
            update_output_dir "$new_output_dir"
        fi
    fi

    echo ""

    # Generate Docker configuration
    print_info "Generating Docker configuration..."
    cd "$SCRIPT_DIR"
    if command -v uv &> /dev/null; then
        if uv run python backend/scripts/create_docker_config.py; then
            print_success "Docker configuration created"
        else
            print_error "Failed to create Docker configuration"
            return 1
        fi
    else
        if python backend/scripts/create_docker_config.py; then
            print_success "Docker configuration created"
        else
            print_error "Failed to create Docker configuration"
            return 1
        fi
    fi

    echo ""
    return 0
}

# Function for local testing without Docker
local_test_no_docker() {
    print_header "Local Testing (No Docker)"

    if ! validate_aws_credentials; then
        return 1
    fi

    echo "This will start the backend and frontend separately."
    echo ""
    echo "Steps:"
    echo "1. Configure directories"
    echo "2. Validate project tree"
    echo "3. Generate codebase summary"
    echo "4. Start backend server (websocket_server.py)"
    echo "5. Start frontend dev server (npm start)"
    echo ""

    # Step 1: Configure directories
    configure_directories

    # Step 2: Show project tree and get confirmation
    if ! show_project_tree; then
        return 1
    fi

    if command -v uv &> /dev/null; then
        print_info "Syncing dependencies..."
        uv sync

        print_info "Generating codebase summary..."
        # Ensure PATH includes common binary locations
        export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
        uv run python backend/scripts/generate_summary.py --local
    else
        print_info "Generating codebase summary..."
        cd backend
        python scripts/generate_summary.py --local
        cd ..
    fi
    print_success "Summary generated"

    echo ""
    read -r -p "Start backend and frontend servers now? [Y/n]: " -r
    REPLY=${REPLY:-Y}
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Skipping server startup. To start manually:"
        echo ""
        echo "Terminal 1 (Backend):"
        echo "  cd $SCRIPT_DIR/backend"
        if command -v uv &> /dev/null; then
            echo "  uv run python websocket_server.py"
        else
            echo "  python websocket_server.py"
        fi
        echo ""
        echo "Terminal 2 (Frontend):"
        echo "  cd $SCRIPT_DIR/frontend"
        echo "  npm install"
        echo "  npm start -- --open"
        echo ""
        return 0
    fi

    # Install frontend dependencies if needed
    if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
        print_info "Installing frontend dependencies..."
        cd "$SCRIPT_DIR/frontend"
        npm ci
        cd "$SCRIPT_DIR"
    fi

    print_info "Starting backend server..."
    cd "$SCRIPT_DIR/backend"
    # Allow unauthenticated access for local testing (no Cognito configured)
    export ALLOW_ANONYMOUS=true
    if command -v uv &> /dev/null; then
        uv run python websocket_server.py > "$SCRIPT_DIR/backend.log" 2>&1 &
    else
        python websocket_server.py > "$SCRIPT_DIR/backend.log" 2>&1 &
    fi
    BACKEND_PID=$!
    cd "$SCRIPT_DIR"
    print_success "Backend started (PID: $BACKEND_PID)"

    # Wait a moment for backend to start
    sleep 2

    print_info "Starting frontend server..."
    cd "$SCRIPT_DIR/frontend"
    print_success "Frontend starting..."
    echo ""
    echo "Backend log: $SCRIPT_DIR/backend.log"
    echo ""
    print_success "Access the application at: http://localhost:3000/"
    echo ""
    print_warning "Servers are running. Press Ctrl+C to stop both servers."
    echo ""

    # Save backend PID for cleanup on exit
    echo "$BACKEND_PID" > "$SCRIPT_DIR/.backend.pid"

    # Trap Ctrl+C to cleanup backend process
    trap 'echo ""; print_info "Stopping servers..."; kill '"$BACKEND_PID"' 2>/dev/null; rm -f "'"$SCRIPT_DIR"'/.backend.pid"; exit 0' INT

    # Run frontend in foreground (this will block until Ctrl+C)
    npm start -- --open
}

# Function to ensure Docker daemon is running
ensure_docker_daemon() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker command not found. Please install Docker first (see 'Checking Prerequisite' section)"
        return 1
    fi

    # Check if Docker daemon is already running
    if docker ps &> /dev/null; then
        return 0
    fi

    # Docker daemon not running, start it
    if command -v colima &> /dev/null; then
        colima start &> /dev/null 2>&1 &
        print_info "Starting Colima daemon..."
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        open -a Docker &> /dev/null 2>&1 &
        print_info "Opening Docker Desktop..."
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        powershell -Command "Start-Process 'Docker Desktop'" &> /dev/null 2>&1 &
        print_info "Opening Docker Desktop..."
    fi
    sleep 3
    return 0
}

# Function for local testing with Docker (local artifacts)
local_test_docker_local() {
    print_header "Local Testing (Docker - Local Artifacts)"

    if ! ensure_docker_daemon; then
        return 1
    fi

    if ! validate_aws_credentials; then
        return 1
    fi

    echo "This will:"
    echo "1. Configure directories and generate Docker config"
    echo "2. Validate project tree"
    echo "3. Generate codebase summary locally"
    echo "4. Start Docker containers with local artifacts"
    echo ""

    # Step 1: Configure directories and generate Docker config
    if ! configure_directories_and_generate_docker_config; then
        return 1
    fi

    # Step 2: Show project tree and get confirmation
    if ! show_project_tree; then
        return 1
    fi

    if command -v uv &> /dev/null; then
        print_info "Syncing dependencies..."
        uv sync
        print_info "Generating codebase summary..."
        # Ensure PATH includes common binary locations
        export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
        uv run python backend/scripts/generate_summary.py --local
    else
        print_info "Generating codebase summary..."
        cd backend
        python scripts/generate_summary.py --local
        cd ..
    fi
    print_success "Summary generated"

    echo ""
    read -r -p "Force rebuild Docker images? [Recommended] [Y/n]: " -r
    REPLY=${REPLY:-Y}

    cd "$SCRIPT_DIR"
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Starting Docker with force rebuild..."
        ./scripts/start-docker.sh --force-build
    else
        print_info "Starting Docker..."
        ./scripts/start-docker.sh
    fi

    echo ""
    print_success "Access the application at: http://localhost:3000"
}

# Function for local testing with Docker (S3 artifacts)
local_test_docker_s3() {
    print_header "Local Testing (Docker - S3 Artifacts)"

    if ! ensure_docker_daemon; then
        return 1
    fi

    if ! validate_aws_credentials; then
        return 1
    fi

    echo "This will:"
    echo "1. Configure directories and generate Docker config"
    echo "2. Generate and upload codebase artifacts to S3"
    echo ""

    # Step 1: Configure directories and generate Docker config
    if ! configure_directories_and_generate_docker_config; then
        return 1
    fi

    # S3 Bucket Setup (same as cloud deployment)
    print_header "S3 Bucket Configuration"
    if ! s3_bucket=$(setup_s3_bucket); then
        return 1
    fi
    echo ""

    # Generate and Upload Artifacts (same as cloud deployment)
    print_header "Generate & Upload Artifacts"

    # Show project tree and get confirmation before generating artifacts
    if ! show_project_tree; then
        return 1
    fi

    if command -v uv &> /dev/null; then
        print_info "Syncing dependencies..."
        cd "$SCRIPT_DIR"
        uv sync
        print_info "Generating codebase summary and uploading to S3..."
        # Ensure PATH includes common binary locations
        export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
        if uv run python backend/scripts/generate_summary.py --s3-bucket "$s3_bucket"; then
            print_success "Artifacts uploaded to S3"
        else
            print_error "Failed to upload artifacts"
            return 1
        fi
    else
        print_info "Generating codebase summary and uploading to S3..."
        cd "$SCRIPT_DIR/backend"
        if python scripts/generate_summary.py --s3-bucket "$s3_bucket"; then
            cd "$SCRIPT_DIR"
            print_success "Artifacts uploaded to S3"
        else
            cd "$SCRIPT_DIR"
            print_error "Failed to upload artifacts"
            return 1
        fi
    fi
    cd "$SCRIPT_DIR"

    echo ""
    read -r -p "Force rebuild Docker images? [Recommended] [Y/n]: " -r
    REPLY=${REPLY:-Y}

    cd "$SCRIPT_DIR"
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ./scripts/start-docker-s3.sh --s3-bucket "$s3_bucket" --force-build
    else
        ./scripts/start-docker-s3.sh --s3-bucket "$s3_bucket"
    fi

    echo ""
    print_success "Access the application at: http://localhost:3000"
}

# Function to show project tree
show_project_tree() {
    print_header "Project Tree Preview"

    echo "This will show you exactly which files will be included for summarization."
    echo ""

    # Check if we have Python available
    if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
        print_error "Python not found. Please install Python to use this feature."
        return 1
    fi

    # Determine Python command
    local python_cmd="python3"
    if ! command -v python3 &> /dev/null; then
        python_cmd="python"
    fi

    # Run the project tree script
    if command -v uv &> /dev/null; then
        print_info "Using uv to run project tree script..."
        cd "$SCRIPT_DIR"
        if ! uv run python backend/scripts/show_project_tree.py; then
            print_error "Failed to generate project tree"
            return 1
        fi
    else
        print_info "Running project tree script with system Python..."
        cd "$SCRIPT_DIR"
        if ! $python_cmd backend/scripts/show_project_tree.py; then
            print_error "Failed to generate project tree"
            return 1
        fi
    fi

    echo ""
    print_info "Carefully review the file tree to make sure all necessary files and only the necessary files are included. Edit config.yaml to modify ignore_patterns otherwise."
    echo ""
    read -r -p "Do you want to proceed with these files? [Y/n]: " -r
    REPLY=${REPLY:-Y}

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "You can edit ignore_patterns in config.yaml to modify which files are included."
        return 1
    fi

    print_success "Project tree confirmed - proceeding..."
    return 0
}

# Function for cloud deployment
cloud_deploy_workflow() {
    print_header "Cloud Deployment Wizard"

    if ! ensure_docker_daemon; then
        return 1
    fi

    if ! validate_aws_credentials; then
        return 1
    fi

    echo "This wizard will guide you through deploying to AWS."
    echo ""

    # Step 1: Configure directories and generate Docker config
    print_header "Step 1: Configurations"
    if ! configure_directories_and_generate_docker_config; then
        return 1
    fi

    # Step 2: S3 Bucket Setup
    print_header "Step 2: S3 Bucket Configuration"
    if ! bucket_name=$(setup_s3_bucket); then
        return 1
    fi
    echo ""

    # Step 3: Region Selection
    print_header "Step 3: AWS Region Selection"
    read -r -e -p "Enter AWS region for deployment [us-east-1]: " deploy_region
    deploy_region=${deploy_region:-us-east-1}
    # Export the region to environment variables so CDK can pick it up
    export AWS_DEFAULT_REGION="$deploy_region"
    export AWS_REGION="$deploy_region"

    print_success "Region set to: $deploy_region"
    echo ""

    # Step 4: Configuration Review
    print_header "Step 4: Configuration Review"

    # Step 4a: CDK Stack Name
    current_stack_name=$(grep "^app_name:" "$SCRIPT_DIR/infra/config.yaml" | sed 's/app_name: "\(.*\)"/\1/' | tr -d '"')
    print_info "Current CDK stack name: $current_stack_name"
    while true; do
        print_prompt "Keep current CDK stack name? [Y/n]: "
        read -r reply
        reply=${reply:-Y}
        case $reply in
            [Yy]* )
                print_info "Keeping current CDK stack name: $current_stack_name"
                break
                ;;
            [Nn]* )
                # User chose no, get new stack name
                read -r -p "Enter new CDK stack name [$current_stack_name]: " new_stack_name
                new_stack_name=${new_stack_name:-$current_stack_name}
                if [ -n "$new_stack_name" ]; then
                    update_app_name "$new_stack_name"
                else
                    print_warning "Stack name cannot be empty. Keeping current name: $current_stack_name"
                fi
                break
                ;;
            * )
                print_error "Please answer y or n."
                ;;
        esac
    done
    echo ""

    # Step 4b: Frontend App Name
    current_frontend_name=""
    if [ -f "$SCRIPT_DIR/frontend/runtime-config-cloud.js" ]; then
        current_frontend_name=$(grep "appName:" "$SCRIPT_DIR/frontend/runtime-config-cloud.js" | sed "s/.*appName: *'\([^']*\)'.*/\1/")
    fi
    print_info "Current frontend app name: $current_frontend_name"
    while true; do
        print_prompt "Keep current app name? [Y/n]: "
        read -r reply
        reply=${reply:-Y}
        case $reply in
            [Yy]* )
                print_info "Keeping current frontend app name: $current_frontend_name"
                break
                ;;
            [Nn]* )
                # User chose no, get new frontend name
                read -r -p "Enter new frontend app name [$current_frontend_name]: " new_frontend_name
                new_frontend_name=${new_frontend_name:-$current_frontend_name}
                if [ -n "$new_frontend_name" ]; then
                    update_react_app_name "$new_frontend_name"
                else
                    print_warning "Frontend app name cannot be empty. Keeping current name: $current_frontend_name"
                fi
                break
                ;;
            * )
                print_error "Please answer y or n."
                ;;
        esac
    done
    echo ""

    # Step 5: Generate and Upload Artifacts
    print_header "Step 5: Generate & Upload Artifacts"

    # Show project tree and get confirmation before generating artifacts
    if ! show_project_tree; then
        return 1
    fi

    if command -v uv &> /dev/null; then
        print_info "Syncing dependencies..."
        cd "$SCRIPT_DIR"
        uv sync
        print_info "Generating codebase summary and uploading to S3..."
        # Ensure PATH includes common binary locations
        export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
        if uv run python backend/scripts/generate_summary.py --s3-bucket "$bucket_name"; then
            print_success "Artifacts uploaded to S3"
        else
            print_error "Failed to upload artifacts"
            return 1
        fi
    else
        print_info "Generating codebase summary and uploading to S3..."
        cd "$SCRIPT_DIR/backend"
        if python scripts/generate_summary.py --s3-bucket "$bucket_name"; then
            cd "$SCRIPT_DIR"
            print_success "Artifacts uploaded to S3"
        else
            cd "$SCRIPT_DIR"
            print_error "Failed to upload artifacts"
            return 1
        fi
    fi
    cd "$SCRIPT_DIR"
    echo ""

    # Step 6: Deploy Infrastructure
    print_header "Step 6: Deploy Infrastructure with CDK"

    print_info "This will deploy the infrastructure to AWS..."
    read -r -p "Proceed with CDK deployment? This process may take a few minutes. [Y/n]: " -r
    REPLY=${REPLY:-Y}
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Deployment cancelled"
        return 0
    fi

    cd "$SCRIPT_DIR/infra"

    # Check if CDK is installed
    if ! command -v cdk &> /dev/null; then
        print_error "AWS CDK CLI not found. Install with: npm install -g aws-cdk"
        return 1
    fi

    print_info "Running CDK deployment..."

    # Determine CDK command prefix and app path based on installation approach (uv or pip)
    if command -v uv &> /dev/null; then
        cdk_prefix="uv run "
        app_path="python \"$SCRIPT_DIR/infra/app.py\""
    else
        cdk_prefix=""
        app_path="\"$SCRIPT_DIR/.venv/bin/python\" app.py"
    fi

    # Check if CDK bootstrap stack exists
    print_info "Checking CDK bootstrap status in region $deploy_region..."
    if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region "$deploy_region" &>/dev/null; then
        print_warning "CDK bootstrap stack (CDKToolkit) not found in region $deploy_region"
        echo ""
        echo "CDK requires a bootstrap stack to deploy resources. You can run bootstrap with:"
        echo ""
        echo "1. Default settings:"
        echo "   ${cdk_prefix}cdk bootstrap aws://ACCOUNT-ID/$deploy_region"
        echo ""
        echo "2. Custom settings (e.g., custom bucket name, stack name):"
        echo "   ${cdk_prefix}cdk bootstrap aws://ACCOUNT-ID/$deploy_region \\"
        echo "     --bootstrap-bucket-name my-custom-bucket \\"
        echo "     --toolkit-stack-name MyCustomCDKToolkit \\"
        echo "     --qualifier myqualifier"
        echo ""
        print_prompt "Continue CDK deployment? (in case bootstrap has been done with different stack name or is just manually done now) (Y/n)"
        read -r continue_deployment

        if [[ "$continue_deployment" =~ ^[Yy]([Ee][Ss])?$ ]]; then
            print_info "Proceeding with deployment (assuming bootstrap was already done)..."
        else
            print_info "Please run the bootstrap command above, then restart deployment."
            return 1
        fi
    else
        print_success "CDK bootstrap stack found - environment ready"
    fi

    print_info "Starting deployment (this may take several minutes)..."

    # shellcheck disable=SC2086
    if ! ${cdk_prefix}cdk deploy --context region="$deploy_region" --app "$app_path"; then
        deploy_result=1
    else
        deploy_result=0
    fi

    if [ $deploy_result -eq 0 ]; then
        print_success "Deployment complete!"
        echo ""

        # Extract CloudFormation stack outputs
        print_info "Extracting deployment outputs..."
        print_info "Stack name: $current_stack_name"
        print_info "Region: $deploy_region"

        # Wait for outputs to be available (retry up to 5 times with 5 second delay)
        for i in {1..5}; do
            cloudfront_url=$(aws cloudformation describe-stacks --stack-name "$current_stack_name" --region "$deploy_region" --query "Stacks[0].Outputs[?OutputKey=='CloudFrontURL'].OutputValue" --output text 2>/dev/null || echo "")
            cognito_pool_url=$(aws cloudformation describe-stacks --stack-name "$current_stack_name" --region "$deploy_region" --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolUrl'].OutputValue" --output text 2>/dev/null || echo "")

            print_info "Attempt $i: cloudfront_url='$cloudfront_url', cognito_pool_url='$cognito_pool_url'"

            if [ -n "$cloudfront_url" ] && [ -n "$cognito_pool_url" ]; then
                break
            fi

            if [ "$i" -lt 5 ]; then
                sleep 5
            fi
        done

        # Step 7: Post-Deployment Instructions
        print_header "Post-Deployment Steps"
        if [ -n "${cloudfront_url:-}" ] && [ "$cloudfront_url" != "None" ]; then
            echo "✅ Application URL: $cloudfront_url"
        else
            echo "⚠️  Application URL: Check CloudFormation Stack Outputs"
        fi
        echo ""
        echo "1. Create Cognito Users:"
        if [ -n "${cognito_pool_url:-}" ] && [ "$cognito_pool_url" != "None" ]; then
            echo "   - User Pool Console:"
            print_info "  $cognito_pool_url"
        fi
        echo "   - Go to AWS Console → CloudFormation → Your Stack → Resources"
        echo "   - Find and click on the Cognito User Pool"
        echo "   - Click 'Users' → 'Create user'"
        echo ""
        echo "   Email-based users:"
        echo "   - User name: user@example.com"
        echo "   - Email address: user@example.com"
        echo "   - ✅ Mark email address as verified"
        echo "   - Set temporary password"
        echo ""
        echo "   Username-based users:"
        echo "   - User name: johndoe (custom username)"
        echo "   - Email address: user@example.com"
        echo "   - ✅ Mark email address as verified"
        echo "   - Set temporary password"
        echo "   - ⚠️  IMPORTANT: Administrator must login first to set permanent password"
        echo "   - Only then share credentials with actual user"
        echo ""
        echo "   📖 For detailed user creation instructions, see docs/user-management.md"
        echo ""
        echo "2. Access Your Application:"
        if [ -n "${cloudfront_url:-}" ] && [ "$cloudfront_url" != "None" ]; then
            echo "   - URL: "
            print_info "  $cloudfront_url"
        else
            echo "   - Find the CloudFront URL in CloudFormation Stack Outputs"
        fi
        echo "   - Share this URL with your users"
        echo ""
    else
        print_error "Deployment failed. Check the error messages above."
        print_info "If the error is due to Docker Hub rate limiting. You can retry in a few minutes."
        return 1
    fi

    cd "$SCRIPT_DIR"
}


# Configure MCP server for a specific tool
configure_mcp_tool() {
    local tool_name="$1"
    local config_dir="$2"
    local config_filename="$3"
    local venv_python="$4"
    local server_path="$5"
    local aws_profile="$6"

    local config_file="$config_dir/$config_filename"
    print_info "Configuring MCP server for $tool_name..."

    mkdir -p "$config_dir"

    local config
    config=$([ -f "$config_file" ] && cat "$config_file" || echo '{"mcpServers":{}}')

    if echo "$config" | grep -q '"iris-server"'; then
        print_warning "iris-server already configured for $tool_name"
        return 0
    fi

    # Set timeout to 10 minutes (600000ms) for Kiro and Cline
    # Set timeout to 600000000ms for Amazon Q due to plugin bug (the plugin will divide the value with 1000)
    # MCP operations can take 30-60+ seconds for large codebases
    local timeout=600000
    if [ "$tool_name" = "Amazon Q" ]; then
        timeout=600000000
    fi

    # Use bash command with source activation for Kiro
    if [ "$tool_name" = "Kiro" ]; then
        local venv_activate
        if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
            venv_activate="${venv_python%/Scripts/python.exe}/Scripts/activate"
        else
            venv_activate="${venv_python%/bin/python}/bin/activate"
        fi

        config=$(echo "$config" | jq --arg activate "$venv_activate" --arg server "$server_path" --arg profile "$aws_profile" --argjson timeout "$timeout" \
            '.mcpServers["iris-server"] = {
                "command": "bash",
                "args": ["-c", ("source " + $activate + " && python " + $server)],
                "env": {"AWS_PROFILE": $profile},
                "timeout": $timeout,
                "disabled": false
            }')
    else
        # For Cline and Amazon Q, keep original direct python command
        config=$(echo "$config" | jq --arg python "$venv_python" --arg server "$server_path" --arg profile "$aws_profile" --argjson timeout "$timeout" \
            '.mcpServers["iris-server"] = {
                "command": $python,
                "args": [$server],
                "env": {"AWS_PROFILE": $profile},
                "timeout": $timeout,
                "disabled": false
            }')
    fi

    echo "$config" > "$config_file"
    print_success "$tool_name MCP server configured at: $config_file"
}

# Setup MCP server for AI assistants
setup_mcp_server() {
    print_header "MCP Server Deployment (Cline, Kiro and Amazon Q)"

    # Prompt for AWS profile
    print_info "AWS profiles are configured in ~/.aws/config (macOS/Linux) or %USERPROFILE%\.aws\config (Windows)"
    printf "\n"
    read -r -p "Enter AWS profile name used [default]: " aws_profile
    aws_profile=${aws_profile:-default}
    print_success "Using AWS profile: $aws_profile"
    echo ""

    # Detect OS and set config paths
    local is_windows=false
    [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]] && is_windows=true

    local cline_dir q_dir kiro_dir
    if [ "$is_windows" = true ]; then
        cline_dir="$APPDATA/Code/User/globalStorage/saoudrizwan.claude-dev/settings"
        q_dir="$APPDATA/amazonq"
        kiro_dir="$HOME/.kiro/settings"
    else
        cline_dir="$HOME/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings"
        q_dir="$HOME/.aws/amazonq"
        kiro_dir="$HOME/.kiro/settings"
    fi

    # Detect installed tools
    local found_tools=()
    local tool_dirs=()
    local tool_files=()

    if [ -d "$cline_dir" ]; then
        found_tools+=("Cline")
        tool_dirs+=("$cline_dir")
        tool_files+=("cline_mcp_settings.json")
    fi

    if [ -d "$q_dir" ]; then
        found_tools+=("Amazon Q")
        tool_dirs+=("$q_dir")
        tool_files+=("mcp.json")
    fi

    if [ -d "$kiro_dir" ]; then
        found_tools+=("Kiro")
        tool_dirs+=("$kiro_dir")
        tool_files+=("mcp.json")
    fi

    if [ ${#found_tools[@]} -eq 0 ]; then
        print_warning "No AI assistant tools detected."
        print_info "Please install Cline, Kiro or Amazon Q first."
        return 1
    fi

    print_success "Detected: ${found_tools[*]}"
    echo ""

    # Get venv python path
    local venv_python
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        if [ -d "$SCRIPT_DIR/.venv" ]; then
            venv_python="$SCRIPT_DIR/.venv/Scripts/python.exe"
        elif [ -d "$SCRIPT_DIR/venv" ]; then
            venv_python="$SCRIPT_DIR/venv/Scripts/python.exe"
        else
            print_error "Virtual environment not found."
            return 1
        fi
    else
        if [ -d "$SCRIPT_DIR/.venv" ]; then
            venv_python="$SCRIPT_DIR/.venv/bin/python"
        elif [ -d "$SCRIPT_DIR/venv" ]; then
            venv_python="$SCRIPT_DIR/venv/bin/python"
        else
            print_error "Virtual environment not found."
            return 1
        fi
    fi

    local server_path="$SCRIPT_DIR/iris_mcp/mcp_server.py"

    # Configure each detected tool
    for i in "${!found_tools[@]}"; do
        configure_mcp_tool "${found_tools[$i]}" "${tool_dirs[$i]}" "${tool_files[$i]}" "$venv_python" "$server_path" "$aws_profile"
    done

    echo ""
    print_success "MCP server configuration complete!"
    print_info "Restart your AI assistant tools to use the iris MCP server."
    echo ""
    print_info "To test the iris-server, try this question:"
    echo "  \"use codebase_query tool in iris-server mcp server to answer question: what does this repo do?\""
}

# Main menu
show_main_menu() {
    while true; do
        print_header "IRIS Deployment Tools with UI"
        echo "1. Local Testing (No Docker)"
        echo "2. Local Testing (Docker - Local Artifacts)"
        echo "3. Local Testing (Docker - S3 Artifacts)"
        echo "4. Cloud Deployment (Docker)"
        echo "5. MCP Server Deployment (Cline, Kiro and Amazon Q)"
        echo "6. Exit "
        echo ""
        read -r -p "Select option [1-6]: " choice

        case $choice in
            1)
                local_test_no_docker
                ;;
            2)
                local_test_docker_local
                ;;
            3)
                local_test_docker_s3
                ;;
            4)
                cloud_deploy_workflow
                ;;
            5)
                setup_mcp_server
                ;;
            6)
                print_info "Exiting..."
                exit 0
                ;;
            *)
                print_error "Invalid option. Please select 1-6."
                ;;
        esac

        echo ""
        read -r -p "Press Enter to return to main menu..."
    done
}

# Function to create config files from templates
create_config_files() {
    # Create config.yaml from template if it doesn't exist
    if [ ! -f "${SCRIPT_DIR}/config.yaml" ] && [ -f "${SCRIPT_DIR}/config_template.yaml" ]; then
        print_info "Creating config.yaml from config_template.yaml..."
        cp "${SCRIPT_DIR}/config_template.yaml" "${SCRIPT_DIR}/config.yaml"
        print_success "config.yaml created. Please update it with your settings."
    fi

    # Create infra/config.yaml from template if it doesn't exist
    if [ ! -f "${SCRIPT_DIR}/infra/config.yaml" ] && [ -f "${SCRIPT_DIR}/infra/config_template.yaml" ]; then
        print_info "Creating infra/config.yaml from infra/config_template.yaml..."
        cp "${SCRIPT_DIR}/infra/config_template.yaml" "${SCRIPT_DIR}/infra/config.yaml"
        print_success "infra/config.yaml created. Please update it with your settings."
    fi
}

# Function to setup config file features
# Main execution
main() {
    create_config_files
    check_prerequisites
    run_installation
    show_main_menu
}

# Run main function
main
