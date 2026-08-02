"""QwenClawBench v1.1 routing tests."""

import pytest

from matric_eval.tasks.qwenclawbench import (
    QWENCLAW_DATASET_REVISION,
    QWENCLAW_RELEASE,
    build_qwenclawbench_command,
    qwenclawbench,
    qwenclawbench_scorer,
    record_to_sample,
)
from matric_eval.tasks.registry import BenchmarkStatus, BenchmarkUnavailableError


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def test_manifest_conversion() -> None:
    sample = record_to_sample(
        {
            "id": "task_1",
            "prompt": "Analyze data",
            "category": "analysis",
            "grading_type": "hybrid",
            "grading_weights": {"automated": 0.7, "llm_judge": 0.3},
        }
    )
    assert sample.id == "task_1"
    assert sample.metadata["grading_type"] == "hybrid"
    assert sample.metadata["dataset_revision"] == QWENCLAW_DATASET_REVISION


def test_official_command() -> None:
    command = build_qwenclawbench_command(
        "/repo", model="provider/model", runs=3, concurrency=4, output_dir="out"
    )
    assert command[command.index("--dataset") + 1] == QWENCLAW_RELEASE
    assert command[command.index("--runs") + 1] == "3"


def test_inspect_placeholder_is_rejected() -> None:
    with pytest.raises(BenchmarkUnavailableError, match="OpenClaw transcript"):
        qwenclawbench_scorer()
    with pytest.raises(BenchmarkUnavailableError, match="OpenClaw trajectory"):
        qwenclawbench()


def test_registration() -> None:
    metadata = qwenclawbench._benchmark_metadata
    assert metadata.total_samples == 100
    assert metadata.protocol_version == "1.1"
    assert metadata.status == BenchmarkStatus.GATED
