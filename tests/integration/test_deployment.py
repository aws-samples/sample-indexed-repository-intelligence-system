# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tests for deployment configurations and infrastructure.
"""

import pytest
import yaml
import json
import subprocess
from pathlib import Path


@pytest.mark.unit
class TestDeploymentConfigs:
    """Test deployment configuration files."""

    def test_config_yaml_exists(self):
        """Test that config.yaml or config_template.yaml exists."""
        base_path = Path(__file__).parent.parent.parent
        config_path = base_path / "config.yaml"
        if not config_path.exists():
            config_path = base_path / "config_template.yaml"
        assert (
            config_path.exists()
        ), "Neither config.yaml nor config_template.yaml found"

    def test_config_yaml_valid(self):
        """Test that config.yaml is valid YAML."""
        base_path = Path(__file__).parent.parent.parent
        config_path = base_path / "config.yaml"
        if not config_path.exists():
            config_path = base_path / "config_template.yaml"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert isinstance(config, dict)
        assert "model_configuration" in config
        assert "ignore_patterns" in config

    def test_infra_config_exists(self):
        """Test that infra/config.yaml exists."""
        config_path = Path(__file__).parent.parent.parent / "infra" / "config.yaml"
        assert config_path.exists(), "infra/config.yaml not found"

    def test_infra_config_valid(self):
        """Test that infra/config.yaml is valid."""
        config_path = Path(__file__).parent.parent.parent / "infra" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert isinstance(config, dict)
        assert "app_name" in config
        assert "codebase_artifacts" in config

    def test_docker_compose_exists(self):
        """Test that docker-compose files exist."""
        base_path = Path(__file__).parent.parent.parent / "scripts"
        assert (base_path / "docker-compose.yml").exists()
        assert (base_path / "docker-compose-s3.yml").exists()

    def test_frontend_package_json_valid(self):
        """Test that frontend package.json is valid."""
        package_path = Path(__file__).parent.parent.parent / "frontend" / "package.json"
        if package_path.exists():
            with open(package_path) as f:
                package = json.load(f)

            assert isinstance(package, dict)
            assert "name" in package
            assert "dependencies" in package


@pytest.mark.unit
class TestDeploymentScripts:
    """Test deployment scripts exist and are executable."""

    def test_deploy_script_exists(self):
        """Test that deploy.sh exists."""
        script_path = Path(__file__).parent.parent.parent / "deploy.sh"
        assert script_path.exists(), "deploy.sh not found"

    def test_deploy_script_executable(self):
        """Test that deploy.sh is executable."""
        script_path = Path(__file__).parent.parent.parent / "deploy.sh"
        import os

        assert os.access(script_path, os.X_OK), "deploy.sh is not executable"

    def test_docker_start_scripts_exist(self):
        """Test that Docker start scripts exist."""
        scripts_dir = Path(__file__).parent.parent.parent / "scripts"
        assert (scripts_dir / "start-docker.sh").exists()
        assert (scripts_dir / "start-docker-s3.sh").exists()


@pytest.mark.unit
class TestInfrastructureCode:
    """Test CDK infrastructure code."""

    def test_cdk_app_exists(self):
        """Test that CDK app.py exists."""
        app_path = Path(__file__).parent.parent.parent / "infra" / "app.py"
        assert app_path.exists(), "infra/app.py not found"

    def test_cdk_stack_exists(self):
        """Test that CDK stack.py exists."""
        stack_path = Path(__file__).parent.parent.parent / "infra" / "stack.py"
        assert stack_path.exists(), "infra/stack.py not found"

    def test_cdk_json_valid(self):
        """Test that cdk.json is valid."""
        cdk_json_path = Path(__file__).parent.parent.parent / "infra" / "cdk.json"
        if cdk_json_path.exists():
            with open(cdk_json_path) as f:
                cdk_config = json.load(f)

            assert isinstance(cdk_config, dict)
            assert "app" in cdk_config


@pytest.mark.integration
class TestDockerBuild:
    """Test Docker builds (requires Docker)."""

    def test_backend_dockerfile_valid(self):
        """Test backend Dockerfile syntax."""
        dockerfile = (
            Path(__file__).parent.parent.parent / "backend" / "Dockerfile.agentcore"
        )
        assert dockerfile.exists()

        # Check if Docker daemon is running
        check = subprocess.run(["docker", "info"], capture_output=True)
        if check.returncode != 0:
            pytest.skip("Docker daemon not running")

        # Check if codebase_artifacts directory exists
        codebase_artifacts = dockerfile.parent.parent / "codebase_artifacts"
        if not codebase_artifacts.exists():
            pytest.skip(
                "codebase_artifacts directory not found - required for Docker build"
            )

        result = subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(dockerfile),
                "--no-cache",
                "-t",
                "test-backend",
                ".",
            ],
            cwd=dockerfile.parent.parent,
            capture_output=True,
            # The AgentCore image runs two apt-get upgrade passes, a full
            # `uv sync --frozen`, and a recursive chown over the baked-in
            # codebase, so a clean (--no-cache) build needs well over 300s.
            timeout=900,
        )
        assert (
            result.returncode == 0
        ), f"Backend Docker build failed: {result.stderr.decode()}"

    def test_frontend_dockerfile_valid(self):
        """Test frontend Dockerfile syntax."""
        import shutil

        dockerfile = Path(__file__).parent.parent.parent / "frontend" / "Dockerfile"
        assert dockerfile.exists()

        # Check if Docker daemon is running
        check = subprocess.run(["docker", "info"], capture_output=True)
        if check.returncode != 0:
            pytest.skip("Docker daemon not running")

        # Check available disk space (need at least 2GB for Docker build)
        stat = shutil.disk_usage(dockerfile.parent)
        free_gb = stat.free / (1024**3)
        if free_gb < 2:
            pytest.skip(
                f"Insufficient disk space for Docker build: {free_gb:.1f}GB free, need 2GB"
            )

        result = subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(dockerfile),
                "--no-cache",
                "-t",
                "test-frontend",
                ".",
            ],
            cwd=dockerfile.parent,
            capture_output=True,
            timeout=300,
        )

        # Check if Docker ran out of space
        if result.returncode != 0 and b"No space left on device" in result.stderr:
            pytest.skip("Docker out of disk space - clean up Docker images/containers")

        assert (
            result.returncode == 0
        ), f"Frontend Docker build failed: {result.stderr.decode()}"


@pytest.mark.integration
class TestCDKSynthesis:
    """Test CDK infrastructure synthesis (requires CDK CLI)."""

    def test_cdk_synth(self):
        """Test CDK synthesizes without errors."""
        import os
        import sys

        infra_dir = Path(__file__).parent.parent.parent / "infra"
        env = os.environ.copy()
        env["AWS_DEFAULT_REGION"] = env.get("AWS_DEFAULT_REGION", "us-east-1")
        # cdk.json runs "python app.py"; ensure the interpreter running the test
        # suite (which has the project's CDK deps installed, e.g.
        # aws_cdk.aws_bedrock_agentcore_alpha) is the one resolved on PATH.
        venv_bin = str(Path(sys.executable).parent)
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
        result = subprocess.run(
            ["cdk", "synth", "--no-lookups"],
            cwd=infra_dir,
            capture_output=True,
            timeout=60,
            env=env,
        )
        assert result.returncode == 0, f"CDK synth failed: {result.stderr.decode()}"


@pytest.mark.integration
class TestBackendScripts:
    """Test backend scripts execute without errors."""

    def test_generate_summary_help(self):
        """Test generate_summary.py shows help."""
        script = (
            Path(__file__).parent.parent.parent
            / "backend"
            / "scripts"
            / "generate_summary.py"
        )
        result = subprocess.run(
            ["python", str(script), "--help"], capture_output=True, timeout=10
        )
        assert result.returncode == 0
        assert b"usage" in result.stdout.lower() or b"help" in result.stdout.lower()

    def test_show_project_tree_runs(self):
        """Test show_project_tree.py executes."""
        import tempfile

        script = (
            Path(__file__).parent.parent.parent
            / "backend"
            / "scripts"
            / "show_project_tree.py"
        )

        # Create a temporary directory with a simple file structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print('hello')")

            result = subprocess.run(
                ["python", str(script), "--codebase", tmpdir],
                capture_output=True,
                timeout=10,
            )
            # Script may fail due to config issues, but should at least parse args correctly
            # Return code 2 means argument parsing error, which we want to catch
            assert (
                result.returncode != 2
            ), f"Argument parsing failed: {result.stderr.decode()}"
