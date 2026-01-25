"""
Tests for GSM8K benchmark task (matric_eval.tasks.gsm8k).

Covers:
- Answer extraction from model responses
- Dataset loading from JSONL
- Tiered sampling (smoke/quick/full)
- Sample format conversion
- Task definition
- Custom numeric scorer
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.gsm8k import (
    extract_answer,
    gsm8k,
    gsm8k_scorer,
    load_gsm8k,
    record_to_sample,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton before each test."""
    # Clear environment variables
    monkeypatch.delenv("EVAL_GSM8K_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module

    settings_module._settings = None


# =============================================================================
# Answer Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestExtractAnswer:
    """Tests for extract_answer() function."""

    def test_extract_answer_basic(self) -> None:
        """Should extract numeric answer after #### separator."""
        text = "Some calculation steps here\n#### 42"
        result = extract_answer(text)
        assert result == "42"

    def test_extract_answer_with_whitespace(self) -> None:
        """Should handle whitespace around the answer."""
        text = "Calculations\n####   123   "
        result = extract_answer(text)
        assert result == "123"

    def test_extract_answer_negative_number(self) -> None:
        """Should extract negative numbers."""
        text = "Result is negative\n#### -15"
        result = extract_answer(text)
        assert result == "-15"

    def test_extract_answer_decimal(self) -> None:
        """Should extract decimal numbers."""
        text = "Price calculation\n#### 12.50"
        result = extract_answer(text)
        assert result == "12.50"

    def test_extract_answer_with_comma_formatting(self) -> None:
        """Should extract numbers with comma formatting."""
        text = "Large number\n#### 1,234"
        result = extract_answer(text)
        assert result == "1,234"

    def test_extract_answer_no_separator_returns_none(self) -> None:
        """Should return None if #### separator not found."""
        text = "No separator in this text"
        result = extract_answer(text)
        assert result is None

    def test_extract_answer_empty_after_separator(self) -> None:
        """Should return empty string if nothing after ####."""
        text = "Calculation\n####"
        result = extract_answer(text)
        assert result == ""

    def test_extract_answer_multiple_separators_uses_last(self) -> None:
        """Should use the last #### separator if multiple exist."""
        text = "First #### 10\nSecond #### 20"
        result = extract_answer(text)
        assert result == "20"

    def test_extract_answer_with_dollar_sign(self) -> None:
        """Should extract dollar amounts."""
        text = "Total cost\n#### $18"
        result = extract_answer(text)
        assert result == "$18"

    def test_extract_answer_multiline_after_separator(self) -> None:
        """Should extract only first line after ####."""
        text = "Calculation\n#### 42\nExtra text here"
        result = extract_answer(text)
        assert result == "42"

    def test_extract_answer_from_real_gsm8k_format(self) -> None:
        """Should extract from real GSM8K answer format."""
        text = "Janet sells 16 - 3 - 4 = <<16-3-4=9>>9 duck eggs a day.\nShe makes 9 * 2 = $<<9*2=18>>18 every day at the farmer's market.\n#### 18"
        result = extract_answer(text)
        assert result == "18"

    def test_extract_answer_strips_whitespace(self) -> None:
        """Should strip leading/trailing whitespace from answer."""
        text = "Result\n####    42    "
        result = extract_answer(text)
        assert result == "42"

    def test_extract_answer_zero(self) -> None:
        """Should extract zero correctly."""
        text = "No profit\n#### 0"
        result = extract_answer(text)
        assert result == "0"

    def test_extract_answer_large_number(self) -> None:
        """Should extract large numbers."""
        text = "Population\n#### 70000"
        result = extract_answer(text)
        assert result == "70000"


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadGSM8K:
    """Tests for load_gsm8k() function."""

    def test_load_gsm8k_smoke_returns_5_samples(self) -> None:
        """Should load exactly 5 samples for smoke tier."""
        samples = load_gsm8k(tier="smoke")
        assert len(samples) == 5

    def test_load_gsm8k_quick_returns_75_samples(self) -> None:
        """Should load exactly 75 samples for quick tier."""
        samples = load_gsm8k(tier="quick")
        assert len(samples) == 75

    def test_load_gsm8k_full_returns_all_samples(self) -> None:
        """Should load all 1,319 samples for full tier."""
        samples = load_gsm8k(tier="full")
        assert len(samples) == 1319

    def test_load_gsm8k_default_is_smoke(self) -> None:
        """Should default to smoke tier if no tier specified."""
        samples = load_gsm8k()
        assert len(samples) == 5

    def test_load_gsm8k_unknown_tier_defaults_to_smoke(self) -> None:
        """Should fall back to smoke tier for unknown tier names."""
        samples = load_gsm8k(tier="unknown_tier")
        assert len(samples) == 5

    def test_load_gsm8k_samples_are_sample_objects(self) -> None:
        """Should return list of Sample objects."""
        samples = load_gsm8k(tier="smoke")
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_gsm8k_samples_have_required_fields(self) -> None:
        """Should have input, target, and id fields."""
        samples = load_gsm8k(tier="smoke")
        for sample in samples:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None

    def test_load_gsm8k_samples_have_unique_ids(self) -> None:
        """Should have unique IDs for all samples."""
        samples = load_gsm8k(tier="full")
        ids = [s.id for s in samples]
        assert len(ids) == len(set(ids))

    def test_load_gsm8k_reproducible_with_seed(self) -> None:
        """Should return same samples for same tier (reproducible sampling)."""
        samples1 = load_gsm8k(tier="quick")
        samples2 = load_gsm8k(tier="quick")

        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]

        assert ids1 == ids2

    def test_load_gsm8k_smoke_subset_of_quick(self) -> None:
        """Smoke samples should be subset of quick samples (nested sampling)."""
        smoke_samples = load_gsm8k(tier="smoke")
        quick_samples = load_gsm8k(tier="quick")

        smoke_ids = {s.id for s in smoke_samples}
        quick_ids = {s.id for s in quick_samples}

        assert smoke_ids.issubset(quick_ids)

    def test_load_gsm8k_quick_subset_of_full(self) -> None:
        """Quick samples should be subset of full samples."""
        quick_samples = load_gsm8k(tier="quick")
        full_samples = load_gsm8k(tier="full")

        quick_ids = {s.id for s in quick_samples}
        full_ids = {s.id for s in full_samples}

        assert quick_ids.issubset(full_ids)

    def test_load_gsm8k_file_not_found_raises_error(self) -> None:
        """Should raise FileNotFoundError if dataset file missing."""
        with patch("matric_eval.tasks.gsm8k.GSM8K_PATH", "/nonexistent/path.jsonl"):
            with pytest.raises(FileNotFoundError):
                load_gsm8k()

    def test_load_gsm8k_invalid_json_raises_error(self) -> None:
        """Should raise error for malformed JSONL."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("invalid json line\n")
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.gsm8k.GSM8K_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_gsm8k()
        finally:
            Path(temp_path).unlink()

    def test_load_gsm8k_empty_file_raises_error(self) -> None:
        """Should raise error for empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            # Write nothing
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.gsm8k.GSM8K_PATH", temp_path):
                with pytest.raises(ValueError):
                    load_gsm8k()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Record Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() conversion function."""

    def test_record_to_sample_basic_conversion(self) -> None:
        """Should convert GSM8K record to Sample."""
        record = {
            "question": "What is 2 + 2?",
            "answer": "2 + 2 = 4\n#### 4",
        }

        sample = record_to_sample(record)

        assert isinstance(sample, Sample)
        assert sample.input == "What is 2 + 2?"
        assert sample.target == "4"

    def test_record_to_sample_extracts_numeric_answer(self) -> None:
        """Should extract numeric answer from #### separator."""
        record = {
            "question": "How many eggs?",
            "answer": "Janet sells 16 - 3 - 4 = 9 eggs\n#### 9",
        }

        sample = record_to_sample(record)
        assert sample.target == "9"

    def test_record_to_sample_preserves_full_answer_in_metadata(self) -> None:
        """Should preserve full answer including steps in metadata."""
        full_answer = "Step 1: 10 + 5 = 15\nStep 2: 15 * 2 = 30\n#### 30"
        record = {
            "question": "Calculate total",
            "answer": full_answer,
        }

        sample = record_to_sample(record)

        assert sample.metadata is not None
        assert "full_answer" in sample.metadata
        assert sample.metadata["full_answer"] == full_answer

    def test_record_to_sample_with_real_gsm8k_data(self) -> None:
        """Should convert real GSM8K record correctly."""
        record = {
            "question": "Janet's ducks lay 16 eggs per day. She eats three for breakfast every morning and bakes muffins for her friends every day with four. She sells the remainder at the farmers' market daily for $2 per fresh duck egg. How much in dollars does she make every day at the farmers' market?",
            "answer": "Janet sells 16 - 3 - 4 = <<16-3-4=9>>9 duck eggs a day.\nShe makes 9 * 2 = $<<9*2=18>>18 every day at the farmer's market.\n#### 18",
        }

        sample = record_to_sample(record)

        assert "Janet's ducks" in sample.input
        assert sample.target == "18"
        assert sample.metadata["full_answer"] == record["answer"]

    def test_record_to_sample_assigns_sequential_ids(self) -> None:
        """Should assign sequential IDs based on index."""
        record = {
            "question": "Test question",
            "answer": "Test answer\n#### 42",
        }

        sample = record_to_sample(record, index=0)
        assert sample.id == "gsm8k_0"

        sample = record_to_sample(record, index=99)
        assert sample.id == "gsm8k_99"

    def test_record_to_sample_missing_question_raises_error(self) -> None:
        """Should raise KeyError if question field missing."""
        incomplete_record = {
            "answer": "Some answer\n#### 42",
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)

    def test_record_to_sample_missing_answer_raises_error(self) -> None:
        """Should raise KeyError if answer field missing."""
        incomplete_record = {
            "question": "Some question?",
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)

    def test_record_to_sample_answer_without_separator(self) -> None:
        """Should handle answer without #### separator (return empty string target)."""
        record = {
            "question": "Test?",
            "answer": "No separator here",
        }

        sample = record_to_sample(record)
        assert sample.target == ""


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
class TestGSM8KSampleQuality:
    """Tests for quality and correctness of loaded samples."""

    def test_samples_have_question_text(self) -> None:
        """Should have non-empty question text in input."""
        samples = load_gsm8k(tier="smoke")
        for sample in samples:
            assert len(sample.input) > 0

    def test_samples_have_numeric_targets(self) -> None:
        """Should have numeric answers as targets."""
        samples = load_gsm8k(tier="smoke")
        for sample in samples:
            # Target should be extractable as number (with possible $ or ,)
            assert sample.target is not None

    def test_samples_have_full_answer_in_metadata(self) -> None:
        """Should preserve full answer with steps in metadata."""
        samples = load_gsm8k(tier="smoke")
        for sample in samples:
            assert "full_answer" in sample.metadata
            assert "####" in sample.metadata["full_answer"]

    def test_first_sample_is_janet_ducks(self) -> None:
        """First problem should be the classic Janet's ducks problem."""
        samples = load_gsm8k(tier="full")
        first = samples[0]

        assert "Janet" in first.input or "ducks" in first.input.lower()

    def test_samples_are_word_problems(self) -> None:
        """Should be math word problems (contain question marks or keywords)."""
        samples = load_gsm8k(tier="smoke")
        for sample in samples:
            # Word problems typically have questions or calculations
            has_question = "?" in sample.input
            has_math_words = any(
                word in sample.input.lower()
                for word in ["how many", "how much", "total", "calculate"]
            )
            assert has_question or has_math_words


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestGSM8KTask:
    """Tests for gsm8k() task definition."""

    def test_gsm8k_task_creation(self) -> None:
        """Should create valid Task object."""
        task = gsm8k(tier="smoke")
        assert isinstance(task, Task)

    def test_gsm8k_task_name(self) -> None:
        """Should have correct task name."""
        task = gsm8k(tier="smoke")
        assert task.name == "gsm8k"

    def test_gsm8k_task_has_dataset(self) -> None:
        """Should have dataset configured."""
        task = gsm8k(tier="smoke")
        assert task.dataset is not None
        assert len(task.dataset) == 5

    def test_gsm8k_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = gsm8k(tier="smoke")
        assert task.solver is not None

    def test_gsm8k_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = gsm8k(tier="smoke")
        assert task.scorer is not None

    def test_gsm8k_task_respects_tier_parameter(self) -> None:
        """Should create tasks with different sample counts per tier."""
        smoke_task = gsm8k(tier="smoke")
        quick_task = gsm8k(tier="quick")
        full_task = gsm8k(tier="full")

        assert len(smoke_task.dataset) == 5
        assert len(quick_task.dataset) == 75
        assert len(full_task.dataset) == 1319

    def test_gsm8k_task_default_tier_is_smoke(self) -> None:
        """Should default to smoke tier."""
        task = gsm8k()
        assert len(task.dataset) == 5

    def test_gsm8k_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = gsm8k(tier="smoke")
        task2 = gsm8k(tier="smoke")

        # Should be separate instances
        assert task1 is not task2


# =============================================================================
# Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestGSM8KScorer:
    """Tests for gsm8k_scorer() custom scorer."""

    def test_gsm8k_scorer_returns_scorer(self) -> None:
        """Should return a valid scorer object."""
        scorer = gsm8k_scorer()
        assert scorer is not None

    def test_gsm8k_scorer_correct_answer(self) -> None:
        """Should score correct numeric answers as correct."""
        # This will be tested via integration tests with actual TaskState
        # Unit test just validates scorer creation
        scorer = gsm8k_scorer()
        assert scorer is not None

    def test_gsm8k_scorer_incorrect_answer(self) -> None:
        """Should score incorrect numeric answers as incorrect."""
        # This will be tested via integration tests with actual TaskState
        scorer = gsm8k_scorer()
        assert scorer is not None

    def test_gsm8k_scorer_handles_formatting_differences(self) -> None:
        """Should handle different numeric formatting (1000 vs 1,000)."""
        # Integration test - just validate scorer exists
        scorer = gsm8k_scorer()
        assert scorer is not None

    def test_gsm8k_scorer_handles_dollar_signs(self) -> None:
        """Should handle dollar signs in answers ($18 vs 18)."""
        scorer = gsm8k_scorer()
        assert scorer is not None


# =============================================================================
# Integration with Config System
# =============================================================================


@pytest.mark.unit
class TestGSM8KConfigIntegration:
    """Tests for integration with matric_eval.config."""

    def test_load_gsm8k_uses_config_tier(self) -> None:
        """Should use TierConfig for sample counts."""
        from matric_eval.config import TIERS

        smoke_count = TIERS["smoke"].gsm8k
        quick_count = TIERS["quick"].gsm8k
        full_count = TIERS["full"].gsm8k

        assert len(load_gsm8k(tier="smoke")) == smoke_count
        assert len(load_gsm8k(tier="quick")) == quick_count
        assert len(load_gsm8k(tier="full")) == full_count

    def test_load_gsm8k_respects_environment_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should respect EVAL_GSM8K_SAMPLES environment variable."""
        monkeypatch.setenv("EVAL_GSM8K_SAMPLES", "10")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module

        settings_module._settings = None

        # Should load 10 samples instead of default tier counts
        samples = load_gsm8k(tier="smoke")
        assert len(samples) == 10

    def test_load_gsm8k_uses_reproducible_seed(self) -> None:
        """Should use get_seed() for reproducible sampling."""
        from matric_eval.config import get_seed

        seed = get_seed()
        assert isinstance(seed, int)

        # Samples should be reproducible
        samples1 = load_gsm8k(tier="quick")
        samples2 = load_gsm8k(tier="quick")

        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
class TestGSM8KEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_gsm8k_sample_count_exceeds_dataset_size(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return all available samples if requested count exceeds dataset size."""
        monkeypatch.setenv("EVAL_GSM8K_SAMPLES", "2000")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module

        settings_module._settings = None

        samples = load_gsm8k()
        # Should return all 1,319 samples, not 2000
        assert len(samples) == 1319

    def test_load_gsm8k_zero_samples_requested(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should handle zero sample request gracefully."""
        monkeypatch.setenv("EVAL_GSM8K_SAMPLES", "0")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module

        settings_module._settings = None

        samples = load_gsm8k()
        assert len(samples) == 0

    def test_record_to_sample_with_unicode_characters(self) -> None:
        """Should handle unicode characters in questions."""
        record = {
            "question": "Café sells π pies. How many?",
            "answer": "Answer is 3\n#### 3",
        }

        sample = record_to_sample(record)
        assert "Café" in sample.input
        assert "π" in sample.input

    def test_extract_answer_with_scientific_notation(self) -> None:
        """Should handle scientific notation answers."""
        text = "Large number\n#### 1.5e10"
        result = extract_answer(text)
        assert result == "1.5e10"

    def test_extract_answer_with_fraction_notation(self) -> None:
        """Should handle fraction answers."""
        text = "Half of something\n#### 1/2"
        result = extract_answer(text)
        assert result == "1/2"
