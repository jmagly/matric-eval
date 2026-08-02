"""Reproducibility metadata emitted with every evaluation result."""

from __future__ import annotations

import platform
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from matric_eval.tasks.registry import BenchmarkMetadata

PROVENANCE_SCHEMA_VERSION = "1"


def _package_version(distribution: str, fallback: str = "unknown") -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return fallback


def framework_provenance() -> dict[str, str]:
    """Return package/runtime versions that affect evaluation behavior."""
    return {
        "matric_eval": _package_version("matric-eval", "0.1.0"),
        "inspect_ai": _package_version("inspect-ai"),
        "inspect_evals": _package_version("inspect-evals"),
        "python": platform.python_version(),
    }


def benchmark_provenance(
    name: str,
    metadata: BenchmarkMetadata | None,
) -> dict[str, Any]:
    """Serialize registry metadata without leaking runtime credentials."""
    benchmark: dict[str, Any] = {"name": name}
    if metadata is not None:
        fields = (
            "protocol_version",
            "dataset_source",
            "dataset_revision",
            "evaluator_source",
            "evaluator_revision",
            "release_date",
            "license",
            "prompt_revision",
            "container_revision",
            "latest_protocol_version",
            "successor",
        )
        benchmark.update(
            {field: getattr(metadata, field) for field in fields if getattr(metadata, field)}
        )
        benchmark.update(
            {
                "status": metadata.status.value,
                "category": metadata.category.value,
                "access": metadata.access.value if metadata.access else None,
                "source_kind": metadata.source_kind.value if metadata.source_kind else None,
                "release_policy": (
                    metadata.release_policy.value if metadata.release_policy else None
                ),
                "dataset_configs": list(metadata.dataset_configs),
                "dataset_splits": list(metadata.dataset_splits),
            }
        )
        benchmark = {key: value for key, value in benchmark.items() if value not in (None, [], ())}

    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "framework": framework_provenance(),
        "benchmark": benchmark,
    }
