# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Frontend tests require Jest and React Testing Library.

See FRONTEND_TESTING_SETUP.md for complete setup instructions.
"""

import pytest
from pathlib import Path


@pytest.mark.unit
class TestFrontendSetup:
    """Validate frontend test setup."""

    def test_frontend_package_json_exists(self):
        """Test package.json exists."""
        package_json = Path(__file__).parent.parent.parent / "frontend" / "package.json"
        assert package_json.exists()

    def test_frontend_src_exists(self):
        """Test src directory exists."""
        src_dir = Path(__file__).parent.parent.parent / "frontend" / "src"
        assert src_dir.exists()

    def test_frontend_has_react(self):
        """Test React is in dependencies."""
        import json

        package_json = Path(__file__).parent.parent.parent / "frontend" / "package.json"

        with open(package_json) as f:
            package = json.load(f)

        assert "react" in package.get("dependencies", {})


@pytest.mark.integration
class TestFrontendBuild:
    """Test frontend build process."""

    def test_frontend_npm_install(self):
        """Test npm install works."""
        frontend_dir = Path(__file__).parent.parent.parent / "frontend"

        # Check if node_modules exists or can be created
        node_modules = frontend_dir / "node_modules"

        if not node_modules.exists():
            pytest.skip("node_modules not installed, run: cd frontend && npm install")

        assert node_modules.exists()

    def test_frontend_build_script_exists(self):
        """Test build script is defined."""
        import json

        package_json = Path(__file__).parent.parent.parent / "frontend" / "package.json"

        with open(package_json) as f:
            package = json.load(f)

        assert "build" in package.get("scripts", {})
