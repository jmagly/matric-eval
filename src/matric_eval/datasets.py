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
import re
from pathlib import Path
from typing import Any, Callable, Sequence

from inspect_ai.dataset import MemoryDataset, Sample, json_dataset

from .config import get_sample_count, get_seed


class DatasetSourceError(RuntimeError):
    """Base error for remote dataset source failures."""


class DatasetAccessError(DatasetSourceError):
    """Dataset requires authentication or access approval."""


class DatasetRevisionError(DatasetSourceError):
    """Requested dataset revision is missing or not immutable."""


class DatasetOfflineError(DatasetSourceError):
    """Pinned dataset is unavailable from the local offline cache."""


_IMMUTABLE_HF_REVISION = re.compile(r"^[0-9a-f]{40,64}$", re.IGNORECASE)


def is_immutable_hf_revision(revision: str | None) -> bool:
    """Return whether a Hugging Face revision is a full commit hash."""
    return bool(revision and _IMMUTABLE_HF_REVISION.fullmatch(revision))


def _attach_dataset_provenance(
    samples: list[Sample],
    *,
    dataset_id: str,
    revision: str | None,
    subset: str | None,
    split: str,
) -> list[Sample]:
    for sample in samples:
        metadata = dict(sample.metadata or {})
        metadata.update(
            {
                "dataset_source": dataset_id,
                "dataset_revision": revision or "mutable:main",
                "dataset_config": subset,
                "dataset_split": split,
            }
        )
        sample.metadata = metadata
    return samples


def _raise_dataset_source_error(
    exc: Exception,
    *,
    dataset_id: str,
    revision: str | None,
    offline: bool,
) -> None:
    error_name = type(exc).__name__.lower()
    if offline:
        raise DatasetOfflineError(
            f"Pinned dataset {dataset_id}@{revision or 'main'} is not available "
            "in the offline cache"
        ) from exc
    if any(marker in error_name for marker in ("gated", "unauthorized", "forbidden")):
        raise DatasetAccessError(
            f"Dataset {dataset_id} requires Hugging Face authentication or access approval"
        ) from exc
    if "revision" in error_name:
        raise DatasetRevisionError(
            f"Dataset revision {dataset_id}@{revision or 'main'} does not exist"
        ) from exc
    if any(marker in error_name for marker in ("notfound", "not_found", "missing")):
        raise DatasetSourceError(f"Dataset source {dataset_id} does not exist") from exc
    raise exc


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
    revision: str | None = None,
    token: bool | str | None = None,
    cache_dir: str | Path | None = None,
    offline: bool = False,
    require_immutable_revision: bool = False,
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
        revision: Dataset commit hash or tag. Use a full hash for reproducible runs.
        token: Hugging Face token behavior. ``True`` uses the locally configured token.
            Token values are never retained in sample or result metadata.
        cache_dir: Optional deterministic cache root.
        offline: Restrict loading to files already present in the local cache.
        require_immutable_revision: Reject branches, tags, and missing revisions.

    Returns:
        List of Sample objects

    Raises:
        ImportError: If the `datasets` library is not installed
    """
    if require_immutable_revision and not is_immutable_hf_revision(revision):
        raise DatasetRevisionError(
            f"Dataset {dataset_id} requires an immutable full commit revision; got {revision!r}"
        )

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
    if revision is not None:
        load_kwargs["revision"] = revision
    if token is not None:
        load_kwargs["token"] = token
    if cache_dir is not None:
        load_kwargs["cache_dir"] = str(cache_dir)
    if offline:
        load_kwargs["download_config"] = hf_datasets.DownloadConfig(
            cache_dir=str(cache_dir) if cache_dir is not None else None,
            local_files_only=True,
        )

    try:
        ds = hf_datasets.load_dataset(dataset_id, **load_kwargs)
    except Exception as exc:
        _raise_dataset_source_error(
            exc,
            dataset_id=dataset_id,
            revision=revision,
            offline=offline,
        )
        raise AssertionError("unreachable") from exc

    # For streaming datasets, use reservoir sampling
    if streaming and sample_count is not None:
        if record_to_sample is not None:
            sampled_records = reservoir_sample(ds, k=sample_count, seed=seed)
            samples = [record_to_sample(r) for r in sampled_records]
            return _attach_dataset_provenance(
                samples,
                dataset_id=dataset_id,
                revision=revision,
                subset=subset,
                split=split,
            )
        else:
            sampled_records = reservoir_sample(ds, k=sample_count, seed=seed)
            samples = [
                Sample(
                    input=str(r.get("input", "")),
                    target=str(r.get("target", "")),
                )
                for r in sampled_records
            ]
            return _attach_dataset_provenance(
                samples,
                dataset_id=dataset_id,
                revision=revision,
                subset=subset,
                split=split,
            )

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

    return _attach_dataset_provenance(
        all_samples,
        dataset_id=dataset_id,
        revision=revision,
        subset=subset,
        split=split,
    )
