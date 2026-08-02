"""
SWE-bench Verified benchmark — 500 verified GitHub issue resolution tasks.

The industry standard for agentic coding evaluation. Models are given a
repo + issue description and must produce a git patch that resolves the
issue and passes the repo's test suite.

Dataset: princeton-nlp/SWE-bench_Verified (HuggingFace)
"""

from inspect_ai import Task, task

from matric_eval.tasks.registry import register_benchmark
from matric_eval.tasks.swebench.factory import create_swebench_task


@register_benchmark(
    name="swebench_verified",
    description="SWE-bench Verified - official 500-task repository evaluation",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 500},
    total_samples=500,
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="official_resolved",
    protocol_version="official-harness-2026",
    dataset_source="SWE-bench/SWE-bench_Verified",
    dataset_revision="91aa3ed51b709be6457e12d00300a6a596d4c6a3",
    dataset_configs=("default",),
    dataset_splits=("test",),
    license="upstream repository terms",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
    evaluator_source="inspect-evals/swe_bench",
    evaluator_revision="6a35510e530f236fd1dbcd9df888f01937c8494a",
)
@task
def swebench_verified(tier: str = "smoke") -> Task:
    """SWE-bench Verified benchmark.

    Models receive a GitHub issue description and repository context,
    then must generate a git patch that resolves the issue.

    Scored binary: patch applies cleanly AND tests pass = 1.0, else 0.0.

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples
            - "quick": 50 samples
            - "full": 500 samples (all)

    Returns:
        Task configured for SWE-bench Verified evaluation
    """
    return create_swebench_task(variant="verified", tier=tier)
