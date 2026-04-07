"""
SWE-bench Pro benchmark — harder variant with more complex real-world issues.

Same scaffolding as SWE-bench Verified but with increased difficulty.
Dataset availability is unconfirmed (RISK-008).

Dataset: princeton-nlp/SWE-bench_Pro (HuggingFace, TBD)
"""

from inspect_ai import Task, task

from matric_eval.tasks.registry import register_benchmark
from matric_eval.tasks.swebench.factory import create_swebench_task


@register_benchmark(
    name="swebench_pro",
    description="SWE-bench Pro - complex GitHub issue resolution (TBD tasks)",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 0},
    total_samples=0,  # TBD — dataset not yet confirmed
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="standard",
)
@task
def swebench_pro(tier: str = "smoke") -> Task:
    """SWE-bench Pro benchmark — harder variant of SWE-bench.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for SWE-bench Pro evaluation
    """
    return create_swebench_task(variant="pro", tier=tier)
