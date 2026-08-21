#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Script to create config_docker.yaml from config.yaml for Docker deployment.
Transforms local paths to Docker container paths.
"""

import yaml
from pathlib import Path


def create_docker_config():
    """Create config_docker.yaml with Docker-compatible paths."""

    # Path to config files (relative to project root)
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "config.yaml"
    docker_config_path = project_root / "config_docker.yaml"

    if not config_path.exists():
        print(f"❌ Error: {config_path} not found")
        return False

    # Load original config
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Transform paths for Docker
    original_codebase = config.get("codebase_dir", "")
    original_output = config.get("output_dir", "")
    original_artifact = config.get("artifact_dir", "")

    # Extract folder name from codebase path
    codebase_folder = Path(original_codebase).name

    # Set Docker paths
    config["codebase_dir"] = f"/app/codebase_data/codebase/{codebase_folder}"
    config["output_dir"] = "/app/codebase_data/output"

    # Blank artifact_dir: the host artifact folder is never mounted into the
    # container, so keeping the host path would only bake an unusable absolute
    # path (including the user's home directory) into the image. Artifacts reach
    # the container as a pre-built index inside the representation zip that is
    # unpacked into output_dir, and create_agent() enables the artifact tool from
    # that pre-computed artifact_overview.json. Leaving this blank therefore keeps
    # artifact QA working while making codebase-only deployments the clean default.
    config["artifact_dir"] = ""

    # Write Docker config with proper indentation
    with open(docker_config_path, "w") as f:
        yaml.dump(
            config,
            f,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
            width=200,
        )

    print(f"✅ Created {docker_config_path}")
    print(f"   Original codebase_dir: {original_codebase}")
    print(f"   Original output_dir: {original_output}")
    print(f"   Docker codebase_dir:   {config['codebase_dir']}")
    print(f"   Docker output_dir:     {config['output_dir']}")
    if original_artifact:
        print(f"   Original artifact_dir: {original_artifact}")
        print(
            "   Docker artifact_dir:   (blank — artifacts served from pre-built index)"
        )
    else:
        print("   Docker artifact_dir:   (blank — codebase-only mode)")

    return True


if __name__ == "__main__":
    create_docker_config()
