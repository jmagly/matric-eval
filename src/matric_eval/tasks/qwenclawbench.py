"""QwenClawBench v1.1 manifest support and official-runner routing."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, seeded_sample
from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

QWENCLAW_DATASET = "skylenage-ai/QwenClawBench"
QWENCLAW_DATASET_REVISION = "762e8b9e38953256c71b0c660eb81e9ce11404d4"
QWENCLAW_REPOSITORY = "SKYLENAGE-AI/QwenClawBench"
QWENCLAW_EVALUATOR_REVISION = "ca8af7f914f76082b4c27c21481da2495a5d5125"
QWENCLAW_RELEASE = "qwenclawbench-v1.1-100"
QWENCLAW_TASKS = 100


def _sections(body: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+)$", body, re.MULTILINE))
    return {
        match.group(1).strip(): body[
            match.end() : matches[index + 1].start() if index + 1 < len(matches) else None
        ].strip()
        for index, match in enumerate(matches)
    }


def _parse_task(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError(f"QwenClawBench task lacks YAML frontmatter: {path}")
    metadata = yaml.safe_load(match.group(1)) or {}
    sections = _sections(match.group(2))
    return {**metadata, **{key.lower().replace(" ", "_"): value for key, value in sections.items()}}


def record_to_sample(record: dict[str, Any]) -> Sample:
    return Sample(
        input=str(record.get("prompt", record.get("description", ""))),
        target="",
        id=str(record.get("id", record.get("task_id", ""))),
        metadata={
            "name": record.get("name", ""),
            "category": record.get("category", ""),
            "subcategory": record.get("subcategory", ""),
            "grading_type": record.get("grading_type", "automated"),
            "grading_weights": record.get("grading_weights", {}),
            "timeout_seconds": record.get("timeout_seconds", 120),
            "workspace_files": record.get("workspace_files", []),
            "expected_behavior": record.get("expected_behavior", ""),
            "automated_checks": record.get("automated_checks", ""),
            "llm_judge_rubric": record.get("llm_judge_rubric", ""),
            "dataset_revision": QWENCLAW_DATASET_REVISION,
            "evaluator_revision": QWENCLAW_EVALUATOR_REVISION,
        },
    )


def load_qwenclawbench(tier: str = "smoke") -> list[Sample]:
    root_value = get_dataset_path("qwenclawbench")
    if not root_value:
        raise FileNotFoundError(
            "QwenClawBench v1.1 is gated on Hugging Face. Set "
            "MATRIC_EVAL_QWENCLAWBENCH_DATA_PATH to an accepted local snapshot."
        )
    root = Path(root_value)
    release = root / "data" / QWENCLAW_RELEASE
    if not release.exists():
        release = root
    records = [_parse_task(path) for path in sorted((release / "tasks").glob("task_*.md"))]
    if len(records) != QWENCLAW_TASKS:
        raise ValueError(
            f"Expected {QWENCLAW_TASKS} QwenClawBench v1.1 tasks, found {len(records)}"
        )
    samples = [record_to_sample(record) for record in records]
    sample_count = get_sample_count("qwenclawbench", tier)
    if 0 < sample_count < len(samples):
        samples = seeded_sample(samples, sample_count, get_seed())
    return samples


def build_qwenclawbench_command(
    repository: str | Path,
    *,
    model: str,
    runs: int = 3,
    concurrency: int = 10,
    output_dir: str | Path,
) -> list[str]:
    return [
        "bash",
        "scripts/run.sh",
        "--model",
        model,
        "--dataset",
        QWENCLAW_RELEASE,
        "--runs",
        str(runs),
        "--concurrency",
        str(concurrency),
        "--output-dir",
        str(output_dir),
    ]


def run_qwenclawbench(
    repository: str | Path,
    *,
    model: str,
    runs: int = 3,
    concurrency: int = 10,
    output_dir: str | Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_qwenclawbench_command(
            repository,
            model=model,
            runs=runs,
            concurrency=concurrency,
            output_dir=output_dir,
        ),
        cwd=repository,
        check=True,
        text=True,
    )


def qwenclawbench_scorer():
    raise BenchmarkUnavailableError(
        "QwenClawBench scoring requires its OpenClaw transcript, automated checks, "
        "and penalized hybrid judge; use run_qwenclawbench()."
    )


@register_benchmark(
    name="qwenclawbench",
    description="QwenClawBench v1.1 - 100 OpenClaw tasks across 8 domains",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": QWENCLAW_TASKS},
    total_samples=QWENCLAW_TASKS,
    requires_sandbox=True,
    sandbox_profile="openclaw",
    scoring_type="official_automated_judge_hybrid",
    provider_requirements=("docker", "openclaw", "judge-model"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires accepted dataset access, OpenClaw, and judge credentials.",
    protocol_version="1.1",
    dataset_source=QWENCLAW_DATASET,
    dataset_revision=QWENCLAW_DATASET_REVISION,
    dataset_splits=("test",),
    license="MIT",
    access="gated",
    source_kind="huggingface",
    release_policy="versioned",
    evaluator_source=QWENCLAW_REPOSITORY,
    evaluator_revision=QWENCLAW_EVALUATOR_REVISION,
)
@task
def qwenclawbench(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "QwenClawBench is an OpenClaw trajectory benchmark. Use "
        "run_qwenclawbench() with the pinned upstream checkout."
    )
