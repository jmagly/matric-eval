"""SWE-bench-Live MultiLang adapter for pinned official patch evaluation."""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task

from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

SWEBENCH_LIVE_REPOSITORY = "microsoft/SWE-bench-Live"
SWEBENCH_LIVE_REVISION = "9b4b11c5d77365107e91bc19d7a3aebbe8da76b7"
SWEBENCH_LIVE_DATASET = "SWE-bench-Live/MultiLang"
SWEBENCH_LIVE_DATASET_REVISION = "22091f6ce331c5c60c241d76512d4be7ee1a555b"
SWEBENCH_LIVE_TASKS = 1077


def build_swebench_live_evaluate_command(
    *,
    patch_dir: str | Path,
    output_dir: str | Path,
    instance_ids: tuple[str, ...] = (),
    workers: int = 1,
    overwrite: bool = False,
) -> list[str]:
    """Build the official Linux MultiLang patch-evaluation command."""
    command = [
        "python",
        "-m",
        "evaluation.evaluation",
        "--dataset",
        SWEBENCH_LIVE_DATASET,
        "--platform",
        "linux",
        "--patch_dir",
        str(patch_dir),
        "--output_dir",
        str(output_dir),
        "--workers",
        str(workers),
        "--overwrite",
        "1" if overwrite else "0",
    ]
    if instance_ids:
        command.extend(["--instance_ids", *instance_ids])
    return command


@register_benchmark(
    name="swebench_live_multilang",
    description="SWE-bench-Live MultiLang - pinned 1,077-task fresh coding snapshot",
    category="agentic",
    tier_samples={"smoke": 1, "quick": 25, "full": SWEBENCH_LIVE_TASKS},
    total_samples=SWEBENCH_LIVE_TASKS,
    requires_sandbox=True,
    sandbox_profile="docker",
    scoring_type="official_swebench_live_tests",
    provider_requirements=("docker", "coding-agent", "trajectory-capture"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires compliant agent trajectories, prediction patches, and task images.",
    protocol_version="1.0-multilang-linux",
    dataset_source=SWEBENCH_LIVE_DATASET,
    dataset_revision=SWEBENCH_LIVE_DATASET_REVISION,
    dataset_configs=("all_languages",),
    dataset_splits=("test",),
    evaluator_source=SWEBENCH_LIVE_REPOSITORY,
    evaluator_revision=SWEBENCH_LIVE_REVISION,
    release_date="2026-08-21",
    license="MIT",
    access="gated",
    source_kind="huggingface",
    release_policy="continuous",
)
@task
def swebench_live_multilang(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "SWE-bench-Live requires a coding-agent rollout followed by the official Docker "
        "patch evaluator. Use build_swebench_live_evaluate_command() from the upstream "
        f"checkout pinned at {SWEBENCH_LIVE_REVISION}."
    )
