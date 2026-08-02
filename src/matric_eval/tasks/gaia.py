"""Classic GAIA 2023 integration using the maintained official protocol."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_evals.gaia.gaia import (
    DATASET_REVISION,
    DEFAULT_DOCKER_SANDBOX,
    default_solver,
)
from inspect_evals.gaia.gaia import (
    gaia as upstream_gaia,
)
from inspect_evals.gaia.scorer import gaia_scorer, normalize_str

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, seeded_sample
from matric_eval.tasks.registry import register_benchmark
from matric_eval.tasks.upstream import INSPECT_EVALS_REVISION, adapt_upstream_task

GAIA_DATASET = "gaia-benchmark/GAIA"
GAIA_PATH: str | None = None
LEVELS = {1: "simple", 2: "moderate", 3: "complex"}


def normalize_answer(answer: str) -> str:
    """Normalize with the official GAIA string normalization."""
    return normalize_str(answer)


def _extract_final_answer(response: str) -> str:
    """Extract a concise answer for compatibility with legacy callers."""
    for pattern in (
        r"(?i)final\s+answer\s*:\s*(.+)$",
        r"(?i)answer\s*:\s*(.+)$",
        r"\*\*([^*]+)\*\*",
    ):
        match = re.search(pattern, response, re.MULTILINE)
        if match:
            return match.group(1).strip()
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def record_to_sample(record: dict[str, Any], base_dir: Path | None = None) -> Sample:
    """Convert either current Parquet or legacy JSONL GAIA records."""
    question = str(record.get("Question", record.get("question", "")))
    answer = str(record.get("Final answer", record.get("answer", record.get("final_answer", ""))))
    level = int(record.get("Level", record.get("level", 1)))
    task_id = str(record.get("task_id", record.get("id", "")))
    file_path = record.get("file_path") or record.get("file_name")

    files: dict[str, str] | None = None
    file_note = ""
    if file_path:
        source = Path(str(file_path))
        if base_dir is not None and not source.is_absolute():
            source = base_dir / source
        destination = f"/shared_files/{source.name}"
        files = {destination: str(source)}
        file_note = f"\nReferenced file: {destination}\n"

    return Sample(
        input=(
            "Return only the final answer as a number, short phrase, or comma-separated "
            f"list.{file_note}\nQuestion:\n{question}"
        ),
        target=answer,
        id=task_id,
        metadata={
            "level": level,
            "level_name": LEVELS.get(level, "unknown"),
            "question": question,
            "split": record.get("split", "validation"),
            "dataset_source": GAIA_DATASET,
            "dataset_revision": DATASET_REVISION,
            "annotator_metadata": record.get("Annotator Metadata", {}),
        },
        files=files,
        setup="mkdir -p /shared_files" if files else None,
    )


def _load_local_records(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        candidates = [
            path / "gaia.jsonl",
            path / "gaia_validation.jsonl",
            path / "validation.jsonl",
        ]
        path = next((candidate for candidate in candidates if candidate.exists()), path)
    if not path.is_file():
        raise FileNotFoundError(
            f"GAIA local override does not contain a supported JSONL file: {path}"
        )
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def load_gaia(
    tier: str = "smoke",
    levels: list[int] | None = None,
    split: str = "validation",
) -> list[Sample]:
    """Load GAIA through a local override or the pinned authenticated snapshot."""
    sample_count = get_sample_count("gaia", tier)
    if sample_count == 0:
        return []
    local_path = get_dataset_path("gaia") or GAIA_PATH
    if local_path:
        path = Path(local_path)
        records = _load_local_records(path)
        records = [
            record
            for record in records
            if not levels or int(record.get("Level", record.get("level", 1))) in levels
        ]
        samples = [record_to_sample(record, path.parent) for record in records]
    else:
        subset = "2023_all" if not levels or len(levels) != 1 else f"2023_level{levels[0]}"
        upstream = upstream_gaia(subset=subset, split=split)
        samples = list(upstream.dataset)

    if sample_count > 0 and sample_count < len(samples):
        samples = seeded_sample(samples, sample_count, get_seed())
    return samples


@register_benchmark(
    name="gaia",
    description="GAIA 2023 classic - official agent, attachments, and exact scoring (466 tasks)",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 466},
    total_samples=466,
    requires_sandbox=True,
    sandbox_profile="docker",
    scoring_type="official_exact_match",
    provider_requirements=("docker", "network"),
    status="gated",
    status_reason="GAIA requires accepting the Hugging Face dataset terms and authentication.",
    protocol_version="2023",
    dataset_source=GAIA_DATASET,
    dataset_revision=DATASET_REVISION,
    dataset_configs=("2023_all", "2023_level1", "2023_level2", "2023_level3"),
    dataset_splits=("validation", "test"),
    license="GAIA dataset terms",
    access="gated",
    source_kind="huggingface",
    release_policy="immutable",
    evaluator_source="inspect-evals/gaia",
    evaluator_revision=INSPECT_EVALS_REVISION,
)
@task
def gaia(
    tier: str = "smoke",
    levels: list[int] | None = None,
    split: str = "validation",
) -> Task:
    """Run classic GAIA with the maintained agent, sandbox, and official scorer."""
    if get_dataset_path("gaia") or GAIA_PATH:
        return Task(
            dataset=load_gaia(tier=tier, levels=levels, split=split),
            solver=default_solver(max_attempts=1),
            scorer=gaia_scorer(),
            sandbox=DEFAULT_DOCKER_SANDBOX,
            message_limit=100,
            name=f"gaia_2023_{split}",
            metadata={
                "protocol_version": "2023",
                "dataset_source": GAIA_DATASET,
                "dataset_revision": DATASET_REVISION,
                "evaluator_revision": INSPECT_EVALS_REVISION,
                "split": split,
                "local_override": True,
            },
        )

    subset = "2023_all" if not levels or len(levels) != 1 else f"2023_level{levels[0]}"
    upstream = upstream_gaia(subset=subset, split=split)
    # The current public release includes answers; retain the official scorer when present.
    if any(str(sample.target) for sample in upstream.dataset):
        upstream.scorer = gaia_scorer()
    return adapt_upstream_task(
        upstream,
        benchmark="gaia",
        tier=tier,
        task_name=f"gaia_2023_{split}",
        protocol_metadata={
            "protocol_version": "2023",
            "dataset_source": GAIA_DATASET,
            "dataset_revision": DATASET_REVISION,
            "evaluator_revision": INSPECT_EVALS_REVISION,
            "split": split,
            "local_override": False,
        },
    )
