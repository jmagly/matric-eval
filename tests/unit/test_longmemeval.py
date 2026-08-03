"""
Tests for LongMemEval benchmark task (matric_eval.tasks.longmemeval).

Covers:
- Sample conversion from different record formats
- Dataset loading with tiered sampling
- Per-question-type metadata preservation
- Task definition
- Tier configuration
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.longmemeval import (
    QUESTION_TYPES,
    VALID_SCALES,
    load_longmemeval,
    longmemeval,
    record_to_sample,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton."""
    monkeypatch.delenv("EVAL_LONGMEMEVAL_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    import matric_eval.config.settings as settings_module

    settings_module._settings = None


@pytest.fixture
def sample_records() -> list[dict]:
    """Create sample LongMemEval records in JSONL format."""
    return [
        {
            "question_id": "lme_001",
            "question_type": "single-session-user",
            "question": "What restaurant did I mention wanting to try last Tuesday?",
            "answer": "Sakura Sushi",
            "question_date": "2024-03-15",
            "haystack_session_ids": ["sess_001", "sess_002", "sess_003"],
            "haystack_dates": ["2024-03-10", "2024-03-12", "2024-03-14"],
            "answer_session_ids": ["sess_002"],
        },
        {
            "question_id": "lme_002",
            "question_type": "multi-session",
            "question": "What are all the books I asked you to recommend across our conversations?",
            "answer": "The Great Gatsby, 1984, Dune",
            "question_date": "2024-03-16",
            "haystack_session_ids": ["sess_001", "sess_002", "sess_003", "sess_004"],
            "haystack_dates": ["2024-03-10", "2024-03-12", "2024-03-14", "2024-03-15"],
            "answer_session_ids": ["sess_001", "sess_003"],
        },
        {
            "question_id": "lme_003",
            "question_type": "temporal-reasoning",
            "question": (
                "Did I change my preferred programming language between our first "
                "and last conversation?"
            ),
            "answer": "Yes, from Python to Rust",
            "question_date": "2024-03-17",
            "haystack_session_ids": ["sess_001", "sess_005"],
            "haystack_dates": ["2024-03-10", "2024-03-16"],
            "answer_session_ids": ["sess_001", "sess_005"],
        },
        {
            "question_id": "lme_004",
            "question_type": "knowledge-update",
            "question": "What is my current email address?",
            "answer": "new@example.com",
            "question_date": "2024-03-18",
            "haystack_session_ids": ["sess_002", "sess_006"],
            "haystack_dates": ["2024-03-12", "2024-03-17"],
            "answer_session_ids": ["sess_006"],
        },
        {
            "question_id": "lme_005",
            "question_type": "abstention",
            "question": "What did I say about quantum computing?",
            "answer": "I never discussed quantum computing.",
            "question_date": "2024-03-19",
            "haystack_session_ids": ["sess_001", "sess_002", "sess_003"],
            "haystack_dates": ["2024-03-10", "2024-03-12", "2024-03-14"],
            "answer_session_ids": [],
        },
    ]


@pytest.fixture
def sample_records_simplified() -> list[dict]:
    """Create sample LongMemEval records in simplified JSONL format."""
    return [
        {
            "id": "simple_001",
            "type": "single-session-assistant",
            "question": "What advice did you give me about cooking pasta?",
            "answer": "Salt the water generously and cook al dente",
            "date": "2024-04-01",
        },
        {
            "id": "simple_002",
            "type": "single-session-preference",
            "question": "What is my favorite color?",
            "answer": "Blue",
            "date": "2024-04-02",
        },
    ]


@pytest.fixture
def longmemeval_jsonl_file(sample_records: list[dict], tmp_path: Path) -> Path:
    """Create a temporary LongMemEval JSONL file."""
    data_dir = tmp_path / "longmemeval"
    data_dir.mkdir()
    jsonl_file = data_dir / "longmemeval_s.jsonl"
    with open(jsonl_file, "w") as f:
        for record in sample_records:
            f.write(json.dumps(record) + "\n")
    return data_dir


@pytest.fixture
def longmemeval_jsonl_file_m(sample_records: list[dict], tmp_path: Path) -> Path:
    """Create a temporary LongMemEval JSONL file for medium scale."""
    data_dir = tmp_path / "longmemeval"
    data_dir.mkdir()
    jsonl_file = data_dir / "longmemeval_m.jsonl"
    with open(jsonl_file, "w") as f:
        for record in sample_records:
            f.write(json.dumps(record) + "\n")
    return data_dir


# =============================================================================
# Record to Sample Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() function."""

    def test_converts_huggingface_format(self) -> None:
        """Should convert HuggingFace format with full metadata."""
        record = {
            "question_id": "lme_001",
            "question_type": "single-session-user",
            "question": "What restaurant did I mention?",
            "answer": "Sakura Sushi",
            "question_date": "2024-03-15",
            "haystack_session_ids": ["sess_001", "sess_002"],
            "haystack_dates": ["2024-03-10", "2024-03-12"],
            "answer_session_ids": ["sess_002"],
        }
        sample = record_to_sample(record)
        assert isinstance(sample, Sample)
        assert "restaurant" in sample.input.lower()
        assert sample.target == "Sakura Sushi"
        assert sample.id == "lme_001"

    def test_converts_simplified_format(self) -> None:
        """Should convert simplified JSONL format with fallback fields."""
        record = {
            "id": "simple_001",
            "type": "single-session-assistant",
            "question": "What advice did you give about pasta?",
            "answer": "Salt the water",
            "date": "2024-04-01",
        }
        sample = record_to_sample(record)
        assert isinstance(sample, Sample)
        assert "pasta" in sample.input.lower()
        assert sample.target == "Salt the water"
        assert sample.id == "simple_001"

    def test_preserves_question_type_metadata(self) -> None:
        """Should include question_type in metadata."""
        record = {
            "question_id": "lme_002",
            "question_type": "temporal-reasoning",
            "question": "Did I change my preference?",
            "answer": "Yes",
            "question_date": "2024-03-17",
            "haystack_session_ids": [],
            "haystack_dates": [],
            "answer_session_ids": [],
        }
        sample = record_to_sample(record)
        assert sample.metadata["question_type"] == "temporal-reasoning"

    def test_preserves_session_ids_in_metadata(self) -> None:
        """Should store gold session IDs in metadata for future Recall@K."""
        record = {
            "question_id": "lme_003",
            "question_type": "multi-session",
            "question": "What books did I ask about?",
            "answer": "Dune, 1984",
            "question_date": "2024-03-16",
            "haystack_session_ids": ["sess_001", "sess_002", "sess_003"],
            "haystack_dates": ["2024-03-10", "2024-03-12", "2024-03-14"],
            "answer_session_ids": ["sess_001", "sess_003"],
        }
        sample = record_to_sample(record)
        assert sample.metadata["haystack_session_ids"] == ["sess_001", "sess_002", "sess_003"]
        assert sample.metadata["answer_session_ids"] == ["sess_001", "sess_003"]
        assert sample.metadata["haystack_dates"] == ["2024-03-10", "2024-03-12", "2024-03-14"]

    def test_preserves_question_date(self) -> None:
        """Should include question_date in metadata."""
        record = {
            "question_id": "lme_004",
            "question_type": "knowledge-update",
            "question": "What is my email?",
            "answer": "new@example.com",
            "question_date": "2024-03-18",
        }
        sample = record_to_sample(record)
        assert sample.metadata["question_date"] == "2024-03-18"

    def test_handles_missing_optional_fields(self) -> None:
        """Should handle records with minimal fields gracefully."""
        record = {
            "question": "What did I say?",
            "answer": "Something important",
        }
        sample = record_to_sample(record)
        assert isinstance(sample, Sample)
        assert sample.target == "Something important"
        assert sample.metadata["question_type"] == "unknown"
        assert sample.metadata["haystack_session_ids"] == []
        assert sample.metadata["answer_session_ids"] == []

    def test_simplified_format_uses_fallback_fields(self) -> None:
        """Should fall back to 'type' when 'question_type' is missing."""
        record = {
            "id": "s_001",
            "type": "single-session-preference",
            "question": "Favorite color?",
            "answer": "Blue",
            "date": "2024-04-02",
        }
        sample = record_to_sample(record)
        assert sample.metadata["question_type"] == "single-session-preference"
        assert sample.metadata["question_date"] == "2024-04-02"
        assert sample.id == "s_001"


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadLongmemeval:
    """Tests for load_longmemeval() function."""

    def test_loads_from_jsonl(self, longmemeval_jsonl_file: Path) -> None:
        """Should load samples from JSONL file."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file)):
            samples = load_longmemeval(tier="smoke")
            assert len(samples) == 5  # All records (fewer than smoke count)
            assert all(isinstance(s, Sample) for s in samples)

    def test_loads_medium_scale(self, longmemeval_jsonl_file_m: Path) -> None:
        """Should load medium scale dataset."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file_m)):
            samples = load_longmemeval(tier="smoke", scale="m")
            assert len(samples) == 5
            assert all(isinstance(s, Sample) for s in samples)

    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when dataset missing."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(tmp_path / "nonexistent")):
            with pytest.raises(FileNotFoundError, match="LongMemEval dataset not found"):
                load_longmemeval(tier="smoke")

    def test_returns_empty_for_zero_samples(self, longmemeval_jsonl_file: Path) -> None:
        """Should return empty list when tier has 0 samples."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file)):
            with patch("matric_eval.tasks.longmemeval.get_sample_count", return_value=0):
                samples = load_longmemeval(tier="smoke")
                assert samples == []

    def test_reproducible_sampling(self, longmemeval_jsonl_file: Path) -> None:
        """Should produce same samples with same seed."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file)):
            with patch("matric_eval.tasks.longmemeval.get_sample_count", return_value=3):
                samples_1 = load_longmemeval(tier="smoke")
                samples_2 = load_longmemeval(tier="smoke")
                assert [s.id for s in samples_1] == [s.id for s in samples_2]

    def test_invalid_scale_raises(self) -> None:
        """Should raise ValueError for invalid scale."""
        with pytest.raises(ValueError, match="Invalid scale"):
            load_longmemeval(tier="smoke", scale="xl")

    def test_preserves_all_question_types(self, longmemeval_jsonl_file: Path) -> None:
        """Should preserve question_type metadata across all samples."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file)):
            samples = load_longmemeval(tier="smoke")
            question_types = {s.metadata["question_type"] for s in samples}
            # Our fixture has 5 different types
            assert len(question_types) == 5
            assert "single-session-user" in question_types
            assert "multi-session" in question_types
            assert "temporal-reasoning" in question_types


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestLongmemevalTask:
    """Tests for longmemeval() task definition."""

    def test_creates_task(self, longmemeval_jsonl_file: Path) -> None:
        """Should create a valid Inspect AI Task."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file)):
            task = longmemeval(tier="smoke")
            assert isinstance(task, Task)

    def test_task_has_scorer(self, longmemeval_jsonl_file: Path) -> None:
        """Should include match scorer for QA correctness."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file)):
            task = longmemeval(tier="smoke")
            assert task.scorer is not None

    def test_task_name_includes_scale(self, longmemeval_jsonl_file: Path) -> None:
        """Should name task with scale."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file)):
            task = longmemeval(tier="smoke", scale="s")
            assert "longmemeval_s" in task.name

    def test_task_with_thinking(self, longmemeval_jsonl_file: Path) -> None:
        """Should create task with thinking-enabled system message."""
        with patch("matric_eval.tasks.longmemeval.LONGMEMEVAL_PATH", str(longmemeval_jsonl_file)):
            task = longmemeval(tier="smoke", thinking=True)
            assert isinstance(task, Task)


# =============================================================================
# Tier Configuration Tests
# =============================================================================


@pytest.mark.unit
class TestLongmemevalTierConfig:
    """Tests for LongMemEval tier configuration."""

    def test_smoke_tier_has_longmemeval(self) -> None:
        """Smoke tier should have LongMemEval samples configured."""
        from matric_eval.config import get_tier

        tier = get_tier("smoke")
        assert tier.longmemeval > 0

    def test_smoke_tier_value(self) -> None:
        """Smoke tier should have 10 samples."""
        from matric_eval.config import get_tier

        tier = get_tier("smoke")
        assert tier.longmemeval == 10

    def test_quick_tier_has_longmemeval(self) -> None:
        """Quick tier should have LongMemEval samples configured."""
        from matric_eval.config import get_tier

        tier = get_tier("quick")
        assert tier.longmemeval > 0

    def test_quick_tier_value(self) -> None:
        """Quick tier should have 100 samples."""
        from matric_eval.config import get_tier

        tier = get_tier("quick")
        assert tier.longmemeval == 100

    def test_full_tier_has_all_longmemeval(self) -> None:
        """Full tier should have all 500 questions."""
        from matric_eval.config import get_tier

        tier = get_tier("full")
        assert tier.longmemeval == 500


# =============================================================================
# Constants Tests
# =============================================================================


@pytest.mark.unit
class TestConstants:
    """Tests for module-level constants."""

    def test_valid_scales(self) -> None:
        """Should have s and m scales."""
        assert "s" in VALID_SCALES
        assert "m" in VALID_SCALES

    def test_question_types_defined(self) -> None:
        """Should define expected question types."""
        assert "single-session-user" in QUESTION_TYPES
        assert "multi-session" in QUESTION_TYPES
        assert "temporal-reasoning" in QUESTION_TYPES
        assert "knowledge-update" in QUESTION_TYPES
        assert "abstention" in QUESTION_TYPES
