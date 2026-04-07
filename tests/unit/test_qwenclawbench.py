"""
Tests for QwenClawBench benchmark task.
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.qwenclawbench import (
    load_qwenclawbench,
    qwenclawbench,
    qwenclawbench_scorer,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "task_id": "qcb-001",
        "description": "Parse a CSV file and compute the average of column 3.",
        "expected_output": "42.5",
        "category": "data_processing",
        "difficulty": "medium",
    }


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "qcb-001"
        assert "CSV" in sample.input

    def test_metadata(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["category"] == "data_processing"
        assert sample.metadata["difficulty"] == "medium"


class TestRegistration:
    def test_registered(self) -> None:
        meta = qwenclawbench._benchmark_metadata
        assert meta.name == "qwenclawbench"
        assert meta.requires_sandbox is True
        assert meta.category.value == "agentic"

    @patch("matric_eval.tasks.qwenclawbench.load_qwenclawbench")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="t", target="e", id="1")]
        task = qwenclawbench(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "qwenclawbench"
