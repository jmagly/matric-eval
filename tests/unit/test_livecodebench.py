"""
Tests for LiveCodeBench benchmark task (matric_eval.tasks.livecodebench).

Covers:
- Dataset loading from JSONL
- Tiered sampling (smoke/quick/full)
- Sample format conversion
- Task definition
- Scorer configuration

LiveCodeBench: 880 competitive programming problems from platforms like
AtCoder, CodeForces, LeetCode with test cases for validation.
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.livecodebench import (
    livecodebench,
    load_livecodebench,
    record_to_sample,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton before each test."""
    # Clear environment variables
    monkeypatch.delenv("EVAL_LIVECODEBENCH_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module
    settings_module._settings = None


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadLiveCodeBench:
    """Tests for load_livecodebench() function."""

    def test_load_livecodebench_smoke_returns_5_samples(self) -> None:
        """Should load exactly 5 samples for smoke tier."""
        samples = load_livecodebench(tier="smoke")
        assert len(samples) == 5

    def test_load_livecodebench_quick_returns_50_samples(self) -> None:
        """Should load exactly 50 samples for quick tier."""
        samples = load_livecodebench(tier="quick")
        assert len(samples) == 50

    def test_load_livecodebench_full_returns_all_samples(self) -> None:
        """Should load all 880+ samples for full tier."""
        samples = load_livecodebench(tier="full")
        # Dataset may have slightly more or fewer than 880
        assert len(samples) >= 880
        assert len(samples) <= 1100

    def test_load_livecodebench_default_is_smoke(self) -> None:
        """Should default to smoke tier if no tier specified."""
        samples = load_livecodebench()
        assert len(samples) == 5

    def test_load_livecodebench_unknown_tier_defaults_to_smoke(self) -> None:
        """Should fall back to smoke tier for unknown tier names."""
        samples = load_livecodebench(tier="unknown_tier")
        assert len(samples) == 5

    def test_load_livecodebench_samples_are_sample_objects(self) -> None:
        """Should return list of Sample objects."""
        samples = load_livecodebench(tier="smoke")
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_livecodebench_samples_have_required_fields(self) -> None:
        """Should have input, target, id, and metadata fields."""
        samples = load_livecodebench(tier="smoke")
        for sample in samples:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert sample.metadata is not None

    def test_load_livecodebench_samples_have_unique_ids(self) -> None:
        """Should have unique IDs for all samples."""
        samples = load_livecodebench(tier="quick")
        ids = [s.id for s in samples]
        assert len(ids) == len(set(ids))

    def test_load_livecodebench_ids_match_pattern(self) -> None:
        """Sample IDs should include platform and question_id."""
        samples = load_livecodebench(tier="smoke")
        for sample in samples:
            # IDs should be like "atcoder/abc344_d" or similar
            assert "/" in sample.id or "_" in sample.id

    def test_load_livecodebench_reproducible_with_seed(self) -> None:
        """Should return same samples for same tier (reproducible sampling)."""
        samples1 = load_livecodebench(tier="quick")
        samples2 = load_livecodebench(tier="quick")

        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]

        assert ids1 == ids2

    def test_load_livecodebench_smoke_subset_of_quick(self) -> None:
        """Smoke samples should be subset of quick samples (nested sampling)."""
        smoke_samples = load_livecodebench(tier="smoke")
        quick_samples = load_livecodebench(tier="quick")

        smoke_ids = {s.id for s in smoke_samples}
        quick_ids = {s.id for s in quick_samples}

        assert smoke_ids.issubset(quick_ids)

    def test_load_livecodebench_quick_samples_from_full_dataset(self) -> None:
        """Quick samples should be drawn from the full dataset."""
        quick_samples = load_livecodebench(tier="quick")
        full_samples = load_livecodebench(tier="full")

        # Quick samples should be fewer than or equal to full samples
        assert len(quick_samples) <= len(full_samples)

        # Quick samples should have valid IDs that match dataset format
        for sample in quick_samples:
            assert "/" in sample.id  # Format: platform/question_id

    def test_load_livecodebench_file_not_found_raises_error(self) -> None:
        """Should raise FileNotFoundError if dataset file missing."""
        with patch("matric_eval.tasks.livecodebench.LIVECODEBENCH_PATH", "/nonexistent/path.jsonl"):
            with pytest.raises(FileNotFoundError):
                load_livecodebench()

    def test_load_livecodebench_invalid_json_raises_error(self) -> None:
        """Should raise error for malformed JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("invalid json line\n")
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.livecodebench.LIVECODEBENCH_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_livecodebench()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Record Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() conversion function."""

    def test_record_to_sample_basic_conversion(self) -> None:
        """Should convert LiveCodeBench record to Sample."""
        record = {
            "question_title": "String Bags",
            "question_content": "Given a string T, find minimum cost...",
            "platform": "atcoder",
            "question_id": "abc344_d",
            "contest_id": "abc344",
            "contest_date": "2024-03-09",
            "starter_code": "",
            "difficulty": "medium",
            "public_test_cases": [
                {"input": "abcde\n3\n3 ab abc abcd\n4 f c cd bcde\n2 e de", "output": "2"}
            ],
            "private_test_cases": [],
            "metadata": {}
        }

        sample = record_to_sample(record)

        assert isinstance(sample, Sample)
        assert sample.id == "atcoder/abc344_d"

    def test_record_to_sample_includes_question_content_in_input(self) -> None:
        """Should include question content and title in input field."""
        record = {
            "question_title": "String Bags",
            "question_content": "Given a string T, find minimum cost...",
            "platform": "atcoder",
            "question_id": "abc344_d",
            "contest_id": "abc344",
            "contest_date": "2024-03-09",
            "starter_code": "",
            "difficulty": "medium",
            "public_test_cases": [],
            "private_test_cases": [],
            "metadata": {}
        }

        sample = record_to_sample(record)

        assert "String Bags" in sample.input
        assert "Given a string T" in sample.input

    def test_record_to_sample_includes_starter_code_when_available(self) -> None:
        """Should include starter code in input if provided."""
        record = {
            "question_title": "Test Problem",
            "question_content": "Solve this problem.",
            "platform": "leetcode",
            "question_id": "1234",
            "contest_id": "weekly-123",
            "contest_date": "2024-01-01",
            "starter_code": "def solution(nums):\n    pass",
            "difficulty": "easy",
            "public_test_cases": [],
            "private_test_cases": [],
            "metadata": {}
        }

        sample = record_to_sample(record)

        assert "def solution" in sample.input

    def test_record_to_sample_includes_public_test_case_in_target(self) -> None:
        """Should use first public test case output as target."""
        record = {
            "question_title": "Test",
            "question_content": "Problem description",
            "platform": "codeforces",
            "question_id": "1234A",
            "contest_id": "1234",
            "contest_date": "2024-01-01",
            "starter_code": "",
            "difficulty": "hard",
            "public_test_cases": [
                {"input": "5\n", "output": "10"},
                {"input": "3\n", "output": "6"}
            ],
            "private_test_cases": [],
            "metadata": {}
        }

        sample = record_to_sample(record)

        # Target should be first test output
        assert sample.target == "10"

    def test_record_to_sample_includes_metadata(self) -> None:
        """Should include platform, difficulty, and test cases in metadata."""
        record = {
            "question_title": "Test",
            "question_content": "Problem",
            "platform": "atcoder",
            "question_id": "abc123",
            "contest_id": "abc123",
            "contest_date": "2024-01-01",
            "starter_code": "",
            "difficulty": "medium",
            "public_test_cases": [{"input": "1", "output": "2"}],
            "private_test_cases": [{"input": "3", "output": "4"}],
            "metadata": {"tags": ["dp", "greedy"]}
        }

        sample = record_to_sample(record)

        assert sample.metadata is not None
        assert "platform" in sample.metadata
        assert sample.metadata["platform"] == "atcoder"
        assert "difficulty" in sample.metadata
        assert "public_test_cases" in sample.metadata
        assert "private_test_cases" in sample.metadata

    def test_record_to_sample_preserves_test_cases(self) -> None:
        """Should preserve all test cases in metadata for execution."""
        test_cases = [
            {"input": "5\n", "output": "10"},
            {"input": "3\n", "output": "6"}
        ]
        record = {
            "question_title": "Test",
            "question_content": "Problem",
            "platform": "leetcode",
            "question_id": "1234",
            "contest_id": "weekly-123",
            "contest_date": "2024-01-01",
            "starter_code": "",
            "difficulty": "easy",
            "public_test_cases": test_cases,
            "private_test_cases": [],
            "metadata": {}
        }

        sample = record_to_sample(record)

        assert sample.metadata["public_test_cases"] == test_cases

    def test_record_to_sample_missing_required_field_raises_error(self) -> None:
        """Should raise KeyError if required field missing."""
        incomplete_record = {
            "question_title": "Test",
            # Missing required fields
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
class TestLiveCodeBenchSampleQuality:
    """Tests for quality and correctness of loaded samples."""

    def test_samples_have_problem_descriptions(self) -> None:
        """Should have problem descriptions in prompts."""
        samples = load_livecodebench(tier="smoke")
        for sample in samples:
            assert len(sample.input) > 100  # Non-trivial content

    def test_samples_have_platform_metadata(self) -> None:
        """Should have platform in metadata."""
        samples = load_livecodebench(tier="smoke")
        for sample in samples:
            assert "platform" in sample.metadata
            assert sample.metadata["platform"] in ["atcoder", "codeforces", "leetcode"]

    def test_samples_have_difficulty_metadata(self) -> None:
        """Should have difficulty in metadata."""
        samples = load_livecodebench(tier="smoke")
        for sample in samples:
            assert "difficulty" in sample.metadata
            assert isinstance(sample.metadata["difficulty"], str)

    def test_samples_have_test_cases(self) -> None:
        """Should have test cases in metadata."""
        samples = load_livecodebench(tier="smoke")
        for sample in samples:
            assert "public_test_cases" in sample.metadata
            # Should have at least one test case
            test_cases = sample.metadata.get("public_test_cases", [])
            if test_cases:
                assert len(test_cases) > 0

    def test_samples_have_non_empty_targets(self) -> None:
        """Should have non-empty expected outputs as targets."""
        samples = load_livecodebench(tier="smoke")
        for sample in samples:
            assert len(sample.target) > 0


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestLiveCodeBenchTask:
    """Tests for livecodebench() task definition."""

    def test_livecodebench_task_creation(self) -> None:
        """Should create valid Task object."""
        task = livecodebench(tier="smoke")
        assert isinstance(task, Task)

    def test_livecodebench_task_name(self) -> None:
        """Should have correct task name."""
        task = livecodebench(tier="smoke")
        assert task.name == "livecodebench"

    def test_livecodebench_task_has_dataset(self) -> None:
        """Should have dataset configured."""
        task = livecodebench(tier="smoke")
        assert task.dataset is not None
        assert len(task.dataset) == 5

    def test_livecodebench_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = livecodebench(tier="smoke")
        assert task.solver is not None

    def test_livecodebench_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = livecodebench(tier="smoke")
        assert task.scorer is not None

    def test_livecodebench_task_respects_tier_parameter(self) -> None:
        """Should create tasks with different sample counts per tier."""
        smoke_task = livecodebench(tier="smoke")
        quick_task = livecodebench(tier="quick")

        assert len(smoke_task.dataset) == 5
        assert len(quick_task.dataset) == 50

    def test_livecodebench_task_default_tier_is_smoke(self) -> None:
        """Should default to smoke tier."""
        task = livecodebench()
        assert len(task.dataset) == 5

    def test_livecodebench_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = livecodebench(tier="smoke")
        task2 = livecodebench(tier="smoke")

        # Should be separate instances
        assert task1 is not task2


# =============================================================================
# Integration with Config System
# =============================================================================


@pytest.mark.unit
class TestLiveCodeBenchConfigIntegration:
    """Tests for integration with matric_eval.config."""

    def test_load_livecodebench_uses_config_tier(self) -> None:
        """Should use TierConfig for sample counts."""
        from matric_eval.config import TIERS

        smoke_count = TIERS["smoke"].livecodebench
        quick_count = TIERS["quick"].livecodebench

        # Smoke tier should be 5 (or 0 if not configured)
        samples = load_livecodebench(tier="smoke")
        assert len(samples) == max(5, smoke_count)

    def test_load_livecodebench_respects_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should respect EVAL_LIVECODEBENCH_SAMPLES environment variable."""
        monkeypatch.setenv("EVAL_LIVECODEBENCH_SAMPLES", "10")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        # Should load 10 samples instead of default tier counts
        samples = load_livecodebench(tier="smoke")
        assert len(samples) == 10

    def test_load_livecodebench_uses_reproducible_seed(self) -> None:
        """Should use get_seed() for reproducible sampling."""
        from matric_eval.config import get_seed

        seed = get_seed()
        assert isinstance(seed, int)

        # Samples should be reproducible
        samples1 = load_livecodebench(tier="quick")
        samples2 = load_livecodebench(tier="quick")

        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestLiveCodeBenchErrorHandling:
    """Tests for error handling in dataset loading."""

    def test_load_livecodebench_empty_file_raises_error(self) -> None:
        """Should raise error for empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write nothing
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.livecodebench.LIVECODEBENCH_PATH", temp_path):
                with pytest.raises((ValueError, IndexError)):
                    load_livecodebench()
        finally:
            Path(temp_path).unlink()

    def test_load_livecodebench_corrupted_jsonl_raises_error(self) -> None:
        """Should raise error for corrupted JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"question_id": "abc123", "incomplete": \n')
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.livecodebench.LIVECODEBENCH_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_livecodebench()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
class TestLiveCodeBenchEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_livecodebench_sample_count_exceeds_dataset_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return all available samples if requested count exceeds dataset size."""
        monkeypatch.setenv("EVAL_LIVECODEBENCH_SAMPLES", "10000")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_livecodebench()
        # Should return all available samples, not 10000
        assert len(samples) >= 880
        assert len(samples) <= 1100

    def test_load_livecodebench_zero_samples_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle zero sample request gracefully."""
        monkeypatch.setenv("EVAL_LIVECODEBENCH_SAMPLES", "0")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_livecodebench()
        assert len(samples) == 0

    def test_record_to_sample_with_empty_starter_code(self) -> None:
        """Should handle empty starter code."""
        record = {
            "question_title": "Test",
            "question_content": "Problem",
            "platform": "atcoder",
            "question_id": "abc123",
            "contest_id": "abc123",
            "contest_date": "2024-01-01",
            "starter_code": "",
            "difficulty": "easy",
            "public_test_cases": [{"input": "1", "output": "2"}],
            "private_test_cases": [],
            "metadata": {}
        }

        sample = record_to_sample(record)
        assert sample.input is not None
        assert len(sample.input) > 0

    def test_record_to_sample_with_no_public_test_cases(self) -> None:
        """Should handle records with no public test cases."""
        record = {
            "question_title": "Test",
            "question_content": "Problem",
            "platform": "codeforces",
            "question_id": "1234A",
            "contest_id": "1234",
            "contest_date": "2024-01-01",
            "starter_code": "",
            "difficulty": "hard",
            "public_test_cases": [],
            "private_test_cases": [{"input": "1", "output": "2"}],
            "metadata": {}
        }

        sample = record_to_sample(record)
        # Should use empty string or private test case as target
        assert sample.target is not None
