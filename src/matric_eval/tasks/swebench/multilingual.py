"""
SWE-bench Multilingual benchmark — non-Python SWE-bench tasks.

Covers JavaScript, Java, Go, and other languages. Requires multi-language
test runner support in the sandbox.

Dataset availability is unconfirmed (RISK-008).
"""

from __future__ import annotations

from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from matric_eval.tasks.registry import register_benchmark
from matric_eval.tasks.swebench.factory import (
    create_swebench_task,
    swebench_record_to_sample,
)


def multilingual_record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a multilingual SWE-bench record, preserving the language field.

    Extends the base converter by adding the language to metadata,
    which the sandbox uses to select the correct TestRunner.
    """
    sample = swebench_record_to_sample(record)
    language = record.get("language", "python")

    # Create new metadata dict with language
    metadata = dict(sample.metadata or {})
    metadata["language"] = language

    return Sample(
        input=sample.input,
        target=sample.target,
        id=sample.id,
        metadata=metadata,
    )


@register_benchmark(
    name="swebench_multilingual",
    description="SWE-bench Multilingual - multi-language issue resolution (TBD tasks)",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 0},
    total_samples=0,  # TBD — dataset not yet confirmed
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="standard",
)
@task
def swebench_multilingual(tier: str = "smoke") -> Task:
    """SWE-bench Multilingual benchmark — JS, Java, Go, and more.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for SWE-bench Multilingual evaluation
    """
    return create_swebench_task(
        variant="multilingual",
        tier=tier,
        record_to_sample_fn=multilingual_record_to_sample,
    )
