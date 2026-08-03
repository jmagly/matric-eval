"""BABILong protocol and scorer parity tests."""

from unittest.mock import patch

import pytest
from inspect_ai.dataset import Sample

from matric_eval.tasks.babilong import (
    BABILONG_DATASET_REVISION,
    BABILONG_TASKS,
    compare_babilong_answer,
    load_babilong,
    record_to_sample,
    summarize_babilong_results,
)


def test_all_twenty_tasks_and_official_label_constraints() -> None:
    assert len(BABILONG_TASKS) == 20
    assert compare_babilong_answer("garden", "The answer is garden.", "Where is Mary?", "qa1")
    assert not compare_babilong_answer(
        "garden", "Mary moved from office to garden.", "Where is Mary?", "qa1"
    )
    assert compare_babilong_answer("apple,milk", "apple and milk", "What is John carrying?", "qa8")
    assert not compare_babilong_answer(
        "apple,milk", "apple, milk, and football", "What is John carrying?", "qa8"
    )


def test_question_labels_are_excluded_like_upstream() -> None:
    assert compare_babilong_answer("garden", "Not office; garden", "Is Mary in the office?", "qa1")


def test_record_preserves_task_context_and_revisions() -> None:
    sample = record_to_sample(
        {"id": "1", "question": "Where is Mary?", "target": "garden", "input": "Mary went."},
        task_name="qa1",
        context_length="16k",
    )
    assert sample.metadata["task"] == "qa1"
    assert sample.metadata["context_length"] == "16k"
    assert sample.metadata["dataset_revision"] == BABILONG_DATASET_REVISION


def test_loader_pins_1k_variant_and_task_split() -> None:
    calls = []

    def fixture(*args, **kwargs):
        calls.append((args, kwargs))
        return [Sample(id=kwargs["split"], input="x", target="y")]

    with (
        patch("matric_eval.tasks.babilong.load_hf_dataset", side_effect=fixture),
        patch("matric_eval.tasks.babilong.get_sample_count", return_value=2),
    ):
        samples = load_babilong(tasks=("qa1", "qa2"), context_length="16k")
    assert len(samples) == 2
    assert {call[1]["split"] for call in calls} == {"qa1", "qa2"}
    assert all(call[1]["subset"] == "16k" for call in calls)
    assert all(call[1]["revision"] == BABILONG_DATASET_REVISION for call in calls)


def test_only_zero_context_releases_qa6_through_qa20() -> None:
    with pytest.raises(ValueError, match="only releases qa1-qa5"):
        load_babilong(tasks=("qa20",), context_length="16k")


def test_aggregate_retains_task_and_reasoning_complexity() -> None:
    summary = summarize_babilong_results(
        [
            {"task": "qa1", "accuracy": 1.0},
            {"task": "qa2", "accuracy": 0.5},
            {"task": "qa3", "accuracy": 0.25},
        ]
    )
    assert summary["by_task"] == {"qa1": 1.0, "qa2": 0.5, "qa3": 0.25}
    assert set(summary["by_reasoning_complexity"]) == {1, 2, 3}
