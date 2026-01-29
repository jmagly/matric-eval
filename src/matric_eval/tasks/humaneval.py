"""
HumanEval code generation benchmark task.

Loads the HumanEval dataset (164 Python coding problems) and provides
tiered evaluation support (smoke/quick/full).

Based on https://github.com/openai/human-eval
"""

import json
import random
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, json_dataset
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.scorers.code_execution import code_execution_scorer

# Path to HumanEval dataset
HUMANEVAL_PATH = "/home/roctinam/data/evals/humaneval/HumanEval.jsonl"


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert a HumanEval JSONL record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys: task_id, prompt, entry_point,
                canonical_solution, test

    Returns:
        Sample with input=prompt, target=canonical_solution, and metadata
    """
    return Sample(
        input=record["prompt"],
        target=record["canonical_solution"],
        id=record["task_id"],
        metadata={
            "entry_point": record["entry_point"],
            "test": record["test"],
        },
    )


def load_humaneval(tier: str = "smoke") -> list[Sample]:
    """
    Load HumanEval samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If HumanEval dataset file not found
        json.JSONDecodeError: If JSONL file is malformed
        ValueError: If dataset is empty
    """
    # Get sample count from config (respects env overrides)
    sample_count = get_sample_count("humaneval", tier)

    # Handle zero sample request early
    if sample_count == 0:
        return []

    # Load all records from JSONL
    dataset_path = Path(HUMANEVAL_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"HumanEval dataset not found at {HUMANEVAL_PATH}")

    records = []
    with open(dataset_path, "r") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"HumanEval dataset is empty: {HUMANEVAL_PATH}")

    # Convert to samples
    all_samples = [record_to_sample(record) for record in records]

    # Apply tiered sampling with reproducible seed
    if sample_count >= len(all_samples):
        # Return all samples if requested count exceeds dataset size
        return all_samples

    # Reproducible random sampling
    seed = get_seed()
    rng = random.Random(seed)

    # Sample without replacement
    sampled = rng.sample(all_samples, sample_count)

    # Sort by ID to maintain consistent order
    sampled.sort(key=lambda s: s.id)

    return sampled


@task
def humaneval(tier: str = "smoke") -> Task:
    """
    HumanEval code generation benchmark.

    Evaluates model's ability to generate Python code from docstring prompts.
    Uses 164 hand-written programming problems from OpenAI.

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples (~30 seconds)
            - "quick": 75 samples (~8 minutes)
            - "full": 164 samples (all, ~18 minutes)

    Returns:
        Task configured for HumanEval evaluation

    Example:
        >>> task = humaneval(tier="smoke")
        >>> # Run with: inspect eval humaneval.py --model ollama/llama3.2:3b
    """
    return Task(
        dataset=load_humaneval(tier),
        solver=[
            system_message(
                "You are a Python coding assistant. "
                "Complete the function based on the docstring. "
                "Return only the function implementation, no explanations or examples."
            ),
            generate(),
        ],
        scorer=code_execution_scorer(),
        name="humaneval",
    )
