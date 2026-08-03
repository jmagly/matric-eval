"""Pinned external adapter for THUIR MemoryBench."""

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

MEMORYBENCH_REPOSITORY = "THUIR/MemoryBench"
MEMORYBENCH_REVISION = "5eafebca4e9ffbb2f0087ade13c498cf95fbc09a"
MEMORYBENCH_DATASET = "THUIR/MemoryBench"
MEMORYBENCH_DATASET_REVISION = "3acd60a4bd35b43b408f0e6db4c5f1e88df5e96d"
MEMORYBENCH_REGIMES = ("off-policy", "stepwise_off-policy", "on-policy", "train_performance")
MEMORYBENCH_TASK_TYPES = ("Long-Long", "Short-Short", "Short-Long", "Long-Short")
MEMORYBENCH_DOMAINS = ("Academic&Knowledge", "Legal", "Open-Domain")
MEMORYBENCH_DATASET_CONFIGS = (
    "DialSim-bigbang",
    "DialSim-friends",
    "DialSim-theoffice",
    "HelloBench-Academic&Knowledge-QA",
    "HelloBench-Academic&Knowledge-Writing",
    "HelloBench-Creative&Design",
    "IdeaBench",
    "JRE-L",
    "JuDGE",
    "LexEval-Judge",
    "LexEval-QA",
    "LexEval-Summarization",
    "LimitGen-Syn",
    *(f"Locomo-{index}" for index in range(10)),
    "NFCats",
    "WritingBench-Academic&Engineering",
    "WritingBench-Creative&Design",
    "WritingBench-Politics&Law",
    "WritingPrompts",
)
MEMORYBENCH_TOTAL = 4063


def build_memorybench_command(
    repository: str | Path,
    *,
    regime: str,
    memory_system: str,
    dataset_type: str,
    set_name: str,
) -> list[str]:
    if regime not in MEMORYBENCH_REGIMES:
        raise ValueError(f"Unknown MemoryBench regime: {regime}")
    if dataset_type not in {"task", "domain"}:
        raise ValueError("dataset_type must be 'task' or 'domain'")
    valid_names = MEMORYBENCH_TASK_TYPES if dataset_type == "task" else MEMORYBENCH_DOMAINS
    if set_name not in valid_names:
        raise ValueError(f"Unknown {dataset_type} set: {set_name}")
    return [
        "uv",
        "run",
        "--project",
        str(Path(repository)),
        "python",
        "-m",
        f"src.{regime}",
        "--dataset_type",
        dataset_type,
        "--set_name",
        set_name,
        "--memory_system",
        memory_system,
    ]


def run_memorybench(repository: str | Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_memorybench_command(repository, **kwargs), cwd=repository, check=True, text=True
    )


def summarize_memorybench_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve the released regime, task/domain, and metric axes."""
    grouped: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in rows:
        regime = str(row["regime"])
        if regime not in MEMORYBENCH_REGIMES:
            raise ValueError(f"Unknown MemoryBench regime: {regime}")
        axis = str(row.get("task", row.get("domain", "unknown")))
        metric = str(row.get("metric", "score"))
        grouped[regime][axis][metric].append(float(row["score"]))
    return {
        "by_regime": {
            regime: {
                axis: {metric: sum(values) / len(values) for metric, values in metrics.items()}
                for axis, metrics in axes.items()
            }
            for regime, axes in grouped.items()
        },
        "dataset_revision": MEMORYBENCH_DATASET_REVISION,
        "evaluator_revision": MEMORYBENCH_REVISION,
    }


def published_memorybench_summary_rows(
    payload: dict[str, Any],
    *,
    regime: str,
    dataset_type: str,
    set_name: str,
    baseline: str,
) -> list[dict[str, Any]]:
    """Normalize the official published ``summary.json`` result contract."""
    if dataset_type not in {"task", "domain"}:
        raise ValueError("dataset_type must be 'task' or 'domain'")
    rows = []
    for metric, value in payload.get("summary", {}).items():
        if isinstance(value, dict):
            value = value.get(baseline)
        if isinstance(value, (int, float)):
            rows.append(
                {
                    "regime": regime,
                    dataset_type: set_name,
                    "metric": metric,
                    "score": float(value),
                    "baseline": baseline,
                }
            )
    return rows


@register_benchmark(
    name="memorybench",
    description="MemoryBench - feedback-driven memory systems across four evaluation regimes",
    category="agentic",
    tier_samples={"smoke": 1, "quick": 100, "full": MEMORYBENCH_TOTAL},
    total_samples=MEMORYBENCH_TOTAL,
    scoring_type="official_regime_task_domain_metrics",
    provider_requirements=("memory-system", "simulator-model", "judge-model"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires an instrumented memory system plus simulator and evaluator models.",
    protocol_version="four-regime-2026",
    dataset_source=MEMORYBENCH_DATASET,
    dataset_revision=MEMORYBENCH_DATASET_REVISION,
    dataset_configs=MEMORYBENCH_DATASET_CONFIGS,
    dataset_splits=("train", "test"),
    evaluator_source=MEMORYBENCH_REPOSITORY,
    evaluator_revision=MEMORYBENCH_REVISION,
    license="MIT",
    access="public",
    source_kind="huggingface",
    release_policy="continuous",
)
@task
def memorybench(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "MemoryBench evaluates a stateful memory system with external simulator/judge models. "
        f"Use build_memorybench_command() at revision {MEMORYBENCH_REVISION}."
    )
