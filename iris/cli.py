# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
IRIS CLI - Modern interface using the new architecture.
"""

import click
import os
import sys
import subprocess
from pathlib import Path
import logging

from .file_system.file_management import validate_tree
from .generate_context import generate_context
from .generate_artifact_context import generate_artifact_context
from .artifacts import resolve_artifact_dir
from .agentic_chat import cli_chat
from .utils.utils import (
    construct_output_dir,
    get_additional_context,
    get_ignore_patterns,
    load_default_config,
)

log = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """IRIS CLI tool for analyzing codebases."""
    if ctx.invoked_subcommand is None:
        # Default behavior: start interactive chat
        ctx.invoke(chat)


@cli.command()
@click.option("--codebase", "-c", help="Path to codebase directory")
@click.option("--context", help="Path to additional context file")
@click.option(
    "--skip-validation", is_flag=True, help="Skip tree validation confirmation"
)
def chat(codebase, context, skip_validation):
    """Start interactive chat."""

    # Validate tree and get user confirmation
    if not _validate_tree_with_confirmation(codebase, skip_validation):
        print(
            "❌ Tree validation cancelled. Please adjust your ignore patterns in the config file and try again."
        )
        sys.exit(1)

    # Load config and set up proper paths
    config = load_default_config()

    if codebase is None:
        codebase = config["codebase_dir"]

    # Construct output_dir using config pattern
    output_dir = construct_output_dir(codebase_dir=codebase)
    ignore_patterns = get_ignore_patterns(codebase_dir=codebase)
    additional_context = get_additional_context(filepath=context)

    try:
        # Use the core generate_context function directly
        result = generate_context(
            codebase_dir=codebase,
            output_dir=str(output_dir),
            ignore_patterns=ignore_patterns,
            additional_context=additional_context,
        )

        if result.status == "error":
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    try:
        # Load config and start agentic chat
        cli_chat(codebase_dir=codebase, context=context)
    except Exception as e:
        print(f"❌ Error during agentic chat: {e}")
        sys.exit(1)


@cli.command()
@click.option("--codebase", "-c", help="Path to codebase directory")
@click.option(
    "--code", is_flag=True, default=False, help="Generate/update codebase context only"
)
@click.option(
    "--artifact",
    is_flag=True,
    default=False,
    help="Generate/update project artifacts context only",
)
@click.option("--context", help="Path to additional context file")
@click.option(
    "--verbose/--no-verbose",
    "-v",
    default=True,
    help="Show detailed progress information (default: enabled)",
)
@click.option(
    "--force", is_flag=True, help="Re-extract all artifacts, ignoring the cache"
)
def prepare(codebase, code, artifact, context, verbose, force):
    """Generate/update codebase and artifact context.

    By default (no flags), generates both codebase and artifact context.
    Use --code to generate codebase context only.
    Use --artifact to generate artifact context only.
    """

    # If neither flag is set, do both
    do_codebase = True
    do_artifact = True
    if code or artifact:
        do_codebase = code
        do_artifact = artifact

    # Load config and set up proper paths
    config = load_default_config()

    if codebase is None:
        codebase = config["codebase_dir"]

    # Construct output_dir using config pattern
    output_dir = construct_output_dir(codebase_dir=codebase)
    ignore_patterns = get_ignore_patterns(codebase_dir=codebase)
    additional_context = get_additional_context(filepath=context)

    try:
        if do_codebase:
            # Use the core generate_context function directly
            result = generate_context(
                codebase_dir=codebase,
                output_dir=str(output_dir),
                ignore_patterns=ignore_patterns,
                additional_context=additional_context,
                verbose=verbose,  # CLI wants verbose output
            )

            if result.status == "error":
                sys.exit(1)

        if do_artifact:
            artifact_dir = resolve_artifact_dir(config)
            if artifact_dir:
                artifact_result = generate_artifact_context(
                    artifact_dir=artifact_dir,
                    output_dir=str(output_dir),
                    config=config,
                    verbose=verbose,
                    force=force,
                )
                if artifact_result.status == "error":
                    print(f"⚠️  Artifact indexing failed: {artifact_result.message}")
                elif verbose and artifact_result.status == "update_complete":
                    print("\n📊 Artifact Summary:")
                    print(f"   Total artifacts: {artifact_result.total_artifacts}")
                    print(
                        f"   Processed: {len(artifact_result.processed_artifacts or [])}"
                    )
                    if artifact_result.knowledge_base_size:
                        print(
                            f"   Knowledge base: {artifact_result.knowledge_base_size} characters"
                        )
            else:
                print(
                    "⚠️  No usable artifact_dir configured (unset, placeholder, or "
                    "missing directory). Skipping artifact indexing."
                )

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


@cli.command()
def streamlit():
    """Launch the Streamlit UI for IRIS."""
    # Get the path to the streamlit app
    current_dir = Path(__file__).resolve().parent
    streamlit_app_path = current_dir.parent / "streamlit" / "app.py"

    # Launch streamlit with the app
    try:
        print("🚀 Launching Streamlit UI...")
        subprocess.run(["streamlit", "run", str(streamlit_app_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error launching Streamlit: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Streamlit not found. Please install it with: pip install streamlit")
        sys.exit(1)


@cli.command()
def ui():
    """Launch the React App UI with WebSocket backend for IRIS."""
    import time
    import signal
    import requests

    # Store backend process for cleanup
    backend_process = None

    def cleanup_backend():
        """Clean up the backend process"""
        nonlocal backend_process
        if backend_process and backend_process.poll() is None:
            print("\n🛑 Stopping AgentCore Runtime server...")
            backend_process.terminate()
            try:
                backend_process.wait(timeout=5)
                print("✅ AgentCore Runtime server stopped")
            except subprocess.TimeoutExpired:
                print("⚠️  Force killing AgentCore Runtime server...")
                backend_process.kill()
                backend_process.wait()

    def signal_handler(signum, frame):
        """Handle Ctrl+C gracefully"""
        cleanup_backend()
        sys.exit(0)

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Check if Python is available
        try:
            result = subprocess.run(
                ["python", "--version"], capture_output=True, text=True, check=True
            )
            python_version = result.stdout.strip()
            print(f"✅ Python found: {python_version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ Python not found. Please ensure Python is installed and in PATH.")
            sys.exit(1)

        # Check if Node.js is installed
        try:
            result = subprocess.run(
                ["node", "--version"], capture_output=True, text=True, check=True
            )
            node_version = result.stdout.strip()
            print(f"✅ Node.js found: {node_version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(
                "❌ Node.js not found. Please install Node.js from https://nodejs.org/"
            )
            sys.exit(1)

        # Check if npm is installed
        try:
            result = subprocess.run(
                ["npm", "--version"], capture_output=True, text=True, check=True
            )
            npm_version = result.stdout.strip()
            print(f"✅ npm found: {npm_version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ npm not found. Please install npm (usually comes with Node.js)")
            sys.exit(1)

        # Get paths
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parent  # Go up 1 level: iris -> project root
        react_app_path = project_root / "frontend"
        backend_path = project_root / "backend"

        # Check if React app directory exists
        if not react_app_path.exists():
            print(f"❌ React app directory not found: {react_app_path}")
            sys.exit(1)

        # Check if backend directory exists
        if not backend_path.exists():
            print(f"❌ Backend directory not found: {backend_path}")
            sys.exit(1)

        # Check if package.json exists
        package_json_path = react_app_path / "package.json"
        if not package_json_path.exists():
            print(f"❌ package.json not found in: {react_app_path}")
            sys.exit(1)

        # Check if the AgentCore Runtime entrypoint exists
        agent_runtime_path = backend_path / "agent_runtime.py"
        if not agent_runtime_path.exists():
            print(f"❌ Agent runtime not found: {agent_runtime_path}")
            sys.exit(1)

        # Install npm dependencies if needed
        node_modules_path = react_app_path / "node_modules"
        vite_path = node_modules_path / ".bin" / "vite"

        # Check if dependencies need to be installed (node_modules missing or vite not found)
        if not node_modules_path.exists() or not vite_path.exists():
            print("📦 Installing React dependencies...")
            try:
                subprocess.run(["npm", "install"], cwd=str(react_app_path), check=True)
                print("✅ React dependencies installed successfully!")
            except subprocess.CalledProcessError as e:
                print(f"❌ Error installing React dependencies: {e}")
                sys.exit(1)

        # Start AgentCore Runtime server in background (local dev). This is the
        # SAME entrypoint deployed to AgentCore Runtime, so local matches cloud.
        print("🔌 Starting AgentCore Runtime server...")
        try:
            # Local dev environment for the agent process:
            # - CORS_ORIGINS: allow the React dev server (:3000) to call :8080.
            # - ALLOW_ANONYMOUS: no Cognito locally; skip inbound auth.
            agent_env = {
                **os.environ,
                "CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
                "ALLOW_ANONYMOUS": "true",
                "PORT": "8080",
            }
            backend_process = subprocess.Popen(
                ["python", str(agent_runtime_path)],
                cwd=str(project_root),
                env=agent_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Wait for server to be ready (health check on the AgentCore /ping route)
            print("⏳ Waiting for AgentCore Runtime server to start...")
            max_attempts = 30
            server_output = []

            for attempt in range(max_attempts):
                # Check if process is still running
                if backend_process.poll() is not None:
                    # Process has terminated, get all output
                    remaining_output, _ = backend_process.communicate()
                    if remaining_output:
                        server_output.append(remaining_output)

                    print("❌ Agent runtime process terminated unexpectedly:")
                    print("Server output:")
                    for line in server_output:
                        print(f"  {line.strip()}")
                    sys.exit(1)

                # Read any available output
                try:
                    import select

                    if select.select([backend_process.stdout], [], [], 0)[0]:
                        line = backend_process.stdout.readline()
                        if line:
                            server_output.append(line.strip())
                            print(f"Backend: {line.strip()}")
                except Exception:
                    pass

                # Try health check
                try:
                    response = requests.get("http://localhost:8080/ping", timeout=1)
                    if response.status_code == 200:
                        print("✅ AgentCore Runtime server is ready!")
                        break
                except requests.exceptions.RequestException:
                    pass

                time.sleep(1)
            else:
                print("❌ Agent runtime server failed to start within 30 seconds")
                print("Server output so far:")
                for line in server_output:
                    print(f"  {line}")
                cleanup_backend()
                sys.exit(1)

        except Exception as e:
            print(f"❌ Error starting agent runtime server: {e}")
            cleanup_backend()
            sys.exit(1)

        # Launch React app in foreground
        try:
            print("🚀 Launching React UI...")
            print("💡 Press Ctrl+C to stop both React app and AgentCore Runtime server")
            subprocess.run(
                ["npm", "run", "start", "--", "--open"],
                cwd=str(react_app_path),
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"❌ Error launching React app: {e}")
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
        finally:
            cleanup_backend()

    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        cleanup_backend()
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        cleanup_backend()
        sys.exit(1)


def _validate_tree_with_confirmation(codebase_dir=None, skip_validation=False):
    """
    Validate the directory tree and get user confirmation.

    Args:
        codebase_dir: Path to codebase directory
        skip_validation: Skip user confirmation if True

    Returns:
        bool: True if validation passes or is skipped, False if user rejects
    """
    files_result = validate_tree(codebase_dir=codebase_dir)

    # Display tree information
    if files_result.has_changed:
        change_details = files_result.change_details
        log.info("-" * 25)
        log.info("Changes detected:")
        log.info(f"  New files: {len(change_details['new_files'])}")
        log.info(f"  Modified files: {len(change_details['modified_files'])}")
        log.info(f"  Deleted files: {len(change_details['deleted_files'])}")
        log.info(f"  Files to process: {len(files_result.files_to_process)}")
        log.info("-" * 25)

        print(f"📝 Found changes in {len(files_result.files_to_process)} files")

        if change_details["new_files"]:
            print(f"📄 New files ({len(change_details['new_files'])}):")
            for file_path in change_details["new_files"][:5]:  # Show first 5
                print(f"   + {file_path}")
            if len(change_details["new_files"]) > 5:
                print(f"   ... and {len(change_details['new_files']) - 5} more")

        if change_details["modified_files"]:
            print(f"📝 Modified files ({len(change_details['modified_files'])}):")
            for file_path in change_details["modified_files"][:5]:  # Show first 5
                print(f"   ~ {file_path}")
            if len(change_details["modified_files"]) > 5:
                print(f"   ... and {len(change_details['modified_files']) - 5} more")

        if change_details["deleted_files"]:
            print(f"🗑️  Deleted files ({len(change_details['deleted_files'])}):")
            for file_path in change_details["deleted_files"][:5]:  # Show first 5
                print(f"   - {file_path}")
            if len(change_details["deleted_files"]) > 5:
                print(f"   ... and {len(change_details['deleted_files']) - 5} more")
    else:
        print("✅ No changes detected - codebase context is up to date")

    print(f"\n📁 File tree ({files_result.total_files} files):")
    print(files_result.tree_display)

    # Skip confirmation if requested
    if skip_validation:
        print("⏭️  Skipping tree validation confirmation")
        return True

    # Get user confirmation
    return click.confirm(
        "\nDoes the tree capture all the files and only the files you want to include?",
        default=True,
    )


if __name__ == "__main__":
    cli()
