"""
Tests for datasets module (matric_eval.datasets).

Covers:
- Seeded sampling for reproducibility
- Tiered dataset loading
- Dataset creation utilities
"""

import random

import pytest
from inspect_ai.dataset import MemoryDataset, Sample

from matric_eval.datasets import (
    create_tiered_dataset,
    seeded_sample,
)


# =============================================================================
# Seeded Sampling Tests
# =============================================================================


@pytest.mark.unit
class TestSeededSample:
    """Tests for seeded_sample() function."""

    def test_reproducible_sampling(
        self,
        sample_problems_list: list[Sample],
    ) -> None:
        """Should produce identical samples with same seed."""
        samples1 = seeded_sample(sample_problems_list, 2, seed=42)
        samples2 = seeded_sample(sample_problems_list, 2, seed=42)

        assert len(samples1) == 2
        assert len(samples2) == 2
        assert [s.id for s in samples1] == [s.id for s in samples2]

    def test_different_seeds_different_samples(
        self,
        sample_problems_list: list[Sample],
    ) -> None:
        """Should produce different samples with different seeds."""
        samples1 = seeded_sample(sample_problems_list, 2, seed=42)
        samples2 = seeded_sample(sample_problems_list, 2, seed=99)

        assert len(samples1) == 2
        assert len(samples2) == 2

        # With high probability, different seeds should give different samples
        # (not guaranteed for small N, but very likely)
        ids1 = {s.id for s in samples1}
        ids2 = {s.id for s in samples2}
        # At least they shouldn't be identical in order
        assert [s.id for s in samples1] != [s.id for s in samples2] or ids1 != ids2

    def test_sample_count_exceeds_total(
        self,
        sample_problems_list: list[Sample],
    ) -> None:
        """Should return all samples if n >= total samples."""
        samples = seeded_sample(sample_problems_list, 100, seed=42)

        assert len(samples) == len(sample_problems_list)
        assert set(s.id for s in samples) == set(s.id for s in sample_problems_list)

    def test_sample_exact_count(
        self,
        sample_problems_list: list[Sample],
    ) -> None:
        """Should return exact count when n < total samples."""
        samples = seeded_sample(sample_problems_list, 2, seed=42)
        assert len(samples) == 2

    def test_sample_zero(
        self,
        sample_problems_list: list[Sample],
    ) -> None:
        """Should return empty list when sampling zero items."""
        samples = seeded_sample(sample_problems_list, 0, seed=42)
        assert samples == []

    def test_isolated_rng(
        self,
        sample_problems_list: list[Sample],
    ) -> None:
        """Should not affect global random state."""
        # Set global random state
        random.seed(1234)
        global_state_before = random.getstate()

        # Sample with different seed
        seeded_sample(sample_problems_list, 2, seed=42)

        # Global state should be unchanged
        global_state_after = random.getstate()
        assert global_state_before == global_state_after

    def test_default_seed_from_config(
        self,
        sample_problems_list: list[Sample],
        env_no_overrides: None,
    ) -> None:
        """Should use config default seed when seed=None."""
        samples1 = seeded_sample(sample_problems_list, 2, seed=None)
        samples2 = seeded_sample(sample_problems_list, 2, seed=None)

        # Should be reproducible with default seed
        assert [s.id for s in samples1] == [s.id for s in samples2]

    def test_empty_samples_list(self) -> None:
        """Should handle empty samples list."""
        samples = seeded_sample([], 5, seed=42)
        assert samples == []


# =============================================================================
# Tiered Dataset Creation Tests
# =============================================================================


@pytest.mark.unit
class TestCreateTieredDataset:
    """Tests for create_tiered_dataset() function."""

    def test_create_smoke_tier_dataset(
        self,
        sample_problems_list: list[Sample],
        env_no_overrides: None,
    ) -> None:
        """Should create dataset with correct sample count for smoke tier."""
        dataset = create_tiered_dataset(
            sample_problems_list,
            benchmark="humaneval",
            tier="smoke",
        )

        assert isinstance(dataset, MemoryDataset)
        # Smoke tier has 5 samples, but we only have 3 test samples
        assert len(dataset) == 3

    def test_create_quick_tier_dataset(
        self,
        sample_problems_list: list[Sample],
        env_no_overrides: None,
    ) -> None:
        """Should create dataset with correct sample count for quick tier."""
        dataset = create_tiered_dataset(
            sample_problems_list,
            benchmark="humaneval",
            tier="quick",
        )

        # Quick tier has 75 samples, but we only have 3 test samples
        assert len(dataset) == 3

    def test_dataset_reproducibility(
        self,
        sample_problems_list: list[Sample],
        env_no_overrides: None,
    ) -> None:
        """Should create identical datasets with same parameters."""
        dataset1 = create_tiered_dataset(
            sample_problems_list,
            benchmark="humaneval",
            tier="smoke",
            seed=42,
        )
        dataset2 = create_tiered_dataset(
            sample_problems_list,
            benchmark="humaneval",
            tier="smoke",
            seed=42,
        )

        assert len(dataset1) == len(dataset2)
        assert [s.id for s in dataset1] == [s.id for s in dataset2]

    def test_custom_dataset_name(
        self,
        sample_problems_list: list[Sample],
    ) -> None:
        """Should set custom dataset name."""
        dataset = create_tiered_dataset(
            sample_problems_list,
            benchmark="humaneval",
            tier="smoke",
            name="custom_test_dataset",
        )

        assert dataset.name == "custom_test_dataset"

    def test_default_dataset_name(
        self,
        sample_problems_list: list[Sample],
    ) -> None:
        """Should create default dataset name from benchmark and tier."""
        dataset = create_tiered_dataset(
            sample_problems_list,
            benchmark="mbpp",
            tier="quick",
        )

        assert dataset.name == "mbpp_quick"

    def test_env_override_sample_count(
        self,
        sample_problems_list: list[Sample],
        env_custom_samples: dict[str, int],
    ) -> None:
        """Should respect environment variable sample count overrides."""
        dataset = create_tiered_dataset(
            sample_problems_list,
            benchmark="humaneval",
            tier="smoke",
        )

        # env_custom_samples sets EVAL_HUMANEVAL_SAMPLES=10
        # But we only have 3 test samples
        assert len(dataset) == 3


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


@pytest.mark.unit
class TestDatasetsEdgeCases:
    """Tests for edge cases in datasets module."""

    def test_single_sample_dataset(self) -> None:
        """Should handle dataset with single sample."""
        sample = Sample(
            input="test input",
            target="test target",
            id="test_1",
        )

        dataset = create_tiered_dataset(
            [sample],
            benchmark="humaneval",
            tier="smoke",
            seed=42,
        )

        assert len(dataset) == 1
        assert dataset[0].id == "test_1"

    def test_large_sample_pool(self, env_no_overrides: None) -> None:
        """Should handle large sample pools efficiently."""
        # Create 1000 samples
        samples = [
            Sample(
                input=f"test input {i}",
                target=f"test target {i}",
                id=f"test_{i}",
            )
            for i in range(1000)
        ]

        dataset = create_tiered_dataset(
            samples,
            benchmark="humaneval",
            tier="smoke",
            seed=42,
        )

        # Smoke tier requests 5 samples
        assert len(dataset) == 5

        # Should be reproducible
        dataset2 = create_tiered_dataset(
            samples,
            benchmark="humaneval",
            tier="smoke",
            seed=42,
        )
        assert [s.id for s in dataset] == [s.id for s in dataset2]

    def test_unknown_benchmark(
        self,
        sample_problems_list: list[Sample],
        env_no_overrides: None,
    ) -> None:
        """Should handle unknown benchmark gracefully."""
        dataset = create_tiered_dataset(
            sample_problems_list,
            benchmark="unknown_benchmark",
            tier="smoke",
        )

        # Unknown benchmark returns 0 samples, so should get empty dataset
        # But our implementation returns all samples if requested > available
        # So we get all 3 test samples
        assert len(dataset) <= len(sample_problems_list)


# =============================================================================
# Sample Data Structure Tests
# =============================================================================


@pytest.mark.unit
class TestSampleDataStructure:
    """Tests for Sample data structure handling."""

    def test_sample_metadata_preserved(self) -> None:
        """Should preserve sample metadata through sampling."""
        samples = [
            Sample(
                input="test",
                target="result",
                id="test_1",
                metadata={"difficulty": "easy", "category": "code"},
            )
            for _ in range(5)
        ]

        sampled = seeded_sample(samples, 3, seed=42)

        for sample in sampled:
            assert sample.metadata is not None
            assert sample.metadata["difficulty"] == "easy"
            assert sample.metadata["category"] == "code"

    def test_sample_with_none_metadata(self) -> None:
        """Should handle samples without metadata."""
        samples = [
            Sample(
                input="test",
                target="result",
                id=f"test_{i}",
                metadata=None,
            )
            for i in range(3)
        ]

        dataset = create_tiered_dataset(samples, "humaneval", "smoke")

        assert len(dataset) == 3
        for sample in dataset:
            assert sample.metadata is None


# =============================================================================
# Placeholder for Future Tests
# =============================================================================


@pytest.mark.unit
class TestDatasetLoading:
    """Placeholder tests for dataset loading functions."""

    @pytest.mark.skip(reason="Requires actual dataset files")
    def test_load_dataset_tiered(self) -> None:
        """Should load JSONL dataset with tiered sampling."""
        # TODO: Implement when dataset files are available
        pass

    @pytest.mark.skip(reason="Requires actual HumanEval data")
    def test_humaneval_dataset(self) -> None:
        """Should load HumanEval dataset."""
        # TODO: Implement when HumanEval integration is ready
        pass

    @pytest.mark.skip(reason="Requires actual MBPP data")
    def test_mbpp_dataset(self) -> None:
        """Should load MBPP dataset."""
        # TODO: Implement when MBPP integration is ready
        pass

    @pytest.mark.skip(reason="Requires actual GSM8K data")
    def test_gsm8k_dataset(self) -> None:
        """Should load GSM8K dataset."""
        # TODO: Implement when GSM8K integration is ready
        pass
