"""Claw-Eval v1.1 routing tests."""

import pytest

from matric_eval.tasks.claweval import (
    CLAW_DATASET_REVISION,
    CLAW_TRIALS,
    build_claweval_command,
    claweval,
    claweval_scorer,
    record_to_sample,
)
from matric_eval.tasks.registry import BenchmarkStatus, BenchmarkUnavailableError


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def test_manifest_conversion() -> None:
    sample = record_to_sample(
        {"task_id": "T001", "query": "Triage mail", "fixture": ["inbox.json"]},
        split="general",
    )
    assert sample.id == "T001"
    assert sample.metadata["trials"] == CLAW_TRIALS
    assert sample.metadata["dataset_revision"] == CLAW_DATASET_REVISION


def test_official_command_enforces_pass3() -> None:
    command = build_claweval_command("/repo", config="config_general.yaml", parallel=8)
    assert command[command.index("--trials") + 1] == "3"
    assert command[command.index("--parallel") + 1] == "8"


def test_inspect_placeholder_is_rejected() -> None:
    with pytest.raises(BenchmarkUnavailableError, match="trajector"):
        claweval_scorer()
    with pytest.raises(BenchmarkUnavailableError, match="external trajectory"):
        claweval()


def test_registration() -> None:
    metadata = claweval._benchmark_metadata
    assert metadata.total_samples == 300
    assert metadata.protocol_version == "1.1.0"
    assert metadata.scoring_type == "official_pass_power_3"
    assert metadata.status == BenchmarkStatus.GATED
