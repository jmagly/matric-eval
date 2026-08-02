"""
Tests for MemoryAgentBench benchmark task (matric_eval.tasks.memoryagentbench).

Covers:
- Record to sample conversion with competency metadata
- Dataset loading with tiered sampling
- Competency filtering (AR, TTL, LRU, CR)
- Tier configuration
- Task definition
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.memoryagentbench import (
    format_context_turns,
    load_memoryagentbench,
    memoryagentbench,
    record_to_sample,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton."""
    monkeypatch.delenv("EVAL_MEMORYAGENTBENCH_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    import matric_eval.config.settings as settings_module
    settings_module._settings = None


@pytest.fixture
def sample_records() -> list[dict]:
    """Create sample MemoryAgentBench records in JSONL format."""
    return [
        {
            "id": "mab_001",
            "competency": "AR",
            "question": "What city did the user mention moving to?",
            "answer": "Seattle",
            "context_turns": [
                "Turn 1: The user mentioned they grew up in Portland.",
                "Turn 2: The user discussed their job in tech.",
                "Turn 3: The user said they are moving to Seattle next month.",
            ],
            "metadata": {"dataset_source": "EventQA"},
        },
        {
            "id": "mab_002",
            "competency": "TTL",
            "question": "Based on the pattern, what is the next number?",
            "answer": "16",
            "context_turns": [
                "Turn 1: The sequence starts with 2.",
                "Turn 2: The next number is 4.",
                "Turn 3: Then 8.",
            ],
            "metadata": {"dataset_source": "FactConsolidation"},
        },
        {
            "id": "mab_003",
            "competency": "LRU",
            "question": "What is the overall theme of the user's career trajectory?",
            "answer": "Transition from engineering to management",
            "context_turns": [
                "Turn 1: Started as a junior engineer at a startup.",
                "Turn 2: Became a senior engineer after 3 years.",
                "Turn 3: Led a team of 5 engineers.",
                "Turn 4: Was promoted to engineering manager.",
                "Turn 5: Now oversees multiple teams.",
            ],
            "metadata": {"dataset_source": "EventQA"},
        },
        {
            "id": "mab_004",
            "competency": "CR",
            "question": "What is the user's current favorite programming language?",
            "answer": "Rust",
            "context_turns": [
                "Turn 1: The user said their favorite language is Python.",
                "Turn 2: The user started learning Rust.",
                "Turn 3: The user now says Rust is their favorite language.",
            ],
            "metadata": {"dataset_source": "FactConsolidation"},
        },
        {
            "id": "mab_005",
            "competency": "AR",
            "question": "What was the name of the user's dog?",
            "answer": "Max",
            "context_turns": [
                "Turn 1: The user talked about their dog Max.",
                "Turn 2: Max is a golden retriever.",
            ],
            "metadata": {"dataset_source": "EventQA"},
        },
    ]


@pytest.fixture
def mab_jsonl_file(sample_records: list[dict], tmp_path: Path) -> Path:
    """Create a temporary MemoryAgentBench JSONL file."""
    mab_dir = tmp_path / "memoryagentbench"
    mab_dir.mkdir()
    jsonl_file = mab_dir / "memoryagentbench.jsonl"
    with open(jsonl_file, "w") as f:
        for record in sample_records:
            f.write(json.dumps(record) + "\n")
    return mab_dir


# =============================================================================
# Context Formatting Tests
# =============================================================================


@pytest.mark.unit
class TestFormatContextTurns:
    """Tests for format_context_turns() function."""

    def test_formats_as_numbered_list(self) -> None:
        """Should format turns as a numbered list."""
        turns = ["First turn", "Second turn", "Third turn"]
        result = format_context_turns(turns)
        assert "1. First turn" in result
        assert "2. Second turn" in result
        assert "3. Third turn" in result

    def test_empty_turns(self) -> None:
        """Should handle empty turn list."""
        result = format_context_turns([])
        assert result == ""

    def test_single_turn(self) -> None:
        """Should handle single turn."""
        result = format_context_turns(["Only turn"])
        assert result == "1. Only turn"


# =============================================================================
# Record to Sample Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() function."""

    def test_converts_basic_record(self) -> None:
        """Should convert a basic MemoryAgentBench record."""
        record = {
            "id": "test_001",
            "competency": "AR",
            "question": "What city was mentioned?",
            "answer": "Seattle",
            "context_turns": ["Turn 1: Moving to Seattle."],
            "metadata": {"dataset_source": "EventQA"},
        }
        sample = record_to_sample(record)
        assert isinstance(sample, Sample)
        assert "Seattle" in sample.target
        assert sample.id == "test_001"

    def test_includes_question_in_input(self) -> None:
        """Should include the question in the formatted input."""
        record = {
            "id": "test_002",
            "question": "What is the favorite color?",
            "answer": "Blue",
            "context_turns": ["Turn 1: I like blue."],
            "competency": "AR",
            "metadata": {},
        }
        sample = record_to_sample(record)
        assert "What is the favorite color?" in sample.input

    def test_includes_context_turns_in_input(self) -> None:
        """Should include context turns in the formatted input."""
        record = {
            "id": "test_003",
            "question": "Q?",
            "answer": "A",
            "context_turns": ["Turn 1: Important info", "Turn 2: More info"],
            "competency": "TTL",
            "metadata": {},
        }
        sample = record_to_sample(record)
        assert "1. Turn 1: Important info" in sample.input
        assert "2. Turn 2: More info" in sample.input

    def test_preserves_competency_in_metadata(self) -> None:
        """Should store competency type in metadata."""
        record = {
            "id": "test_004",
            "question": "Q?",
            "answer": "A",
            "context_turns": [],
            "competency": "CR",
            "metadata": {"dataset_source": "FactConsolidation"},
        }
        sample = record_to_sample(record)
        assert sample.metadata["competency"] == "CR"

    def test_preserves_dataset_source_in_metadata(self) -> None:
        """Should store dataset_source in metadata."""
        record = {
            "id": "test_005",
            "question": "Q?",
            "answer": "A",
            "context_turns": [],
            "competency": "LRU",
            "metadata": {"dataset_source": "EventQA"},
        }
        sample = record_to_sample(record)
        assert sample.metadata["dataset_source"] == "EventQA"

    def test_tracks_num_turns(self) -> None:
        """Should count number of context turns in metadata."""
        record = {
            "id": "test_006",
            "question": "Q?",
            "answer": "A",
            "context_turns": ["T1", "T2", "T3"],
            "competency": "AR",
            "metadata": {},
        }
        sample = record_to_sample(record)
        assert sample.metadata["num_turns"] == 3

    def test_handles_missing_metadata(self) -> None:
        """Should handle records with no metadata field."""
        record = {
            "id": "test_007",
            "question": "Q?",
            "answer": "A",
            "context_turns": [],
            "competency": "AR",
        }
        sample = record_to_sample(record)
        assert sample.metadata["dataset_source"] == "unknown"


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadMemoryagentbench:
    """Tests for load_memoryagentbench() function."""

    def test_loads_from_jsonl(self, mab_jsonl_file: Path) -> None:
        """Should load samples from JSONL file."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            samples = load_memoryagentbench(tier="smoke")
            assert len(samples) == 5  # All records (fewer than smoke count)
            assert all(isinstance(s, Sample) for s in samples)

    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when dataset missing."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(tmp_path / "nonexistent"),
        ):
            with pytest.raises(FileNotFoundError, match="MemoryAgentBench dataset not found"):
                load_memoryagentbench(tier="smoke")

    def test_returns_empty_for_zero_samples(self, mab_jsonl_file: Path) -> None:
        """Should return empty list when tier has 0 samples."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            with patch(
                "matric_eval.tasks.memoryagentbench.get_sample_count", return_value=0
            ):
                samples = load_memoryagentbench(tier="smoke")
                assert samples == []

    def test_reproducible_sampling(self, mab_jsonl_file: Path) -> None:
        """Should produce same samples with same seed."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            with patch(
                "matric_eval.tasks.memoryagentbench.get_sample_count", return_value=3
            ):
                samples_1 = load_memoryagentbench(tier="smoke")
                samples_2 = load_memoryagentbench(tier="smoke")
                assert [s.id for s in samples_1] == [s.id for s in samples_2]


# =============================================================================
# Competency Filtering Tests
# =============================================================================


@pytest.mark.unit
class TestCompetencyFiltering:
    """Tests for competency-based filtering in load_memoryagentbench()."""

    def test_filter_ar(self, mab_jsonl_file: Path) -> None:
        """Should return only AR competency samples."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            samples = load_memoryagentbench(tier="smoke", competency="AR")
            assert len(samples) == 2  # mab_001 and mab_005
            assert all(s.metadata["competency"] == "AR" for s in samples)

    def test_filter_ttl(self, mab_jsonl_file: Path) -> None:
        """Should return only TTL competency samples."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            samples = load_memoryagentbench(tier="smoke", competency="TTL")
            assert len(samples) == 1
            assert samples[0].metadata["competency"] == "TTL"

    def test_filter_lru(self, mab_jsonl_file: Path) -> None:
        """Should return only LRU competency samples."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            samples = load_memoryagentbench(tier="smoke", competency="LRU")
            assert len(samples) == 1
            assert samples[0].metadata["competency"] == "LRU"

    def test_filter_cr(self, mab_jsonl_file: Path) -> None:
        """Should return only CR competency samples."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            samples = load_memoryagentbench(tier="smoke", competency="CR")
            assert len(samples) == 1
            assert samples[0].metadata["competency"] == "CR"

    def test_filter_none_returns_all(self, mab_jsonl_file: Path) -> None:
        """Should return all competencies when filter is None."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            samples = load_memoryagentbench(tier="smoke", competency=None)
            competencies = {s.metadata["competency"] for s in samples}
            assert competencies == {"AR", "TTL", "LRU", "CR"}

    def test_invalid_competency_raises(self, mab_jsonl_file: Path) -> None:
        """Should raise ValueError for invalid competency."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            with pytest.raises(ValueError, match="Invalid competency"):
                load_memoryagentbench(tier="smoke", competency="INVALID")


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestMemoryagentbenchTask:
    """Tests for memoryagentbench() task definition."""

    def test_creates_task(self, mab_jsonl_file: Path) -> None:
        """Should create a valid Inspect AI Task."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            task = memoryagentbench(tier="smoke")
            assert isinstance(task, Task)

    def test_task_has_scorer(self, mab_jsonl_file: Path) -> None:
        """Should include match scorer."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            task = memoryagentbench(tier="smoke")
            assert task.scorer is not None

    def test_task_name_default(self, mab_jsonl_file: Path) -> None:
        """Should use default task name."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            task = memoryagentbench(tier="smoke")
            assert task.name == "memoryagentbench"

    def test_task_name_with_competency(self, mab_jsonl_file: Path) -> None:
        """Should include competency in task name."""
        with patch(
            "matric_eval.tasks.memoryagentbench.MEMORYAGENTBENCH_PATH",
            str(mab_jsonl_file),
        ):
            task = memoryagentbench(tier="smoke", competency="AR")
            assert "ar" in task.name


# =============================================================================
# Tier Configuration Tests
# =============================================================================


@pytest.mark.unit
class TestMemoryagentbenchTierConfig:
    """Tests for MemoryAgentBench tier configuration."""

    def test_smoke_tier_has_memoryagentbench(self) -> None:
        """Smoke tier should have MemoryAgentBench samples configured."""
        from matric_eval.config import get_tier
        tier = get_tier("smoke")
        assert tier.memoryagentbench > 0

    def test_full_tier_has_all_memoryagentbench(self) -> None:
        """Full tier should have 0 (meaning all samples)."""
        from matric_eval.config import get_tier
        tier = get_tier("full")
        assert tier.memoryagentbench == 0

    def test_quick_tier_has_memoryagentbench(self) -> None:
        """Quick tier should have MemoryAgentBench samples configured."""
        from matric_eval.config import get_tier
        tier = get_tier("quick")
        assert tier.memoryagentbench > 0

    def test_smoke_less_than_quick(self) -> None:
        """Smoke tier should have fewer samples than quick tier."""
        from matric_eval.config import get_tier
        smoke = get_tier("smoke")
        quick = get_tier("quick")
        assert smoke.memoryagentbench < quick.memoryagentbench
