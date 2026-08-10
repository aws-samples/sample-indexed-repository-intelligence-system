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
    echo "  iris chat               - Interactive chat"
    echo "  iris ui                 - Launch ReAct UI"
    echo "  iris streamlit          - Launch legacy Streamlit UI"
    echo "  iris prepare            - Generate/update codebase context"
    echo ""
    echo "  Command options:"
    echo "  --codebase, -c <path>         - Specify codebase directory"
    echo "  --skip-validation             - Skip tree validation confirmation"
    echo ""
    print_info "If you need more deployment options with UI besides iris CLI, continue with the menu below."
    print_info "Otherwise, choose option 7 in the menu to exit."
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

# Sanitize an arbitrary string into a valid AgentCore Runtime name.
# Runtime names must match [a-zA-Z][a-zA-Z0-9_]{0,47} (letters, digits,
# underscores only; no hyphens; must start with a letter; max 48 chars).
# Mirrors _resolve_runtime_name() in infra/stack.py so the proposed default
# matches what CDK would synthesize.
sanitize_runtime_name() {
    local raw=$1
    local sanitized
    # Replace every disallowed character with an underscore.
    sanitized=$(printf '%s' "$raw" | sed 's/[^a-zA-Z0-9_]/_/g')
    # Ensure it starts with a letter.
    if ! printf '%s' "$sanitized" | grep -q '^[a-zA-Z]'; then
        sanitized="iris_${sanitized}"
    fi
    # Enforce the 48-character limit.
    printf '%s' "${sanitized:0:48}"
}

# Read the current runtime_name from infra/config.yaml (may be empty).
get_runtime_name() {
    local config_file="$SCRIPT_DIR/infra/config.yaml"
    [ -f "$config_file" ] || return 0
    grep "^runtime_name:" "$config_file" | sed 's/^runtime_name: *"\(.*\)".*/\1/' | tr -d '"'
}

# Persist the chosen runtime name to infra/config.yaml. Adds the key if the
# config predates this field.
update_runtime_name() {
    local runtime_name=$1
    local config_file="$SCRIPT_DIR/infra/config.yaml"

    if [ ! -f "$config_file" ]; then
        print_error "infra/config.yaml not found"
        return 1
    fi

    if grep -q "^runtime_name:" "$config_file"; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/^runtime_name: \".*\"/runtime_name: \"$runtime_name\"/" "$config_file"
        else
            sed -i "s/^runtime_name: \".*\"/runtime_name: \"$runtime_name\"/" "$config_file"
        fi
    else
        # Older config without the field: append it.
        printf '\nruntime_name: "%s"\n' "$runtime_name" >> "$config_file"
    fi

    print_success "Updated infra/config.yaml with runtime_name: $runtime_name"
}

# Check whether an AgentCore Runtime name can be used by the target stack in
# the given region. Returns 0 (usable) when no runtime with that name exists, or
# when the only runtime with that name is already owned by the stack we're about
# to deploy (an in-place update, not a collision). Returns 1 when the name is
# owned by a different stack or is orphaned. On API/permission errors it warns
# and treats the name as usable so a missing read permission never hard-blocks a
# deploy.
runtime_name_available() {
    local name=$1
    local region=$2
    local stack_name=$3
    local existing
    if ! existing=$(aws bedrock-agentcore-control list-agent-runtimes \
        --region "$region" \
        --query "agentRuntimes[?agentRuntimeName=='$name'].agentRuntimeName" \
        --output text 2>/dev/null); then
        print_warning "Could not check AgentCore Runtime availability (list-agent-runtimes failed). Proceeding without the check." >&2
        return 0
    fi
    if [ -z "$existing" ] || [ "$existing" == "None" ]; then
        return 0
    fi
    # A runtime with this name exists. It's only a problem if it isn't already
    # owned by the stack we're deploying — otherwise CDK updates it in place.
    local owned
    owned=$(aws cloudformation list-stack-resources \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "StackResourceSummaries[?ResourceType=='AWS::BedrockAgentCore::Runtime' && starts_with(PhysicalResourceId, '${name}-')].PhysicalResourceId" \
        --output text 2>/dev/null || echo "")
    if [ -n "$owned" ] && [ "$owned" != "None" ]; then
        print_info "Runtime '$name' is already owned by stack '$stack_name' — will update in place." >&2
        return 0
    fi
    return 1
}

# Pre-flight check on the target CloudFormation stack's state, warning about
# cases 'cdk deploy' cannot cleanly update in place. Returns 0 to proceed, 1 to
# abort. On API/permission errors (or a not-yet-existing stack) it proceeds
# silently so a first-time deploy is never blocked.
check_stack_deployable() {
    local stack_name=$1
    local region=$2
    local status
    status=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].StackStatus" \
        --output text 2>/dev/null || echo "")

    # No stack yet (first deploy) or the status couldn't be read: nothing to warn about.
    if [ -z "$status" ] || [ "$status" == "None" ]; then
        return 0
    fi

    case "$status" in
        ROLLBACK_COMPLETE)
            # A failed initial create that rolled back cleanly: the stack is an
            # empty shell that never had a live resource (a stack that once
            # succeeded lands in UPDATE_ROLLBACK_COMPLETE instead). CDK will
            # delete the shell and create it fresh — the expected, non-destructive
            # move here — so default to proceeding.
            print_warning "Stack '$stack_name' is in ROLLBACK_COMPLETE (its initial create failed and rolled back)."
            echo "   No live resources exist. CDK will delete the empty stack and create it fresh."
            print_prompt "Continue with delete-and-recreate? [Y/n]: "
            read -r reply
            reply=${reply:-Y}
            if [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]; then
                return 0
            fi
            print_info "Deployment cancelled. Delete the stack manually if you want a clean recreate:"
            echo "   aws cloudformation delete-stack --stack-name '$stack_name' --region '$region'"
            return 1
            ;;
        ROLLBACK_FAILED)
            # A failed initial create whose rollback also failed. continue-update-rollback
            # does NOT apply here (it only recovers UPDATE_ROLLBACK_FAILED); the only path
            # forward is to delete the stack and redeploy.
            print_error "Stack '$stack_name' is in ROLLBACK_FAILED and cannot be updated by 'cdk deploy'."
            echo "   Its initial create failed and the rollback couldn't complete. Delete it, then re-run this deployment:"
            echo "       aws cloudformation delete-stack --stack-name '$stack_name' --region '$region'"
            return 1
            ;;
        UPDATE_ROLLBACK_FAILED)
            # A failed update whose rollback also failed. Recover via continue-update-rollback
            # (returns it to UPDATE_ROLLBACK_COMPLETE) or, as a last resort, delete and redeploy.
            print_error "Stack '$stack_name' is in UPDATE_ROLLBACK_FAILED and cannot be updated by 'cdk deploy'."
            echo "   Recover it first, then re-run this deployment. Options:"
            echo "   - Continue the rollback (returns it to a working state):"
            echo "       aws cloudformation continue-update-rollback --stack-name '$stack_name' --region '$region'"
            echo "   - Or delete the stack and redeploy:"
            echo "       aws cloudformation delete-stack --stack-name '$stack_name' --region '$region'"
            return 1
            ;;
        *_IN_PROGRESS)
            # Another stack operation is mid-flight; deploying now will error.
            print_error "Stack '$stack_name' has an operation in progress ($status)."
            echo "   Wait for it to finish (or check the CloudFormation console) before deploying."
            return 1
            ;;
        *)
            # CREATE_COMPLETE, UPDATE_COMPLETE, UPDATE_ROLLBACK_COMPLETE, etc. — deployable in place.
            return 0
            ;;
    esac
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
    echo "4. Start backend server (AgentCore Runtime: agent_runtime.py)"
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
        echo "  export ALLOW_ANONYMOUS=true CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000"
        if command -v uv &> /dev/null; then
            echo "  uv run python agent_runtime.py"
        else
            echo "  python agent_runtime.py"
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

    print_info "Starting backend server (AgentCore Runtime)..."
    cd "$SCRIPT_DIR/backend"
    # Allow unauthenticated access for local testing (no Cognito configured) and
    # enable CORS so the React dev server (:3000) can call the agent (:8080).
    export ALLOW_ANONYMOUS=true
    export CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
    if command -v uv &> /dev/null; then
        uv run python agent_runtime.py > "$SCRIPT_DIR/backend.log" 2>&1 &
    else
        python agent_runtime.py > "$SCRIPT_DIR/backend.log" 2>&1 &
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

# Serverless cloud deployment on Amazon Bedrock AgentCore Runtime.
# Deploys the Runtime + S3/CloudFront static frontend, then builds and uploads the
# frontend with the AgentRuntimeArn injected.
cloud_deploy_agentcore() {
    print_header "Cloud Deployment Wizard (AgentCore Runtime)"

    if ! ensure_docker_daemon; then
        return 1
    fi
    if ! validate_aws_credentials; then
        return 1
    fi

    echo "This deploys IRIS to AWS using Amazon Bedrock AgentCore Runtime."
    echo "The browser invokes the Runtime directly (Cognito JWT auth) and the"
    echo "React app is served from S3 via CloudFront."
    echo ""

    # Step 1: Configurations (codebase dir + docker config)
    print_header "Step 1: Configurations"
    if ! configure_directories_and_generate_docker_config; then
        return 1
    fi

    # Step 2: S3 bucket for codebase artifacts (Runtime pulls index at boot)
    print_header "Step 2: S3 Bucket Configuration"
    if ! bucket_name=$(setup_s3_bucket); then
        return 1
    fi
    echo ""

    # Step 3: Region
    print_header "Step 3: AWS Region Selection"
    read -r -e -p "Enter AWS region for deployment [us-east-1]: " deploy_region
    deploy_region=${deploy_region:-us-east-1}
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
                    current_stack_name="$new_stack_name"
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

    # Step 4c: AgentCore Runtime Name
    # Runtime names are unique per account+region, so propose a default derived
    # from the stack name, let the user confirm/change it, and check that the
    # chosen name isn't already taken before deploying.
    current_runtime_name=$(get_runtime_name)
    if [ -z "$current_runtime_name" ]; then
        current_runtime_name=$(sanitize_runtime_name "$current_stack_name")
        print_info "No runtime name set; proposing one derived from the stack name: $current_runtime_name"
    else
        print_info "Current AgentCore Runtime name: $current_runtime_name"
    fi
    while true; do
        print_prompt "Keep AgentCore Runtime name '$current_runtime_name'? [Y/n]: "
        read -r reply
        reply=${reply:-Y}
        case $reply in
            [Yy]* )
                : # keep current_runtime_name; validated below
                ;;
            [Nn]* )
                read -r -p "Enter new AgentCore Runtime name [$current_runtime_name]: " new_runtime_name
                new_runtime_name=${new_runtime_name:-$current_runtime_name}
                current_runtime_name=$(sanitize_runtime_name "$new_runtime_name")
                if [ "$current_runtime_name" != "$new_runtime_name" ]; then
                    print_info "Adjusted to a valid runtime name (letters/digits/underscores only): $current_runtime_name"
                fi
                ;;
            * )
                print_error "Please answer y or n."
                continue
                ;;
        esac

        # Availability check: reject a name owned by another runtime/stack.
        if runtime_name_available "$current_runtime_name" "$deploy_region" "$current_stack_name"; then
            print_success "Runtime name '$current_runtime_name' is available in $deploy_region"
            update_runtime_name "$current_runtime_name"
            break
        else
            print_warning "An AgentCore Runtime named '$current_runtime_name' already exists in $deploy_region."
            echo "   Names are unique per account+region. Choose a different name (or delete the existing runtime/stack first)."
        fi
    done
    echo ""

    # Step 4d: Target stack state pre-flight. Catch un-updatable/destructive
    # stack states now, before the expensive artifact upload in Step 5.
    if ! check_stack_deployable "$current_stack_name" "$deploy_region"; then
        return 1
    fi

    # Step 5: Generate & upload artifacts to S3 (the index the Runtime pulls at boot)
    print_header "Step 5: Generate & Upload Artifacts to S3"
    if ! show_project_tree; then
        return 1
    fi
    cd "$SCRIPT_DIR"
    if command -v uv &> /dev/null; then
        uv sync
        export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
        if ! uv run python backend/scripts/generate_summary.py --s3-bucket "$bucket_name"; then
            print_error "Failed to upload artifacts"
            return 1
        fi
    else
        cd "$SCRIPT_DIR/backend"
        if ! python scripts/generate_summary.py --s3-bucket "$bucket_name"; then
            cd "$SCRIPT_DIR"; print_error "Failed to upload artifacts"; return 1
        fi
        cd "$SCRIPT_DIR"
    fi
    print_success "Artifacts uploaded to S3"
    echo ""

    # Step 6: Deploy Infrastructure with CDK
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
    if ! ${cdk_prefix}cdk deploy --context region="$deploy_region" --app "$app_path" --require-approval never; then
        print_error "Deployment failed. Check the error messages above."
        return 1
    fi
    print_success "Deployment complete!"
    echo ""

    cd "$SCRIPT_DIR"

    # Extract CloudFormation stack outputs (retry up to 5 times with 5 second delay)
    print_info "Extracting deployment outputs..."
    print_info "Stack name: $current_stack_name"
    print_info "Region: $deploy_region"
    local runtime_arn user_pool_id client_id frontend_bucket cloudfront_url cognito_pool_url
    for i in {1..5}; do
        cloudfront_url=$(aws cloudformation describe-stacks --stack-name "$current_stack_name" --region "$deploy_region" --query "Stacks[0].Outputs[?OutputKey=='CloudFrontURL'].OutputValue" --output text 2>/dev/null || echo "")
        cognito_pool_url=$(aws cloudformation describe-stacks --stack-name "$current_stack_name" --region "$deploy_region" --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolUrl'].OutputValue" --output text 2>/dev/null || echo "")
        runtime_arn=$(aws cloudformation describe-stacks --stack-name "$current_stack_name" --region "$deploy_region" --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" --output text 2>/dev/null || echo "")
        user_pool_id=$(aws cloudformation describe-stacks --stack-name "$current_stack_name" --region "$deploy_region" --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolId'].OutputValue" --output text 2>/dev/null || echo "")
        client_id=$(aws cloudformation describe-stacks --stack-name "$current_stack_name" --region "$deploy_region" --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolClientId'].OutputValue" --output text 2>/dev/null || echo "")
        frontend_bucket=$(aws cloudformation describe-stacks --stack-name "$current_stack_name" --region "$deploy_region" --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text 2>/dev/null || echo "")

        print_info "Attempt $i: cloudfront_url='$cloudfront_url', cognito_pool_url='$cognito_pool_url'"

        if [ -n "$cloudfront_url" ] && [ -n "$cognito_pool_url" ]; then
            break
        fi

        if [ "$i" -lt 5 ]; then
            sleep 5
        fi
    done
    echo ""

    # Step 7: Build and upload the static frontend (served from S3 via CloudFront)
    print_header "Step 7: Build & Upload Frontend"
    if [ -z "$runtime_arn" ] || [ -z "$frontend_bucket" ]; then
        print_error "Could not read AgentRuntimeArn / FrontendBucketName from stack outputs."
        return 1
    fi
    print_info "Agent Runtime ARN: ${runtime_arn:0:50}..."
    print_info "Frontend bucket:   $frontend_bucket"

    cd "$SCRIPT_DIR/frontend"
    print_info "Installing frontend dependencies..."
    npm ci >/dev/null 2>&1 || npm install
    print_info "Building frontend..."
    if ! npm run build; then
        print_error "Frontend build failed"; return 1
    fi
    # Inject runtime config (Cognito + AgentRuntimeArn) into the built app
    cp runtime-config-cloud.js dist/runtime-config.js
    AWS_REGION="$deploy_region" \
        USER_POOL_ID="$user_pool_id" \
        USER_POOL_CLIENT_ID="$client_id" \
        AGENT_RUNTIME_ARN="$runtime_arn" \
        CONFIG_FILE="./dist/runtime-config.js" \
        ./inject-config.sh

    print_info "Uploading frontend to s3://$frontend_bucket ..."
    aws s3 sync dist/ "s3://$frontend_bucket/" --delete --region "$deploy_region"

    # Invalidate CloudFront so the new build is served immediately
    local dist_id
    dist_id=$(aws cloudfront list-distributions --query "DistributionList.Items[?contains(Comment, 'IRIS - static frontend')].Id" --output text 2>/dev/null | head -n1)
    if [ -n "$dist_id" ] && [ "$dist_id" != "None" ]; then
        print_info "Invalidating CloudFront distribution $dist_id ..."
        aws cloudfront create-invalidation --distribution-id "$dist_id" --paths "/*" >/dev/null 2>&1 || true
    fi
    cd "$SCRIPT_DIR"
    print_success "Frontend deployed"
    echo ""

    # Post-Deployment Instructions
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
    echo "   - User name: user@yourcompany.com"
    echo "   - Email address: user@yourcompany.com"
    echo "   - ✅ Mark email address as verified"
    echo "   - Set temporary password"
    echo ""
    echo "   Username-based users:"
    echo "   - User name: johndoe (custom username)"
    echo "   - Email address: john.doe@yourcompany.com"
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

    cd "$SCRIPT_DIR"
}


# Record this IRIS installation where the iris-query skill will look for it.
#
# The skill reads ${IRIS_HOME:-$HOME/.iris}/config.json to find an interpreter
# that can import iris. Writing it here at install time means the skill never has
# to scan the filesystem — and never wrongly concludes IRIS is missing when a
# clone simply sits deeper than its search reaches.
#
# Best-effort: a failure here must not fail the install, since the skill still
# has its own discovery path plus --python/IRIS_PYTHON.
write_iris_home_config() {
    local venv_python="$1" iris_repo="$2"
    local config_dir="${IRIS_HOME:-$HOME/.iris}"
    local config_file="$config_dir/config.json"

    if ! mkdir -p "$config_dir" 2>/dev/null; then
        print_warning "Could not create $config_dir — the skill will fall back to searching."
        return 0
    fi

    # Hand-rolled JSON: jq is not guaranteed, and this is two known-safe
    # absolute paths, not user-supplied text.
    if cat > "$config_file" <<EOF 2>/dev/null
{
  "version": 1,
  "python": "$venv_python",
  "iris_repo": "$iris_repo"
}
EOF
    then
        print_success "Recorded this IRIS install for the skill: $config_file"
        print_info "The skill uses this to locate IRIS from any working directory."
    else
        print_warning "Could not write $config_file — the skill will fall back to searching."
    fi
    return 0
}

# Install the iris-query Agent Skill into a target repo (Claude Code / Kiro)
#
# Ordering is deliberate: the skill is copied BEFORE indexing runs. If indexing
# fails (credentials, model access), the user still has a working-but-degraded
# install whose no-cache path explains what is missing. A Bedrock hiccup must
# not abort the whole option.
setup_agent_skill() {
    print_header "Agent Skill Installation (Claude Code, Kiro, Cline)"

    local skill_src="$SCRIPT_DIR/skills/iris-query"
    if [ ! -f "$skill_src/SKILL.md" ]; then
        print_error "Skill source not found at $skill_src"
        return 1
    fi

    print_info "Installs the 'iris-query' skill so coding assistants answer questions"
    print_info "from IRIS's precomputed index instead of exploring from scratch."
    print_info "This is separate from the MCP Server option (option 6) — both can coexist."
    echo ""

    # Step 1: venv must exist, since indexing needs the iris package.
    if ! detect_venv; then
        print_error "Virtual environment not found. Re-run this script and complete installation first."
        return 1
    fi

    local venv_python
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        if [ -d "$SCRIPT_DIR/.venv" ]; then
            venv_python="$SCRIPT_DIR/.venv/Scripts/python.exe"
        else
            venv_python="$SCRIPT_DIR/venv/Scripts/python.exe"
        fi
    else
        if [ -d "$SCRIPT_DIR/.venv" ]; then
            venv_python="$SCRIPT_DIR/.venv/bin/python"
        else
            venv_python="$SCRIPT_DIR/venv/bin/python"
        fi
    fi
    if [ ! -x "$venv_python" ]; then
        print_error "Virtual environment Python not found at: $venv_python"
        return 1
    fi

    # Record the interpreter and this IRIS clone for the skill to find later.
    # deploy.sh knows both authoritatively; without this the skill has to
    # rediscover them by scanning the filesystem, which fails outright when the
    # clone sits deeper than the search reaches.
    #
    # Written to $HOME (not into the skill folder) deliberately: the skill folder
    # is rm -rf'd on upgrade, and project-level copies get committed — an
    # absolute path in there would travel to teammates' machines where it is
    # meaningless.
    write_iris_home_config "$venv_python" "$SCRIPT_DIR"

    # Step 2: configure directories. output_dir should stay the relative
    # '.iris_cache', which IRIS resolves against codebase_dir — so the cache and
    # skill travel together inside the target repo and stay correct if the
    # codebase_dir changes later.
    print_info "Set the codebase directory to the repo you want indexed."
    print_info "Keep the output directory as '.iris_cache' (relative) — IRIS resolves"
    print_info "it against the codebase directory, so the cache lands inside the target"
    print_info "repo and can be committed alongside the skill."
    echo ""
    if ! configure_directories; then
        print_error "Directory configuration failed."
        return 1
    fi

    local codebase_dir output_dir_cfg cache_parent
    codebase_dir=$(grep "^codebase_dir:" "$SCRIPT_DIR/config.yaml" | sed 's/codebase_dir: //' | tr -d '"')
    if [ -z "$codebase_dir" ] || [ ! -d "$codebase_dir" ]; then
        print_error "codebase_dir is not set to a valid directory in config.yaml"
        return 1
    fi
    codebase_dir="$(cd "$codebase_dir" && pwd)"

    # Resolve where the cache will actually land, mirroring IRIS's own rule
    # (utils.py: construct_output_dir) — relative output_dir resolves against
    # codebase_dir, absolute is used as-is.
    output_dir_cfg=$(grep "^output_dir:" "$SCRIPT_DIR/config.yaml" | sed 's/output_dir: //' | tr -d '"')
    output_dir_cfg=${output_dir_cfg:-.iris_cache}
    case "$output_dir_cfg" in
        /*) cache_parent="$output_dir_cfg" ;;
        *)  cache_parent="$codebase_dir/$output_dir_cfg" ;;
    esac

    # configure_directories() mkdir's a relative output_dir against the current
    # working directory (this IRIS clone), not against codebase_dir. Harmless but
    # confusing: clean up the stray directory when it is empty, and make sure the
    # real cache parent exists instead.
    case "$output_dir_cfg" in
        /*) : ;;
        *)
            local stray="$SCRIPT_DIR/$output_dir_cfg"
            if [ -d "$stray" ] && [ "$stray" != "$cache_parent" ]; then
                rmdir "$stray" 2>/dev/null && \
                    print_info "Removed stray empty directory: $stray"
            fi
            ;;
    esac
    mkdir -p "$cache_parent" 2>/dev/null || true

    print_success "Target repo: $codebase_dir"
    print_info "Cache location: $cache_parent"
    if [ "$cache_parent" != "$codebase_dir/.iris_cache" ]; then
        print_warning "The cache is outside the default <repo>/.iris_cache."
        print_warning "It will not travel with the repo when teammates clone it."
    fi
    echo ""

    # Step 3: copy the skill into the chosen assistant directories.
    # Copy, never symlink: symlinks break when this IRIS clone moves and cannot
    # be committed usefully.
    local -a dest_roots=()
    local -a dest_labels=()

    local claude_installed=false kiro_installed=false cline_installed=false
    [ -d "$HOME/.claude" ] && claude_installed=true
    [ -d "$HOME/.kiro" ] && kiro_installed=true
    # Cline is a VS Code extension, so detect the extension dir rather than a
    # dotfile home — ~/.cline only appears once it has written global state.
    if [ -d "$HOME/.cline" ] || \
       compgen -G "$HOME/.vscode/extensions/saoudrizwan.claude-dev-*" >/dev/null 2>&1 || \
       compgen -G "$HOME/.vscode-server/extensions/saoudrizwan.claude-dev-*" >/dev/null 2>&1; then
        cline_installed=true
    fi

    local detected=""
    [ "$claude_installed" = true ] && detected="Claude Code"
    [ "$kiro_installed" = true ] && detected="${detected:+$detected, }Kiro"
    [ "$cline_installed" = true ] && detected="${detected:+$detected, }Cline"
    if [ -n "$detected" ]; then
        print_success "Detected on this machine: $detected"
    else
        print_warning "No supported assistant detected. You can still install for any of them."
    fi
    echo ""

    # Scope first. This matters more than it looks: a project-level skill is only
    # active when the assistant opens IN that repo, but people routinely run
    # Claude Code from a different directory (a workspace root, another project).
    # A user-level install is active in every session regardless of directory.
    echo "Where should the skill be installed?"
    echo ""
    echo "  1. User-level  ->  \$HOME/.claude|.kiro|.cline/skills/"
    echo "     Active in EVERY session, whatever directory the assistant opens."
    echo "     Pick this if your editor does not open the indexed repo itself."
    echo ""
    echo "  2. Project-level  ->  $codebase_dir/.claude|.kiro/skills/"
    echo "     Commit it so teammates get the skill from 'git clone'."
    echo "     Only active when the assistant opens THAT repo."
    echo ""
    echo "  3. Both (recommended if you are the person indexing)"
    echo "     You get it everywhere; your team gets it from the repo."
    echo ""
    local scope_choice
    read -r -p "Select [1-3] (default 3): " scope_choice
    scope_choice=${scope_choice:-3}

    local install_user=false install_project=false
    case "$scope_choice" in
        1) install_user=true ;;
        2) install_project=true ;;
        3) install_user=true; install_project=true ;;
        *) print_error "Invalid selection."; return 1 ;;
    esac
    echo ""

    echo "Which assistant(s)?"
    echo "  1. Claude Code"
    echo "  2. Kiro"
    echo "  3. Cline"
    echo "  4. All"
    echo ""
    echo "  (comma-separated also works, e.g. '1,3')"
    echo ""
    local target_choice
    read -r -p "Select [1-4] (default 4): " target_choice
    target_choice=${target_choice:-4}

    local want_claude=false want_kiro=false want_cline=false
    local piece
    # Accept a single digit or a comma-separated list, so "1,3" works.
    IFS=',' read -r -a _picks <<< "$target_choice"
    for piece in "${_picks[@]}"; do
        case "$(echo "$piece" | tr -d '[:space:]')" in
            1) want_claude=true ;;
            2) want_kiro=true ;;
            3) want_cline=true ;;
            4) want_claude=true; want_kiro=true; want_cline=true ;;
            "") ;;
            *) print_error "Invalid selection: $piece"; return 1 ;;
        esac
    done
    if [ "$want_claude" = false ] && [ "$want_kiro" = false ] && [ "$want_cline" = false ]; then
        print_error "No assistant selected."
        return 1
    fi

    # Destination mapping. Claude Code and Cline both read <repo>/.claude/skills
    # at project level (verified against Cline 4.1.4, which scans
    # .clinerules/skills, .cline/skills, .claude/skills, .agents/skills), so
    # project-level installs share ONE copy rather than duplicating it.
    # User-level differs: Cline's global roots are ~/.cline/skills and
    # ~/.agents/skills — it does NOT read ~/.claude/skills.
    if [ "$install_user" = true ]; then
        [ "$want_claude" = true ] && { dest_roots+=("$HOME/.claude/skills"); dest_labels+=("Claude Code (user-level)"); }
        [ "$want_kiro" = true ]   && { dest_roots+=("$HOME/.kiro/skills");   dest_labels+=("Kiro (user-level)"); }
        [ "$want_cline" = true ]  && { dest_roots+=("$HOME/.cline/skills");  dest_labels+=("Cline (user-level)"); }
    fi
    if [ "$install_project" = true ]; then
        if [ "$want_claude" = true ] || [ "$want_cline" = true ]; then
            local shared_label="Claude Code (project)"
            if [ "$want_claude" = true ] && [ "$want_cline" = true ]; then
                shared_label="Claude Code + Cline (project)"
            elif [ "$want_cline" = true ]; then
                shared_label="Cline (project)"
            fi
            dest_roots+=("$codebase_dir/.claude/skills")
            dest_labels+=("$shared_label")
        fi
        [ "$want_kiro" = true ] && { dest_roots+=("$codebase_dir/.kiro/skills"); dest_labels+=("Kiro (project)"); }
    fi
    echo ""

    local install_count=0 kept_count=0
    local i
    for i in "${!dest_roots[@]}"; do
        local dest_root="${dest_roots[$i]}"
        local label="${dest_labels[$i]}"
        local dest="$dest_root/iris-query"

        if [ -e "$dest" ]; then
            print_warning "$label: skill already installed at $dest"
            local overwrite
            read -r -p "Overwrite it (this is the upgrade path)? [Y/n]: " overwrite
            overwrite=${overwrite:-Y}
            case "$overwrite" in
                [Yy]*) rm -rf "$dest" ;;
                *)
                    # Declining to overwrite an existing install is a valid
                    # outcome, not a failure — the skill is already there.
                    print_info "$label: left unchanged (existing install kept)."
                    kept_count=$((kept_count + 1))
                    continue
                    ;;
            esac
        fi

        if ! mkdir -p "$dest_root"; then
            print_error "$label: could not create $dest_root"
            continue
        fi
        if ! cp -R "$skill_src" "$dest_root/"; then
            print_error "$label: copy failed"
            continue
        fi
        # Never ship build noise into someone else's repo — it would show up in
        # their git status.
        find "$dest" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
        find "$dest" -name ".DS_Store" -type f -delete 2>/dev/null || true
        chmod +x "$dest/scripts/"*.sh 2>/dev/null || true

        # Verify the artifacts actually landed at the expected paths.
        local missing=""
        local required
        for required in "SKILL.md" "scripts/check_staleness.py" \
                        "scripts/extract_overview.py" "scripts/iris_setup_lite.sh" \
                        "references/details.md"; do
            [ -f "$dest/$required" ] || missing="${missing:+$missing, }$required"
        done
        if [ -n "$missing" ]; then
            print_error "$label: install incomplete, missing: $missing"
            continue
        fi

        print_success "$label: skill installed at $dest"
        install_count=$((install_count + 1))

        # Kiro gets the manual-refresh hook; other hosts have no equivalent.
        if [ "$label" = "Kiro (project)" ]; then
            local hook_dir="$codebase_dir/.kiro/hooks"
            if mkdir -p "$hook_dir" && cp "$dest/templates/iris_reindex_manual.kiro.hook" "$hook_dir/"; then
                print_success "Kiro: manual refresh hook installed at $hook_dir/iris_reindex_manual.kiro.hook"
            else
                print_warning "Kiro: could not install the manual refresh hook (skill still works)"
            fi
        fi
    done

    if [ "$install_count" -eq 0 ] && [ "$kept_count" -eq 0 ]; then
        print_error "No skill installation completed."
        return 1
    fi
    if [ "$install_count" -eq 0 ]; then
        print_info "Existing installation(s) kept as-is."
    fi
    echo ""

    # Step 4: index. This is the only costly, credentialed step — and the only
    # one allowed to fail without failing the option.
    local index_ok=false
    print_info "The skill needs an index to query. Building it calls AWS Bedrock and incurs cost."
    print_info "It is incremental: only new or changed files are summarized."
    echo ""
    local do_index
    read -r -p "Build/update the index now? [Y/n]: " do_index
    do_index=${do_index:-Y}

    case "$do_index" in
        [Yy]*)
            if validate_aws_credentials; then
                print_info "Indexing $codebase_dir (this can take a while on a large repo)..."
                if "$venv_python" -m iris.cli prepare --codebase "$codebase_dir"; then
                    index_ok=true
                    print_success "Index built"
                else
                    print_warning "Indexing failed — the skill is installed but has no cache yet."
                    print_info "Fix the underlying issue (model access, credentials), then re-run"
                    print_info "this option or use the skill's own setup task."
                fi
            else
                print_warning "Skipping indexing: no usable AWS credentials."
                print_info "The skill is installed; it will explain the missing cache when asked."
            fi
            ;;
        *)
            print_info "Skipped indexing. The skill is installed but has no cache yet."
            ;;
    esac

    # Confirm what actually exists on disk, by glob — never by rebuilding the
    # cache folder name from the current directory name.
    local cache_dir=""
    local overview
    while IFS= read -r overview; do
        [ -n "$overview" ] || continue
        cache_dir="$(dirname "$overview")"
        break
    done < <(find "$cache_parent" -maxdepth 2 -name codebase_overview.json 2>/dev/null | sort)

    # Register the repo so a user-level skill install can locate this index from
    # any working directory. Best-effort: never fail the option over it.
    if [ -n "$cache_dir" ]; then
        if "$venv_python" "$skill_src/scripts/check_staleness.py" \
                --repo "$codebase_dir" --register >/dev/null 2>&1; then
            print_success "Registered for cross-directory queries"
        else
            print_warning "Could not update the indexed-repo registry"
            print_info "Queries still work when the repo is named or --repo is passed."
        fi
    fi

    # Step 5: next steps, stated explicitly — this is what turns a one-person
    # setup into a whole-team benefit, and users will not think of it themselves.
    print_header "Next Steps"

    if [ -n "$cache_dir" ]; then
        print_success "Index present at: $cache_dir"
    else
        print_warning "No index found under $cache_parent yet."
        echo "   Ask the assistant to \"set up the IRIS index\" in that repo, or re-run this option."
    fi
    echo ""

    local step=1

    if [ "$install_project" = true ]; then
        # Describe what to commit rather than printing exact git commands: the
        # commands would be generated from what was *requested*, not from what
        # landed on disk (an overwrite can be declined, the cache may live
        # elsewhere, the target may not even be git-tracked).
        echo "$step. Share with your team — commit the skill folder and the cache:"
        echo ""
        print_info "   In $codebase_dir, commit the skill directories installed above"
        print_info "   together with the .iris_cache/ directory. Note that dot-directories"
        print_info "   are often gitignored, so they may need to be force-added."
        echo ""
        print_info "   Teammates then need only 'git clone' — no IRIS install, no Python"
        print_info "   environment, and no AWS credentials to ask questions."
        if [ "$cache_parent" != "$codebase_dir/.iris_cache" ]; then
            echo ""
            print_warning "   The cache currently sits outside that repo ($cache_parent),"
            print_warning "   so it will not travel with a clone. Move it under the repo to share it."
        fi
        echo ""
        step=$((step + 1))
    else
        echo "$step. Share with your team (optional):"
        echo ""
        print_info "   You installed user-level only, so the skill is yours alone."
        print_info "   To give teammates the same thing from a plain 'git clone',"
        print_info "   re-run this option and choose project-level, then commit the"
        print_info "   installed skill folder along with .iris_cache/."
        print_info "   One committed .claude/skills/ serves Claude Code and Cline both."
        echo ""
        step=$((step + 1))
    fi

    echo "$step. Try it. Ask an assistant:"
    echo "     \"what does this repo do?\"  or  \"where is authentication handled?\""
    if [ "$install_user" = true ]; then
        echo ""
        print_info "   Because the skill is installed user-level, it works from ANY"
        print_info "   directory — the assistant does not have to open $codebase_dir."
        print_info "   This repo was registered, so the skill can locate its index."
        print_info "   With several indexed repos it will ask which one you mean;"
        print_info "   naming the repo in your question avoids the round-trip."
    fi
    echo ""
    step=$((step + 1))

    echo "$step. Refresh later, whenever you reach a good stopping point:"
    echo "     ask the assistant to \"refresh the IRIS index\", or re-run this option."
    if [ "$install_project" = true ] && [ "$want_kiro" = true ]; then
        echo "     Kiro users also get a 'Refresh IRIS Index' button in the hooks UI."
    fi
    echo ""
    print_info "Re-running this option after pulling IRIS updates is the upgrade path"
    print_info "for the skill — it will offer to overwrite the installed copy."

    if [ "$index_ok" = false ] && [ -z "$cache_dir" ]; then
        echo ""
        print_warning "Reminder: the skill works but will report a missing index until one is built."
    fi

    return 0
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
        echo "4. Cloud Deployment (AgentCore Runtime - serverless)"
        echo "5. Agent Skill Installation (Claude Code, Kiro, Cline)"
        echo "6. MCP Server Deployment (Cline, Kiro and Amazon Q)"
        echo "7. Exit "
        echo ""
        read -r -p "Select option [1-7]: " choice

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
                cloud_deploy_agentcore
                ;;
            5)
                setup_agent_skill
                ;;
            6)
                setup_mcp_server
                ;;
            7)
                print_info "Exiting..."
                exit 0
                ;;
            *)
                print_error "Invalid option. Please select 1-7."
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
