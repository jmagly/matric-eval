"""
Tests for Video-MME benchmark task (multimodal video).
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.videomme import (
    DEFAULT_MAX_FRAMES,
    PROVIDER_FRAME_CAPS,
    _extract_answer,
    load_videomme,
    record_to_sample,
    videomme,
    videomme_scorer,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "video_id": "vmme-001",
        "question": "What happens at the end of the video?",
        "options": [
            "A. The cat jumps",
            "B. The dog barks",
            "C. Nothing happens",
            "D. The scene changes",
        ],
        "answer": "A",
        "video_path": "/data/videos/sample.mp4",
        "subtitle_path": "/data/subs/sample.srt",
        "duration": "short",
    }


# =============================================================================
# Record to Sample
# =============================================================================


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "vmme-001"
        assert "cat jumps" in sample.input
        assert sample.target == "A"

    def test_metadata(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["video_path"] == "/data/videos/sample.mp4"
        assert sample.metadata["subtitle_path"] == "/data/subs/sample.srt"
        assert sample.metadata["duration_category"] == "short"
        assert sample.metadata["requires_vision"] is True
        assert sample.metadata["requires_ffmpeg"] is True


# =============================================================================
# Answer Extraction
# =============================================================================


class TestExtractAnswer:
    def test_single_letter(self) -> None:
        assert _extract_answer("A") == "A"
        assert _extract_answer("D") == "D"

    def test_letter_with_period(self) -> None:
        assert _extract_answer("B.") == "B"

    def test_parenthesized(self) -> None:
        assert _extract_answer("I think (C)") == "C"

    def test_answer_pattern(self) -> None:
        assert _extract_answer("The answer is D") == "D"
        assert _extract_answer("Answer: A") == "A"

    def test_lowercase(self) -> None:
        assert _extract_answer("b") == "B"

    def test_empty(self) -> None:
        assert _extract_answer("") == ""

    def test_no_match(self) -> None:
        assert _extract_answer("I'm not sure") == ""


# =============================================================================
# Constants
# =============================================================================


class TestConstants:
    def test_default_max_frames(self) -> None:
        assert DEFAULT_MAX_FRAMES == 64

    def test_provider_caps(self) -> None:
        assert PROVIDER_FRAME_CAPS["ollama"] == 16
        assert PROVIDER_FRAME_CAPS["openrouter"] == 32


# =============================================================================
# Registration
# =============================================================================


class TestRegistration:
    def test_registered(self) -> None:
        meta = videomme._benchmark_metadata
        assert meta.name == "videomme"
        assert meta.requires_vision is True
        assert meta.category.value == "multimodal"
        assert "ffmpeg" in meta.provider_requirements

    @patch("matric_eval.tasks.videomme.load_videomme")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="q", target="A", id="1")]
        task = videomme(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "videomme"
