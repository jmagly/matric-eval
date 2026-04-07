"""
Tests for OmniDocBench v1.5 benchmark task (multimodal).
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.omnidocbench import (
    TASK_TYPES,
    load_omnidocbench,
    omnidocbench,
    omnidocbench_scorer,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "id": "odb-001",
        "question": "What is the total in the bottom-right cell of the table?",
        "answer": "1,234",
        "task_type": "table",
        "document_type": "financial_report",
    }


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "odb-001"
        assert "table" in sample.input
        assert sample.target == "1,234"

    def test_task_type_in_metadata(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["task_type"] == "table"
        assert sample.metadata["document_type"] == "financial_report"

    def test_vision_metadata(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["requires_vision"] is True


class TestTaskTypes:
    def test_valid_types(self) -> None:
        assert "ocr" in TASK_TYPES
        assert "layout" in TASK_TYPES
        assert "table" in TASK_TYPES
        assert "comprehension" in TASK_TYPES


class TestRegistration:
    def test_registered(self) -> None:
        meta = omnidocbench._benchmark_metadata
        assert meta.name == "omnidocbench"
        assert meta.requires_vision is True
        assert meta.category.value == "multimodal"

    @patch("matric_eval.tasks.omnidocbench.load_omnidocbench")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="q", target="a", id="1")]
        task = omnidocbench(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "omnidocbench"
