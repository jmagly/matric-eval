"""
Tests for HumanEval benchmark task (matric_eval.tasks.humaneval).

Covers:
- Dataset loading from JSONL
- Tiered sampling (smoke/quick/full)
- Sample format conversion
- Task definition
- Scorer configuration
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.humaneval import (
    humaneval,
    load_humaneval,
    record_to_sample,
)

# Import skip marker for tests requiring external data
from tests.conftest import requires_humaneval_data


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton before each test."""
    # Clear environment variables
    monkeypatch.delenv("EVAL_HUMANEVAL_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module
    settings_module._settings = None


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
@requires_humaneval_data
class TestLoadHumanEval:
    """Tests for load_humaneval() function."""

    def test_load_humaneval_smoke_returns_5_samples(self) -> None:
        """Should load exactly 5 samples for smoke tier."""
        samples = load_humaneval(tier="smoke")
        assert len(samples) == 5

    def test_load_humaneval_quick_returns_75_samples(self) -> None:
        """Should load exactly 75 samples for quick tier."""
        samples = load_humaneval(tier="quick")
        assert len(samples) == 75

    def test_load_humaneval_full_returns_all_samples(self) -> None:
        """Should load all 164 samples for full tier."""
        samples = load_humaneval(tier="full")
        assert len(samples) == 164

    def test_load_humaneval_default_is_smoke(self) -> None:
        """Should default to smoke tier if no tier specified."""
        samples = load_humaneval()
        assert len(samples) == 5

    def test_load_humaneval_unknown_tier_defaults_to_smoke(self) -> None:
        """Should fall back to smoke tier for unknown tier names."""
        samples = load_humaneval(tier="unknown_tier")
        assert len(samples) == 5

    def test_load_humaneval_samples_are_sample_objects(self) -> None:
        """Should return list of Sample objects."""
        samples = load_humaneval(tier="smoke")
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_humaneval_samples_have_required_fields(self) -> None:
        """Should have input, target, id, and metadata fields."""
        samples = load_humaneval(tier="smoke")
        for sample in samples:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert sample.metadata is not None

    def test_load_humaneval_samples_have_unique_ids(self) -> None:
        """Should have unique IDs for all samples."""
        samples = load_humaneval(tier="full")
        ids = [s.id for s in samples]
        assert len(ids) == len(set(ids))

    def test_load_humaneval_ids_match_task_id_pattern(self) -> None:
        """Sample IDs should match original task_id from dataset."""
        samples = load_humaneval(tier="smoke")
        for sample in samples:
            # IDs should be like "HumanEval/0", "HumanEval/1", etc.
            assert sample.id.startswith("HumanEval/")

    def test_load_humaneval_reproducible_with_seed(self) -> None:
        """Should return same samples for same tier (reproducible sampling)."""
        samples1 = load_humaneval(tier="quick")
        samples2 = load_humaneval(tier="quick")

        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]

        assert ids1 == ids2

    def test_load_humaneval_smoke_subset_of_quick(self) -> None:
        """Smoke samples should be subset of quick samples (nested sampling)."""
        smoke_samples = load_humaneval(tier="smoke")
        quick_samples = load_humaneval(tier="quick")

        smoke_ids = {s.id for s in smoke_samples}
        quick_ids = {s.id for s in quick_samples}

        assert smoke_ids.issubset(quick_ids)

    def test_load_humaneval_quick_subset_of_full(self) -> None:
        """Quick samples should be subset of full samples."""
        quick_samples = load_humaneval(tier="quick")
        full_samples = load_humaneval(tier="full")

        quick_ids = {s.id for s in quick_samples}
        full_ids = {s.id for s in full_samples}

        assert quick_ids.issubset(full_ids)

    def test_load_humaneval_file_not_found_raises_error(self) -> None:
        """Should raise FileNotFoundError if dataset file missing."""
        with patch("matric_eval.tasks.humaneval.HUMANEVAL_PATH", "/nonexistent/path.jsonl"):
            with pytest.raises(FileNotFoundError):
                load_humaneval()

    def test_load_humaneval_invalid_json_raises_error(self) -> None:
        """Should raise error for malformed JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("invalid json line\n")
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.humaneval.HUMANEVAL_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_humaneval()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Record Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() conversion function."""

    def test_record_to_sample_basic_conversion(self) -> None:
        """Should convert HumanEval record to Sample."""
        record = {
            "task_id": "HumanEval/0",
            "prompt": "def has_close_elements(numbers, threshold):\n    pass",
            "entry_point": "has_close_elements",
            "canonical_solution": "    return False",
            "test": "def check(candidate):\n    assert True"
        }

        sample = record_to_sample(record)

        assert isinstance(sample, Sample)
        assert sample.id == "HumanEval/0"

    def test_record_to_sample_includes_prompt_in_input(self) -> None:
        """Should include the code prompt in input field."""
        record = {
            "task_id": "HumanEval/0",
            "prompt": "def has_close_elements(numbers, threshold):\n    pass",
            "entry_point": "has_close_elements",
            "canonical_solution": "    return False",
            "test": "def check(candidate):\n    assert True"
        }

        sample = record_to_sample(record)

        assert "has_close_elements" in sample.input
        assert "def has_close_elements" in sample.input

    def test_record_to_sample_includes_canonical_solution_in_target(self) -> None:
        """Should use canonical_solution as target."""
        record = {
            "task_id": "HumanEval/0",
            "prompt": "def has_close_elements(numbers, threshold):\n    pass",
            "entry_point": "has_close_elements",
            "canonical_solution": "    return False",
            "test": "def check(candidate):\n    assert True"
        }

        sample = record_to_sample(record)

        assert sample.target == "    return False"

    def test_record_to_sample_includes_metadata(self) -> None:
        """Should include entry_point and test in metadata."""
        record = {
            "task_id": "HumanEval/0",
            "prompt": "def has_close_elements(numbers, threshold):\n    pass",
            "entry_point": "has_close_elements",
            "canonical_solution": "    return False",
            "test": "def check(candidate):\n    assert True"
        }

        sample = record_to_sample(record)

        assert sample.metadata is not None
        assert "entry_point" in sample.metadata
        assert sample.metadata["entry_point"] == "has_close_elements"
        assert "test" in sample.metadata

    def test_record_to_sample_preserves_test_code(self) -> None:
        """Should preserve test code in metadata for execution."""
        test_code = "def check(candidate):\n    assert candidate([1, 2], 0.5) == False"
        record = {
            "task_id": "HumanEval/0",
            "prompt": "def has_close_elements(numbers, threshold):\n    pass",
            "entry_point": "has_close_elements",
            "canonical_solution": "    return False",
            "test": test_code
        }

        sample = record_to_sample(record)

        assert sample.metadata["test"] == test_code

    def test_record_to_sample_missing_required_field_raises_error(self) -> None:
        """Should raise KeyError if required field missing."""
        incomplete_record = {
            "task_id": "HumanEval/0",
            "prompt": "def foo():\n    pass",
            # Missing entry_point, canonical_solution, test
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
@requires_humaneval_data
class TestHumanEvalSampleQuality:
    """Tests for quality and correctness of loaded samples."""

    def test_samples_have_python_code_prompts(self) -> None:
        """Should have Python function definitions in prompts."""
        samples = load_humaneval(tier="smoke")
        for sample in samples:
            assert "def " in sample.input

    def test_samples_have_function_signatures(self) -> None:
        """Should include function signatures with parameters."""
        samples = load_humaneval(tier="smoke")
        for sample in samples:
            assert "def " in sample.input
            assert "(" in sample.input
            assert ")" in sample.input

    def test_samples_have_entry_point_metadata(self) -> None:
        """Should have entry_point in metadata."""
        samples = load_humaneval(tier="smoke")
        for sample in samples:
            assert "entry_point" in sample.metadata
            assert isinstance(sample.metadata["entry_point"], str)
            assert len(sample.metadata["entry_point"]) > 0

    def test_samples_have_test_metadata(self) -> None:
        """Should have test code in metadata."""
        samples = load_humaneval(tier="smoke")
        for sample in samples:
            assert "test" in sample.metadata
            assert "def check" in sample.metadata["test"]

    def test_samples_have_canonical_solutions(self) -> None:
        """Should have non-empty canonical solutions as targets."""
        samples = load_humaneval(tier="smoke")
        for sample in samples:
            assert len(sample.target) > 0

    def test_first_sample_is_has_close_elements(self) -> None:
        """First problem should be the classic has_close_elements."""
        samples = load_humaneval(tier="full")
        first = samples[0]

        assert first.id == "HumanEval/0"
        assert "has_close_elements" in first.input
        assert first.metadata["entry_point"] == "has_close_elements"


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
@requires_humaneval_data
class TestHumanEvalTask:
    """Tests for humaneval() task definition."""

    def test_humaneval_task_creation(self) -> None:
        """Should create valid Task object."""
        task = humaneval(tier="smoke")
        assert isinstance(task, Task)

    def test_humaneval_task_name(self) -> None:
        """Should have correct task name."""
        task = humaneval(tier="smoke")
        assert task.name == "humaneval"

    def test_humaneval_task_has_dataset(self) -> None:
        """Should have dataset configured."""
        task = humaneval(tier="smoke")
        assert task.dataset is not None
        assert len(task.dataset) == 5

    def test_humaneval_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = humaneval(tier="smoke")
        assert task.solver is not None

    def test_humaneval_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = humaneval(tier="smoke")
        assert task.scorer is not None

    def test_humaneval_task_respects_tier_parameter(self) -> None:
        """Should create tasks with different sample counts per tier."""
        smoke_task = humaneval(tier="smoke")
        quick_task = humaneval(tier="quick")
        full_task = humaneval(tier="full")

        assert len(smoke_task.dataset) == 5
        assert len(quick_task.dataset) == 75
        assert len(full_task.dataset) == 164

    def test_humaneval_task_default_tier_is_smoke(self) -> None:
        """Should default to smoke tier."""
        task = humaneval()
        assert len(task.dataset) == 5

    def test_humaneval_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = humaneval(tier="smoke")
        task2 = humaneval(tier="smoke")

        # Should be separate instances
        assert task1 is not task2


# =============================================================================
# Scorer Configuration Tests
# =============================================================================


@pytest.mark.unit
@requires_humaneval_data
class TestHumanEvalScorer:
    """Tests for code execution scorer configuration."""

    def test_task_has_code_execution_scorer(self) -> None:
        """Should use code execution scorer for validation."""
        task = humaneval(tier="smoke")

        # Scorer should be configured (type check)
        assert task.scorer is not None
        # The actual scorer implementation will be tested in integration tests

    def test_scorer_can_access_test_metadata(self) -> None:
        """Scorer should be able to access test code from metadata."""
        samples = load_humaneval(tier="smoke")

        # All samples should have test metadata for scorer to use
        for sample in samples:
            assert "test" in sample.metadata
            assert "entry_point" in sample.metadata


# =============================================================================
# Integration with Config System
# =============================================================================


@pytest.mark.unit
@requires_humaneval_data
class TestHumanEvalConfigIntegration:
    """Tests for integration with matric_eval.config."""

    def test_load_humaneval_uses_config_tier(self) -> None:
        """Should use TierConfig for sample counts."""
        from matric_eval.config import TIERS

        smoke_count = TIERS["smoke"].humaneval
        quick_count = TIERS["quick"].humaneval
        full_count = TIERS["full"].humaneval

        assert len(load_humaneval(tier="smoke")) == smoke_count
        assert len(load_humaneval(tier="quick")) == quick_count
        assert len(load_humaneval(tier="full")) == full_count

    def test_load_humaneval_respects_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should respect EVAL_HUMANEVAL_SAMPLES environment variable."""
        monkeypatch.setenv("EVAL_HUMANEVAL_SAMPLES", "10")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        # Should load 10 samples instead of default tier counts
        samples = load_humaneval(tier="smoke")
        assert len(samples) == 10

    def test_load_humaneval_uses_reproducible_seed(self) -> None:
        """Should use get_seed() for reproducible sampling."""
        from matric_eval.config import get_seed

        seed = get_seed()
        assert isinstance(seed, int)

        # Samples should be reproducible
        samples1 = load_humaneval(tier="quick")
        samples2 = load_humaneval(tier="quick")

        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestHumanEvalErrorHandling:
    """Tests for error handling in dataset loading."""

    def test_load_humaneval_empty_file_raises_error(self) -> None:
        """Should raise error for empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write nothing
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.humaneval.HUMANEVAL_PATH", temp_path):
                with pytest.raises((ValueError, IndexError)):
                    load_humaneval()
        finally:
            Path(temp_path).unlink()

    def test_load_humaneval_corrupted_jsonl_raises_error(self) -> None:
        """Should raise error for corrupted JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"task_id": "HumanEval/0", "incomplete": \n')
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.humaneval.HUMANEVAL_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_humaneval()
        finally:
            Path(temp_path).unlink()

    def test_record_to_sample_handles_empty_test(self) -> None:
        """Should handle records with empty test field."""
        record = {
            "task_id": "HumanEval/0",
            "prompt": "def foo():\n    pass",
            "entry_point": "foo",
            "canonical_solution": "    pass",
            "test": ""
        }

        sample = record_to_sample(record)
        assert sample.metadata["test"] == ""


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
@requires_humaneval_data
class TestHumanEvalEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_humaneval_sample_count_exceeds_dataset_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return all available samples if requested count exceeds dataset size."""
        monkeypatch.setenv("EVAL_HUMANEVAL_SAMPLES", "1000")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_humaneval()
        # Should return all 164 samples, not 1000
        assert len(samples) == 164

    def test_load_humaneval_zero_samples_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle zero sample request gracefully."""
        monkeypatch.setenv("EVAL_HUMANEVAL_SAMPLES", "0")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_humaneval()
        assert len(samples) == 0

    def test_record_to_sample_with_unicode_characters(self) -> None:
        """Should handle unicode characters in prompts."""
        record = {
            "task_id": "HumanEval/Test",
            "prompt": "def foo():\n    \"\"\"Return π\"\"\"",
            "entry_point": "foo",
            "canonical_solution": "    return 3.14159",
            "test": "def check(candidate):\n    assert True"
        }

        sample = record_to_sample(record)
        assert "π" in sample.input

    def test_record_to_sample_with_long_solution(self) -> None:
        """Should handle long canonical solutions."""
        long_solution = "    " + "\n    ".join(["pass"] * 100)
        record = {
            "task_id": "HumanEval/Long",
            "prompt": "def long_function():\n    pass",
            "entry_point": "long_function",
            "canonical_solution": long_solution,
            "test": "def check(candidate):\n    assert True"
        }

        sample = record_to_sample(record)
        assert len(sample.target) > 0
        assert sample.target == long_solution
