"""Claw-Eval v1.1 discovery and canonical-runner routing."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import seeded_sample
from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

CLAW_DATASET = "claw-eval/Claw-Eval"
CLAW_DATASET_REVISION = "ca978fd82edb77d52f26f4ccf3f9684a8df84341"
CLAW_REPOSITORY = "claw-eval/claw-eval"
CLAW_EVALUATOR_REVISION = "d3f02d4938ab0832377d90535013def2b1a2fdc0"
CLAW_SPLITS = ("general", "multimodal", "multi_turn")
CLAW_TASKS = 300
CLAW_TRIALS = 3


def record_to_sample(record: dict[str, Any], *, split: str = "general") -> Sample:
    return Sample(
        input=str(record.get("query", record.get("description", ""))),
        target="",
        id=str(record.get("task_id", record.get("id", ""))),
        metadata={
            "split": split,
            "fixture": list(record.get("fixture", [])),
            "language": record.get("language", ""),
            "category": record.get("category", ""),
            "trials": CLAW_TRIALS,
            "dataset_revision": CLAW_DATASET_REVISION,
            "evaluator_revision": CLAW_EVALUATOR_REVISION,
        },
    )


def load_claweval(tier: str = "smoke") -> list[Sample]:
    """Load all three pinned public manifests for inspection and tier selection."""
    from datasets import load_dataset

    samples = []
    for split in CLAW_SPLITS:
        dataset = load_dataset(
            CLAW_DATASET,
            split=split,
            revision=CLAW_DATASET_REVISION,
        )
        samples.extend(record_to_sample(dict(record), split=split) for record in dataset)
    if len(samples) != CLAW_TASKS:
        raise ValueError(f"Expected {CLAW_TASKS} Claw-Eval v1.1 tasks, found {len(samples)}")
    sample_count = get_sample_count("claweval", tier)
    if 0 < sample_count < len(samples):
        samples = seeded_sample(samples, sample_count, get_seed())
    return samples


def build_claweval_command(
    repository: str | Path,
    *,
    config: str | Path,
    parallel: int = 16,
) -> list[str]:
    """Build the official v1.1 Pass^3 runner command."""
    return [
        "uv",
        "run",
        "claw-eval",
        "batch",
        "--config",
        str(Path(repository) / config),
        "--sandbox",
        "--trials",
        str(CLAW_TRIALS),
        "--parallel",
        str(parallel),
    ]


def run_claweval(
    repository: str | Path,
    *,
    config: str | Path,
    parallel: int = 16,
) -> subprocess.CompletedProcess[str]:
    """Execute the pinned upstream runner from its checked-out repository."""
    return subprocess.run(
        build_claweval_command(repository, config=config, parallel=parallel),
        cwd=repository,
        check=True,
        text=True,
    )


def claweval_scorer():
    raise BenchmarkUnavailableError(
        "Claw-Eval v1.1 grades complete tool trajectories with task-specific graders; "
        "use run_claweval() so Pass^3 is computed from exactly three successful trials."
    )


@register_benchmark(
    name="claweval",
    description="Claw-Eval v1.1 - 300 tasks with official trajectory grading and Pass^3",
    category="agentic",
    tier_samples={"smoke": 3, "quick": 20, "full": CLAW_TASKS},
    total_samples=CLAW_TASKS,
    requires_sandbox=True,
    requires_vision=True,
    sandbox_profile="claw-eval",
    scoring_type="official_pass_power_3",
    provider_requirements=("claw-eval", "docker", "judge-model"),
    status=BenchmarkStatus.GATED,
    status_reason="Runs through the upstream sandbox, mock services, and trajectory graders.",
    protocol_version="1.1.0",
    dataset_source=CLAW_DATASET,
    dataset_revision=CLAW_DATASET_REVISION,
    dataset_splits=CLAW_SPLITS,
    license="MIT",
    access="gated",
    source_kind="huggingface",
    release_policy="versioned",
    evaluator_source=CLAW_REPOSITORY,
    evaluator_revision=CLAW_EVALUATOR_REVISION,
)
@task
def claweval(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "Claw-Eval is an external trajectory benchmark, not an Inspect completion task. "
        "Use run_claweval() with the pinned upstream checkout."
    )
