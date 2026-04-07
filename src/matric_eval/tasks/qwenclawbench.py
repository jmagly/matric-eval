"""
QwenClawBench — real-world agent benchmark from the Qwen team.

Tests agentic capabilities across diverse real-world tasks.
Dataset availability unconfirmed (RISK-008).
"""

from __future__ import annotations

import random
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState, generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, load_hf_dataset
from matric_eval.tasks.registry import register_benchmark


QWENCLAWBENCH_SYSTEM_PROMPT = """\
You are an autonomous agent. You will be given a real-world task to \
accomplish. Complete the task using the tools available to you.\
"""


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a QwenClawBench record to an Inspect AI Sample."""
    task_id = record.get("task_id", record.get("id", ""))
    description = record.get("description", record.get("input", ""))
    expected = record.get("expected_output", record.get("target", ""))

    return Sample(
        input=description,
        target=expected,
        id=str(task_id),
        metadata={
            "category": record.get("category", ""),
            "difficulty": record.get("difficulty", ""),
        },
    )


@scorer(metrics=[mean()])
def qwenclawbench_scorer() -> Scorer:
    """Task completion scorer for QwenClawBench."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion
        if not completion or not completion.strip():
            return Score(value=0.0, explanation="No output generated")

        return Score(
            value=0.0,
            explanation="Scoring requires agentic-sandbox execution",
            metadata={"sandbox_required": True},
        )

    return score


def load_qwenclawbench(tier: str = "smoke") -> list[Sample]:
    """Load QwenClawBench samples for the given tier."""
    benchmark_name = "qwenclawbench"
    sample_count = get_sample_count(benchmark_name, tier)

    local_path = get_dataset_path(benchmark_name)
    if local_path:
        import json
        from pathlib import Path

        records = []
        with open(Path(local_path)) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        all_samples = [record_to_sample(r) for r in records]
    else:
        all_samples = load_hf_dataset(
            "Qwen/QwenClawBench",
            split="test",
            sample_count=sample_count,
            seed=get_seed(),
            record_to_sample=record_to_sample,
        )
        return all_samples

    if sample_count >= len(all_samples):
        return all_samples

    rng = random.Random(get_seed())
    sampled = rng.sample(all_samples, sample_count)
    sampled.sort(key=lambda s: s.id or "")
    return sampled


@register_benchmark(
    name="qwenclawbench",
    description="QwenClawBench - Qwen team agentic benchmark",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 0},
    total_samples=0,  # TBD — dataset may not be publicly released
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="standard",
)
@task
def qwenclawbench(tier: str = "smoke") -> Task:
    """QwenClawBench benchmark from the Qwen team.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for QwenClawBench evaluation
    """
    return Task(
        dataset=load_qwenclawbench(tier),
        solver=[
            system_message(QWENCLAWBENCH_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=qwenclawbench_scorer(),
        name="qwenclawbench",
    )
