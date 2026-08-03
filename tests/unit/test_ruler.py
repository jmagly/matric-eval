"""RULER v1 protocol adapter tests."""

import json

import pytest

from matric_eval.tasks.registry import BenchmarkStatus, BenchmarkUnavailableError
from matric_eval.tasks.ruler import (
    RULER_REVISION,
    RULER_TASKS,
    build_ruler_prepare_command,
    ruler,
    summarize_ruler_results,
    trim_ruler_generated_data,
)


def test_all_thirteen_official_generators_are_selected() -> None:
    assert len(RULER_TASKS) == 13
    assert set(RULER_TASKS) == {
        "niah_single_1",
        "niah_single_2",
        "niah_single_3",
        "niah_multikey_1",
        "niah_multikey_2",
        "niah_multikey_3",
        "niah_multivalue",
        "niah_multiquery",
        "vt",
        "cwe",
        "fwe",
        "qa_1",
        "qa_2",
    }


def test_prepare_command_pins_context_tokenizer_and_tasks() -> None:
    command = build_ruler_prepare_command(
        "/skills", setup="model_128k", tokenizer_path="org/model", context_length=131072
    )
    assert command[:5] == ["uv", "run", "--project", "/skills", "ns"]
    assert command[command.index("--tokenizer_path") + 1] == "org/model"
    assert command[command.index("--max_seq_length") + 1] == "131072"
    assert command[-13:] == list(RULER_TASKS)


def test_each_generated_task_is_tier_trimmed(tmp_path) -> None:
    for task_name in RULER_TASKS:
        directory = tmp_path / task_name
        directory.mkdir()
        (directory / "test.jsonl").write_text(
            "".join(json.dumps({"index": index}) + "\n" for index in range(12)),
            encoding="utf-8",
        )
    counts = trim_ruler_generated_data(tmp_path, tier="quick")
    assert counts == {task_name: 10 for task_name in RULER_TASKS}
    for task_name in RULER_TASKS:
        assert len((tmp_path / task_name / "test.jsonl").read_text().splitlines()) == 10


def test_official_average_and_effective_context_fixture() -> None:
    rows = []
    for task_name in RULER_TASKS:
        rows.extend(
            (
                {"task": task_name, "context_length": 4096, "accuracy": 0.9},
                {"task": task_name, "context_length": 8192, "accuracy": 0.81},
                {"task": task_name, "context_length": 16384, "accuracy": 0.8},
            )
        )
    summary = summarize_ruler_results(rows)
    assert summary["average_accuracy"] == pytest.approx((0.9 + 0.81 + 0.8) / 3)
    assert summary["effective_context_length"] == 8192
    assert summary["evaluator_revision"] == RULER_REVISION


def test_ruler_is_explicitly_gated() -> None:
    with pytest.raises(BenchmarkUnavailableError, match="NeMo Skills"):
        ruler()
    assert ruler._benchmark_metadata.status == BenchmarkStatus.GATED
