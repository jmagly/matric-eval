"""Pinned adapter and score aggregation for the Tulving Episodic Memory Benchmark."""

from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from inspect_ai import Task, task

from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

TULVING_REPOSITORY = "ahstat/episodic-memory-benchmark"
TULVING_REVISION = "892b22af097d4389d4f1b9cd47b5c51fdacd9bef"
TULVING_EVENT_COUNTS = (20, 200, 2000)
TULVING_RECALL_BINS = ("0", "1", "2", "3-5", "6+")


def build_tulving_command(
    repository: str | Path,
    *,
    data_folder: str | Path,
    env_file: str | Path,
    event_count: int = 200,
    answering_kind: str = "prompting",
) -> list[str]:
    if event_count not in TULVING_EVENT_COUNTS:
        raise ValueError(f"Unsupported Tulving event count: {event_count}")
    repository = Path(repository)
    return [
        "python",
        str(repository / "epbench" / "experiments" / "quickstart.py"),
        "--data_folder",
        str(data_folder),
        "--env_file",
        str(env_file),
        "--book_nb_events",
        str(event_count),
        "--answering_kind",
        answering_kind,
    ]


def run_tulving(repository: str | Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_tulving_command(repository, **kwargs), cwd=repository, check=True, text=True
    )


def simple_recall_score(rows: list[dict[str, Any]]) -> float:
    """Average mean lenient F1 across the five official event-count bins."""
    bins: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get("get") == "all":
            bins[str(row["event_bin"])].append(float(row["f1_score_lenient"]))
    scores = [sum(bins[name]) / len(bins[name]) for name in TULVING_RECALL_BINS if bins[name]]
    return sum(scores) / len(scores) if scores else 0.0


def chronological_awareness_score(
    *, latest_state: float, exact_set_rate: float, kendall_tau: float
) -> float:
    """Apply the official mean(latest, exact-set * max(0, tau)) formula."""
    return (latest_state + exact_set_rate * max(0.0, kendall_tau)) / 2


def summarize_tulving_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_events: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_events[int(row["event_count"])].append(row)
    result: dict[int, dict[str, float]] = {}
    for event_count, event_rows in by_events.items():
        latest = [
            float(row["f1_score_lenient"]) for row in event_rows if row.get("get") == "latest"
        ]
        chronology = [row for row in event_rows if row.get("get") == "chronological"]
        exact = (
            sum(float(row["exact_set"]) for row in chronology) / len(chronology)
            if chronology
            else 0.0
        )
        tau = (
            sum(float(row["kendall_tau"]) for row in chronology) / len(chronology)
            if chronology
            else 0.0
        )
        result[event_count] = {
            "simple_recall": simple_recall_score(event_rows),
            "chronological_awareness": chronological_awareness_score(
                latest_state=sum(latest) / len(latest) if latest else 0.0,
                exact_set_rate=exact,
                kendall_tau=tau,
            ),
        }
    return {"by_event_count": result, "evaluator_revision": TULVING_REVISION}


@register_benchmark(
    name="tulving",
    description="Tulving episodic memory - recall and chronological awareness",
    category="reasoning",
    tier_samples={"smoke": 20, "quick": 200, "full": 686},
    total_samples=686,
    scoring_type="official_simple_recall_and_chronological_awareness",
    provider_requirements=("tulving-data", "answer-model", "judge-model"),
    status=BenchmarkStatus.GATED,
    status_reason=(
        "Narrative generation, answer generation, and semantic scoring use external model calls."
    ),
    protocol_version="ICLR-2025",
    dataset_source=TULVING_REPOSITORY,
    dataset_revision=TULVING_REVISION,
    dataset_configs=("20", "200", "2000"),
    dataset_splits=("questions",),
    evaluator_source=TULVING_REPOSITORY,
    evaluator_revision=TULVING_REVISION,
    prompt_revision=TULVING_REVISION,
    license="MIT",
    access="public",
    source_kind="github",
    release_policy="continuous",
)
@task
def tulving(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "Tulving uses its external narrative and evaluator pipeline. "
        f"Use build_tulving_command() at revision {TULVING_REVISION}."
    )
