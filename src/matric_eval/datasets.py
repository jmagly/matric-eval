"""
Dataset loading with reproducible seeded sampling.

Mirrors matric-cli's approach:
1. Load full dataset
2. Seed RNG for reproducibility
3. Sample N items based on tier
"""

import random
from pathlib import Path
from typing import Sequence

from inspect_ai.dataset import Sample, MemoryDataset, json_dataset

from .config import get_seed, get_sample_count


def seeded_sample(
    samples: Sequence[Sample],
    n: int,
    seed: int | None = None,
) -> list[Sample]:
    """
    Sample n items from samples with reproducible seeding.

    Args:
        samples: Full list of samples
        n: Number to sample (if > len(samples), returns all)
        seed: Random seed (default: from config/env)

    Returns:
        Reproducibly sampled list of n samples
    """
    if seed is None:
        seed = get_seed()

    if n >= len(samples):
        return list(samples)

    # Create isolated RNG to avoid affecting global state
    rng = random.Random(seed)
    return rng.sample(list(samples), n)


def load_dataset_tiered(
    dataset_path: str | Path,
    benchmark: str,
    tier: str = "smoke",
    seed: int | None = None,
) -> MemoryDataset:
    """
    Load a JSONL dataset with tiered sampling.

    Args:
        dataset_path: Path to .jsonl file
        benchmark: Benchmark name (humaneval, mbpp, gsm8k, etc.)
        tier: Evaluation tier (smoke, quick, full)
        seed: Override seed for sampling

    Returns:
        MemoryDataset with sampled data
    """
    if seed is None:
        seed = get_seed()

    n_samples = get_sample_count(benchmark, tier)

    # Use Inspect AI's json_dataset with built-in seed support
    return json_dataset(
        json_file=str(dataset_path),
        shuffle=True,
        seed=seed,
        limit=n_samples,
    )


def create_tiered_dataset(
    samples: Sequence[Sample],
    benchmark: str,
    tier: str = "smoke",
    seed: int | None = None,
    name: str | None = None,
) -> MemoryDataset:
    """
    Create a MemoryDataset with tiered sampling from in-memory samples.

    Args:
        samples: Full list of Sample objects
        benchmark: Benchmark name for tier lookup
        tier: Evaluation tier
        seed: Override seed
        name: Optional dataset name

    Returns:
        MemoryDataset with sampled data
    """
    n_samples = get_sample_count(benchmark, tier)
    sampled = seeded_sample(samples, n_samples, seed)

    return MemoryDataset(
        samples=sampled,
        name=name or f"{benchmark}_{tier}",
    )


# Convenience functions for common benchmarks
def humaneval_dataset(tier: str = "smoke", seed: int | None = None) -> MemoryDataset:
    """Load HumanEval with tiered sampling."""
    from .tasks.builtin import HUMANEVAL_SAMPLES
    return create_tiered_dataset(HUMANEVAL_SAMPLES, "humaneval", tier, seed)


def mbpp_dataset(tier: str = "smoke", seed: int | None = None) -> MemoryDataset:
    """Load MBPP with tiered sampling."""
    from .tasks.builtin import MBPP_SAMPLES
    return create_tiered_dataset(MBPP_SAMPLES, "mbpp", tier, seed)


def gsm8k_dataset(tier: str = "smoke", seed: int | None = None) -> MemoryDataset:
    """Load GSM8K with tiered sampling."""
    from .tasks.builtin import GSM8K_SAMPLES
    return create_tiered_dataset(GSM8K_SAMPLES, "gsm8k", tier, seed)
