"""
QwenWebBench — web artifact generation benchmark with Elo rating.

Models generate web pages/components and are compared pairwise using
LLM-as-judge, producing Elo ratings.

Scoring: EloAggregator (base 1200, K=32) with pairwise LLM judge.
Dataset: TBD from Qwen team (RISK-008).
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


QWENWEBBENCH_SYSTEM_PROMPT = """\
You are an expert web developer. You will be given a specification for a \
web page or component. Generate the complete HTML, CSS, and JavaScript \
needed to implement it.

Output clean, production-quality code that matches the specification.\
"""


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a QwenWebBench record to an Inspect AI Sample."""
    task_id = record.get("task_id", record.get("id", ""))
    spec = record.get("specification", record.get("input", ""))
    reference = record.get("reference_html", record.get("target", ""))

    return Sample(
        input=spec,
        target=reference,
        id=str(task_id),
        metadata={
            "category": record.get("category", ""),
            "complexity": record.get("complexity", ""),
        },
    )


@scorer(metrics=[mean()])
def webbench_scorer() -> Scorer:
    """Placeholder scorer for QwenWebBench.

    Actual Elo scoring requires pairwise comparison of multiple models.
    Use EloAggregator for cross-model comparison after individual evals.
    """

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion
        if not completion or not completion.strip():
            return Score(value=0.0, explanation="No web artifact generated")

        # Check for basic HTML presence
        has_html = "<" in completion and ">" in completion
        return Score(
            value=0.5 if has_html else 0.0,
            explanation="Elo ranking requires pairwise comparison via EloAggregator",
            metadata={
                "scoring_type": "elo",
                "has_html": has_html,
                "artifact_length": len(completion),
            },
        )

    return score


def load_qwenwebbench(tier: str = "smoke") -> list[Sample]:
    """Load QwenWebBench samples for the given tier."""
    benchmark_name = "qwenwebbench"
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
            "Qwen/QwenWebBench",
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
    name="qwenwebbench",
    description="QwenWebBench - web artifact generation with Elo rating",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 30, "full": 0},
    total_samples=0,  # TBD
    requires_sandbox=False,
    scoring_type="elo",
)
@task
def qwenwebbench(tier: str = "smoke") -> Task:
    """QwenWebBench benchmark with Elo-based scoring.

    Models generate web artifacts rated via pairwise LLM judge comparison.
    Use EloAggregator for cross-model Elo ratings after evaluation.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for QwenWebBench evaluation
    """
    return Task(
        dataset=load_qwenwebbench(tier),
        solver=[
            system_message(QWENWEBBENCH_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=webbench_scorer(),
        name="qwenwebbench",
    )
