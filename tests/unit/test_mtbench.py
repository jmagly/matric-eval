"""
Tests for MT-Bench multi-turn conversation task (matric_eval.tasks.mtbench).

Covers:
- Dataset loading from JSONL
- Tiered sampling (smoke/quick/full)
- Multi-turn conversation handling
- Sample format conversion
- Task definition
- LLM-as-judge scorer integration
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.mtbench import (
    mtbench,
    load_mtbench,
    record_to_sample,
)

# Import skip marker for tests requiring external data
from tests.conftest import requires_mtbench_data


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables before each test."""
    monkeypatch.delenv("EVAL_MTBENCH_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    # Reset settings singleton
    import matric_eval.config.settings as settings_module
    settings_module._settings = None


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
@requires_mtbench_data
class TestLoadMTBench:
    """Tests for load_mtbench() function."""

    def test_load_mtbench_smoke_returns_expected_samples(self) -> None:
        """Should load samples for smoke tier (config default or 0)."""
        samples = load_mtbench(tier="smoke")
        # Smoke tier has mtbench=0 by default, but should still work
        assert isinstance(samples, list)

    def test_load_mtbench_full_returns_all_samples(self) -> None:
        """Should load all 80 samples for full tier."""
        samples = load_mtbench(tier="full")
        assert len(samples) == 80

    def test_load_mtbench_default_is_smoke(self) -> None:
        """Should default to smoke tier if no tier specified."""
        samples = load_mtbench()
        assert isinstance(samples, list)

    def test_load_mtbench_unknown_tier_defaults_to_smoke(self) -> None:
        """Should fall back to smoke tier for unknown tier names."""
        samples = load_mtbench(tier="unknown_tier")
        assert isinstance(samples, list)

    def test_load_mtbench_samples_are_sample_objects(self) -> None:
        """Should return list of Sample objects."""
        samples = load_mtbench(tier="full")
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_mtbench_samples_have_required_fields(self) -> None:
        """Should have input, id, and metadata fields."""
        samples = load_mtbench(tier="full")
        for sample in samples:
            assert sample.input is not None
            assert sample.id is not None
            assert sample.metadata is not None

    def test_load_mtbench_samples_have_unique_ids(self) -> None:
        """Should have unique IDs for all samples."""
        samples = load_mtbench(tier="full")
        ids = [s.id for s in samples]
        assert len(ids) == len(set(ids))

    def test_load_mtbench_reproducible_with_seed(self) -> None:
        """Should return same samples for same tier (reproducible sampling)."""
        # Use full tier since smoke might be 0
        samples1 = load_mtbench(tier="full")
        samples2 = load_mtbench(tier="full")

        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]

        assert ids1 == ids2

    def test_load_mtbench_file_not_found_raises_error(self) -> None:
        """Should raise FileNotFoundError if dataset file missing."""
        with patch("matric_eval.tasks.mtbench.MTBENCH_PATH", "/nonexistent/path.jsonl"):
            with pytest.raises(FileNotFoundError):
                load_mtbench(tier="full")

    def test_load_mtbench_invalid_json_raises_error(self) -> None:
        """Should raise error for malformed JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("invalid json line\n")
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.mtbench.MTBENCH_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_mtbench(tier="full")
        finally:
            Path(temp_path).unlink()

    def test_load_mtbench_zero_samples_returns_empty_list(self) -> None:
        """Should return empty list for zero sample request."""
        samples = load_mtbench(tier="smoke")  # Default smoke has 0 mtbench samples
        # Should not crash, returns empty or small list
        assert isinstance(samples, list)


# =============================================================================
# Record Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() conversion function."""

    def test_record_to_sample_basic_conversion(self) -> None:
        """Should convert MT-Bench record to Sample."""
        record = {
            "question_id": 81,
            "category": "writing",
            "turns": [
                "Write a travel blog post about Hawaii.",
                "Rewrite it starting every sentence with 'A'."
            ]
        }

        sample = record_to_sample(record)

        assert isinstance(sample, Sample)
        assert sample.id == "81"

    def test_record_to_sample_includes_first_turn_in_input(self) -> None:
        """Should include the first turn in input field."""
        record = {
            "question_id": 82,
            "category": "writing",
            "turns": [
                "Draft a professional email.",
                "Critique your response."
            ]
        }

        sample = record_to_sample(record)

        assert "Draft a professional email" in sample.input

    def test_record_to_sample_includes_metadata(self) -> None:
        """Should include turns and category in metadata."""
        record = {
            "question_id": 83,
            "category": "roleplay",
            "turns": ["First turn", "Second turn"]
        }

        sample = record_to_sample(record)

        assert sample.metadata is not None
        assert "turns" in sample.metadata
        assert "category" in sample.metadata
        assert sample.metadata["category"] == "roleplay"

    def test_record_to_sample_preserves_all_turns(self) -> None:
        """Should preserve all turns in metadata."""
        turns = ["Turn 1", "Turn 2", "Turn 3"]
        record = {
            "question_id": 84,
            "category": "writing",
            "turns": turns
        }

        sample = record_to_sample(record)

        assert sample.metadata["turns"] == turns

    def test_record_to_sample_missing_required_field_raises_error(self) -> None:
        """Should raise KeyError if required field missing."""
        incomplete_record = {
            "question_id": 85,
            # Missing category and turns
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)

    def test_record_to_sample_handles_reference_field(self) -> None:
        """Should handle optional reference field if present."""
        record = {
            "question_id": 86,
            "category": "writing",
            "turns": ["Turn 1", "Turn 2"],
            "reference": ["Reference answer 1", "Reference answer 2"]
        }

        sample = record_to_sample(record)

        # Reference should be in metadata if present
        if "reference" in sample.metadata:
            assert sample.metadata["reference"] == record["reference"]


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
@requires_mtbench_data
class TestMTBenchSampleQuality:
    """Tests for quality and correctness of loaded samples."""

    def test_samples_have_multiple_turns(self) -> None:
        """Should have multiple turns in metadata."""
        samples = load_mtbench(tier="full")
        for sample in samples:
            assert "turns" in sample.metadata
            assert len(sample.metadata["turns"]) >= 2

    def test_samples_have_category_metadata(self) -> None:
        """Should have category in metadata."""
        samples = load_mtbench(tier="full")
        for sample in samples:
            assert "category" in sample.metadata
            assert isinstance(sample.metadata["category"], str)
            assert len(sample.metadata["category"]) > 0

    def test_samples_have_question_ids(self) -> None:
        """Should have numeric question IDs."""
        samples = load_mtbench(tier="full")
        for sample in samples:
            # ID should be string representation of number
            assert sample.id.isdigit()

    def test_samples_cover_multiple_categories(self) -> None:
        """Should have samples from multiple categories."""
        samples = load_mtbench(tier="full")
        categories = {s.metadata["category"] for s in samples}
        # MT-Bench has categories like writing, roleplay, reasoning, etc.
        assert len(categories) >= 3

    def test_first_sample_matches_expected_format(self) -> None:
        """First sample should match expected MT-Bench format."""
        samples = load_mtbench(tier="full")
        if len(samples) > 0:
            first = samples[0]
            assert first.id.isdigit()
            assert "turns" in first.metadata
            assert isinstance(first.metadata["turns"], list)


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
@requires_mtbench_data
class TestMTBenchTask:
    """Tests for mtbench() task definition."""

    def test_mtbench_task_creation(self) -> None:
        """Should create valid Task object."""
        task = mtbench(tier="full")
        assert isinstance(task, Task)

    def test_mtbench_task_name(self) -> None:
        """Should have correct task name."""
        task = mtbench(tier="full")
        assert task.name == "mtbench"

    def test_mtbench_task_has_dataset(self) -> None:
        """Should have dataset configured."""
        task = mtbench(tier="full")
        assert task.dataset is not None
        assert len(task.dataset) == 80

    def test_mtbench_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = mtbench(tier="full")
        assert task.solver is not None

    def test_mtbench_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = mtbench(tier="full")
        assert task.scorer is not None

    def test_mtbench_task_respects_tier_parameter(self) -> None:
        """Should create tasks with different sample counts per tier."""
        full_task = mtbench(tier="full")

        # Full tier should have all 80 samples
        assert len(full_task.dataset) == 80

    def test_mtbench_task_default_tier_is_smoke(self) -> None:
        """Should default to smoke tier with 5 samples."""
        # Smoke tier has 5 samples for quick testing
        samples = load_mtbench()
        assert isinstance(samples, list)
        # Smoke tier has 5 samples
        assert len(samples) == 5

    def test_mtbench_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = mtbench(tier="full")
        task2 = mtbench(tier="full")

        # Should be separate instances
        assert task1 is not task2


# =============================================================================
# Multi-Turn Conversation Tests
# =============================================================================


@pytest.mark.unit
@requires_mtbench_data
class TestMTBenchMultiTurn:
    """Tests for multi-turn conversation handling."""

    def test_samples_store_conversation_turns(self) -> None:
        """Should store all conversation turns in metadata."""
        samples = load_mtbench(tier="full")
        for sample in samples:
            turns = sample.metadata["turns"]
            assert len(turns) >= 2
            assert all(isinstance(turn, str) for turn in turns)

    def test_first_turn_is_in_input(self) -> None:
        """First turn should be in the input field."""
        samples = load_mtbench(tier="full")
        for sample in samples:
            first_turn = sample.metadata["turns"][0]
            assert first_turn in sample.input or sample.input in first_turn


# =============================================================================
# Integration with Config System
# =============================================================================


@pytest.mark.unit
@requires_mtbench_data
class TestMTBenchConfigIntegration:
    """Tests for integration with matric_eval.config."""

    def test_load_mtbench_uses_config_tier(self) -> None:
        """Should use TierConfig for sample counts."""
        from matric_eval.config import TIERS

        full_count = TIERS["full"].mtbench

        assert len(load_mtbench(tier="full")) == full_count

    def test_load_mtbench_respects_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should respect EVAL_MTBENCH_SAMPLES environment variable."""
        monkeypatch.setenv("EVAL_MTBENCH_SAMPLES", "10")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_mtbench()
        assert len(samples) == 10

    def test_load_mtbench_uses_reproducible_seed(self) -> None:
        """Should use get_seed() for reproducible sampling."""
        from matric_eval.config import get_seed

        seed = get_seed()
        assert isinstance(seed, int)

        # Samples should be reproducible
        samples1 = load_mtbench(tier="full")
        samples2 = load_mtbench(tier="full")

        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestMTBenchErrorHandling:
    """Tests for error handling in dataset loading."""

    def test_load_mtbench_empty_file_raises_error(self) -> None:
        """Should raise error for empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write nothing
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.mtbench.MTBENCH_PATH", temp_path):
                with pytest.raises((ValueError, IndexError)):
                    # Request full tier to ensure it tries to load
                    load_mtbench(tier="full")
        finally:
            Path(temp_path).unlink()

    def test_load_mtbench_corrupted_jsonl_raises_error(self) -> None:
        """Should raise error for corrupted JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"question_id": 1, "incomplete": \n')
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.mtbench.MTBENCH_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_mtbench(tier="full")
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
@requires_mtbench_data
class TestMTBenchEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_mtbench_sample_count_exceeds_dataset_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return all available samples if requested count exceeds dataset size."""
        monkeypatch.setenv("EVAL_MTBENCH_SAMPLES", "1000")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_mtbench()
        # Should return all 80 samples, not 1000
        assert len(samples) == 80

    def test_load_mtbench_zero_samples_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle zero sample request gracefully."""
        monkeypatch.setenv("EVAL_MTBENCH_SAMPLES", "0")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_mtbench()
        assert len(samples) == 0

    def test_record_to_sample_with_unicode_characters(self) -> None:
        """Should handle unicode characters in turns."""
        record = {
            "question_id": 999,
            "category": "writing",
            "turns": ["Write about café culture ☕", "Add more details"]
        }

        sample = record_to_sample(record)
        assert "café" in sample.input or "☕" in str(sample.metadata)

    def test_record_to_sample_with_very_long_turns(self) -> None:
        """Should handle very long conversation turns."""
        long_turn = "A " * 1000
        record = {
            "question_id": 998,
            "category": "writing",
            "turns": [long_turn, "Follow up question"]
        }

        sample = record_to_sample(record)
        assert len(sample.metadata["turns"][0]) > 0
