"""
Tests for ARC (AI2 Reasoning Challenge) benchmark task (matric_eval.tasks.arc).

Covers:
- Dataset loading from JSONL
- Tiered sampling (smoke/quick/full)
- Sample format conversion
- Multiple choice prompt formatting
- Task definition
- Scorer configuration
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.arc import (
    arc,
    format_arc_prompt,
    load_arc,
    record_to_sample,
)

# Import skip marker for tests requiring external data
from tests.conftest import requires_arc_data


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton before each test."""
    # Clear environment variables
    monkeypatch.delenv("EVAL_ARC_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module
    settings_module._settings = None


# =============================================================================
# Prompt Formatting Tests
# =============================================================================


@pytest.mark.unit
class TestFormatArcPrompt:
    """Tests for format_arc_prompt() function."""

    def test_format_arc_prompt_basic_structure(self) -> None:
        """Should format question with choices in A/B/C/D format."""
        question = "Which is heavier?"
        choices = [
            {"text": "Feather", "label": "A"},
            {"text": "Brick", "label": "B"},
            {"text": "Paper", "label": "C"},
            {"text": "Leaf", "label": "D"},
        ]

        prompt = format_arc_prompt(question, choices)

        assert "Which is heavier?" in prompt
        assert "A)" in prompt
        assert "B)" in prompt
        assert "C)" in prompt
        assert "D)" in prompt
        assert "Feather" in prompt
        assert "Brick" in prompt

    def test_format_arc_prompt_includes_answer_line(self) -> None:
        """Should include 'Answer:' prompt at the end."""
        question = "What color is the sky?"
        choices = [
            {"text": "Blue", "label": "A"},
            {"text": "Green", "label": "B"},
            {"text": "Red", "label": "C"},
            {"text": "Yellow", "label": "D"},
        ]

        prompt = format_arc_prompt(question, choices)

        assert prompt.endswith("Answer:")

    def test_format_arc_prompt_preserves_choice_order(self) -> None:
        """Should preserve the order of choices A, B, C, D."""
        question = "Test question?"
        choices = [
            {"text": "First", "label": "A"},
            {"text": "Second", "label": "B"},
            {"text": "Third", "label": "C"},
            {"text": "Fourth", "label": "D"},
        ]

        prompt = format_arc_prompt(question, choices)

        # Verify order by checking positions
        a_pos = prompt.index("A)")
        b_pos = prompt.index("B)")
        c_pos = prompt.index("C)")
        d_pos = prompt.index("D)")

        assert a_pos < b_pos < c_pos < d_pos

    def test_format_arc_prompt_with_long_question(self) -> None:
        """Should handle long, complex questions."""
        question = (
            "An astronomer observes that a planet rotates faster after a meteorite impact. "
            "Which is the most likely effect of this increase in rotation?"
        )
        choices = [
            {"text": "Planetary density will decrease.", "label": "A"},
            {"text": "Planetary years will become longer.", "label": "B"},
            {"text": "Planetary days will become shorter.", "label": "C"},
            {"text": "Planetary gravity will become stronger.", "label": "D"},
        ]

        prompt = format_arc_prompt(question, choices)

        assert "astronomer observes" in prompt
        assert "meteorite impact" in prompt
        assert all(choice["text"] in prompt for choice in choices)

    def test_format_arc_prompt_question_header(self) -> None:
        """Should include 'Question:' header."""
        question = "What is 2+2?"
        choices = [
            {"text": "3", "label": "A"},
            {"text": "4", "label": "B"},
            {"text": "5", "label": "C"},
            {"text": "6", "label": "D"},
        ]

        prompt = format_arc_prompt(question, choices)

        assert prompt.startswith("Question:")

    def test_format_arc_prompt_choice_formatting(self) -> None:
        """Should format each choice as 'LABEL) TEXT'."""
        question = "Pick one"
        choices = [
            {"text": "Option Alpha", "label": "A"},
            {"text": "Option Beta", "label": "B"},
            {"text": "Option Gamma", "label": "C"},
            {"text": "Option Delta", "label": "D"},
        ]

        prompt = format_arc_prompt(question, choices)

        assert "A) Option Alpha" in prompt
        assert "B) Option Beta" in prompt
        assert "C) Option Gamma" in prompt
        assert "D) Option Delta" in prompt

    def test_format_arc_prompt_with_fewer_choices(self) -> None:
        """Should handle questions with fewer than 4 choices."""
        question = "True or false?"
        choices = [
            {"text": "True", "label": "A"},
            {"text": "False", "label": "B"},
        ]

        prompt = format_arc_prompt(question, choices)

        assert "A) True" in prompt
        assert "B) False" in prompt
        assert "C)" not in prompt


# =============================================================================
# Record Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() conversion function."""

    def test_record_to_sample_basic_conversion(self) -> None:
        """Should convert ARC record to Sample."""
        record = {
            "id": "Mercury_7175875",
            "question": {
                "stem": "Which is heavier?",
                "choices": [
                    {"text": "Feather", "label": "A"},
                    {"text": "Brick", "label": "B"},
                    {"text": "Paper", "label": "C"},
                    {"text": "Leaf", "label": "D"},
                ],
            },
            "answerKey": "B",
        }

        sample = record_to_sample(record)

        assert isinstance(sample, Sample)
        assert sample.id == "Mercury_7175875"

    def test_record_to_sample_includes_formatted_prompt(self) -> None:
        """Should use formatted prompt as input."""
        record = {
            "id": "Mercury_123",
            "question": {
                "stem": "What color is grass?",
                "choices": [
                    {"text": "Green", "label": "A"},
                    {"text": "Blue", "label": "B"},
                    {"text": "Red", "label": "C"},
                    {"text": "Yellow", "label": "D"},
                ],
            },
            "answerKey": "A",
        }

        sample = record_to_sample(record)

        assert "Question:" in sample.input
        assert "What color is grass?" in sample.input
        assert "A) Green" in sample.input
        assert "Answer:" in sample.input

    def test_record_to_sample_includes_answer_key_as_target(self) -> None:
        """Should use answerKey as target."""
        record = {
            "id": "Mercury_123",
            "question": {
                "stem": "Pick B",
                "choices": [
                    {"text": "Wrong", "label": "A"},
                    {"text": "Correct", "label": "B"},
                    {"text": "Wrong", "label": "C"},
                    {"text": "Wrong", "label": "D"},
                ],
            },
            "answerKey": "B",
        }

        sample = record_to_sample(record)

        assert sample.target == "B"

    def test_record_to_sample_includes_metadata(self) -> None:
        """Should include question stem and choices in metadata."""
        record = {
            "id": "Mercury_456",
            "question": {
                "stem": "Test question",
                "choices": [
                    {"text": "A1", "label": "A"},
                    {"text": "A2", "label": "B"},
                ],
            },
            "answerKey": "A",
        }

        sample = record_to_sample(record)

        assert sample.metadata is not None
        assert "question_stem" in sample.metadata
        assert sample.metadata["question_stem"] == "Test question"
        assert "choices" in sample.metadata
        assert len(sample.metadata["choices"]) == 2

    def test_record_to_sample_preserves_all_choices(self) -> None:
        """Should preserve all choice information in metadata."""
        choices = [
            {"text": "First choice", "label": "A"},
            {"text": "Second choice", "label": "B"},
            {"text": "Third choice", "label": "C"},
            {"text": "Fourth choice", "label": "D"},
        ]
        record = {
            "id": "Test_001",
            "question": {"stem": "Question", "choices": choices},
            "answerKey": "C",
        }

        sample = record_to_sample(record)

        assert sample.metadata["choices"] == choices

    def test_record_to_sample_missing_required_field_raises_error(self) -> None:
        """Should raise KeyError if required field missing."""
        incomplete_record = {
            "id": "Test_001",
            "question": {
                "stem": "Question?",
                # Missing choices
            },
            "answerKey": "A",
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
@requires_arc_data
class TestLoadArc:
    """Tests for load_arc() function."""

    def test_load_arc_smoke_returns_5_samples(self) -> None:
        """Should load exactly 5 samples for smoke tier."""
        samples = load_arc(tier="smoke")
        assert len(samples) == 5

    def test_load_arc_quick_returns_75_samples(self) -> None:
        """Should load exactly 75 samples for quick tier."""
        samples = load_arc(tier="quick")
        assert len(samples) == 75

    def test_load_arc_full_returns_all_samples(self) -> None:
        """Should load all 1,172 samples for full tier."""
        samples = load_arc(tier="full")
        assert len(samples) == 1172

    def test_load_arc_default_is_smoke(self) -> None:
        """Should default to smoke tier if no tier specified."""
        samples = load_arc()
        assert len(samples) == 5

    def test_load_arc_unknown_tier_defaults_to_smoke(self) -> None:
        """Should fall back to smoke tier for unknown tier names."""
        samples = load_arc(tier="unknown_tier")
        assert len(samples) == 5

    def test_load_arc_samples_are_sample_objects(self) -> None:
        """Should return list of Sample objects."""
        samples = load_arc(tier="smoke")
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_arc_samples_have_required_fields(self) -> None:
        """Should have input, target, id, and metadata fields."""
        samples = load_arc(tier="smoke")
        for sample in samples:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert sample.metadata is not None

    def test_load_arc_samples_have_unique_ids(self) -> None:
        """Should have unique IDs for all samples."""
        samples = load_arc(tier="full")
        ids = [s.id for s in samples]
        assert len(ids) == len(set(ids))

    def test_load_arc_ids_match_pattern(self) -> None:
        """Sample IDs should match Mercury/ACTAAP/etc. patterns."""
        samples = load_arc(tier="smoke")
        for sample in samples:
            # IDs should be like "Mercury_7175875", "ACTAAP_2008_5", etc.
            assert "_" in sample.id or sample.id.isalnum()

    def test_load_arc_reproducible_with_seed(self) -> None:
        """Should return same samples for same tier (reproducible sampling)."""
        samples1 = load_arc(tier="quick")
        samples2 = load_arc(tier="quick")

        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]

        assert ids1 == ids2

    def test_load_arc_smoke_subset_of_quick(self) -> None:
        """Smoke samples should be subset of quick samples (nested sampling)."""
        smoke_samples = load_arc(tier="smoke")
        quick_samples = load_arc(tier="quick")

        smoke_ids = {s.id for s in smoke_samples}
        quick_ids = {s.id for s in quick_samples}

        assert smoke_ids.issubset(quick_ids)

    def test_load_arc_quick_subset_of_full(self) -> None:
        """Quick samples should be subset of full samples."""
        quick_samples = load_arc(tier="quick")
        full_samples = load_arc(tier="full")

        quick_ids = {s.id for s in quick_samples}
        full_ids = {s.id for s in full_samples}

        assert quick_ids.issubset(full_ids)

    def test_load_arc_file_not_found_raises_error(self) -> None:
        """Should raise FileNotFoundError if dataset file missing."""
        with patch("matric_eval.tasks.arc.ARC_PATH", "/nonexistent/path.jsonl"):
            with pytest.raises(FileNotFoundError):
                load_arc()

    def test_load_arc_invalid_json_raises_error(self) -> None:
        """Should raise error for malformed JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("invalid json line\n")
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.arc.ARC_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_arc()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
@requires_arc_data
class TestArcSampleQuality:
    """Tests for quality and correctness of loaded samples."""

    def test_samples_have_multiple_choice_prompts(self) -> None:
        """Should have multiple choice format in prompts."""
        samples = load_arc(tier="smoke")
        for sample in samples:
            assert "Question:" in sample.input
            assert "Answer:" in sample.input
            assert "A)" in sample.input

    def test_samples_have_four_choices(self) -> None:
        """Should typically have 4 choices (A, B, C, D)."""
        samples = load_arc(tier="smoke")
        for sample in samples:
            # Most ARC questions have 4 choices
            if len(sample.metadata["choices"]) == 4:
                assert "A)" in sample.input
                assert "B)" in sample.input
                assert "C)" in sample.input
                assert "D)" in sample.input

    def test_samples_have_valid_answer_keys(self) -> None:
        """Should have answer keys A, B, C, or D."""
        samples = load_arc(tier="smoke")
        valid_keys = {"A", "B", "C", "D", "1", "2", "3", "4"}  # Some datasets use 1-4
        for sample in samples:
            assert sample.target in valid_keys

    def test_samples_have_question_stem_metadata(self) -> None:
        """Should have question_stem in metadata."""
        samples = load_arc(tier="smoke")
        for sample in samples:
            assert "question_stem" in sample.metadata
            assert isinstance(sample.metadata["question_stem"], str)
            assert len(sample.metadata["question_stem"]) > 0

    def test_samples_have_choices_metadata(self) -> None:
        """Should have choices list in metadata."""
        samples = load_arc(tier="smoke")
        for sample in samples:
            assert "choices" in sample.metadata
            assert isinstance(sample.metadata["choices"], list)
            assert len(sample.metadata["choices"]) > 0

    def test_sample_choices_have_text_and_label(self) -> None:
        """Each choice should have text and label fields."""
        samples = load_arc(tier="smoke")
        for sample in samples:
            for choice in sample.metadata["choices"]:
                assert "text" in choice
                assert "label" in choice
                assert isinstance(choice["text"], str)
                assert isinstance(choice["label"], str)


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
@requires_arc_data
class TestArcTask:
    """Tests for arc() task definition."""

    def test_arc_task_creation(self) -> None:
        """Should create valid Task object."""
        task = arc(tier="smoke")
        assert isinstance(task, Task)

    def test_arc_task_name(self) -> None:
        """Should have correct task name."""
        task = arc(tier="smoke")
        assert task.name == "arc"

    def test_arc_task_has_dataset(self) -> None:
        """Should have dataset configured."""
        task = arc(tier="smoke")
        assert task.dataset is not None
        assert len(task.dataset) == 5

    def test_arc_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = arc(tier="smoke")
        assert task.solver is not None

    def test_arc_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = arc(tier="smoke")
        assert task.scorer is not None

    def test_arc_task_respects_tier_parameter(self) -> None:
        """Should create tasks with different sample counts per tier."""
        smoke_task = arc(tier="smoke")
        quick_task = arc(tier="quick")
        full_task = arc(tier="full")

        assert len(smoke_task.dataset) == 5
        assert len(quick_task.dataset) == 75
        assert len(full_task.dataset) == 1172

    def test_arc_task_default_tier_is_smoke(self) -> None:
        """Should default to smoke tier."""
        task = arc()
        assert len(task.dataset) == 5

    def test_arc_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = arc(tier="smoke")
        task2 = arc(tier="smoke")

        # Should be separate instances
        assert task1 is not task2


# =============================================================================
# Scorer Configuration Tests
# =============================================================================


@pytest.mark.unit
@requires_arc_data
class TestArcScorer:
    """Tests for multiple choice scorer configuration."""

    def test_task_has_multiple_choice_scorer(self) -> None:
        """Should use multiple choice scorer for validation."""
        task = arc(tier="smoke")

        # Scorer should be configured (type check)
        assert task.scorer is not None

    def test_scorer_can_access_answer_key(self) -> None:
        """Scorer should be able to access answer key from target."""
        samples = load_arc(tier="smoke")

        # All samples should have answer key in target
        for sample in samples:
            assert sample.target is not None
            assert len(sample.target) > 0


# =============================================================================
# Integration with Config System
# =============================================================================


@pytest.mark.unit
@requires_arc_data
class TestArcConfigIntegration:
    """Tests for integration with matric_eval.config."""

    def test_load_arc_uses_config_tier(self) -> None:
        """Should use TierConfig for sample counts."""
        from matric_eval.config import TIERS

        smoke_count = TIERS["smoke"].arc
        quick_count = TIERS["quick"].arc
        full_count = TIERS["full"].arc

        assert len(load_arc(tier="smoke")) == smoke_count
        assert len(load_arc(tier="quick")) == quick_count
        assert len(load_arc(tier="full")) == full_count

    def test_load_arc_respects_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should respect EVAL_ARC_SAMPLES environment variable."""
        monkeypatch.setenv("EVAL_ARC_SAMPLES", "10")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        # Should load 10 samples instead of default tier counts
        samples = load_arc(tier="smoke")
        assert len(samples) == 10

    def test_load_arc_uses_reproducible_seed(self) -> None:
        """Should use get_seed() for reproducible sampling."""
        from matric_eval.config import get_seed

        seed = get_seed()
        assert isinstance(seed, int)

        # Samples should be reproducible
        samples1 = load_arc(tier="quick")
        samples2 = load_arc(tier="quick")

        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestArcErrorHandling:
    """Tests for error handling in dataset loading."""

    def test_load_arc_empty_file_raises_error(self) -> None:
        """Should raise error for empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write nothing
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.arc.ARC_PATH", temp_path):
                with pytest.raises((ValueError, IndexError)):
                    load_arc()
        finally:
            Path(temp_path).unlink()

    def test_load_arc_corrupted_jsonl_raises_error(self) -> None:
        """Should raise error for corrupted JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"id": "Test", "incomplete": \n')
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.arc.ARC_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_arc()
        finally:
            Path(temp_path).unlink()

    def test_record_to_sample_handles_missing_answer_key(self) -> None:
        """Should raise error for missing answer key."""
        record = {
            "id": "Test_001",
            "question": {
                "stem": "Question?",
                "choices": [{"text": "A", "label": "A"}],
            },
            # Missing answerKey
        }

        with pytest.raises(KeyError):
            record_to_sample(record)


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
@requires_arc_data
class TestArcEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_arc_sample_count_exceeds_dataset_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return all available samples if requested count exceeds dataset size."""
        monkeypatch.setenv("EVAL_ARC_SAMPLES", "5000")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_arc()
        # Should return all 1,172 samples, not 5000
        assert len(samples) == 1172

    def test_load_arc_zero_samples_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle zero sample request gracefully."""
        monkeypatch.setenv("EVAL_ARC_SAMPLES", "0")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_arc()
        assert len(samples) == 0

    def test_record_to_sample_with_unicode_characters(self) -> None:
        """Should handle unicode characters in questions."""
        record = {
            "id": "Unicode_Test",
            "question": {
                "stem": "What is π approximately?",
                "choices": [
                    {"text": "3.14", "label": "A"},
                    {"text": "2.71", "label": "B"},
                    {"text": "1.41", "label": "C"},
                    {"text": "1.73", "label": "D"},
                ],
            },
            "answerKey": "A",
        }

        sample = record_to_sample(record)
        assert "π" in sample.input

    def test_format_arc_prompt_with_special_characters(self) -> None:
        """Should handle special characters in choices."""
        question = "What does H₂O represent?"
        choices = [
            {"text": "Water (H₂O)", "label": "A"},
            {"text": "Hydrogen peroxide (H₂O₂)", "label": "B"},
            {"text": "Carbon dioxide (CO₂)", "label": "C"},
            {"text": "Oxygen (O₂)", "label": "D"},
        ]

        prompt = format_arc_prompt(question, choices)
        assert "H₂O" in prompt
        assert "CO₂" in prompt
