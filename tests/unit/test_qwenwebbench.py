"""
Tests for QwenWebBench benchmark task (Elo rating).
"""

from typing import Any

import pytest

from matric_eval.tasks.qwenwebbench import (
    QWENWEBBENCH_UNAVAILABLE_REASON,
    load_qwenwebbench,
    qwenwebbench,
    record_to_sample,
    webbench_scorer,
)
from matric_eval.tasks.registry import BenchmarkStatus, BenchmarkUnavailableError


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
    def test_scorer_is_quarantined(self) -> None:
        with pytest.raises(BenchmarkUnavailableError, match="unavailable"):
            webbench_scorer()


class TestUnavailableSource:
    def test_loader_never_attempts_remote_source(self) -> None:
        with pytest.raises(BenchmarkUnavailableError, match="unavailable"):
            load_qwenwebbench()


class TestRegistration:
    def test_registered(self) -> None:
        meta = qwenwebbench._benchmark_metadata
        assert meta.name == "qwenwebbench"
        assert meta.scoring_type == "elo"
        assert meta.requires_sandbox is False
        assert meta.status == BenchmarkStatus.UNAVAILABLE
        assert meta.status_reason == QWENWEBBENCH_UNAVAILABLE_REASON

    def test_task_execution_is_quarantined(self) -> None:
        with pytest.raises(BenchmarkUnavailableError, match="unavailable"):
            qwenwebbench(tier="smoke")
