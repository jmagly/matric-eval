"""
Tests for tasks module (matric_eval.tasks.smoke).

Covers:
- Smoke test data samples
- Task definitions
- Scorer configurations
"""

import pytest
from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset

from matric_eval.tasks.smoke import (
    GSM8K_SAMPLES,
    HUMANEVAL_SAMPLES,
    MBPP_SAMPLES,
    smoke_gsm8k,
    smoke_humaneval,
    smoke_mbpp,
    smoke_suite,
)


# =============================================================================
# Sample Data Tests
# =============================================================================


@pytest.mark.unit
class TestHumanEvalSamples:
    """Tests for HUMANEVAL_SAMPLES data."""

    def test_sample_count(self) -> None:
        """Should have exactly 5 HumanEval samples."""
        assert len(HUMANEVAL_SAMPLES) == 5

    def test_sample_structure(self) -> None:
        """Should have correct Sample structure."""
        for sample in HUMANEVAL_SAMPLES:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert sample.id.startswith("humaneval_")

    def test_sample_metadata(self) -> None:
        """Should have difficulty and category metadata."""
        for sample in HUMANEVAL_SAMPLES:
            assert sample.metadata is not None
            assert "difficulty" in sample.metadata
            assert "category" in sample.metadata
            assert sample.metadata["category"] == "code"

    def test_unique_ids(self) -> None:
        """Should have unique sample IDs."""
        ids = [s.id for s in HUMANEVAL_SAMPLES]
        assert len(ids) == len(set(ids))

    def test_variety_of_difficulties(self) -> None:
        """Should include multiple difficulty levels."""
        difficulties = {s.metadata["difficulty"] for s in HUMANEVAL_SAMPLES if s.metadata}
        assert "easy" in difficulties
        assert "medium" in difficulties


@pytest.mark.unit
class TestMBPPSamples:
    """Tests for MBPP_SAMPLES data."""

    def test_sample_count(self) -> None:
        """Should have exactly 5 MBPP samples."""
        assert len(MBPP_SAMPLES) == 5

    def test_sample_structure(self) -> None:
        """Should have correct Sample structure."""
        for sample in MBPP_SAMPLES:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert sample.id.startswith("mbpp_")

    def test_function_name_metadata(self) -> None:
        """Should include function_name in metadata."""
        for sample in MBPP_SAMPLES:
            assert sample.metadata is not None
            assert "function_name" in sample.metadata
            assert sample.metadata["category"] == "code"

    def test_test_cases_in_prompts(self) -> None:
        """Should include test cases in prompts."""
        for sample in MBPP_SAMPLES:
            assert "assert" in sample.input.lower()
            assert "test cases" in sample.input.lower()

    def test_unique_ids(self) -> None:
        """Should have unique sample IDs."""
        ids = [s.id for s in MBPP_SAMPLES]
        assert len(ids) == len(set(ids))


@pytest.mark.unit
class TestGSM8KSamples:
    """Tests for GSM8K_SAMPLES data."""

    def test_sample_count(self) -> None:
        """Should have exactly 5 GSM8K samples."""
        assert len(GSM8K_SAMPLES) == 5

    def test_sample_structure(self) -> None:
        """Should have correct Sample structure."""
        for sample in GSM8K_SAMPLES:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert sample.id.startswith("gsm8k_")

    def test_numeric_targets(self) -> None:
        """Should have numeric string targets."""
        for sample in GSM8K_SAMPLES:
            # Targets should be numeric strings
            assert sample.target.isdigit() or sample.target.replace(".", "", 1).isdigit()

    def test_math_category(self) -> None:
        """Should have math category metadata."""
        for sample in GSM8K_SAMPLES:
            assert sample.metadata is not None
            assert sample.metadata["category"] == "math"

    def test_problem_prompts(self) -> None:
        """Should include 'Think step by step' in prompts."""
        for sample in GSM8K_SAMPLES:
            assert "think step by step" in sample.input.lower()

    def test_unique_ids(self) -> None:
        """Should have unique sample IDs."""
        ids = [s.id for s in GSM8K_SAMPLES]
        assert len(ids) == len(set(ids))


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestSmokeHumanEvalTask:
    """Tests for smoke_humaneval() task."""

    def test_task_creation(self) -> None:
        """Should create valid Task object."""
        task = smoke_humaneval()
        assert isinstance(task, Task)

    def test_task_dataset(self) -> None:
        """Should use HumanEval samples."""
        task = smoke_humaneval()
        assert isinstance(task.dataset, MemoryDataset)
        assert len(task.dataset) == 5

    def test_task_name(self) -> None:
        """Should have correct task name."""
        task = smoke_humaneval()
        assert task.name == "humaneval_smoke"

    def test_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = smoke_humaneval()
        assert task.solver is not None
        assert len(task.solver) > 0

    def test_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = smoke_humaneval()
        assert task.scorer is not None


@pytest.mark.unit
class TestSmokeMBPPTask:
    """Tests for smoke_mbpp() task."""

    def test_task_creation(self) -> None:
        """Should create valid Task object."""
        task = smoke_mbpp()
        assert isinstance(task, Task)

    def test_task_dataset(self) -> None:
        """Should use MBPP samples."""
        task = smoke_mbpp()
        assert isinstance(task.dataset, MemoryDataset)
        assert len(task.dataset) == 5

    def test_task_name(self) -> None:
        """Should have correct task name."""
        task = smoke_mbpp()
        assert task.name == "mbpp_smoke"

    def test_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = smoke_mbpp()
        assert task.solver is not None
        assert len(task.solver) > 0

    def test_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = smoke_mbpp()
        assert task.scorer is not None


@pytest.mark.unit
class TestSmokeGSM8KTask:
    """Tests for smoke_gsm8k() task."""

    def test_task_creation(self) -> None:
        """Should create valid Task object."""
        task = smoke_gsm8k()
        assert isinstance(task, Task)

    def test_task_dataset(self) -> None:
        """Should use GSM8K samples."""
        task = smoke_gsm8k()
        assert isinstance(task.dataset, MemoryDataset)
        assert len(task.dataset) == 5

    def test_task_name(self) -> None:
        """Should have correct task name."""
        task = smoke_gsm8k()
        assert task.name == "gsm8k_smoke"

    def test_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = smoke_gsm8k()
        assert task.solver is not None
        assert len(task.solver) > 0

    def test_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = smoke_gsm8k()
        assert task.scorer is not None


@pytest.mark.unit
class TestSmokeSuiteTask:
    """Tests for smoke_suite() combined task."""

    def test_task_creation(self) -> None:
        """Should create valid Task object."""
        task = smoke_suite()
        assert isinstance(task, Task)

    def test_task_dataset(self) -> None:
        """Should combine all smoke samples."""
        task = smoke_suite()
        assert isinstance(task.dataset, MemoryDataset)
        # Should have 5 + 5 + 5 = 15 total samples
        assert len(task.dataset) == 15

    def test_task_name(self) -> None:
        """Should have correct task name."""
        task = smoke_suite()
        assert task.name == "smoke_suite"

    def test_combined_samples(self) -> None:
        """Should include samples from all benchmarks."""
        task = smoke_suite()
        sample_ids = [s.id for s in task.dataset]

        # Should have samples from each benchmark
        humaneval_count = sum(1 for sid in sample_ids if sid.startswith("humaneval_"))
        mbpp_count = sum(1 for sid in sample_ids if sid.startswith("mbpp_"))
        gsm8k_count = sum(1 for sid in sample_ids if sid.startswith("gsm8k_"))

        assert humaneval_count == 5
        assert mbpp_count == 5
        assert gsm8k_count == 5


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
class TestSampleContentQuality:
    """Tests for quality of sample content."""

    def test_humaneval_samples_have_examples(self) -> None:
        """Should include example usage in prompts."""
        for sample in HUMANEVAL_SAMPLES:
            assert "example" in sample.input.lower() or ">>>" in sample.input

    def test_mbpp_samples_have_assertions(self) -> None:
        """Should include test assertions."""
        for sample in MBPP_SAMPLES:
            assert "assert" in sample.input

    def test_gsm8k_samples_are_word_problems(self) -> None:
        """Should be word problems with numeric answers."""
        for sample in GSM8K_SAMPLES:
            # Should have question structure
            assert len(sample.input) > 20
            # Should end with instruction
            assert "step by step" in sample.input.lower()
            # Should have numeric answer
            assert sample.target.replace(".", "", 1).replace("-", "", 1).isdigit()

    def test_all_samples_have_instructions(self) -> None:
        """Should have clear instructions in all samples."""
        all_samples = HUMANEVAL_SAMPLES + MBPP_SAMPLES + GSM8K_SAMPLES

        for sample in all_samples:
            # Should have substantial prompt
            assert len(sample.input) > 10
            # Should have target answer
            assert len(sample.target) > 0


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
class TestTasksEdgeCases:
    """Tests for edge cases in tasks module."""

    def test_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = smoke_humaneval()
        task2 = smoke_humaneval()

        # Should be separate instances
        assert task1 is not task2

    def test_sample_lists_immutability(self) -> None:
        """Should not mutate original sample lists."""
        original_humaneval_count = len(HUMANEVAL_SAMPLES)
        original_mbpp_count = len(MBPP_SAMPLES)
        original_gsm8k_count = len(GSM8K_SAMPLES)

        # Create tasks
        smoke_humaneval()
        smoke_mbpp()
        smoke_gsm8k()
        smoke_suite()

        # Original lists should be unchanged
        assert len(HUMANEVAL_SAMPLES) == original_humaneval_count
        assert len(MBPP_SAMPLES) == original_mbpp_count
        assert len(GSM8K_SAMPLES) == original_gsm8k_count


# =============================================================================
# Placeholder for Future Integration Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.skip(reason="Requires Ollama running")
class TestTaskExecution:
    """Placeholder for task execution integration tests."""

    def test_run_humaneval_task(self) -> None:
        """Should execute HumanEval task against real model."""
        # TODO: Implement when integration test infrastructure ready
        pass

    def test_run_mbpp_task(self) -> None:
        """Should execute MBPP task against real model."""
        # TODO: Implement when integration test infrastructure ready
        pass

    def test_run_gsm8k_task(self) -> None:
        """Should execute GSM8K task against real model."""
        # TODO: Implement when integration test infrastructure ready
        pass
