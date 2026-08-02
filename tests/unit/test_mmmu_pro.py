"""MMMU-Pro setting, image-order, and evaluator tests."""

from unittest.mock import Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.model import ContentImage, ContentText
from inspect_ai.scorer import Target
from PIL import Image

from matric_eval.tasks.mmmu_pro import (
    MMMU_PRO_DATASET_REVISION,
    mmmu_pro,
    mmmu_pro_scorer,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def _standard_record() -> dict:
    return {
        "id": "test_History_1",
        "question": "Compare <image 2> with <image 1>.",
        "options": repr([str(index) for index in range(10)]),
        "answer": "B",
        "subject": "History",
        "image_1": Image.new("RGB", (2, 2), "red"),
        "image_2": Image.new("RGB", (2, 2), "blue"),
    }


def test_standard_record_preserves_token_image_order() -> None:
    sample = record_to_sample(_standard_record(), setting="standard")
    content = sample.input[0].content
    assert [type(item) for item in content[:4]] == [
        ContentText,
        ContentImage,
        ContentText,
        ContentImage,
    ]
    assert len(sample.choices or []) == 10
    assert sample.metadata["image_count"] == 2
    assert sample.metadata["dataset_revision"] == MMMU_PRO_DATASET_REVISION


def test_vision_record_uses_rendered_single_image() -> None:
    sample = record_to_sample(
        {
            "id": "test_Math_1",
            "image": Image.new("RGB", (2, 2)),
            "options": repr(["one", "two", "three", "four"]),
            "answer": "A",
            "subject": "Math",
        },
        setting="vision",
    )
    assert isinstance(sample.input[0].content[0], ContentImage)
    assert sample.metadata["setting"] == "vision"


def test_open_answer_schema_is_rejected_as_non_official() -> None:
    with pytest.raises(ValueError, match="only multiple-choice"):
        record_to_sample({"id": "x", "question": "q", "answer": "free", "image_1": b"x"})


@pytest.mark.asyncio
async def test_official_parser_parity_fixture() -> None:
    scorer_fn = mmmu_pro_scorer()
    state = Mock()
    state.output.completion = "Analysis mentions A. Answer: (B)"
    state.metadata = {"options": ["one", "two"], "discipline": "Science"}
    result = await scorer_fn(state, Target(target="B"))
    assert result.value == 1.0


def test_settings_have_distinct_task_names() -> None:
    sample = record_to_sample(_standard_record(), setting="standard")
    with patch("matric_eval.tasks.mmmu_pro.load_mmmu_pro", return_value=[sample]):
        standard = mmmu_pro(setting="standard")
        vision = mmmu_pro(setting="vision", prompt_mode="direct")
    assert isinstance(standard, Task)
    assert standard.name == "mmmu_pro_standard_cot"
    assert vision.name == "mmmu_pro_vision_direct"
