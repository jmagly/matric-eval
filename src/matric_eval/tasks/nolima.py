"""Pinned external adapter for Adobe NoLiMa."""

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

NOLIMA_REPOSITORY = "adobe-research/NoLiMa"
NOLIMA_REVISION = "cb14780b249fecf2851127b2101a062c1b2c6430"
NOLIMA_DATASET = "amodaresi/NoLiMa"
NOLIMA_DATASET_REVISION = "378115b1f136b6ba78f90f78682bc55f70ec3ddd"
NOLIMA_DEPTH_INTERVALS = 26
NOLIMA_EFFECTIVE_THRESHOLD = 0.85


def build_nolima_command(repository: str | Path, *, config: str | Path) -> list[str]:
    repository = Path(repository)
    config_path = Path(config)
    if not config_path.is_absolute():
        config_path = repository / config_path
    return [
        "python",
        "-u",
        str(repository / "evaluation" / "run_tests.py"),
        "--config",
        str(config_path),
    ]


def run_nolima(repository: str | Path, *, config: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_nolima_command(repository, config=config), cwd=repository, check=True, text=True
    )


def summarize_nolima_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate exact-match results while retaining placement and overlap slices."""
    by_length: dict[int, list[float]] = defaultdict(list)
    by_depth: dict[float, list[float]] = defaultdict(list)
    by_overlap: dict[str, list[float]] = defaultdict(list)
    by_test: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        score = float(row.get("score", row.get("accuracy", row.get("correct", 0))))
        by_length[int(row["context_length"])].append(score)
        by_depth[float(row["document_depth_percent"])].append(score)
        by_overlap[str(row.get("lexical_overlap", "unspecified"))].append(score)
        by_test[str(row.get("test_name", "unspecified"))].append(score)
    lengths = {key: sum(values) / len(values) for key, values in by_length.items()}
    baseline = lengths[min(lengths)] if lengths else 0.0
    passing = [
        length
        for length, value in lengths.items()
        if baseline and value >= baseline * NOLIMA_EFFECTIVE_THRESHOLD
    ]
    return {
        "by_context_length": lengths,
        "by_needle_position": {key: sum(values) / len(values) for key, values in by_depth.items()},
        "by_lexical_overlap": {
            key: sum(values) / len(values) for key, values in by_overlap.items()
        },
        "by_test": {key: sum(values) / len(values) for key, values in by_test.items()},
        "effective_context_length": max(passing) if passing else 0,
        "effective_threshold_of_shortest_context": NOLIMA_EFFECTIVE_THRESHOLD,
        "dataset_revision": NOLIMA_DATASET_REVISION,
        "evaluator_revision": NOLIMA_REVISION,
    }


def load_nolima_results(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    files = sorted(path.rglob("*.json")) if path.is_dir() else [path]
    rows: list[dict[str, Any]] = []
    for file in files:
        payload = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows.extend(payload)
            continue
        if "results" not in payload:
            rows.append(payload)
            continue
        for result in payload["results"]:
            placement = result.get("placement_metadata", {})
            depth = float(placement.get("depth", 0.0))
            rows.append(
                {
                    "context_length": payload["context_length"],
                    "document_depth_percent": depth * 100,
                    "lexical_overlap": payload.get("lexical_overlap", "minimal"),
                    "test_name": payload.get("test_name", "unspecified"),
                    "score": result.get("metric", 0),
                }
            )
    return summarize_nolima_results(rows)


@register_benchmark(
    name="nolima",
    description="NoLiMa - latent-association needle retrieval without lexical overlap",
    category="reasoning",
    tier_samples={"smoke": 26, "quick": 260, "full": 2600},
    total_samples=2600,
    scoring_type="official_exact_match_by_length_depth_overlap",
    provider_requirements=("official-nolima-runtime", "model-tokenizer", "long-context-model"),
    status=BenchmarkStatus.GATED,
    status_reason=(
        "Exact context construction depends on the evaluated model tokenizer and official runner."
    ),
    protocol_version="NoLiMa-2025",
    dataset_source=NOLIMA_DATASET,
    dataset_revision=NOLIMA_DATASET_REVISION,
    dataset_splits=("train",),
    evaluator_source=NOLIMA_REPOSITORY,
    evaluator_revision=NOLIMA_REVISION,
    prompt_revision=NOLIMA_REVISION,
    license="Adobe Research License (noncommercial)",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
)
@task
def nolima(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "NoLiMa requires tokenizer-exact context placement in its official external runner. "
        f"Use build_nolima_command() at revision {NOLIMA_REVISION}."
    )
