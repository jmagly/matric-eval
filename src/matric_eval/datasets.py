"""
Dataset loading with reproducible seeded sampling.

Mirrors matric-cli's approach:
1. Load full dataset
2. Seed RNG for reproducibility
3. Sample N items based on tier

Extended (issue #37, ADR-005):
- HuggingFace Hub loading via `datasets` library
- Parquet loading via PyArrow
- Reservoir sampling for streaming datasets
- Per-benchmark env var path overrides
- SHA-256 integrity checksums
"""

import hashlib
import os
import random
from pathlib import Path
from typing import Any, Callable, Sequence

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


# =============================================================================
# Extended Dataset Management (Issue #37, ADR-005)
# =============================================================================


def get_dataset_path(benchmark: str) -> str | None:
    """Check for per-benchmark dataset path override via environment variable.

    Checks: MATRIC_EVAL_{BENCHMARK}_DATA_PATH
    Example: MATRIC_EVAL_HUMANEVAL_DATA_PATH=/custom/path

    Args:
        benchmark: Benchmark name (case-insensitive)

    Returns:
        Path string if override is set, None otherwise
    """
    env_var = f"MATRIC_EVAL_{benchmark.upper()}_DATA_PATH"
    return os.environ.get(env_var)


def reservoir_sample(iterator: Any, k: int, seed: int = 42) -> list:
    """Reservoir sampling (Vitter's Algorithm R) for streaming datasets.

    Selects k items uniformly at random from an iterator of unknown length
    in a single pass with O(k) memory.

    Args:
        iterator: Any iterable to sample from
        k: Number of items to sample
        seed: Random seed for reproducibility

    Returns:
        List of k sampled items (or fewer if iterator is shorter)
    """
    if k <= 0:
        return []

    rng = random.Random(seed)
    reservoir: list = []

    for i, item in enumerate(iterator):
        if i < k:
            reservoir.append(item)
        else:
            j = rng.randint(0, i)
            if j < k:
                reservoir[j] = item

    return reservoir


def compute_checksum(path: str | Path) -> str:
    """Compute SHA-256 checksum of a file.

    Args:
        path: Path to file

    Returns:
        Hex-encoded SHA-256 digest string (64 characters)
    """
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def verify_checksum(path: str | Path, expected: str) -> bool:
    """Verify a file matches an expected SHA-256 checksum.

    Args:
        path: Path to file
        expected: Expected hex-encoded SHA-256 digest

    Returns:
        True if checksum matches, False otherwise
    """
    return compute_checksum(path) == expected


def generate_checksum_manifest(directory: str | Path) -> dict[str, str]:
    """Generate SHA-256 checksums for all files in a directory.

    Recursively walks the directory and computes checksums for every file.

    Args:
        directory: Path to directory

    Returns:
        Dict mapping relative file paths to SHA-256 hex digests
    """
    directory = Path(directory)
    manifest: dict[str, str] = {}
    for file_path in sorted(directory.rglob("*")):
        if file_path.is_file():
            rel_path = str(file_path.relative_to(directory))
            manifest[rel_path] = compute_checksum(file_path)
    return manifest


def _read_parquet_table(path: str | Path) -> Any:
    """Read a Parquet file via PyArrow.

    Isolated for mockability in tests.

    Raises:
        ImportError: If pyarrow is not installed
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError(
            "PyArrow is required for Parquet loading. "
            "Install it with: pip install pyarrow"
        )
    return pq.read_table(str(path))


def load_parquet(
    path: str | Path,
    *,
    sample_count: int | None = None,
    seed: int = 42,
    record_to_sample: Callable | None = None,
) -> list[Sample]:
    """Load dataset from a local Parquet file.

    Args:
        path: Path to .parquet file
        sample_count: Number of samples to return (None = all)
        seed: Random seed for reproducible sampling
        record_to_sample: Optional function to convert records to Samples

    Returns:
        List of Sample objects
    """
    table = _read_parquet_table(path)
    records = table.to_pylist()

    # Apply sampling if needed
    if sample_count is not None and sample_count < len(records):
        rng = random.Random(seed)
        records = rng.sample(records, sample_count)

    # Convert records to Samples
    if record_to_sample is not None:
        return [record_to_sample(r) for r in records]

    # Default: treat records as dicts with 'input' and 'target' keys
    return [
        Sample(
            input=str(r.get("input", "")),
            target=str(r.get("target", "")),
            id=str(r.get("id", "")),
        )
        for r in records
    ]


def load_hf_dataset(
    dataset_id: str,
    *,
    split: str = "test",
    subset: str | None = None,
    sample_count: int | None = None,
    seed: int = 42,
    streaming: bool = False,
    record_to_sample: Callable | None = None,
) -> list[Sample]:
    """Load a dataset from HuggingFace Hub.

    Args:
        dataset_id: HF dataset identifier (e.g., "openai/humaneval")
        split: Dataset split to load (default: "test")
        subset: Optional subset/config name
        sample_count: Number of samples to return (None = all)
        seed: Random seed for reproducible sampling
        streaming: Use streaming mode for huge datasets
        record_to_sample: Optional function to convert records to Samples

    Returns:
        List of Sample objects

    Raises:
        ImportError: If the `datasets` library is not installed
    """
    try:
        import datasets as hf_datasets
    except ImportError:
        raise ImportError(
            "The 'datasets' library is required for HuggingFace Hub loading. "
            "Install it with: pip install datasets"
        )

    # Build load_dataset kwargs
    load_kwargs: dict[str, Any] = {"split": split}
    if subset is not None:
        load_kwargs["name"] = subset
    if streaming:
        load_kwargs["streaming"] = True

    ds = hf_datasets.load_dataset(dataset_id, **load_kwargs)

    # For streaming datasets, use reservoir sampling
    if streaming and sample_count is not None:
        if record_to_sample is not None:
            sampled_records = reservoir_sample(ds, k=sample_count, seed=seed)
            return [record_to_sample(r) for r in sampled_records]
        else:
            sampled_records = reservoir_sample(ds, k=sample_count, seed=seed)
            return [
                Sample(
                    input=str(r.get("input", "")),
                    target=str(r.get("target", "")),
                )
                for r in sampled_records
            ]

    # Non-streaming: convert all records
    all_records = list(ds)

    if record_to_sample is not None:
        all_samples = [record_to_sample(r) for r in all_records]
    else:
        all_samples = [
            Sample(
                input=str(r.get("input", "")),
                target=str(r.get("target", "")),
            )
            for r in all_records
        ]

    # Apply sampling if needed
    if sample_count is not None and sample_count < len(all_samples):
        rng = random.Random(seed)
        all_samples = rng.sample(all_samples, sample_count)

    return all_samples
