"""
Tests for RealWorldQA benchmark task (multimodal).
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.realworldqa import (
    realworldqa,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "id": "rwqa-001",
        "question": "What does the sign in the image say?",
        "answer": "Stop",
        "options": ["A. Stop", "B. Go", "C. Yield", "D. Merge"],
    }


@pytest.fixture
def sample_record_no_options() -> dict[str, Any]:
    return {
        "id": "rwqa-002",
        "question": "How many people are in this image?",
        "answer": "3",
    }


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "rwqa-001"
        assert "sign" in sample.input
        assert sample.target == "Stop"

    def test_options_included(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert "Stop" in sample.input
        assert "Yield" in sample.input

    def test_no_options(self, sample_record_no_options: dict) -> None:
        sample = record_to_sample(sample_record_no_options)
        assert sample.input == "How many people are in this image?"

    def test_vision_metadata(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["requires_vision"] is True


class TestRegistration:
    def test_registered(self) -> None:
        meta = realworldqa._benchmark_metadata
        assert meta.name == "realworldqa"
        assert meta.requires_vision is True
        assert meta.category.value == "multimodal"
        assert meta.total_samples == 700

    @patch("matric_eval.tasks.realworldqa.load_realworldqa")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="q", target="A", id="1")]
        task = realworldqa(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "realworldqa"
