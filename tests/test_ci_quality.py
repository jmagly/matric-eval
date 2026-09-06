"""Regression tests for authoritative CI quality gates."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from scripts.check_mypy_baseline import find_regressions

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".gitea/workflows/ci.yml",
    ROOT / ".github/workflows/ci.yml",
)


def test_quality_workflows_cannot_suppress_failures() -> None:
    """Quality commands must retain their process exit status."""
    for workflow in WORKFLOWS:
        content = workflow.read_text()
        assert "|| true" not in content, workflow
        assert "continue-on-error" not in content, workflow


def test_quality_workflows_use_local_authoritative_commands() -> None:
    """Both providers must invoke the same local quality gates."""
    required_commands = (
        "make lint",
        "make format-check",
        "make type-check",
        "make test-coverage-fail",
    )
    for workflow in WORKFLOWS:
        content = workflow.read_text()
        for command in required_commands:
            assert command in content, f"{workflow} is missing {command}"


def test_local_quality_targets_cover_automation_scripts() -> None:
    """Repository automation must be included in lint and format checks."""
    makefile = (ROOT / "Makefile").read_text()
    assert "ruff check src/ tests/ scripts/" in makefile
    assert "ruff format --check src/ tests/ scripts/" in makefile


def test_mypy_ratchet_rejects_new_and_increased_findings() -> None:
    """The baseline permits removals but blocks added type debt."""
    existing = ("src/example.py", "type-arg", "Missing type arguments")
    added = ("src/new.py", "assignment", "Incompatible assignment")
    baseline = Counter({existing: 2})

    assert not find_regressions(Counter({existing: 1}), baseline)
    assert find_regressions(Counter({existing: 3}), baseline) == Counter({existing: 1})
    assert find_regressions(Counter({existing: 2, added: 1}), baseline) == Counter({added: 1})


def test_gitea_test_jobs_install_study_scoring_dependencies() -> None:
    """CI runs the real IFEval regression, which requires the study extra."""
    import yaml

    workflow = yaml.safe_load((ROOT / ".gitea/workflows/ci.yml").read_text())
    for job_name in ("test", "smoke"):
        steps = workflow["jobs"][job_name]["steps"]
        installs = [step.get("run", "") for step in steps if "uv sync" in step.get("run", "")]
        assert any("--extra dev" in cmd and "--extra study" in cmd for cmd in installs), job_name
