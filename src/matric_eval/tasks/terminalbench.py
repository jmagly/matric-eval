"""
Terminal-Bench 2.0 — terminal/shell agentic coding benchmark.

Models are given terminal tasks and must execute shell commands to accomplish
them. Tests terminal agent capabilities with bash_exec tool only.

Dataset: Terminal-Bench 2.0 public dataset (TBD)
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


TERMINALBENCH_SYSTEM_PROMPT = """\
You are an expert Linux system administrator. You will be given a task \
to accomplish using shell commands in a terminal environment. Execute \
the necessary commands to complete the task.

You have access to standard Linux tools (bash, grep, sed, awk, find, etc.). \
Output the shell commands needed to accomplish the task.\
"""


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a Terminal-Bench record to an Inspect AI Sample.

    Expected schema:
        - task_id: str
        - description: str (task description)
        - expected_output: str (expected terminal state/output)
        - setup_commands: list[str] (optional pre-task setup)
        - verification: str (command to verify completion)
    """
    task_id = record.get("task_id", record.get("id", ""))
    description = record.get("description", record.get("input", ""))
    expected = record.get("expected_output", record.get("target", ""))
    setup = record.get("setup_commands", [])
    verification = record.get("verification", "")

    return Sample(
        input=description,
        target=expected,
        id=str(task_id),
        metadata={
            "setup_commands": setup,
            "verification": verification,
            "sandbox_type": "terminal",
        },
    )


@scorer(metrics=[mean()])
def terminal_task_scorer() -> Scorer:
    """Scorer for terminal task completion.

    Scores 1.0 if the verification command succeeds after model execution,
    0.0 otherwise. Requires agentic-sandbox for actual execution.
    """

    async def score(state: TaskState, target: Target) -> Score:
        metadata = state.metadata or {}
        verification = metadata.get("verification", "")
        completion = state.output.completion

        if not completion or not completion.strip():
            return Score(value=0.0, explanation="No commands generated")

        return Score(
            value=0.0,
            explanation="Terminal scoring requires agentic-sandbox execution",
            metadata={
                "commands": completion,
                "verification": verification,
                "sandbox_required": True,
                "sandbox_type": "terminal",
            },
        )

    return score


def load_terminalbench(tier: str = "smoke") -> list[Sample]:
    """Load Terminal-Bench samples for the given tier."""
    benchmark_name = "terminalbench"
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
            "terminal-bench/terminal-bench-2.0",
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
    name="terminalbench",
    description="Terminal-Bench 2.0 - terminal/shell agentic tasks",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 0},
    total_samples=0,  # TBD
    requires_sandbox=True,
    sandbox_profile="basic",
    scoring_type="standard",
)
@task
def terminalbench(tier: str = "smoke") -> Task:
    """Terminal-Bench 2.0 benchmark.

    Models interact via bash_exec tool only (no file editing tools).
    Scored by task completion verification.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for Terminal-Bench evaluation
    """
    return Task(
        dataset=load_terminalbench(tier),
        solver=[
            system_message(TERMINALBENCH_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=terminal_task_scorer(),
        name="terminalbench",
    )
