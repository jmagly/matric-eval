"""
External dataset auto-discovery for matric-eval.

Scans the datasets directory for external evaluation datasets (git clones,
submodules, or manually created directories) and makes them available as
benchmarks with minimal to no configuration.

Convention over configuration:
- Drop a directory into datasets/ with .jsonl files → it works
- Optionally add dataset.yaml for control over scorer, prompts, tiers, field mapping
"""

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import match, includes, model_graded_fact, pattern
from inspect_ai.solver import generate, system_message
from pydantic import BaseModel, Field as PydanticField

logger = logging.getLogger(__name__)

# Directories to skip when scanning for external datasets
SKIP_DIRS = {"custom", "public"}

# Scorer name to factory mapping
SCORER_MAP: dict[str, Any] = {
    "match": match,
    "includes": includes,
    "model_graded_fact": model_graded_fact,
    "semantic_similarity": model_graded_fact,
    "pattern": pattern,
}

# Field name priority chains for auto-detection
INPUT_FIELD_PRIORITY = ["input", "prompt", "question"]
TARGET_FIELD_PRIORITY = ["target", "expected", "answer"]
ID_FIELD_PRIORITY = ["id", "task_id"]


# =============================================================================
# Manifest Models
# =============================================================================


class TierSampling(BaseModel):
    """Tier-based sampling configuration."""

    smoke: int = 10
    quick: int = 50
    full: int = 0  # 0 = all samples


class DatasetManifest(BaseModel):
    """Parsed dataset.yaml manifest with sensible defaults."""

    name: str | None = None
    description: str | None = None
    version: str | None = None
    scorer: str = "match"
    system_prompt: str = "You are a helpful assistant. Answer concisely."
    field_mapping: dict[str, str] = PydanticField(
        default_factory=lambda: {"input": "input", "target": "target", "id": "id"}
    )
    tiers: TierSampling = PydanticField(default_factory=TierSampling)
    metadata: dict[str, str] = PydanticField(default_factory=dict)


def load_manifest(manifest_path: Path) -> DatasetManifest:
    """
    Load and validate a dataset.yaml manifest file.

    Args:
        manifest_path: Path to dataset.yaml

    Returns:
        Parsed DatasetManifest with defaults for missing fields
    """
    with open(manifest_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return DatasetManifest(**data)


# =============================================================================
# Discovered Dataset
# =============================================================================


@dataclass
class DiscoveredDataset:
    """Represents a discovered external dataset."""

    name: str
    directory: Path
    manifest: DatasetManifest
    jsonl_files: list[Path]
    total_samples: int
    source_type: str  # "manifest" or "auto-detected"


# =============================================================================
# Field Detection
# =============================================================================


def detect_field_mapping(record: dict[str, Any]) -> dict[str, str]:
    """
    Auto-detect field mapping from the first JSONL record.

    Checks for known field names in priority order:
    - input: input > prompt > question
    - target: target > expected > answer
    - id: id > task_id > (auto-generate)

    Args:
        record: First record from a JSONL file

    Returns:
        Dict mapping canonical names (input, target, id) to actual field names
    """
    mapping: dict[str, str] = {}

    # Detect input field
    for field_name in INPUT_FIELD_PRIORITY:
        if field_name in record:
            mapping["input"] = field_name
            break

    # Detect target field
    for field_name in TARGET_FIELD_PRIORITY:
        if field_name in record:
            mapping["target"] = field_name
            break

    # Detect id field
    for field_name in ID_FIELD_PRIORITY:
        if field_name in record:
            mapping["id"] = field_name
            break

    return mapping


# =============================================================================
# Sample Loading
# =============================================================================


def _count_jsonl_lines(path: Path) -> int:
    """Count non-empty lines in a JSONL file."""
    count = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _read_first_record(path: Path) -> dict[str, Any] | None:
    """Read and parse the first non-empty line from a JSONL file."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    return None
    return None


def load_external_samples(
    jsonl_files: list[Path],
    field_mapping: dict[str, str],
    dataset_name: str,
) -> list[Sample]:
    """
    Load samples from JSONL files, applying field mapping.

    Args:
        jsonl_files: List of JSONL file paths to load
        field_mapping: Maps canonical names (input, target, id) to actual field names
        dataset_name: Dataset name for auto-generating IDs

    Returns:
        List of Inspect AI Sample objects
    """
    input_field = field_mapping.get("input", "input")
    target_field = field_mapping.get("target", "target")
    id_field = field_mapping.get("id")

    samples: list[Sample] = []
    global_idx = 0

    for jsonl_path in jsonl_files:
        with open(jsonl_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "Skipping malformed JSON in %s line %d", jsonl_path.name, line_num
                    )
                    continue

                # Extract input
                input_val = record.get(input_field)
                if input_val is None:
                    logger.warning(
                        "Missing '%s' field in %s line %d, skipping",
                        input_field, jsonl_path.name, line_num,
                    )
                    continue

                # Extract target
                target_val = record.get(target_field, "")
                if isinstance(target_val, (dict, list)):
                    target_val = json.dumps(target_val)
                else:
                    target_val = str(target_val)

                # Extract or generate ID
                if id_field and id_field in record:
                    sample_id = str(record[id_field])
                else:
                    sample_id = f"{dataset_name}_{global_idx}"

                # Collect remaining fields as metadata
                skip_fields = {input_field, target_field}
                if id_field:
                    skip_fields.add(id_field)
                metadata = {k: v for k, v in record.items() if k not in skip_fields}

                samples.append(Sample(
                    input=str(input_val),
                    target=target_val,
                    id=sample_id,
                    metadata=metadata,
                ))
                global_idx += 1

    return samples


# =============================================================================
# Task Factory
# =============================================================================


def _resolve_scorer(scorer_name: str) -> Any:
    """Resolve a scorer name to an Inspect AI scorer instance."""
    factory = SCORER_MAP.get(scorer_name)
    if factory is None:
        logger.warning("Unknown scorer '%s', falling back to match()", scorer_name)
        factory = match
    return factory()


def create_external_task(
    dataset: DiscoveredDataset,
    tier: str = "smoke",
) -> Task:
    """
    Create an Inspect AI Task from a discovered external dataset.

    Args:
        dataset: Discovered dataset metadata
        tier: Evaluation tier (smoke/quick/full)

    Returns:
        Configured Inspect AI Task
    """
    from matric_eval.config import get_seed

    manifest = dataset.manifest

    # Determine field mapping
    if manifest.field_mapping != {"input": "input", "target": "target", "id": "id"}:
        # Manifest specified explicit mapping
        mapping = manifest.field_mapping
    elif dataset.jsonl_files:
        # Auto-detect from first record
        first_record = _read_first_record(dataset.jsonl_files[0])
        if first_record:
            mapping = detect_field_mapping(first_record)
        else:
            mapping = {"input": "input", "target": "target", "id": "id"}
    else:
        mapping = {"input": "input", "target": "target", "id": "id"}

    # Load all samples
    all_samples = load_external_samples(dataset.jsonl_files, mapping, dataset.name)

    # Apply tier sampling
    tiers = manifest.tiers
    tier_count = getattr(tiers, tier, 0)

    if tier_count > 0 and tier_count < len(all_samples):
        seed = get_seed()
        rng = random.Random(seed)
        sampled = rng.sample(all_samples, tier_count)
        sampled.sort(key=lambda s: s.id)
    else:
        sampled = all_samples

    # Resolve scorer
    scorer = _resolve_scorer(manifest.scorer)

    return Task(
        dataset=sampled,
        solver=[
            system_message(manifest.system_prompt),
            generate(),
        ],
        scorer=scorer,
        name=dataset.name,
    )


# =============================================================================
# Scanner
# =============================================================================


def scan_datasets_dir(datasets_dir: Path) -> list[DiscoveredDataset]:
    """
    Scan a directory for external datasets.

    Iterates subdirectories looking for dataset.yaml manifests or bare JSONL files.
    Skips reserved directories (custom, public) and hidden directories.

    Args:
        datasets_dir: Root datasets directory to scan

    Returns:
        List of discovered datasets, sorted by name
    """
    if not datasets_dir.exists() or not datasets_dir.is_dir():
        return []

    discovered: list[DiscoveredDataset] = []

    for entry in sorted(datasets_dir.iterdir()):
        if not entry.is_dir():
            continue

        dir_name = entry.name

        # Skip reserved and hidden directories
        if dir_name in SKIP_DIRS or dir_name.startswith(".") or dir_name.startswith("_"):
            continue

        # Check for manifest
        manifest_path = entry / "dataset.yaml"
        if manifest_path.exists():
            try:
                manifest = load_manifest(manifest_path)
                source_type = "manifest"
            except Exception:
                logger.warning("Failed to parse %s, using defaults", manifest_path)
                manifest = DatasetManifest()
                source_type = "auto-detected"
        else:
            manifest = DatasetManifest()
            source_type = "auto-detected"

        # Use directory name if manifest doesn't specify a name
        if manifest.name is None:
            manifest.name = dir_name

        # Discover JSONL files
        jsonl_files = sorted(entry.glob("*.jsonl"))
        if not jsonl_files:
            # No JSONL files — check one level deep in common subdirs
            for subdir_name in ["data", "test", "eval"]:
                subdir = entry / subdir_name
                if subdir.is_dir():
                    jsonl_files.extend(sorted(subdir.glob("*.jsonl")))
            if not jsonl_files:
                continue  # No data found, skip

        # Count total samples
        total_samples = sum(_count_jsonl_lines(f) for f in jsonl_files)
        if total_samples == 0:
            continue

        # If auto-detected, try to detect field mapping from first file
        if source_type == "auto-detected" and jsonl_files:
            first_record = _read_first_record(jsonl_files[0])
            if first_record:
                detected = detect_field_mapping(first_record)
                if detected:
                    manifest.field_mapping = {
                        "input": detected.get("input", "input"),
                        "target": detected.get("target", "target"),
                        "id": detected.get("id", "id"),
                    }

        discovered.append(DiscoveredDataset(
            name=dir_name,
            directory=entry,
            manifest=manifest,
            jsonl_files=jsonl_files,
            total_samples=total_samples,
            source_type=source_type,
        ))

    return discovered


# =============================================================================
# Registry (lazy-initialized cache)
# =============================================================================

_registry: dict[str, DiscoveredDataset] | None = None


def _get_datasets_dir() -> Path:
    """Get the configured datasets directory."""
    from matric_eval.config import get_datasets_dir
    return Path(get_datasets_dir())


def get_external_datasets(force_rescan: bool = False) -> dict[str, DiscoveredDataset]:
    """
    Get all discovered external datasets (lazy-scanned on first call).

    Args:
        force_rescan: If True, rescan the directory even if cached

    Returns:
        Dict mapping dataset name to DiscoveredDataset
    """
    global _registry

    if _registry is None or force_rescan:
        datasets_dir = _get_datasets_dir()
        datasets = scan_datasets_dir(datasets_dir)
        _registry = {ds.name: ds for ds in datasets}

    return _registry


def get_external_dataset(name: str) -> DiscoveredDataset | None:
    """
    Get a single external dataset by name.

    Args:
        name: Dataset name (directory name)

    Returns:
        DiscoveredDataset or None if not found
    """
    return get_external_datasets().get(name)


def reset_registry() -> None:
    """Reset the registry cache. Useful for testing."""
    global _registry
    _registry = None
