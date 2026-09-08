"""Delivery policy regressions for the executable workflow configuration."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(path: str) -> dict:
    return yaml.load((ROOT / path).read_text(), Loader=yaml.BaseLoader)


def test_release_has_no_registry_publication() -> None:
    for directory in (".gitea/workflows", ".github/workflows"):
        for path in (ROOT / directory).glob("*.yml"):
            document = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            for job in document["jobs"].values():
                for step in job.get("steps", []):
                    command = step.get("run", "")
                    assert not re.search(
                        r"\b(?:uv\s+publish|npm\s+publish|twine\s+upload)\b", command
                    )
                    assert "gh-action-pypi-publish" not in step.get("uses", "")


def test_only_tagged_release_can_mutate_the_forge() -> None:
    document = workflow(".gitea/workflows/release.yml")
    assert "workflow_dispatch" in document["on"]
    steps = document["jobs"]["release"]["steps"]
    publication = [
        step for step in steps if "publish_forge_release.py publish" in step.get("run", "")
    ]
    assert len(publication) == 1
    assert publication[0]["if"] == "startsWith(github.ref, 'refs/tags/v')"
    verification = [
        step for step in steps if "publish_forge_release.py verify" in step.get("run", "")
    ]
    assert len(verification) == 1
    assert verification[0]["if"] == publication[0]["if"]
    assert steps.index(verification[0]) < next(
        i for i, step in enumerate(steps) if step["name"] == "Build Python packages"
    )
    for gate in (
        "Verify package contents",
        "Review dependency licenses",
        "Review vulnerability findings",
        "Validate clean package consumers",
        "Generate manifest and checksums",
    ):
        assert next(i for i, step in enumerate(steps) if step["name"] == gate) < steps.index(
            publication[0]
        )
    assert steps[-1]["if"] == "always()"


def test_ci_locks_dependencies_and_retains_mandatory_client_evidence() -> None:
    for path in (".gitea/workflows/ci.yml", ".github/workflows/ci.yml"):
        document = workflow(path)
        assert document["env"]["UV_LOCKED"] == "1"
        steps = [step for job in document["jobs"].values() for step in job.get("steps", [])]
        assert any("release_contract.py versions" in step.get("run", "") for step in steps)
        assert any("make test-coverage-fail" in step.get("run", "") for step in steps)
        assert any(
            "client-conformance-junit.xml" in step.get("with", {}).get("path", "") for step in steps
        )
        for step in steps:
            for line in step.get("run", "").splitlines():
                if "uv sync" in line:
                    assert "--locked" in line


def test_release_audits_use_runtime_inventory_and_producer_status() -> None:
    steps = workflow(".gitea/workflows/release.yml")["jobs"]["release"]["steps"]
    licenses = next(step for step in steps if step["name"] == "Review dependency licenses")
    assert "uv run --no-sync python scripts/release_contract.py licenses" in licenses["run"]
    vulnerabilities = next(
        step for step in steps if step["name"] == "Review vulnerability findings"
    )
    assert (
        "--audit-exit-codes release-artifacts/evidence/audit-exit-codes.json"
        in vulnerabilities["run"]
    )


def test_canonical_build_provisions_python_for_actual_typescript_cli_test() -> None:
    steps = workflow(".gitea/workflows/ci.yml")["jobs"]["build"]["steps"]
    command = next(
        step["run"] for step in steps if step["name"] == "Build and test TypeScript package"
    )
    assert command.index("uv sync --locked --project ../..") < command.index("npm test")
    assert 'export MATRIC_EVAL_TEST_PYTHON="$(cd ../.. && pwd)/.venv/bin/python"' in command


def test_tag_wrapper_checks_clean_main_and_never_pushes(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "source"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    for key, value in (
        ("user.name", "Fixture"),
        ("user.email", "fixture@example.invalid"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
    ):
        git("config", key, value)
    (repo / "scripts").mkdir()
    # Helper behavior is qualified separately by HTTP/source contract fixtures.
    for name in ("release_contract.py", "publish_forge_release.py"):
        (repo / "scripts" / name).write_text("print('verified fixture')\n")
    notes = repo / "docs/releases/2026.9.0.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("Prepared release\n")
    (repo / "CHANGELOG.md").write_text("## [2026.9.0]\n")
    git("add", ".")
    git("commit", "-m", "fixture")
    git("remote", "add", "origin", str(remote))
    git("push", "-u", "origin", "main")
    command = ["bash", str(ROOT / "tools/release/cut-tag.sh"), "2026.9.0"]
    subprocess.run([*command, "--check"], cwd=repo, check=True, capture_output=True)
    assert git("tag", "--list") == ""
    notes.write_text("uncommitted change\n")
    assert subprocess.run(command, cwd=repo, capture_output=True).returncode != 0
    git("restore", "docs/releases/2026.9.0.md")
    subprocess.run(command, cwd=repo, check=True, capture_output=True)
    assert git("tag", "--list") == "v2026.9.0"
    assert git("ls-remote", "--tags", "origin") == ""
    assert subprocess.run(command, cwd=repo, capture_output=True).returncode != 0
    git("tag", "-d", "v2026.9.0")
    notes.write_text("unreviewed commit\n")
    git("add", ".")
    git("commit", "-m", "not on main remote")
    assert subprocess.run(command, cwd=repo, capture_output=True).returncode != 0
    assert git("tag", "--list") == ""


def test_python_audit_export_preserves_vcs_pins_without_incompatible_hash_mode() -> None:
    steps = workflow(".gitea/workflows/release.yml")["jobs"]["release"]["steps"]
    audit = next(step for step in steps if step["name"] == "Audit dependencies")["run"]
    assert "--locked" in audit
    assert "--no-emit-project --no-hashes" in audit
    assert "--all-extras --no-extra dev --no-dev" in audit
    assert "--requirement release-artifacts/evidence/python-requirements.txt" in audit
    assert "--ignore-vuln" not in audit
    assert "--skip-editable" not in audit
