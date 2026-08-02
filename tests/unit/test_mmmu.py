"""MMMU current multimodal protocol tests."""

from unittest.mock import Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.model import ContentImage
from inspect_ai.scorer import Target
from PIL import Image

from matric_eval.tasks.mmmu import (
    MMMU_DATASET_REVISION,
    _extract_answer,
    _parse_open_response,
    mmmu,
    mmmu_scorer,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def test_record_contains_ordered_real_images_and_options() -> None:
    sample = record_to_sample(
        {
            "id": "Art_1",
            "question": "What style is shown?",
            "options": ["Impressionism", "Cubism"],
            "answer": "A",
            "question_type": "multiple-choice",
            "image_1": Image.new("RGB", (2, 2)),
        }
    )
    content = sample.input[0].content
    assert any(isinstance(item, ContentImage) for item in content)
    assert sample.choices == ["Impressionism", "Cubism"]
    assert sample.metadata["options"] == ["Impressionism", "Cubism"]
    assert sample.metadata["requires_vision"] is True
    assert sample.metadata["dataset_revision"] == MMMU_DATASET_REVISION


def test_multiple_choice_parser_uses_declared_options() -> None:
    assert _extract_answer("The final answer is (E).", ["1", "2", "3", "4", "5"]) == "E"
    assert (
        _extract_answer(
            "After reviewing every option, I choose Cubism as the answer",
            ["Impressionism", "Cubism"],
        )
        == "B"
    )


def test_open_parser_extracts_numeric_answer() -> None:
    assert 42.0 in _parse_open_response("Therefore, the answer is 42.")


@pytest.mark.asyncio
async def test_official_scorer() -> None:
    score_fn = mmmu_scorer()
    state = Mock()
    state.output.completion = "(B)"
    state.metadata = {
        "question_type": "multiple-choice",
        "options": ["one", "two"],
        "subject": "Math",
        "discipline": "Science",
        "split": "test",
    }
    result = await score_fn(state, Target(target="B"))
    assert result.value == 1.0


def test_registration_and_explicit_split_name() -> None:
    metadata = mmmu._benchmark_metadata
    assert metadata.total_samples == 11400
    assert metadata.requires_vision is True
    with patch(
        "matric_eval.tasks.mmmu.load_mmmu",
        return_value=[record_to_sample({"id": "x", "question": "q", "answer": "a"})],
    ):
        result = mmmu(split="test")
    assert isinstance(result, Task)
    assert result.name == "mmmu_test"
