"""
ARC (AI2 Reasoning Challenge) benchmark task.

Loads the ARC-Challenge dataset (1,172 multiple-choice reasoning problems)
and provides tiered evaluation support (smoke/quick/full).

Based on https://allenai.org/data/arc
"""

import json
import random
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import match
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed

# Path to ARC-Challenge dataset
ARC_PATH = "/home/roctinam/data/evals/arc/ARC-Challenge/ARC-Challenge-Test.jsonl"


def format_arc_prompt(question: str, choices: list[dict[str, str]]) -> str:
    """
    Format an ARC question as a multiple-choice prompt.

    Args:
        question: The question stem
        choices: List of choice dicts with 'text' and 'label' keys

    Returns:
        Formatted prompt string in the form:
        Question: <question>

        A) <choice 1>
        B) <choice 2>
        C) <choice 3>
        D) <choice 4>

        Answer:

    Example:
        >>> choices = [
        ...     {"text": "Red", "label": "A"},
        ...     {"text": "Blue", "label": "B"},
        ... ]
        >>> prompt = format_arc_prompt("What color is the sky?", choices)
        >>> print(prompt)
        Question: What color is the sky?

        A) Red
        B) Blue

        Answer:
    """
    lines = [f"Question: {question}", ""]

    # Add each choice
    for choice in choices:
        label = choice["label"]
        text = choice["text"]
        lines.append(f"{label}) {text}")

    # Add answer prompt
    lines.append("")
    lines.append("Answer:")

    return "\n".join(lines)


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert an ARC JSONL record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys:
            - id: Unique identifier (e.g., "Mercury_7175875")
            - question: Dict with 'stem' and 'choices'
                - stem: Question text
                - choices: List of dicts with 'text' and 'label'
            - answerKey: Correct answer label (e.g., "A", "B", "C", "D")

    Returns:
        Sample with formatted multiple-choice input, target=answerKey, and metadata

    Raises:
        KeyError: If required fields are missing from record
    """
    question_data = record["question"]
    question_stem = question_data["stem"]
    choices = question_data["choices"]
    answer_key = record["answerKey"]

    # Format the multiple-choice prompt
    prompt = format_arc_prompt(question_stem, choices)

    return Sample(
        input=prompt,
        target=answer_key,
        id=record["id"],
        metadata={
            "question_stem": question_stem,
            "choices": choices,
            "answer_key": answer_key,
        },
    )


def load_arc(tier: str = "smoke") -> list[Sample]:
    """
    Load ARC samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If ARC dataset file not found
        json.JSONDecodeError: If JSONL file is malformed
        ValueError: If dataset is empty
    """
    # Get sample count from config (respects env overrides)
    sample_count = get_sample_count("arc", tier)

    # Handle zero sample request early
    if sample_count == 0:
        return []

    # Load all records from JSONL
    dataset_path = Path(ARC_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"ARC dataset not found at {ARC_PATH}")

    records = []
    with open(dataset_path, "r") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"ARC dataset is empty: {ARC_PATH}")

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
def arc(tier: str = "smoke") -> Task:
    """
    ARC (AI2 Reasoning Challenge) benchmark.

    Evaluates model's ability to answer grade-school science questions
    requiring reasoning over multiple facts. Uses 1,172 challenge-set
    questions from the Allen Institute for AI.

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples (~30 seconds)
            - "quick": 75 samples (~4 minutes)
            - "full": 1,172 samples (all, ~47 minutes)

    Returns:
        Task configured for ARC evaluation

    Example:
        >>> task = arc(tier="smoke")
        >>> # Run with: inspect eval arc.py --model ollama/llama3.2:3b

    References:
        - Paper: https://arxiv.org/abs/1803.05457
        - Dataset: https://allenai.org/data/arc
    """
    return Task(
        dataset=load_arc(tier),
        solver=[
            system_message(
                "You are a helpful AI assistant answering multiple-choice questions. "
                "Read the question carefully and select the best answer. "
                "Respond with only the letter of your choice (A, B, C, or D), "
                "no explanations or additional text."
            ),
            generate(),
        ],
        scorer=match(),  # Exact match scorer for multiple choice
        name="arc",
    )
