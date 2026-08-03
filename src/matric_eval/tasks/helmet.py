"""Pinned external adapter and coverage analysis for HELMET."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

from inspect_ai import Task, task

from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

HELMET_REPOSITORY = "princeton-nlp/HELMET"
HELMET_REVISION = "af609c4d51b97fc35012099380aa889da961c42d"
HELMET_DATASET = "princeton-nlp/HELMET"
HELMET_DATASET_REVISION = "dddb209d03e38f1f0faf76d6d05ef4ccf96240ee"
HELMET_CATEGORIES = ("recall", "rag", "rerank", "cite", "longqa", "summ", "icl")
HELMET_DATA_SIZE_GB = 34


def build_helmet_command(
    repository: str | Path,
    *,
    category: str,
    model_name_or_path: str,
    output_dir: str | Path,
    short: bool = False,
    max_test_samples: int | None = None,
) -> list[str]:
    if category not in HELMET_CATEGORIES:
        raise ValueError(f"Unknown HELMET category: {category}")
    repository = Path(repository)
    suffix = "_short" if short else ""
    command = [
        "python",
        str(repository / "eval.py"),
        "--config",
        str(repository / "configs" / f"{category}{suffix}.yaml"),
        "--model_name_or_path",
        model_name_or_path,
        "--output_dir",
        str(output_dir),
    ]
    if max_test_samples is not None:
        command.extend(("--max_test_samples", str(max_test_samples)))
    return command


def run_helmet(repository: str | Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_helmet_command(repository, **kwargs), cwd=repository, check=True, text=True
    )


def pearson_correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("Correlation inputs must have the same length of at least two")
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    return numerator / (left_scale * right_scale) if left_scale and right_scale else 0.0


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        rank = (index + end) / 2 + 1
        for position in range(index, end + 1):
            ranks[order[position]] = rank
        index = end + 1
    return ranks


def spearman_correlation(left: list[float], right: list[float]) -> float:
    return pearson_correlation(_ranks(left), _ranks(right))


def helmet_coverage_report(existing_dimensions: set[str]) -> dict[str, Any]:
    covered = set(HELMET_CATEGORIES) & existing_dimensions
    missing = set(HELMET_CATEGORIES) - existing_dimensions
    return {
        "covered": sorted(covered),
        "incremental": sorted(missing),
        "coverage_ratio": len(covered) / len(HELMET_CATEGORIES),
        "longproc_included": False,
        "decision": "integrate-gated",
        "decision_reason": (
            "HELMET adds reranking, citation, long-form QA, summarization, and ICL coverage; "
            "the 34 GB corpus and model-based judges require an external gated adapter."
        ),
    }


def summarize_helmet_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Retain category-specific official metrics without forcing unlike scales together."""
    by_category: dict[str, dict[str, dict[str, float]]] = {}
    for row in rows:
        category = str(row["category"])
        if category not in HELMET_CATEGORIES:
            raise ValueError(f"Unknown HELMET category: {category}")
        metrics = row.get("metrics", {})
        context_length = str(row.get("context_length", "config"))
        by_category.setdefault(category, {})[context_length] = {
            str(name): float(value)
            for name, value in metrics.items()
            if isinstance(value, (int, float))
        }
    return {
        "by_category": by_category,
        "dataset_revision": HELMET_DATASET_REVISION,
        "evaluator_revision": HELMET_REVISION,
        "longproc_included": False,
    }


def load_helmet_score(
    path: str | Path, *, category: str, context_length: int | str = "config"
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    metrics = payload.get("metrics", payload)
    return summarize_helmet_scores(
        [{"category": category, "context_length": context_length, "metrics": metrics}]
    )


@register_benchmark(
    name="helmet",
    description="HELMET - seven-category application-centric long-context evaluation",
    category="reasoning",
    tier_samples={"smoke": 7, "quick": 7, "full": 7},
    total_samples=7,
    scoring_type="official_category_metrics_and_model_judges",
    provider_requirements=("helmet-data", "long-context-model", "judge-model"),
    status=BenchmarkStatus.GATED,
    status_reason=(
        "Requires a roughly 34 GB corpus, accelerator/API inference, and judges for LongQA/Summ."
    ),
    protocol_version="HELMET-2026",
    dataset_source=HELMET_DATASET,
    dataset_revision=HELMET_DATASET_REVISION,
    dataset_configs=HELMET_CATEGORIES,
    dataset_splits=("data_v2_archive",),
    evaluator_source=HELMET_REPOSITORY,
    evaluator_revision=HELMET_REVISION,
    prompt_revision=HELMET_REVISION,
    license="MIT",
    access="public",
    source_kind="huggingface",
    release_policy="continuous",
)
@task
def helmet(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "HELMET runs through its official external runtime; LongProc is intentionally separate. "
        f"Use build_helmet_command() at revision {HELMET_REVISION}."
    )
