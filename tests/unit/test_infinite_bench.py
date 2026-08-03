"""InfiniteBench 2-A integration tests."""

from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import match
from inspect_ai.solver import generate

from matric_eval.tasks.infinite_bench import (
    INFINITE_BENCH_FACTORIES,
    INFINITE_BENCH_PROTOCOL,
    INFINITE_BENCH_TASK_COUNTS,
    INFINITE_BENCH_TASKS,
    INFINITE_BENCH_TOTAL,
    INFINITE_BENCH_TRUNCATION_POLICY,
    create_infinite_bench_task,
)


def test_all_nine_protocol_2a_tasks_keep_identity() -> None:
    assert tuple(INFINITE_BENCH_FACTORIES) == INFINITE_BENCH_TASKS
    assert len(INFINITE_BENCH_TASKS) == 9
    assert INFINITE_BENCH_TASK_COUNTS["math_calc"] == 50
    assert INFINITE_BENCH_TOTAL == 3303


def test_wrapper_keeps_upstream_scorer_and_records_truncation() -> None:
    upstream = Task(
        dataset=MemoryDataset([Sample(id=str(i), input="x", target="x") for i in range(6)]),
        solver=generate(),
        scorer=match(),
        metadata={"upstream": True},
    )
    with (
        patch.dict(INFINITE_BENCH_FACTORIES, {"passkey": lambda: upstream}),
        patch("matric_eval.tasks.upstream.get_sample_count", return_value=5),
    ):
        result = create_infinite_bench_task("passkey", "smoke")
    assert len(result.dataset) == 5
    assert result.metadata["protocol_version"] == INFINITE_BENCH_PROTOCOL
    assert result.metadata["infinite_bench_task"] == "passkey"
    assert result.metadata["truncation_policy"] == INFINITE_BENCH_TRUNCATION_POLICY
    assert result.scorer is upstream.scorer


def test_unknown_task_fails_without_falling_back() -> None:
    with pytest.raises(ValueError, match="Unknown InfiniteBench task"):
        create_infinite_bench_task("unknown")
