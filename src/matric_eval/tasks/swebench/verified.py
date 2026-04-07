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
    description="SWE-bench Verified - GitHub issue resolution (500 tasks)",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 500},
    total_samples=500,
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="standard",
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
