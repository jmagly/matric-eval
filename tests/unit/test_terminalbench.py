"""
Tests for Terminal-Bench 2.0 benchmark task.
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.terminalbench import (
    load_terminalbench,
    record_to_sample,
    terminal_task_scorer,
    terminalbench,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "task_id": "tb-001",
        "description": "Create a directory named 'test' and a file 'test/hello.txt'",
        "expected_output": "test/hello.txt exists",
        "setup_commands": ["rm -rf test"],
        "verification": "test -f test/hello.txt && echo PASS",
    }


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "tb-001"
        assert "Create a directory" in sample.input
        assert sample.metadata["sandbox_type"] == "terminal"

    def test_verification_in_metadata(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["verification"] == "test -f test/hello.txt && echo PASS"

    def test_setup_commands(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["setup_commands"] == ["rm -rf test"]

    def test_empty_record_fallbacks(self) -> None:
        sample = record_to_sample({})
        assert sample.id == ""
        assert sample.metadata["sandbox_type"] == "terminal"


class TestTerminalTaskScorer:
    @pytest.mark.asyncio
    async def test_scorer_factory(self) -> None:
        scorer_fn = terminal_task_scorer()
        assert callable(scorer_fn)


class TestRegistration:
    def test_registered(self) -> None:
        meta = terminalbench._benchmark_metadata
        assert meta.name == "terminalbench"
        assert meta.requires_sandbox is True
        assert meta.category.value == "agentic"
        assert meta.sandbox_profile == "basic"

    @patch("matric_eval.tasks.terminalbench.load_terminalbench")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="t", target="e", id="1")]
        task = terminalbench(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "terminalbench"
