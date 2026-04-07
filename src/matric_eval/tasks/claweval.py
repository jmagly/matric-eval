"""
Claw-Eval benchmark — real-world agent tasks with pass^3 scoring.

Three independent sandbox runs per sample, all must pass for score 1.0.
Tests agent reliability and consistency.

Scoring: pass_power_k(k=3) — all 3 runs must succeed.

Dataset: Claw-Eval public dataset (TBD)
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


CLAWEVAL_SYSTEM_PROMPT = """\
You are an autonomous coding agent. You will be given a real-world task \
to accomplish in a sandboxed environment. Complete the task by generating \
the necessary code and commands.

Your solution must be reliable — it will be tested across multiple \
independent runs.\
"""


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a Claw-Eval record to an Inspect AI Sample.

    Expected schema:
        - task_id: str
        - description: str
        - verification: str (verification command/script)
        - setup: dict (environment setup)
        - difficulty: str
    """
    task_id = record.get("task_id", record.get("id", ""))
    description = record.get("description", record.get("input", ""))
    verification = record.get("verification", record.get("target", ""))

    return Sample(
        input=description,
        target=verification,
        id=str(task_id),
        metadata={
            "verification": verification,
            "setup": record.get("setup", {}),
            "difficulty": record.get("difficulty", "medium"),
            "k": 3,  # pass^3
        },
    )


@scorer(metrics=[mean()])
def claweval_scorer() -> Scorer:
    """Scorer placeholder for Claw-Eval pass^3 evaluation.

    Actual scoring requires 3 independent sandbox runs via
    EvaluationEngine.run_pass_k_benchmark(k=3).
    """

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion
        if not completion or not completion.strip():
            return Score(value=0.0, explanation="No output generated")

        return Score(
            value=0.0,
            explanation="pass^3 scoring requires 3 sandbox runs via EvaluationEngine",
            metadata={
                "sandbox_required": True,
                "scoring_type": "pass_k",
                "k": 3,
            },
        )

    return score


def load_claweval(tier: str = "smoke") -> list[Sample]:
    """Load Claw-Eval samples for the given tier."""
    benchmark_name = "claweval"
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
            "claw-eval/claw-eval",
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
    name="claweval",
    description="Claw-Eval - agentic tasks with pass^3 reliability scoring",
    category="agentic",
    tier_samples={"smoke": 3, "quick": 20, "full": 0},
    total_samples=0,  # TBD
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="pass_k",
)
@task
def claweval(tier: str = "smoke") -> Task:
    """Claw-Eval benchmark with pass^3 scoring.

    Each sample is run 3 times independently; all must pass for score 1.0.
    Use EvaluationEngine.run_pass_k_benchmark(k=3) for full evaluation.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for Claw-Eval evaluation
    """
    return Task(
        dataset=load_claweval(tier),
        solver=[
            system_message(CLAWEVAL_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=claweval_scorer(),
        name="claweval",
    )
