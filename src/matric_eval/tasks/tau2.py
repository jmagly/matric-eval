"""tau3-bench v1.0.1 adapter for official dual-control agent evaluation."""

from __future__ import annotations

from inspect_ai import Task, task

from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

TAU2_REPOSITORY = "sierra-research/tau2-bench"
TAU2_REVISION = "672227c6b6676edc20d57ea53b7000262aae77b9"
TAU2_VERSION = "1.0.1"
TAU2_DOMAINS = ("airline", "retail", "telecom", "banking_knowledge")
TAU2_TASKS = 375


def build_tau2_command(
    *,
    domain: str,
    agent_model: str,
    user_model: str,
    trials: int = 1,
    num_tasks: int | None = None,
    task_ids: tuple[str, ...] = (),
    task_split: str = "base",
    max_concurrency: int = 3,
    seed: int = 300,
    save_to: str | None = None,
) -> list[str]:
    """Build the official text-mode command with comparison-critical controls."""
    if domain not in TAU2_DOMAINS:
        raise ValueError(f"unsupported tau2 domain: {domain}")
    if num_tasks is not None and task_ids:
        raise ValueError("num_tasks and task_ids are mutually exclusive")
    command = [
        "tau2",
        "run",
        "--domain",
        domain,
        "--agent-llm",
        agent_model,
        "--user-llm",
        user_model,
        "--num-trials",
        str(trials),
        "--task-split-name",
        task_split,
        "--max-concurrency",
        str(max_concurrency),
        "--seed",
        str(seed),
    ]
    if num_tasks is not None:
        command.extend(["--num-tasks", str(num_tasks)])
    if task_ids:
        command.extend(["--task-ids", *task_ids])
    if save_to:
        command.extend(["--save-to", save_to])
    return command


@register_benchmark(
    name="tau2",
    description="tau3-bench v1.0.1 - 375 dual-control tasks across four service domains",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": TAU2_TASKS},
    total_samples=TAU2_TASKS,
    requires_sandbox=True,
    sandbox_profile="tau2-services",
    scoring_type="official_tau2_reward_and_pass_at_k",
    provider_requirements=("tau2", "tool-calling", "user-simulator"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires the pinned tau2 runtime and a separately pinned user-simulator model.",
    protocol_version=TAU2_VERSION,
    dataset_source=TAU2_REPOSITORY,
    dataset_revision=TAU2_REVISION,
    dataset_configs=TAU2_DOMAINS,
    dataset_splits=("base",),
    evaluator_source=TAU2_REPOSITORY,
    evaluator_revision=TAU2_REVISION,
    release_date="2026-07-22",
    license="MIT",
    access="gated",
    source_kind="github",
    release_policy="versioned",
)
@task
def tau2(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "tau3-bench is a dual-control trajectory evaluation. Use build_tau2_command() "
        f"from an upstream checkout pinned at {TAU2_REVISION}."
    )
