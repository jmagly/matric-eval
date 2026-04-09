"""
Tests for GPQA (Graduate-Level Q&A) benchmark task (matric_eval.tasks.gpqa).

Covers:
- Prompt formatting for multiple-choice science questions
- Sample conversion from different record formats
- Dataset loading with tiered sampling
- Task definition
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.gpqa import (
    ANSWER_LETTERS,
    format_gpqa_prompt,
    gpqa,
    load_gpqa,
    record_to_sample,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton."""
    monkeypatch.delenv("EVAL_GPQA_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    import matric_eval.config.settings as settings_module
    settings_module._settings = None


@pytest.fixture
def sample_records() -> list[dict]:
    """Create sample GPQA records in JSONL format."""
    return [
        {
            "id": "gpqa_001",
            "question": "What is the ground state electron configuration of nitrogen?",
            "choices": ["1s2 2s2 2p3", "1s2 2s2 2p2", "1s2 2s2 2p4", "1s2 2s2 2p1"],
            "answer": "A",
            "domain": "chemistry",
            "subdomain": "atomic structure",
        },
        {
            "id": "gpqa_002",
            "question": "In quantum mechanics, which operator corresponds to the observable of momentum?",
            "choices": ["-ih_bar d/dx", "ih_bar d/dx", "x", "d^2/dx^2"],
            "answer": "A",
            "domain": "physics",
            "subdomain": "quantum mechanics",
        },
        {
            "id": "gpqa_003",
            "question": "Which enzyme catalyzes the first committed step of glycolysis?",
            "choices": ["Phosphofructokinase-1", "Hexokinase", "Pyruvate kinase", "Aldolase"],
            "answer": "A",
            "domain": "biology",
            "subdomain": "biochemistry",
        },
    ]


@pytest.fixture
def gpqa_jsonl_file(sample_records: list[dict], tmp_path: Path) -> Path:
    """Create a temporary GPQA JSONL file."""
    gpqa_dir = tmp_path / "gpqa"
    gpqa_dir.mkdir()
    jsonl_file = gpqa_dir / "gpqa_diamond.jsonl"
    with open(jsonl_file, "w") as f:
        for record in sample_records:
            f.write(json.dumps(record) + "\n")
    return gpqa_dir


# =============================================================================
# Prompt Formatting Tests
# =============================================================================


@pytest.mark.unit
class TestFormatGpqaPrompt:
    """Tests for format_gpqa_prompt() function."""

    def test_includes_question(self) -> None:
        """Should include the question text."""
        prompt = format_gpqa_prompt(
            "What is the speed of light?",
            ["3e8 m/s", "3e6 m/s", "3e10 m/s", "3e4 m/s"],
        )
        assert "What is the speed of light?" in prompt

    def test_includes_all_choices(self) -> None:
        """Should include all answer choices with labels."""
        choices = ["Option 1", "Option 2", "Option 3", "Option 4"]
        prompt = format_gpqa_prompt("Question?", choices)
        assert "A)" in prompt
        assert "B)" in prompt
        assert "C)" in prompt
        assert "D)" in prompt
        assert "Option 1" in prompt
        assert "Option 4" in prompt

    def test_includes_instruction(self) -> None:
        """Should include answer instruction."""
        prompt = format_gpqa_prompt("Q?", ["A", "B", "C", "D"])
        assert "Answer" in prompt

    def test_includes_science_context(self) -> None:
        """Should mention graduate-level science context."""
        prompt = format_gpqa_prompt("Q?", ["A", "B", "C", "D"])
        assert "graduate-level" in prompt.lower() or "science" in prompt.lower()


# =============================================================================
# Record to Sample Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() function."""

    def test_converts_jsonl_format(self) -> None:
        """Should convert JSONL format with choices list."""
        record = {
            "id": "test_001",
            "question": "What is entropy?",
            "choices": ["Disorder measure", "Energy", "Temperature", "Pressure"],
            "answer": "A",
            "domain": "physics",
        }
        sample = record_to_sample(record)
        assert isinstance(sample, Sample)
        assert "entropy" in sample.input.lower()
        assert sample.target == "A"
        assert sample.id == "test_001"

    def test_converts_huggingface_format(self) -> None:
        """Should convert HuggingFace format with separate correct/incorrect answers."""
        record = {
            "Question": "What is the Higgs boson?",
            "Correct Answer": "A scalar boson",
            "Incorrect Answer 1": "A fermion",
            "Incorrect Answer 2": "A photon",
            "Incorrect Answer 3": "A gluon",
            "High-level domain": "physics",
            "Subdomain": "particle physics",
        }
        sample = record_to_sample(record)
        assert isinstance(sample, Sample)
        assert "Higgs" in sample.input
        assert sample.target in ANSWER_LETTERS

    def test_preserves_domain_metadata(self) -> None:
        """Should include domain in metadata."""
        record = {
            "id": "test_002",
            "question": "Q?",
            "choices": ["A", "B", "C", "D"],
            "answer": "B",
            "domain": "chemistry",
            "subdomain": "organic",
        }
        sample = record_to_sample(record)
        assert sample.metadata["domain"] == "chemistry"
        assert sample.metadata["subdomain"] == "organic"

    def test_raises_on_unknown_format(self) -> None:
        """Should raise KeyError for unrecognized format."""
        with pytest.raises(KeyError, match="Unrecognized GPQA record format"):
            record_to_sample({"unknown_field": "value"})


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadGpqa:
    """Tests for load_gpqa() function."""

    def test_loads_from_jsonl(self, gpqa_jsonl_file: Path) -> None:
        """Should load samples from JSONL file."""
        with patch("matric_eval.tasks.gpqa.GPQA_PATH", str(gpqa_jsonl_file)):
            samples = load_gpqa(tier="smoke")
            assert len(samples) == 3  # All records (fewer than smoke count)
            assert all(isinstance(s, Sample) for s in samples)

    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when dataset missing."""
        with patch("matric_eval.tasks.gpqa.GPQA_PATH", str(tmp_path / "nonexistent")):
            with pytest.raises(FileNotFoundError, match="GPQA dataset not found"):
                load_gpqa(tier="smoke")

    def test_returns_empty_for_zero_samples(self, gpqa_jsonl_file: Path) -> None:
        """Should return empty list when tier has 0 samples."""
        with patch("matric_eval.tasks.gpqa.GPQA_PATH", str(gpqa_jsonl_file)):
            with patch("matric_eval.tasks.gpqa.get_sample_count", return_value=0):
                samples = load_gpqa(tier="smoke")
                assert samples == []

    def test_reproducible_sampling(self, gpqa_jsonl_file: Path) -> None:
        """Should produce same samples with same seed."""
        with patch("matric_eval.tasks.gpqa.GPQA_PATH", str(gpqa_jsonl_file)):
            with patch("matric_eval.tasks.gpqa.get_sample_count", return_value=2):
                samples_1 = load_gpqa(tier="smoke")
                samples_2 = load_gpqa(tier="smoke")
                assert [s.id for s in samples_1] == [s.id for s in samples_2]


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestGpqaTask:
    """Tests for gpqa() task definition."""

    def test_creates_task(self, gpqa_jsonl_file: Path) -> None:
        """Should create a valid Inspect AI Task."""
        with patch("matric_eval.tasks.gpqa.GPQA_PATH", str(gpqa_jsonl_file)):
            task = gpqa(tier="smoke")
            assert isinstance(task, Task)

    def test_task_has_scorer(self, gpqa_jsonl_file: Path) -> None:
        """Should include match scorer for multiple choice."""
        with patch("matric_eval.tasks.gpqa.GPQA_PATH", str(gpqa_jsonl_file)):
            task = gpqa(tier="smoke")
            assert task.scorer is not None

    def test_task_name_includes_subset(self, gpqa_jsonl_file: Path) -> None:
        """Should name task with subset."""
        with patch("matric_eval.tasks.gpqa.GPQA_PATH", str(gpqa_jsonl_file)):
            task = gpqa(tier="smoke", subset="diamond")
            assert "diamond" in task.name


# =============================================================================
# Tier Configuration Tests
# =============================================================================


@pytest.mark.unit
class TestGpqaTierConfig:
    """Tests for GPQA tier configuration."""

    def test_smoke_tier_has_gpqa(self) -> None:
        """Smoke tier should have GPQA samples configured."""
        from matric_eval.config import get_tier
        tier = get_tier("smoke")
        assert tier.gpqa > 0

    def test_full_tier_has_all_gpqa(self) -> None:
        """Full tier should have all 198 Diamond questions."""
        from matric_eval.config import get_tier
        tier = get_tier("full")
        assert tier.gpqa == 198

    def test_quick_tier_has_gpqa(self) -> None:
        """Quick tier should have GPQA samples configured."""
        from matric_eval.config import get_tier
        tier = get_tier("quick")
        assert tier.gpqa > 0
