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
    language = record.get("language") or record.get("repo_language")
    if not language:
        from swebench.harness.constants import MAP_REPO_TO_EXT

        extension = MAP_REPO_TO_EXT.get(str(record.get("repo", "")), "py")
        language = {
            "py": "python",
            "js": "javascript",
            "rb": "ruby",
            "rs": "rust",
        }.get(extension, extension)

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
    description="SWE-bench Multilingual - 300 tasks across 9 languages",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 300},
    total_samples=300,
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="official_resolved",
    protocol_version="official-harness-2026",
    dataset_source="SWE-bench/SWE-bench_Multilingual",
    dataset_revision="e5c585e008e2cb5eecc7c64192d855c53279d788",
    dataset_configs=("default",),
    dataset_splits=("test",),
    license="MIT",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
    evaluator_source="SWE-bench/SWE-bench",
    evaluator_revision="6a35510e530f236fd1dbcd9df888f01937c8494a",
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
