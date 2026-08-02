"""Video-MME-v2 official configuration and grouped-metric tests."""

from unittest.mock import Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.model import ContentImage
from inspect_ai.scorer import Target

from matric_eval.tasks.videomme import (
    DEFAULT_MAX_FRAMES,
    VIDEOMME_DATASET_REVISION,
    _extract_answer,
    logic_rating,
    record_to_sample,
    relevance_rating,
    videomme,
    videomme_scorer,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


@pytest.fixture
def record() -> dict:
    return {
        "video_id": "video-1",
        "question_id": "video-1-0",
        "question": "What happens?",
        "options": ["A. One", "B. Two", "C. Three", "D. Four"],
        "answer": "A",
        "group_type": "relevance",
        "group_structure": [1, 2, 3, 4],
        "level": 1,
        "second_head": "perception",
        "third_head": "detail",
    }


def test_record_contains_actual_ordered_frames(record: dict) -> None:
    sample = record_to_sample(record, frame_paths=["/tmp/a.jpg", "/tmp/b.jpg"])
    images = [item for item in sample.input[0].content if isinstance(item, ContentImage)]
    assert [image.image for image in images] == ["/tmp/a.jpg", "/tmp/b.jpg"]
    assert sample.metadata["frame_count"] == 2
    assert sample.metadata["dataset_revision"] == VIDEOMME_DATASET_REVISION


def test_answer_parser_matches_upstream() -> None:
    assert _extract_answer("Final Answer: H") == "H"
    assert _extract_answer("Answer: A") == "A"
    assert _extract_answer("") == ""


def test_official_group_ratings() -> None:
    assert relevance_rating([True, True, True, True]) == 100.0
    assert relevance_rating([True, False, False, False]) == 6.25
    assert logic_rating([True, True, True, True], [1, 2, 3, 4]) == 100.0
    assert logic_rating([True, False, False, False], [1, [2, 3], 4]) == pytest.approx(100 / 12)


@pytest.mark.asyncio
async def test_question_scorer() -> None:
    score_fn = videomme_scorer()
    state = Mock()
    state.output.completion = "Final Answer: B"
    result = await score_fn(state, Target(target="B"))
    assert result.value == 1.0


def test_registration_and_configuration_name(record: dict) -> None:
    assert DEFAULT_MAX_FRAMES == 64
    metadata = videomme._benchmark_metadata
    assert metadata.total_samples == 3200
    assert metadata.protocol_version == "v2"
    with patch(
        "matric_eval.tasks.videomme.load_videomme",
        return_value=[record_to_sample(record, frame_paths=["/tmp/a.jpg"])],
    ):
        result = videomme(frame_mode="1fps", subtitle_mode="interleave", reasoning=True)
    assert isinstance(result, Task)
    assert result.name == "videomme_v2_1fps_interleave_reasoning"
