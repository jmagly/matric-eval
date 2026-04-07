"""
Shared factory for SWE-bench benchmark variants.

All SWE-bench variants share the same task structure:
1. Load dataset (repo + issue description + base commit)
2. Provision sandbox at the correct commit
3. Model receives issue context and generates a patch
4. Score via patch_apply_scorer (binary: applies + tests pass)

Variants differ only in dataset source and difficulty.
"""

from __future__ import annotations

import random
from typing import Any, Callable

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, load_hf_dataset
from matric_eval.scorers.patch_apply import patch_apply_scorer


# ---------------------------------------------------------------------------
# Dataset schema → Sample conversion
# ---------------------------------------------------------------------------

def swebench_record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a SWE-bench HuggingFace record to an Inspect AI Sample.

    SWE-bench schema (princeton-nlp/SWE-bench_Verified):
        - instance_id: str (e.g., "django__django-11099")
        - repo: str (e.g., "django/django")
        - base_commit: str (40-char SHA)
        - patch: str (gold patch)
        - test_patch: str (test additions for verification)
        - problem_statement: str (GitHub issue body)
        - hints_text: str (optional hints)
        - version: str (e.g., "4.0")

    Returns:
        Sample with input=problem_statement, target=patch, metadata with
        repo info needed by the sandbox and patch_apply_scorer.
    """
    instance_id = record.get("instance_id", "")
    repo = record.get("repo", "")
    base_commit = record.get("base_commit", "")
    problem_statement = record.get("problem_statement", "")
    patch = record.get("patch", "")
    test_patch = record.get("test_patch", "")
    hints = record.get("hints_text", "")

    # Build the prompt context
    prompt_parts = [
        f"Repository: {repo}",
        f"Base commit: {base_commit}",
        "",
        "## Issue Description",
        problem_statement,
    ]
    if hints:
        prompt_parts.extend(["", "## Hints", hints])

    prompt_parts.extend([
        "",
        "## Task",
        "Generate a git patch that resolves the issue described above.",
        "Output ONLY the patch content (unified diff format).",
    ])

    return Sample(
        input="\n".join(prompt_parts),
        target=patch,
        id=instance_id,
        metadata={
            "instance_id": instance_id,
            "repo": repo,
            "base_commit": base_commit,
            "test_patch": test_patch,
            "repo_path": f"/workspace/{repo.replace('/', '_')}",
            "test_path": _extract_test_path(test_patch),
        },
    )


def _extract_test_path(test_patch: str) -> str:
    """Extract the primary test file path from a test patch.

    Looks for the first +++ b/path/to/test.py line in the diff.
    Returns empty string if no test path found.
    """
    for line in test_patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path and not path.startswith("/dev/null"):
                return path
    return ""


# ---------------------------------------------------------------------------
# Shared loader
# ---------------------------------------------------------------------------

SWEBENCH_SYSTEM_PROMPT = """\
You are an expert software engineer. You will be given a GitHub issue \
description from a real open-source repository. Your task is to generate \
a git patch (unified diff format) that resolves the issue.

Output ONLY the patch content. Do not include explanations or markdown fences.\
"""

# Dataset IDs and known sizes per variant
VARIANT_CONFIG: dict[str, dict[str, Any]] = {
    "verified": {
        "dataset_id": "princeton-nlp/SWE-bench_Verified",
        "split": "test",
        "total_samples": 500,
    },
    "pro": {
        "dataset_id": "princeton-nlp/SWE-bench_Pro",
        "split": "test",
        "total_samples": 0,  # TBD — dataset not yet confirmed
    },
    "multilingual": {
        "dataset_id": "princeton-nlp/SWE-bench_Multilingual",
        "split": "test",
        "total_samples": 0,  # TBD — dataset not yet confirmed
    },
}


def load_swebench(
    variant: str,
    tier: str = "smoke",
    record_to_sample_fn: Callable | None = None,
) -> list[Sample]:
    """Load SWE-bench samples for a given variant and tier.

    Args:
        variant: One of "verified", "pro", "multilingual"
        tier: Evaluation tier ("smoke", "quick", "full")
        record_to_sample_fn: Override record converter (for multilingual)

    Returns:
        List of Sample objects

    Raises:
        ValueError: If variant is unknown
    """
    if variant not in VARIANT_CONFIG:
        raise ValueError(
            f"Unknown SWE-bench variant '{variant}'. "
            f"Available: {', '.join(sorted(VARIANT_CONFIG))}"
        )

    config = VARIANT_CONFIG[variant]
    benchmark_name = f"swebench_{variant}"
    converter = record_to_sample_fn or swebench_record_to_sample

    # Check for local path override
    local_path = get_dataset_path(benchmark_name)
    if local_path:
        import json
        from pathlib import Path

        records = []
        with open(Path(local_path)) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

        all_samples = [converter(r) for r in records]
    else:
        sample_count = get_sample_count(benchmark_name, tier)
        all_samples = load_hf_dataset(
            config["dataset_id"],
            split=config["split"],
            sample_count=sample_count,
            seed=get_seed(),
            record_to_sample=converter,
        )
        return all_samples

    # Apply tier sampling
    sample_count = get_sample_count(benchmark_name, tier)
    if sample_count >= len(all_samples):
        return all_samples

    rng = random.Random(get_seed())
    sampled = rng.sample(all_samples, sample_count)
    sampled.sort(key=lambda s: s.id or "")
    return sampled


def create_swebench_task(
    variant: str,
    tier: str = "smoke",
    record_to_sample_fn: Callable | None = None,
) -> Task:
    """Create an Inspect AI Task for a SWE-bench variant.

    Args:
        variant: One of "verified", "pro", "multilingual"
        tier: Evaluation tier
        record_to_sample_fn: Override record converter

    Returns:
        Inspect AI Task configured for SWE-bench evaluation
    """
    samples = load_swebench(variant, tier, record_to_sample_fn)

    return Task(
        dataset=samples,
        solver=[
            system_message(SWEBENCH_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=patch_apply_scorer(),
        name=f"swebench_{variant}",
    )
