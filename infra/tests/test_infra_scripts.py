"""Tests for infrastructure scripts and Bicep templates."""

import os
import subprocess
import pytest

INFRA_DIR = os.path.join(os.path.dirname(__file__), "..")
SCRIPTS_DIR = os.path.join(INFRA_DIR, "scripts")
BICEP_DIR = os.path.join(INFRA_DIR, "bicep")


class TestShellScripts:
    """Validate shell scripts have valid syntax."""

    @pytest.fixture(params=[
        "deploy-foundation.sh",
        "setup-custom-engine-app-registrations.sh",
        "create-azure-bot-resource.sh",
        "deploy-agent.sh",
        "deploy-wrapper.sh",
        "setup-github-oidc.sh",
    ])
    def script_path(self, request):
        return os.path.join(SCRIPTS_DIR, request.param)

    def test_script_exists(self, script_path):
        assert os.path.exists(script_path), f"{script_path} does not exist"

    def test_script_is_executable(self, script_path):
        assert os.access(script_path, os.X_OK), f"{script_path} is not executable"

    def test_script_syntax_valid(self, script_path):
        """bash -n checks syntax without executing."""
        result = subprocess.run(
            ["bash", "-n", script_path],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error in {script_path}: {result.stderr}"

    def test_script_has_set_euo_pipefail(self, script_path):
        """All scripts should use strict mode."""
        with open(script_path) as f:
            content = f.read()
        assert "set -euo pipefail" in content


class TestBicep:
    """Validate Bicep template."""

    def test_foundation_bicep_exists(self):
        path = os.path.join(BICEP_DIR, "foundation.bicep")
        assert os.path.exists(path)

    def test_foundation_bicep_has_outputs(self):
        path = os.path.join(BICEP_DIR, "foundation.bicep")
        with open(path) as f:
            content = f.read()
        assert "output " in content
        assert "logWorkspaceId" in content
        assert "keyVaultName" in content
        assert "acrName" in content
