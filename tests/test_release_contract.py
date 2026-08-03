"""Release version and evidence contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release_contract.py"


def test_release_versions_agree() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(ROOT), "versions", "--expected", "0.2.0"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["version"] == "0.2.0"
    assert set(report["surfaces"].values()) == {"0.2.0"}


def test_release_versions_reject_mismatch() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(ROOT), "versions", "--expected", "9.9.9"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Expected release 9.9.9" in result.stderr


def test_release_manifest_hashes_artifacts(tmp_path: Path) -> None:
    artifact = tmp_path / "packages/example.txt"
    artifact.parent.mkdir()
    artifact.write_text("release artifact\n")
    output = tmp_path / "release-manifest.json"
    sums = tmp_path / "SHA256SUMS"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(ROOT),
            "manifest",
            "--artifact-root",
            str(tmp_path),
            "--expected",
            "0.2.0",
            "--output",
            str(output),
            "--sums-output",
            str(sums),
        ],
        check=True,
    )

    report = json.loads(output.read_text())
    assert report["version"] == "0.2.0"
    assert report["artifacts"][0]["path"] == "packages/example.txt"
    assert "release-manifest.json" in sums.read_text()


@pytest.mark.parametrize(
    "command", ["versions", "artifacts", "licenses", "vulnerabilities", "manifest"]
)
def test_release_contract_exposes_commands(command: str) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), command, "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "usage:" in result.stdout


def test_vulnerability_review_rejects_unknown_finding(tmp_path: Path) -> None:
    python_audit = tmp_path / "python.json"
    npm_audit = tmp_path / "npm.json"
    policy = tmp_path / "policy.json"
    report = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    python_audit.write_text(
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "example",
                        "version": "1.0.0",
                        "vulns": [{"id": "PYSEC-UNKNOWN", "aliases": [], "fix_versions": []}],
                    }
                ]
            }
        )
    )
    npm_audit.write_text(json.dumps({"metadata": {"vulnerabilities": {"critical": 0}}}))
    policy.write_text(json.dumps({"accepted_findings": [], "schema_version": 1}))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(ROOT),
            "vulnerabilities",
            "--python-audit",
            str(python_audit),
            "--npm-audit",
            str(npm_audit),
            "--policy",
            str(policy),
            "--json-output",
            str(report),
            "--markdown-output",
            str(markdown),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert json.loads(report.read_text())["summary"]["unaccepted"] == 1
