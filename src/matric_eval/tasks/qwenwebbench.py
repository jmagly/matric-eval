"""Quarantined QwenWebBench integration scaffold.

No canonical public dataset and evaluator are currently available. The task is
kept visible in the registry, but execution and scoring are disabled until a
reproducible upstream protocol can be pinned.
"""

from __future__ import annotations

from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Scorer, scorer

from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

QWENWEBBENCH_UNAVAILABLE_REASON = (
    "no canonical public dataset, license, renderer, pairwise evaluator, "
    "or reproducible Elo protocol has been verified"
)


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a QwenWebBench record to an Inspect AI Sample."""
    task_id = record.get("task_id", record.get("id", ""))
    spec = record.get("specification", record.get("input", ""))
    reference = record.get("reference_html", record.get("target", ""))

    return Sample(
        input=spec,
        target=reference,
        id=str(task_id),
        metadata={
            "category": record.get("category", ""),
            "complexity": record.get("complexity", ""),
        },
    )


@scorer(metrics=[])
def webbench_scorer() -> Scorer:
    """Reject scoring until the official pairwise protocol is available."""
    raise BenchmarkUnavailableError(
        f"Benchmark 'qwenwebbench' is unavailable: {QWENWEBBENCH_UNAVAILABLE_REASON}"
    )


def load_qwenwebbench(tier: str = "smoke") -> list[Sample]:
    """Reject loading until the official dataset and protocol are available."""
    del tier
    raise BenchmarkUnavailableError(
        f"Benchmark 'qwenwebbench' is unavailable: {QWENWEBBENCH_UNAVAILABLE_REASON}"
    )


@register_benchmark(
    name="qwenwebbench",
    description="QwenWebBench - web artifact generation with Elo rating",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 30, "full": 0},
    total_samples=0,  # TBD
    requires_sandbox=False,
    scoring_type="elo",
    status=BenchmarkStatus.UNAVAILABLE,
    status_reason=QWENWEBBENCH_UNAVAILABLE_REASON,
    protocol_version="unreleased",
    access="unavailable",
    source_kind="other",
    release_policy="unreleased",
)
@task
def qwenwebbench(tier: str = "smoke") -> Task:
    """Reject execution until QwenWebBench has a reproducible public release."""
    del tier
    raise BenchmarkUnavailableError(
        f"Benchmark 'qwenwebbench' is unavailable: {QWENWEBBENCH_UNAVAILABLE_REASON}"
    )
