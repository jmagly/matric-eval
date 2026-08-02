"""Terminal-Bench 2.1 Harbor adapter tests."""

from unittest.mock import patch

import pytest
from inspect_ai import Task

from matric_eval.tasks.terminalbench import (
    HARBOR_VERSION,
    TERMINALBENCH_REVISION,
    build_harbor_command,
    load_terminalbench,
    record_to_sample,
    terminal_task_scorer,
    terminalbench,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def test_record_preserves_harbor_manifest() -> None:
    sample = record_to_sample(
        {
            "task_id": "demo",
            "instruction": "Repair the service.",
            "docker_image": "example/task:1",
            "verifier_timeout": 42,
            "test_files": {"tests/test.sh": "/tmp/test.sh"},
        }
    )
    assert sample.id == "demo"
    assert sample.metadata["verification"] == "bash /tests/test.sh"
    assert sample.metadata["timeout_sec"] == 42
    assert sample.metadata["dataset_revision"] == TERMINALBENCH_REVISION


def test_scorer_is_runnable() -> None:
    assert callable(terminal_task_scorer())


def test_harbor_command_targets_2_1() -> None:
    command = build_harbor_command(agent="codex", model="openai/model", environment="docker")
    assert command[command.index("-d") + 1] == "terminal-bench/terminal-bench-2-1"
    assert HARBOR_VERSION == "0.20.0"


def test_missing_snapshot_fails_clearly() -> None:
    with patch("matric_eval.tasks.terminalbench.get_dataset_path", return_value=None):
        with pytest.raises(FileNotFoundError, match="local canonical snapshot"):
            load_terminalbench()


def test_registration_and_task() -> None:
    metadata = terminalbench._benchmark_metadata
    assert metadata.protocol_version == "2.1"
    assert metadata.total_samples == 89
    assert metadata.scoring_type == "official_harbor_verifier"
    with patch(
        "matric_eval.tasks.terminalbench.load_terminalbench",
        return_value=[record_to_sample({"task_id": "x"})],
    ):
        result = terminalbench()
    assert isinstance(result, Task)
    assert result.name == "terminalbench_2_1"
