"""GAIA2 CLI adapter for the official containerized ARE runtime."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import load_hf_dataset, seeded_sample
from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

GAIA2_DATASET = "meta-agents-research-environments/gaia2-cli"
GAIA2_DATASET_REVISION = "240ac47bfc62b24c934f95d014ffa5a3cab8b04c"
GAIA2_ARE_REPOSITORY = "facebookresearch/meta-agents-research-environments"
GAIA2_ARE_REVISION = "7946367413129784139e785ae4c351090002a0bb"
GAIA2_RUNNER_VERSION = "0.1.0"
GAIA2_CONTAINER_VERSION = "gaia2-cli-1.2.0"
GAIA2_SPLITS = ("execution", "search", "adaptability", "ambiguity", "time")
GAIA2_TOTAL = 800


def _user_instruction(scenario: dict[str, Any]) -> str:
    for event in scenario.get("events", []):
        action = event.get("action", {})
        if event.get("event_type") != "USER" or action.get("function") != "send_message_to_agent":
            continue
        for argument in action.get("args", []):
            if argument.get("name") == "content":
                return str(argument.get("value", ""))
    return ""


def _oracle_answer(scenario: dict[str, Any]) -> str:
    for event in scenario.get("events", []):
        action = event.get("action", {})
        if event.get("class_name") != "OracleEvent":
            continue
        for argument in action.get("args", []):
            if argument.get("name") == "content":
                return str(argument.get("value", ""))
    return ""


def record_to_sample(record: dict[str, Any], *, split: str) -> Sample:
    """Expose a scenario for discovery; execution remains in the official runner."""
    scenario = json.loads(str(record["scenario"]))
    return Sample(
        id=str(record["scenario_id"]),
        input=_user_instruction(scenario),
        target=_oracle_answer(scenario),
        metadata={
            "split": split,
            "scenario_version": scenario.get("version", ""),
            "duration": scenario.get("metadata", {}).get("definition", {}).get("duration"),
            "dataset_revision": GAIA2_DATASET_REVISION,
            "are_revision": GAIA2_ARE_REVISION,
            "runner_version": GAIA2_RUNNER_VERSION,
            "container_revision": GAIA2_CONTAINER_VERSION,
            "execution": "external-gaia2-runner",
        },
    )


def load_gaia2(tier: str = "smoke", splits: list[str] | None = None) -> list[Sample]:
    """Load the pinned public manifests for inspection and deterministic selection."""
    selected = tuple(splits or GAIA2_SPLITS)
    unknown = set(selected) - set(GAIA2_SPLITS)
    if unknown:
        raise ValueError(f"Unknown GAIA2 splits: {', '.join(sorted(unknown))}")
    samples: list[Sample] = []
    for split in selected:
        samples.extend(
            load_hf_dataset(
                GAIA2_DATASET,
                subset=split,
                split="test",
                revision=GAIA2_DATASET_REVISION,
                require_immutable_revision=True,
                record_to_sample=lambda record, split=split: record_to_sample(
                    record, split=split
                ),
            )
        )
    count = get_sample_count("gaia2", tier)
    return seeded_sample(samples, count, get_seed())


def build_gaia2_command(repository: str | Path, *, config: str | Path) -> list[str]:
    """Build the official Python 3.12 runner command."""
    repository = Path(repository)
    config_path = Path(config)
    if not config_path.is_absolute():
        config_path = repository / config_path
    return [
        "uv",
        "run",
        "--project",
        str(repository / "gaia2-cli" / "runner"),
        "--python",
        "3.12",
        "gaia2-runner",
        "run-config",
        "--config",
        str(config_path),
    ]


def run_gaia2(
    repository: str | Path, *, config: str | Path
) -> subprocess.CompletedProcess[str]:
    """Run GAIA2 through its per-scenario Podman isolation boundary."""
    return subprocess.run(
        build_gaia2_command(repository, config=config),
        cwd=repository,
        check=True,
        text=True,
    )


def summarize_gaia2_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the official boolean/null verdict contract."""
    completed = [result for result in results if result.get("success") is not None]
    passed = sum(result.get("success") is True for result in completed)
    by_split: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_split.setdefault(str(result.get("split", "unknown")), []).append(result)
    split_rewards = {}
    for split, rows in by_split.items():
        split_completed = [row for row in rows if row.get("success") is not None]
        split_rewards[split] = (
            sum(row.get("success") is True for row in split_completed) / len(split_completed)
            if split_completed
            else 0.0
        )
    return {
        "runs": len(results),
        "completed": len(completed),
        "infrastructure_errors": len(results) - len(completed),
        "average_reward": passed / len(completed) if completed else 0.0,
        "by_split": split_rewards,
        "dataset_revision": GAIA2_DATASET_REVISION,
        "evaluator_revision": GAIA2_ARE_REVISION,
        "are_revision": GAIA2_ARE_REVISION,
        "container_revision": GAIA2_CONTAINER_VERSION,
    }


def load_gaia2_results(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    return summarize_gaia2_results(rows)


@register_benchmark(
    name="gaia2",
    description="GAIA2 CLI - 800 dynamic read/write scenarios in isolated ARE containers",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": GAIA2_TOTAL},
    total_samples=GAIA2_TOTAL,
    requires_sandbox=True,
    sandbox_profile="gaia2-podman",
    scoring_type="official_boolean_reward_and_pass_at_k",
    provider_requirements=("gaia2-runtime", "podman", "network", "judge-model"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires the official GAIA2 CLI runtime, Podman, and agent/judge credentials.",
    protocol_version="gaia2-cli-1.2.0",
    dataset_source=GAIA2_DATASET,
    dataset_revision=GAIA2_DATASET_REVISION,
    dataset_configs=GAIA2_SPLITS,
    dataset_splits=("test",),
    evaluator_source=GAIA2_ARE_REPOSITORY,
    evaluator_revision=GAIA2_ARE_REVISION,
    container_revision=GAIA2_CONTAINER_VERSION,
    license="MIT runtime; dataset card terms",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
)
@task
def gaia2(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "GAIA2 requires the external gaia2-runner capability (Python 3.12, Podman, "
        "built GAIA2 runtime image, network, and agent/judge credentials). Use run_gaia2() "
        f"with the ARE repository pinned at {GAIA2_ARE_REVISION}; it cannot run as a "
        "completion-only Inspect task."
    )
