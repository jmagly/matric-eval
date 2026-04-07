"""
Tests for NL2Repo benchmark task.
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.nl2repo import (
    load_nl2repo,
    nl2repo,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry."""


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "id": "nl2r-001",
        "specification": "Create a REST API with user authentication using Flask.",
        "build_command": "pip install -r requirements.txt",
        "test_command": "pytest tests/",
        "language": "python",
        "expected_structure": {"src/app.py": True, "tests/": True},
    }


class TestRecordToSample:
    def test_basic_conversion(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.id == "nl2r-001"
        assert "REST API" in sample.input
        assert sample.target == ""  # No single target for project gen

    def test_metadata_fields(self, sample_record: dict) -> None:
        sample = record_to_sample(sample_record)
        assert sample.metadata["language"] == "python"
        assert sample.metadata["build_command"] == "pip install -r requirements.txt"
        assert sample.metadata["test_command"] == "pytest tests/"

    def test_empty_record(self) -> None:
        sample = record_to_sample({})
        assert sample.id == ""
        assert sample.metadata["language"] == "python"  # default


class TestRegistration:
    def test_registered(self) -> None:
        meta = nl2repo._benchmark_metadata
        assert meta.name == "nl2repo"
        assert meta.requires_sandbox is True
        assert meta.scoring_type == "project"
        assert meta.category.value == "agentic"

    @patch("matric_eval.tasks.nl2repo.load_nl2repo")
    def test_task_creation(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="spec", target="", id="1")]
        task = nl2repo(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "nl2repo"
