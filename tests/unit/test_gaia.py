"""
Tests for GAIA benchmark task (matric_eval.tasks.gaia).

Covers:
- Answer normalization
- Answer extraction from model responses
- Sample conversion
- Dataset loading
- Scorer logic (exact match + partial credit)
- Task definition
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target

from matric_eval.tasks.gaia import (
    _extract_final_answer,
    gaia,
    gaia_scorer,
    load_gaia,
    normalize_answer,
    record_to_sample,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean environment and reset settings singleton."""
    monkeypatch.delenv("EVAL_GAIA_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)
    import matric_eval.config.settings as settings_module
    settings_module._settings = None


@pytest.fixture
def sample_records() -> list[dict]:
    """Create sample GAIA records."""
    return [
        {
            "task_id": "gaia_001",
            "Question": "What is the capital of France?",
            "Final answer": "Paris",
            "Level": 1,
        },
        {
            "task_id": "gaia_002",
            "Question": "How many planets are in our solar system?",
            "Final answer": "8",
            "Level": 1,
        },
        {
            "task_id": "gaia_003",
            "Question": "What year was the Eiffel Tower completed?",
            "Final answer": "1889",
            "Level": 2,
        },
    ]


@pytest.fixture
def gaia_jsonl_file(sample_records: list[dict], tmp_path: Path) -> Path:
    """Create a temporary GAIA JSONL file."""
    data_dir = tmp_path / "gaia"
    data_dir.mkdir()
    jsonl_file = data_dir / "gaia.jsonl"
    with open(jsonl_file, "w") as f:
        for record in sample_records:
            f.write(json.dumps(record) + "\n")
    return data_dir


# =============================================================================
# Normalization Tests
# =============================================================================


@pytest.mark.unit
class TestNormalizeAnswer:
    """Tests for normalize_answer() function."""

    def test_strips_whitespace(self) -> None:
        """Should strip leading/trailing whitespace."""
        assert normalize_answer("  Paris  ") == "paris"

    def test_lowercases(self) -> None:
        """Should lowercase."""
        assert normalize_answer("PARIS") == "paris"

    def test_removes_articles(self) -> None:
        """Should remove leading articles."""
        assert normalize_answer("the Eiffel Tower") == "eiffel tower"
        assert normalize_answer("a dog") == "dog"
        assert normalize_answer("an apple") == "apple"

    def test_removes_trailing_punctuation(self) -> None:
        """Should remove trailing punctuation."""
        assert normalize_answer("Paris.") == "paris"
        assert normalize_answer("1889!") == "1889"

    def test_collapses_whitespace(self) -> None:
        """Should collapse multiple spaces."""
        assert normalize_answer("New   York   City") == "new york city"


# =============================================================================
# Answer Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestExtractFinalAnswer:
    """Tests for _extract_final_answer() function."""

    def test_extracts_explicit_answer(self) -> None:
        """Should extract 'answer: X' format."""
        response = "After analysis, the answer: Paris"
        assert _extract_final_answer(response).strip() == "Paris"

    def test_extracts_final_answer_label(self) -> None:
        """Should extract 'Final answer: X' format."""
        response = "The capital is in France.\nFinal answer: Paris"
        assert _extract_final_answer(response).strip() == "Paris"

    def test_extracts_bold_text(self) -> None:
        """Should extract **bold** as the answer."""
        response = "The answer is **Paris**"
        assert _extract_final_answer(response).strip() == "Paris"

    def test_falls_back_to_last_line(self) -> None:
        """Should use last line as fallback."""
        response = "Let me think about this.\nIt's a European capital.\nParis"
        assert _extract_final_answer(response).strip() == "Paris"

    def test_handles_single_line(self) -> None:
        """Should handle single-line response."""
        assert _extract_final_answer("42").strip() == "42"


# =============================================================================
# Record to Sample Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() function."""

    def test_converts_standard_format(self) -> None:
        """Should convert GAIA record to Sample."""
        record = {
            "task_id": "test_001",
            "Question": "What color is the sky?",
            "Final answer": "blue",
            "Level": 1,
        }
        sample = record_to_sample(record)
        assert isinstance(sample, Sample)
        assert "sky" in sample.input
        assert sample.target == "blue"
        assert sample.metadata["level"] == 1

    def test_preserves_level_metadata(self) -> None:
        """Should preserve difficulty level."""
        record = {
            "Question": "Complex question",
            "Final answer": "42",
            "Level": 3,
        }
        sample = record_to_sample(record)
        assert sample.metadata["level"] == 3
        assert sample.metadata["level_name"] == "complex"


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadGaia:
    """Tests for load_gaia() function."""

    def test_loads_from_jsonl(self, gaia_jsonl_file: Path) -> None:
        """Should load samples from JSONL."""
        with patch("matric_eval.tasks.gaia.GAIA_PATH", str(gaia_jsonl_file)):
            samples = load_gaia(tier="smoke")
            assert len(samples) == 3
            assert all(isinstance(s, Sample) for s in samples)

    def test_filters_by_level(self, gaia_jsonl_file: Path) -> None:
        """Should filter by difficulty level."""
        with patch("matric_eval.tasks.gaia.GAIA_PATH", str(gaia_jsonl_file)):
            samples = load_gaia(tier="smoke", levels=[1])
            assert len(samples) == 2  # Only level 1 questions
            assert all(s.metadata["level"] == 1 for s in samples)

    def test_raises_when_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when dataset missing."""
        with patch("matric_eval.tasks.gaia.GAIA_PATH", str(tmp_path / "nope")):
            with pytest.raises(FileNotFoundError):
                load_gaia(tier="smoke")

    def test_returns_empty_for_zero(self, gaia_jsonl_file: Path) -> None:
        """Should return empty for zero samples."""
        with patch("matric_eval.tasks.gaia.GAIA_PATH", str(gaia_jsonl_file)):
            with patch("matric_eval.tasks.gaia.get_sample_count", return_value=0):
                assert load_gaia(tier="smoke") == []


# =============================================================================
# Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestGaiaScorer:
    """Tests for gaia_scorer()."""

    def test_returns_callable(self) -> None:
        """Should return callable scorer."""
        scorer = gaia_scorer()
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_exact_match_scores_1(self) -> None:
        """Should score 1.0 for exact match."""
        scorer = gaia_scorer()

        state = Mock()
        state.output.completion = "Paris"
        state.metadata = {"level": 1}

        target = Target(target="Paris")
        score = await scorer(state, target)
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self) -> None:
        """Should match case-insensitively."""
        scorer = gaia_scorer()

        state = Mock()
        state.output.completion = "paris"
        state.metadata = {"level": 1}

        target = Target(target="Paris")
        score = await scorer(state, target)
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_partial_credit_for_contained(self) -> None:
        """Should give 0.5 for answer contained in response."""
        scorer = gaia_scorer()

        state = Mock()
        state.output.completion = "The answer is Paris, which is the capital of France."
        state.metadata = {"level": 1}

        target = Target(target="Paris")
        score = await scorer(state, target)
        assert score.value >= 0.5

    @pytest.mark.asyncio
    async def test_no_match_scores_0(self) -> None:
        """Should score 0.0 for wrong answer."""
        scorer = gaia_scorer()

        state = Mock()
        state.output.completion = "London"
        state.metadata = {"level": 1}

        target = Target(target="Paris")
        score = await scorer(state, target)
        assert score.value == 0.0

    @pytest.mark.asyncio
    async def test_extracts_answer_from_explanation(self) -> None:
        """Should extract answer from verbose response."""
        scorer = gaia_scorer()

        state = Mock()
        state.output.completion = "After careful consideration, I believe the answer: 1889"
        state.metadata = {"level": 2}

        target = Target(target="1889")
        score = await scorer(state, target)
        assert score.value == 1.0


# =============================================================================
# Task Tests
# =============================================================================


@pytest.mark.unit
class TestGaiaTask:
    """Tests for gaia() task definition."""

    def test_creates_task(self, gaia_jsonl_file: Path) -> None:
        """Should create a valid Task."""
        with patch("matric_eval.tasks.gaia.GAIA_PATH", str(gaia_jsonl_file)):
            task = gaia(tier="smoke")
            assert isinstance(task, Task)

    def test_task_has_name(self, gaia_jsonl_file: Path) -> None:
        """Should have 'gaia' in task name."""
        with patch("matric_eval.tasks.gaia.GAIA_PATH", str(gaia_jsonl_file)):
            task = gaia(tier="smoke")
            assert "gaia" in task.name


# =============================================================================
# Tier Config Tests
# =============================================================================


@pytest.mark.unit
class TestGaiaTierConfig:
    """Tests for GAIA tier configuration."""

    def test_smoke_tier_configured(self) -> None:
        """Should have gaia in smoke tier."""
        from matric_eval.config import get_tier
        tier = get_tier("smoke")
        assert tier.gaia > 0

    def test_full_tier_configured(self) -> None:
        """Should have gaia in full tier."""
        from matric_eval.config import get_tier
        tier = get_tier("full")
        assert tier.gaia == 466
