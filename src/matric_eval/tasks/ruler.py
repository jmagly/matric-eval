"""Pinned adapter for the official RULER v1 synthetic benchmark."""

from __future__ import annotations

import json
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

RULER_REPOSITORY = "NVIDIA-NeMo/Skills"
RULER_REVISION = "f4a3fd8e524acd9abd1fea4387e8f179f6d51cf3"
RULER_PROTOCOL = "RULER-v1"
RULER_TASKS = (
    "niah_single_1",
    "niah_single_2",
    "niah_single_3",
    "niah_multikey_1",
    "niah_multikey_2",
    "niah_multikey_3",
    "niah_multivalue",
    "niah_multiquery",
    "vt",
    "cwe",
    "fwe",
    "qa_1",
    "qa_2",
)
RULER_CONTEXT_LENGTHS = (4096, 8192, 16384, 32768, 65536, 131072)
RULER_TIER_SAMPLES_PER_TASK = {"smoke": 1, "quick": 10, "full": 100}


def build_ruler_prepare_command(
    repository: str | Path,
    *,
    setup: str,
    tokenizer_path: str,
    context_length: int,
    tasks: tuple[str, ...] = RULER_TASKS,
) -> list[str]:
    """Build the pinned NeMo Skills generator command."""
    if context_length not in RULER_CONTEXT_LENGTHS:
        raise ValueError(f"Unsupported RULER context length: {context_length}")
    unknown = set(tasks) - set(RULER_TASKS)
    if unknown:
        raise ValueError(f"Unknown RULER tasks: {', '.join(sorted(unknown))}")
    return [
        "uv",
        "run",
        "--project",
        str(Path(repository)),
        "ns",
        "prepare_data",
        "ruler",
        "--setup",
        setup,
        "--tokenizer_path",
        tokenizer_path,
        "--max_seq_length",
        str(context_length),
        "--tasks",
        *tasks,
    ]


def run_ruler_prepare(repository: str | Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_ruler_prepare_command(repository, **kwargs), cwd=repository, check=True, text=True
    )


def trim_ruler_generated_data(root: str | Path, *, tier: str) -> dict[str, int]:
    """Apply matric-eval tiers after the official generator has produced JSONL."""
    try:
        limit = RULER_TIER_SAMPLES_PER_TASK[tier]
    except KeyError as exc:
        raise ValueError(f"Unknown tier: {tier}") from exc
    counts: dict[str, int] = {}
    for task_name in RULER_TASKS:
        path = Path(root) / task_name / "test.jsonl"
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        selected = lines[:limit]
        path.write_text("\n".join(selected) + ("\n" if selected else ""), encoding="utf-8")
        counts[task_name] = len(selected)
    return counts


def summarize_ruler_results(rows: list[dict[str, Any]], threshold: float = 0.8) -> dict[str, Any]:
    """Aggregate official task accuracy and derive effective context length."""
    by_task_values: dict[str, list[float]] = defaultdict(list)
    by_context_values: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        task_name = str(row["task"])
        if task_name not in RULER_TASKS:
            raise ValueError(f"Unknown RULER task in results: {task_name}")
        accuracy = float(row["accuracy"])
        by_task_values[task_name].append(accuracy)
        by_context_values[int(row["context_length"])].append(accuracy)
    by_task = {name: sum(values) / len(values) for name, values in by_task_values.items()}
    by_context = {length: sum(values) / len(values) for length, values in by_context_values.items()}
    passing = [length for length, accuracy in by_context.items() if accuracy > threshold]
    return {
        "average_accuracy": sum(by_task.values()) / len(by_task) if by_task else 0.0,
        "by_task": by_task,
        "by_context_length": by_context,
        "effective_context_length": max(passing) if passing else 0,
        "threshold": threshold,
        "protocol": RULER_PROTOCOL,
        "evaluator_revision": RULER_REVISION,
    }


def load_ruler_results(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as source:
        return summarize_ruler_results([json.loads(line) for line in source if line.strip()])


@register_benchmark(
    name="ruler",
    description="RULER v1 - 13 synthetic long-context tasks from 4K through 128K",
    category="reasoning",
    tier_samples={"smoke": 13, "quick": 130, "full": 1300},
    total_samples=1300,
    scoring_type="official_per_task_accuracy_and_effective_context",
    provider_requirements=("nemo-skills", "tokenizer", "long-context-model"),
    status=BenchmarkStatus.GATED,
    status_reason=(
        "Generation and evaluation require the pinned NeMo Skills runtime and model tokenizer."
    ),
    protocol_version=RULER_PROTOCOL,
    dataset_source=RULER_REPOSITORY,
    dataset_revision=RULER_REVISION,
    dataset_configs=RULER_TASKS,
    dataset_splits=("test",),
    evaluator_source=RULER_REPOSITORY,
    evaluator_revision=RULER_REVISION,
    license="Apache-2.0",
    access="public",
    source_kind="github",
    release_policy="versioned",
)
@task
def ruler(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "RULER requires official NeMo Skills generation with the evaluated model's tokenizer. "
        f"Use build_ruler_prepare_command() at revision {RULER_REVISION}."
    )
