"""Keep GitHub CI on the Linux interpreter required by lifecycle cleanup."""

from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("job", ["quality", "test", "build"])
def test_github_ci_qualifies_container_interpreter_before_gates(job):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    assert workflow["env"]["UV_PYTHON"] == "/usr/local/bin/python"
    definition = workflow["jobs"][job]
    assert definition["container"] == "python:3.11"
    steps = definition["steps"]
    install = next(i for i, step in enumerate(steps) if step.get("name") == "Install dependencies")
    check = next(
        i
        for i, step in enumerate(steps)
        if step.get("name") == "Verify cleanup runtime capabilities"
    )
    assert check == install + 1
    command = steps[check]["run"]
    assert "uv run --no-sync python" in command
    assert "os.pidfd_open(os.getpid())" in command
    assert "signal.pidfd_send_signal(descriptor, 0)" in command
    assert "os.close(descriptor)" in command


@pytest.mark.parametrize("job", ["quality", "test", "build"])
def test_github_container_git_trust_persists_after_checkout(job):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"][job]["steps"]
    checkout = next(i for i, step in enumerate(steps) if step.get("uses") == "actions/checkout@v4")
    command = steps[checkout + 1]["run"]
    assert 'git config --system --add safe.directory "$GITHUB_WORKSPACE"' in command
    assert "git rev-parse --verify HEAD" in command
    assert "*" not in command
