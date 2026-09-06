"""Tests for scheduled real-provider smoke validation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts import run_real_provider_smoke as smoke

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".gitea/workflows/real-provider-smoke.yml",
    ROOT / ".github/workflows/real-provider-smoke.yml",
)


def workflow(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text())
    payload["on"] = payload.pop(True, payload.get("on"))
    return payload


@pytest.mark.parametrize("path", WORKFLOWS)
def test_workflow_has_manual_schedule_service_and_artifact_retention(path: Path) -> None:
    payload = workflow(path)
    triggers = payload["on"]
    job = payload["jobs"]["smoke"]
    serialized = path.read_text()

    assert triggers["schedule"] == [{"cron": "17 6 * * *"}]
    assert "workflow_dispatch" in triggers
    assert job["services"]["ollama"]["image"] == "ollama/ollama:0.32.0"
    assert "if: always()" in serialized
    assert "scripts/run_real_provider_smoke.py" in serialized
    assert "smollm2:135m" in serialized


def test_gitea_workflow_installs_upload_action_runtime() -> None:
    serialized = (ROOT / ".gitea/workflows/real-provider-smoke.yml").read_text()

    assert "apt-get install -y curl git nodejs" in serialized


def test_public_url_removes_credentials_and_query() -> None:
    assert smoke.public_url("https://user:secret@example.test:8443/api?token=x") == (
        "https://example.test:8443/api"
    )


def test_missing_credential_is_gated_and_recorded(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PROVIDER_TOKEN", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "smoke",
            "--provider-url",
            "http://provider.test",
            "--output",
            str(tmp_path),
            "--required-credential-env",
            "PROVIDER_TOKEN",
        ],
    )

    assert smoke.main() == 2
    report = json.loads((tmp_path / "smoke-report.json").read_text())
    assert report["status"] == "gated"
    assert report["gate_reason"] == "Missing required credential: PROVIDER_TOKEN"


def test_success_records_revisions_duration_and_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "smoke",
            "--provider-url",
            "http://provider.test",
            "--model",
            "fixture:1b",
            "--benchmark",
            "matric_cli",
            "--output",
            str(tmp_path),
        ],
    )
    summary_path = tmp_path / "results/run-test/summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(
        json.dumps({"successful": 1, "failed": 0, "results": [{"status": "success"}]})
    )
    process = smoke.subprocess.CompletedProcess([], 0, stdout="{}", stderr="")

    with (
        patch.object(smoke, "wait_for_provider", return_value={"version": "1.2.3"}),
        patch.object(
            smoke,
            "model_snapshot",
            return_value={"name": "fixture:1b", "digest": "sha256:model"},
        ),
        patch.object(smoke.subprocess, "run", return_value=process),
    ):
        assert smoke.main() == 0

    report = json.loads((tmp_path / "smoke-report.json").read_text())
    assert report["status"] == "success"
    assert report["provider"]["version"] == "1.2.3"
    assert report["model"]["digest"] == "sha256:model"
    assert report["benchmark"]["protocol_version"] == "project-v1"
    assert report["benchmark"]["evaluator_revision"] == "0.1.0"
    assert report["duration_seconds"] >= 0


def test_failed_evaluation_is_not_reported_as_success(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "smoke",
            "--provider-url",
            "http://provider.test",
            "--output",
            str(tmp_path),
        ],
    )
    summary_path = tmp_path / "results/run-test/summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(json.dumps({"successful": 0, "failed": 1}))
    process = smoke.subprocess.CompletedProcess([], 0, stdout="{}", stderr="provider error")

    with (
        patch.object(smoke, "wait_for_provider", return_value={"version": "1.2.3"}),
        patch.object(smoke, "model_snapshot", return_value={"name": "fixture"}),
        patch.object(smoke.subprocess, "run", return_value=process),
    ):
        assert smoke.main() == 1

    report = json.loads((tmp_path / "smoke-report.json").read_text())
    assert report["status"] == "failed"
    assert "one successful result" in report["error"]
