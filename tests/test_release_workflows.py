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
