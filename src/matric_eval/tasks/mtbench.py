"""
MT-Bench multi-turn conversation benchmark task.

Loads the MT-Bench dataset (80 multi-turn conversation questions) and provides
tiered evaluation support (smoke/quick/full). Uses LLM-as-judge scoring since
responses are subjective and don't have single correct answers.

Based on https://github.com/lm-sys/FastChat/tree/main/fastchat/llm_judge
"""

import json
import random
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.scorers import llm_judge_scorer

# Path to MT-Bench dataset
MTBENCH_PATH = "/home/roctinam/data/evals/mtbench/question.jsonl"


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert an MT-Bench JSONL record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys: question_id, category, turns
                Optional: reference

    Returns:
        Sample with input=first_turn, and metadata containing all turns
    """
    turns = record["turns"]

    return Sample(
        input=turns[0],  # First turn is the initial prompt
        id=str(record["question_id"]),
        metadata={
            "turns": turns,  # All conversation turns
            "category": record["category"],
            "reference": record.get("reference"),  # Optional reference answers
        },
    )


def load_mtbench(tier: str = "smoke") -> list[Sample]:
    """
    Load MT-Bench samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If MT-Bench dataset file not found
        json.JSONDecodeError: If JSONL file is malformed
        ValueError: If dataset is empty
    """
    # Get sample count from config (respects env overrides)
    sample_count = get_sample_count("mtbench", tier)

    # Handle zero sample request early
    if sample_count == 0:
        return []

    # Load all records from JSONL
    dataset_path = Path(MTBENCH_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"MT-Bench dataset not found at {MTBENCH_PATH}")

    records = []
    with open(dataset_path, "r") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"MT-Bench dataset is empty: {MTBENCH_PATH}")

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
    sampled.sort(key=lambda s: int(s.id))

    return sampled


@task
def mtbench(tier: str = "smoke", judge_model: str = "ollama/llama3.2:3b") -> Task:
    """
    MT-Bench multi-turn conversation benchmark.

    Evaluates model's ability to engage in multi-turn conversations across
    various categories (writing, roleplay, reasoning, math, coding, etc.).
    Uses LLM-as-judge scoring since responses are subjective.

    Args:
        tier: Evaluation tier
            - "smoke": 0 samples (disabled by default)
            - "quick": 0 samples (disabled by default)
            - "full": 80 samples (all, ~40 minutes with judge scoring)
        judge_model: Model to use for scoring responses (default: "llama3.2:3b")

    Returns:
        Task configured for MT-Bench evaluation

    Example:
        >>> task = mtbench(tier="full", judge_model="llama3.2:3b")
        >>> # Run with: inspect eval mtbench.py --model ollama/llama3.2:3b

    Note:
        This benchmark requires a second model call for judge scoring,
        so evaluation time is approximately 2x slower than other benchmarks.
        Multi-turn conversation handling is currently simplified to single-turn
        evaluation. Full multi-turn support coming in future update.
    """
    return Task(
        dataset=load_mtbench(tier),
        solver=[
            system_message(
                "You are a helpful AI assistant. "
                "Provide thoughtful, accurate, and engaging responses to user questions. "
                "Be creative when appropriate and maintain conversation context."
            ),
            generate(),
        ],
        scorer=llm_judge_scorer(judge_model=judge_model),
        name="mtbench",
    )
