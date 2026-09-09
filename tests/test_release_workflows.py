"""Delivery policy regressions for the executable workflow configuration."""

import re
from pathlib import Path

import pytest
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


@pytest.mark.parametrize("provider", ["gitea", "github"])
def test_only_tagged_release_can_mutate_the_forge(provider: str) -> None:
    document = workflow(f".{provider}/workflows/release.yml")
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


@pytest.mark.parametrize("provider", ["gitea", "github"])
def test_release_audits_use_runtime_inventory_and_producer_status(provider: str) -> None:
    steps = workflow(f".{provider}/workflows/release.yml")["jobs"]["release"]["steps"]
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


@pytest.mark.parametrize("provider", ["gitea", "github"])
def test_python_audit_export_preserves_vcs_pins_without_incompatible_hash_mode(
    provider: str,
) -> None:
    steps = workflow(f".{provider}/workflows/release.yml")["jobs"]["release"]["steps"]
    audit = next(step for step in steps if step["name"] == "Audit dependencies")["run"]
    assert "--locked" in audit
    assert "--no-emit-project --no-hashes" in audit
    assert "--all-extras --no-extra dev --no-dev" in audit
    assert "--requirement release-artifacts/evidence/python-requirements.txt" in audit
    assert "--ignore-vuln" not in audit
    assert "--skip-editable" not in audit


def test_github_release_uses_native_token_and_same_candidate_gates() -> None:
    github = workflow(".github/workflows/release.yml")
    gitea = workflow(".gitea/workflows/release.yml")
    job = github["jobs"]["release"]
    assert job["if"] == "github.repository == 'jmagly/matric-eval'"
    assert job["permissions"] == {"contents": "write", "actions": "read"}
    assert github["on"] == gitea["on"]
    steps = {step["name"]: step for step in job["steps"]}
    for step in gitea["jobs"]["release"]["steps"]:
        if step["name"] in {
            "Checkout exact source",
            "Verify tagged source and exact-commit CI",
            "Attach verified Gitea release downloads",
            "Retain release bundle",
        }:
            continue
        assert steps[step["name"]] == step
    for name in (
        "Verify tagged source and exact-commit CI",
        "Attach verified GitHub release downloads",
    ):
        assert steps[name]["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
        assert "--forge github" in steps[name]["run"]
        assert '--commit "$RELEASE_COMMIT"' in steps[name]["run"]
    assert "https://github.com/jmagly/matric-eval.git" in steps["Checkout exact source"]["run"]
    checkout = steps["Checkout exact source"]["run"]
    assert 'git rev-parse "${GITHUB_SHA}^{commit}"' in checkout
    assert 'safe.directory "$GITHUB_WORKSPACE"' in checkout
    assert '"$GITHUB_ENV"' in checkout
    assert steps["Retain release bundle"]["uses"] == (
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )


@pytest.mark.parametrize("tag_object", [False, True])
def test_github_checkout_resolves_exact_event_to_commit(tmp_path: Path, tag_object: bool) -> None:
    import os
    import shlex
    import subprocess

    source, checkout = tmp_path / "source", tmp_path / "checkout"
    source.mkdir()
    checkout.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=source, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("config", "tag.gpgsign", "false")
    git("commit", "--allow-empty", "-m", "release source")
    commit = git("rev-parse", "HEAD")
    git("tag", "-a", "v2026.9.0", "-m", "fixture")
    event = git("rev-parse", "v2026.9.0") if tag_object else commit
    steps = workflow(".github/workflows/release.yml")["jobs"]["release"]["steps"]
    command = next(step["run"] for step in steps if step["name"] == "Checkout exact source")
    command = command.replace("https://github.com/jmagly/matric-eval.git", shlex.quote(str(source)))
    command = command.replace("${{ github.sha }}", event)
    environment_file = tmp_path / "github-env"
    subprocess.run(
        ["sh", "-e", "-c", command],
        cwd=checkout,
        env={
            **os.environ,
            "GITHUB_SHA": event,
            "GITHUB_WORKSPACE": str(checkout),
            "GITHUB_ENV": str(environment_file),
            "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        },
        check=True,
        capture_output=True,
    )
    assert environment_file.read_text() == f"RELEASE_COMMIT={commit}\n"
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
        == commit
    )
