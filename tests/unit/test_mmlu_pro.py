"""MMLU-Pro protocol tests."""

from unittest.mock import Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.scorer import Target

from matric_eval.tasks.mmlu_pro import (
    MMLU_PRO_DATASET_REVISION,
    extract_mmlu_pro_answer,
    mmlu_pro,
    mmlu_pro_scorer,
    record_to_sample,
    stratified_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def _record(index: int, category: str = "math") -> dict:
    return {
        "question_id": index,
        "question": f"Question {index}",
        "options": [str(value) for value in range(10)],
        "answer": "J",
        "cot_content": "Reasoning. The answer is (J).",
        "category": category,
        "src": "fixture",
    }


def test_schema_conversion_supports_ten_options() -> None:
    sample = record_to_sample(_record(1))
    assert len(sample.choices or []) == 10
    assert sample.target == "J"
    assert sample.metadata["dataset_revision"] == MMLU_PRO_DATASET_REVISION


def test_answer_extraction_hierarchy() -> None:
    assert extract_mmlu_pro_answer("Therefore, the answer is (J).") == "J"
    assert extract_mmlu_pro_answer("Reasoning\nANSWER: C") == "C"
    assert extract_mmlu_pro_answer("I considered A and B, finally D") == "D"
    assert extract_mmlu_pro_answer("No choice supplied") is None


def test_stratified_sampling_is_deterministic_and_balanced() -> None:
    categories = ["math"] * 6 + ["history"] * 6 + ["law"] * 6
    samples = [record_to_sample(_record(i, category)) for i, category in enumerate(categories)]
    first = stratified_sample(samples, 6, 42)
    second = stratified_sample(samples, 6, 42)
    assert [sample.id for sample in first] == [sample.id for sample in second]
    assert {sample.metadata["category"] for sample in first} == {"math", "history", "law"}


@pytest.mark.asyncio
async def test_scorer_matches_official_fixture() -> None:
    score_fn = mmlu_pro_scorer()
    state = Mock()
    state.output.completion = "Step by step. ANSWER: J"
    result = await score_fn(state, Target(target="J"))
    assert result.value == "C"


def test_task_is_separate_from_legacy_mmlu() -> None:
    sample = record_to_sample(_record(1))
    with patch("matric_eval.tasks.mmlu_pro.load_mmlu_pro", return_value=[sample]):
        result = mmlu_pro()
    assert isinstance(result, Task)
    assert result.name == "mmlu_pro_2_a"
    assert mmlu_pro._benchmark_metadata.name == "mmlu_pro"
