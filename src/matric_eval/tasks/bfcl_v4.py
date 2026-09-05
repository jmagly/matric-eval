"""BFCL V4 Agentic adapter for the official ``bfcl-eval`` runner."""

from __future__ import annotations

from inspect_ai import Task, task

from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

BFCL_REPOSITORY = "ShishirPatil/gorilla"
BFCL_REVISION = "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
BFCL_PACKAGE_VERSION = "2026.3.23"
BFCL_PACKAGE = f"bfcl-eval=={BFCL_PACKAGE_VERSION}"
BFCL_AGENTIC_CATEGORIES = ("web_search", "memory")
BFCL_AGENTIC_TASKS = 665


def build_bfcl_generate_command(
    *,
    model: str,
    categories: tuple[str, ...] = BFCL_AGENTIC_CATEGORIES,
    endpoint: bool = True,
    backend: str = "vllm",
    local_model_path: str | None = None,
    num_gpus: int = 1,
    gpu_memory_utilization: float = 0.9,
    num_threads: int = 1,
) -> list[str]:
    """Build generation arguments accepted by the pinned official BFCL CLI."""
    if not categories:
        raise ValueError("at least one BFCL category is required")
    command = [
        "bfcl",
        "generate",
        "--model",
        model,
        "--test-category",
        *categories,
        "--num-threads",
        str(num_threads),
    ]
    if endpoint:
        command.append("--skip-server-setup")
    else:
        command.extend(
            [
                "--backend",
                backend,
                "--num-gpus",
                str(num_gpus),
                "--gpu-memory-utilization",
                str(gpu_memory_utilization),
            ]
        )
        if local_model_path:
            command.extend(["--local-model-path", local_model_path])
    return command


def build_bfcl_evaluate_command(
    *,
    model: str,
    categories: tuple[str, ...] = BFCL_AGENTIC_CATEGORIES,
    partial: bool = False,
) -> list[str]:
    """Build the official scoring command without reimplementing BFCL metrics."""
    command = ["bfcl", "evaluate", "--model", model, "--test-category", *categories]
    if partial:
        command.append("--partial-eval")
    return command


@register_benchmark(
    name="bfcl_v4_agentic",
    description="BFCL V4 Agentic - 665 official web-search and memory tool-use cases",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": BFCL_AGENTIC_TASKS},
    total_samples=BFCL_AGENTIC_TASKS,
    requires_sandbox=True,
    sandbox_profile="bfcl-v4",
    scoring_type="official_bfcl_v4_agentic",
    provider_requirements=("bfcl-eval", "openai-compatible-tools", "network"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires the pinned BFCL runner and category-specific service credentials.",
    protocol_version="4",
    dataset_source=BFCL_REPOSITORY,
    dataset_revision=BFCL_REVISION,
    dataset_configs=BFCL_AGENTIC_CATEGORIES,
    dataset_splits=("agentic",),
    evaluator_source="bfcl-eval",
    evaluator_revision=BFCL_PACKAGE_VERSION,
    release_date="2025-07-17",
    license="Apache-2.0",
    access="gated",
    source_kind="github",
    release_policy="versioned",
)
@task
def bfcl_v4_agentic(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "BFCL V4 Agentic requires complete official tool trajectories. Install "
        f"{BFCL_PACKAGE} and use build_bfcl_generate_command() followed by "
        "build_bfcl_evaluate_command(); it is not a completion-only Inspect task."
    )
