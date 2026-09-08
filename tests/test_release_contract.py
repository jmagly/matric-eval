"""Release version and evidence contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release_contract.py"
CURRENT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_release_versions_agree() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(ROOT),
            "versions",
            "--expected",
            CURRENT_VERSION,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["version"] == CURRENT_VERSION
    assert set(report["surfaces"].values()) == {CURRENT_VERSION}


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
            CURRENT_VERSION,
            "--output",
            str(output),
            "--sums-output",
            str(sums),
        ],
        check=True,
    )

    report = json.loads(output.read_text())
    assert report["version"] == CURRENT_VERSION
    assert report["artifacts"][0]["path"] == "packages/example.txt"
    assert "release-manifest.json" in sums.read_text()


@pytest.mark.parametrize(
    "command", ["versions", "bump", "artifacts", "licenses", "vulnerabilities", "manifest"]
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


@pytest.fixture
def contract():
    import importlib.util

    spec = importlib.util.spec_from_file_location("release_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release_root(tmp_path):
    import shutil

    for relative in (
        "pyproject.toml",
        "uv.lock",
        "src/matric_eval/version.py",
        "bindings/typescript/package.json",
        "bindings/typescript/package-lock.json",
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
        destination.write_text(destination.read_text().replace(CURRENT_VERSION, "2026.9.0"))
    return tmp_path


@pytest.mark.parametrize(
    "version",
    [
        "0.2.0",
        "2026.09.0",
        "2026.9.01",
        "2026.0.0",
        "2026.13.0",
        "2026.9",
        "v2026.9.0",
        "2026.9.0rc1",
        "2026.9.0+meta",
        "2026.9.-1",
        "2026.9.0\n",
    ],
)
def test_calver_rejects_noncanonical_versions(contract, version):
    with pytest.raises(ValueError, match="Invalid CalVer"):
        contract.parse_calver(version)


def test_monthly_counter_and_year_rollover(contract):
    from datetime import date

    assert contract.next_version("2026.9.0", date(2026, 9, 8)) == "2026.9.1"
    assert contract.next_version("2026.9.9", date(2026, 9, 9)) == "2026.9.10"
    assert contract.next_version("2026.9.99", date(2026, 10, 1)) == "2026.10.0"
    assert contract.next_version("2026.12.9", date(2027, 1, 1)) == "2027.1.0"
    with pytest.raises(ValueError, match="ahead"):
        contract.next_version("2026.10.0", date(2026, 9, 8))


def test_bump_updates_all_surfaces_without_dependency_changes(contract, release_root):
    import tomllib

    before = tomllib.loads((release_root / "uv.lock").read_text())
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(release_root), "bump", "--version", "2026.9.1"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout)["version"] == "2026.9.1"
    assert set(contract.version_surfaces(release_root).values()) == {"2026.9.1"}
    after = tomllib.loads((release_root / "uv.lock").read_text())
    for package in before["package"]:
        if package["name"] == "matric-eval":
            package["version"] = "2026.9.1"
    assert before == after
    assert contract.verify_versions(release_root) == "2026.9.1"


@pytest.mark.parametrize(
    "version", ["2026.9.0", "2026.8.99", "2026.09.1", "2026.13.0", "2026.9.1rc1"]
)
def test_invalid_bump_does_not_modify_any_file(contract, release_root, version):
    before = {path: path.read_bytes() for path in release_root.rglob("*") if path.is_file()}
    with pytest.raises(ValueError):
        contract.bump_version(release_root, version)
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize("relative", ["uv.lock", "bindings/typescript/package-lock.json"])
def test_lock_drift_blocks_verification_and_bump(contract, release_root, relative):
    path = release_root / relative
    path.write_text(path.read_text().replace("2026.9.0", "2026.9.2", 1))
    before = {path: path.read_bytes() for path in release_root.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="disagree"):
        contract.verify_versions(release_root)
    with pytest.raises(ValueError, match="disagree"):
        contract.bump_version(release_root, "2026.9.3")
    assert before == {path: path.read_bytes() for path in before}


def test_migration_requires_explicit_calver(contract, release_root):
    for path in release_root.rglob("*"):
        if path.is_file():
            path.write_text(path.read_text().replace("2026.9.0", "0.2.0"))
    with pytest.raises(ValueError):
        contract.verify_versions(release_root)
    with pytest.raises(ValueError):
        contract.bump_version(release_root)
    assert contract.bump_version(release_root, "2026.9.0") == "2026.9.0"


def test_bump_rolls_back_partial_write_error(contract, release_root, monkeypatch):
    original_write = Path.write_text
    before = {path: path.read_bytes() for path in release_root.rglob("*") if path.is_file()}

    def fail_runtime_write(path, *args, **kwargs):
        if path.name == "version.py":
            raise OSError("simulated write failure")
        return original_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_runtime_write)
    with pytest.raises(OSError, match="simulated"):
        contract.bump_version(release_root, "2026.9.1")
    assert before == {path: path.read_bytes() for path in before}


def test_artifacts_reject_wrong_sdist_metadata(contract, tmp_path):
    import io
    import tarfile
    import zipfile

    python_dir = tmp_path / "packages/python"
    npm_dir = tmp_path / "packages/typescript"
    python_dir.mkdir(parents=True)
    npm_dir.mkdir(parents=True)
    with zipfile.ZipFile(python_dir / "matric_eval-2026.9.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr("matric_eval-2026.9.0.dist-info/METADATA", "Version: 2026.9.0\n")
    with tarfile.open(python_dir / "matric_eval-2026.9.0.tar.gz", "w:gz") as sdist:
        payload = b"Version: 2026.8.0\n"
        info = tarfile.TarInfo("matric_eval-2026.9.0/PKG-INFO")
        info.size = len(payload)
        sdist.addfile(info, io.BytesIO(payload))
    (npm_dir / "matric-eval-client-2026.9.0.tgz").touch()
    with pytest.raises(ValueError, match="Source distribution metadata"):
        contract.verify_artifacts(tmp_path, "2026.9.0")
