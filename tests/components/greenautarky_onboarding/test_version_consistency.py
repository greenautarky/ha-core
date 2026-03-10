"""Test that the frontend version is consistent across all pin locations.

The frontend version must match in 5 files:
  1. homeassistant_frontend/pyproject.toml
  2. homeassistant/components/frontend/manifest.json
  3. homeassistant/package_constraints.txt
  4. requirements_all.txt
  5. requirements_test_all.txt

A mismatch causes build failures or unexpected runtime behavior.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Core repo root (two levels up from this test file's directory)
CORE_ROOT = Path(__file__).resolve().parents[3]
# Frontend repo is a sibling directory
FRONTEND_ROOT = CORE_ROOT.parent / "homeassistant_frontend"

REQUIREMENT_PATTERN = re.compile(r"home-assistant-frontend==(.+)")
PYPROJECT_VERSION_PATTERN = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _get_frontend_pyproject_version() -> str:
    """Read the version from the frontend pyproject.toml."""
    pyproject = FRONTEND_ROOT / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("Frontend repo not found at expected path")
    content = pyproject.read_text()
    match = PYPROJECT_VERSION_PATTERN.search(content)
    assert match, "Could not parse version from pyproject.toml"
    return match.group(1)


def _extract_version_from_file(path: Path) -> str | None:
    """Extract the home-assistant-frontend version from a requirements-style file."""
    if not path.exists():
        pytest.skip(f"File not found: {path}")
    for line in path.read_text().splitlines():
        match = REQUIREMENT_PATTERN.search(line)
        if match:
            return match.group(1).strip()
    return None


class TestVersionConsistency:
    """Ensure frontend version pins are identical everywhere."""

    @pytest.fixture(autouse=True)
    def _frontend_version(self) -> None:
        self.version = _get_frontend_pyproject_version()

    def test_pyproject_version_format(self) -> None:
        """Version must follow YYYYMMDD.N format."""
        assert re.match(
            r"^\d{8}\.\d+$", self.version
        ), f"Invalid version format: {self.version}"

    def test_manifest_json_matches(self) -> None:
        """manifest.json requirement must match pyproject.toml."""
        manifest_path = (
            CORE_ROOT
            / "homeassistant"
            / "components"
            / "frontend"
            / "manifest.json"
        )
        content = json.loads(manifest_path.read_text())
        reqs = content.get("requirements", [])
        fe_req = [r for r in reqs if r.startswith("home-assistant-frontend==")]
        assert len(fe_req) == 1, "Expected exactly one frontend requirement"
        match = REQUIREMENT_PATTERN.match(fe_req[0])
        assert match, f"Could not parse version from: {fe_req[0]}"
        assert match.group(1) == self.version, (
            f"manifest.json has {match.group(1)}, expected {self.version}"
        )

    def test_package_constraints_matches(self) -> None:
        """package_constraints.txt must match pyproject.toml."""
        version = _extract_version_from_file(
            CORE_ROOT / "homeassistant" / "package_constraints.txt"
        )
        assert version == self.version, (
            f"package_constraints.txt has {version}, expected {self.version}"
        )

    def test_requirements_all_matches(self) -> None:
        """requirements_all.txt must match pyproject.toml."""
        version = _extract_version_from_file(
            CORE_ROOT / "requirements_all.txt"
        )
        assert version == self.version, (
            f"requirements_all.txt has {version}, expected {self.version}"
        )

    def test_requirements_test_all_matches(self) -> None:
        """requirements_test_all.txt must match pyproject.toml."""
        version = _extract_version_from_file(
            CORE_ROOT / "requirements_test_all.txt"
        )
        assert version == self.version, (
            f"requirements_test_all.txt has {version}, expected {self.version}"
        )
