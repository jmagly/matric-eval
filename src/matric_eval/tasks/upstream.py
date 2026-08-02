"""Helpers for adapting maintained upstream Inspect tasks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import seeded_sample

INSPECT_EVALS_VERSION = "0.16.0"
INSPECT_EVALS_REVISION = "6a35510e530f236fd1dbcd9df888f01937c8494a"


def adapt_upstream_task(
    upstream: Task,
    *,
    benchmark: str,
    tier: str,
    task_name: str,
    protocol_metadata: Mapping[str, Any],
) -> Task:
    """Apply matric-eval tiering and provenance to an upstream Inspect task."""
    samples = list(upstream.dataset)
    sample_count = get_sample_count(benchmark, tier)
    if sample_count > 0 and sample_count < len(samples):
        samples = seeded_sample(samples, sample_count, get_seed())

    upstream.dataset = MemoryDataset(
        samples=samples,
        name=f"{task_name}_{tier}",
        location=upstream.dataset.location,
    )
    upstream._name = task_name
    upstream.metadata = {
        **(upstream.metadata or {}),
        **protocol_metadata,
        "matric_eval_tier": tier,
        "matric_eval_seed": get_seed(),
        "inspect_evals_version": INSPECT_EVALS_VERSION,
        "inspect_evals_revision": INSPECT_EVALS_REVISION,
    }
    return upstream
