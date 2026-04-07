"""
Tests for MMMU benchmark task (multimodal).
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.mmmu import (
    _extract_answer,
    load_mmmu,
    mmmu,
    mmmu_scorer,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "id": "mmmu-art-001",
        "question": "What art movement does this painting belong to?",
        "options": ["A. Impressionism", "B. Cubism", "C. Surrealism", "D. Baroque"],
        "answer": "A",
        "subject": "Art",
        "subfield": "Art History",
        "question_type": "multiple-choice",
        "image_1": "mock_image",  # would be PIL.Image in practice
    }


@pytest.fixture
def sample_record_no_images() -> dict[str, Any]:
    return {
        "id": "mmmu-math-001",
        "question": "Solve: 2x + 3 = 7",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "answer": "B",
        "subject": "Math",
        "subfield": "Algebra",
        "question_type": "multiple-choice",
    }


# =============================================================================
# Record to Sample
# =============================================================================


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "mmmu-art-001"
        assert "art movement" in sample.input
        assert sample.target == "A"

    def test_options_in_input(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert "Impressionism" in sample.input
        assert "Cubism" in sample.input

    def test_metadata_subject(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["subject"] == "Art"
        assert sample.metadata["subfield"] == "Art History"

    def test_image_detection(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["has_images"] is True
        assert sample.metadata["image_count"] == 1

    def test_no_images(self, sample_record_no_images: dict) -> None:
        sample = record_to_sample(sample_record_no_images)
        assert sample.metadata["has_images"] is False
        assert sample.metadata["image_count"] == 0


# =============================================================================
# Answer Extraction
# =============================================================================


class TestExtractAnswer:
    def test_single_letter(self) -> None:
        assert _extract_answer("A") == "A"
        assert _extract_answer("B") == "B"
        assert _extract_answer("E") == "E"

    def test_letter_with_period(self) -> None:
        assert _extract_answer("A.") == "A"
        assert _extract_answer("C.") == "C"

    def test_parenthesized(self) -> None:
        assert _extract_answer("The answer is (B)") == "B"

    def test_answer_is_pattern(self) -> None:
        assert _extract_answer("The answer is C") == "C"
        assert _extract_answer("Answer: D") == "D"

    def test_lowercase_normalized(self) -> None:
        assert _extract_answer("a") == "A"
        assert _extract_answer("b.") == "B"

    def test_empty_string(self) -> None:
        assert _extract_answer("") == ""

    def test_no_valid_answer(self) -> None:
        assert _extract_answer("I don't know") == ""

    def test_trailing_letter(self) -> None:
        assert _extract_answer("After analysis, the answer is B") == "B"


# =============================================================================
# Registration
# =============================================================================


class TestRegistration:
    def test_registered(self) -> None:
        meta = mmmu._benchmark_metadata
        assert meta.name == "mmmu"
        assert meta.requires_vision is True
        assert meta.category.value == "multimodal"
        assert meta.total_samples == 11500

    @patch("matric_eval.tasks.mmmu.load_mmmu")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="q", target="A", id="1")]
        task = mmmu(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "mmmu"


class TestMmmuScorer:
    @pytest.mark.asyncio
    async def test_scorer_factory(self) -> None:
        scorer_fn = mmmu_scorer()
        assert callable(scorer_fn)
