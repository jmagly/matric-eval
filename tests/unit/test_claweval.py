"""
Tests for Claw-Eval benchmark task (pass^3 scoring).
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.claweval import (
    claweval,
    claweval_scorer,
    load_claweval,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "task_id": "claw-001",
        "description": "Set up a Python virtual environment and install requests.",
        "verification": "python -c 'import requests'",
        "setup": {"os": "ubuntu-22.04"},
        "difficulty": "easy",
    }


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "claw-001"
        assert "virtual environment" in sample.input
        assert sample.metadata["k"] == 3

    def test_difficulty_preserved(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["difficulty"] == "easy"

    def test_empty_record(self) -> None:
        sample = record_to_sample({})
        assert sample.metadata["k"] == 3
        assert sample.metadata["difficulty"] == "medium"


class TestClawEvalScorer:
    @pytest.mark.asyncio
    async def test_scorer_factory(self) -> None:
        scorer_fn = claweval_scorer()
        assert callable(scorer_fn)


class TestRegistration:
    def test_registered(self) -> None:
        meta = claweval._benchmark_metadata
        assert meta.name == "claweval"
        assert meta.requires_sandbox is True
        assert meta.scoring_type == "pass_k"
        assert meta.category.value == "agentic"

    @patch("matric_eval.tasks.claweval.load_claweval")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="t", target="v", id="1")]
        task = claweval(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "claweval"
