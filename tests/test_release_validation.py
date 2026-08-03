"""Tests for clean release package validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import validate_release_candidate as validation

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".gitea/workflows/release.yml"


def test_release_validation_hashes_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.whl"
    artifact.write_bytes(b"release artifact")

    assert validation._sha256(artifact) == hashlib.sha256(b"release artifact").hexdigest()


def test_release_validation_requires_exactly_one_artifact(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Expected one wheel"):
        validation._one([tmp_path / "one.whl", tmp_path / "two.whl"], "wheel")


def test_clean_environment_removes_checkout_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/workspace/src")
    monkeypatch.setenv("VIRTUAL_ENV", "/workspace/.venv")

    environment = validation._clean_environment()

    assert "PYTHONPATH" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert environment["UV_LINK_MODE"] == "copy"


def test_release_workflow_validates_supported_versions_before_manifest() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    validation_step = workflow.index("Validate clean package consumers")
    manifest_step = workflow.index("Generate manifest and checksums")
    assert validation_step < manifest_step
    assert "scripts/validate_release_candidate.py" in workflow
    for version in ("3.11", "3.12", "3.13", "3.14"):
        assert f"--python-version {version}" in workflow
