"""
Tests for QwenWebBench benchmark task (Elo rating).
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.qwenwebbench import (
    load_qwenwebbench,
    qwenwebbench,
    record_to_sample,
    webbench_scorer,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "task_id": "qwb-001",
        "specification": "Create a responsive login form with email and password fields.",
        "reference_html": "<form>...</form>",
        "category": "forms",
        "complexity": "medium",
    }


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "qwb-001"
        assert "login form" in sample.input

    def test_metadata(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["category"] == "forms"
        assert sample.metadata["complexity"] == "medium"


class TestWebbenchScorer:
    @pytest.mark.asyncio
    async def test_scorer_factory(self) -> None:
        scorer_fn = webbench_scorer()
        assert callable(scorer_fn)


class TestRegistration:
    def test_registered(self) -> None:
        meta = qwenwebbench._benchmark_metadata
        assert meta.name == "qwenwebbench"
        assert meta.scoring_type == "elo"
        assert meta.requires_sandbox is False

    @patch("matric_eval.tasks.qwenwebbench.load_qwenwebbench")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="spec", target="html", id="1")]
        task = qwenwebbench(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "qwenwebbench"
