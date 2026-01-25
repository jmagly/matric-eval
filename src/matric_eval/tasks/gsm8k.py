"""
GSM8K (Grade School Math 8K) benchmark task.

Loads the GSM8K dataset (1,319 grade school math word problems) and provides
tiered evaluation support (smoke/quick/full).

Based on https://github.com/openai/grade-school-math
"""

import json
import random
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState, generate, system_message

from matric_eval.config import get_sample_count, get_seed

# Path to GSM8K dataset
GSM8K_PATH = "/home/roctinam/data/evals/gsm8k/test.jsonl"


def extract_answer(text: str) -> str | None:
    """
    Extract the numeric answer from a GSM8K answer string.

    GSM8K answers use the format:
        "Step-by-step solution...\n#### ANSWER"

    Args:
        text: Answer text containing #### separator

    Returns:
        Extracted answer after #### (stripped of whitespace), or None if not found
    """
    if "####" not in text:
        return None

    # Split on #### and take everything after the last occurrence
    parts = text.split("####")
    answer_part = parts[-1]

    # Extract first line (in case there's extra text after)
    first_line = answer_part.split("\n")[0]

    # Strip whitespace
    return first_line.strip()


def record_to_sample(record: dict[str, Any], index: int = 0) -> Sample:
    """
    Convert a GSM8K JSONL record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys: question, answer
        index: Index of the record (used for ID generation)

    Returns:
        Sample with input=question, target=extracted_answer, and metadata

    Raises:
        KeyError: If required fields are missing
    """
    question = record["question"]
    full_answer = record["answer"]

    # Extract numeric answer from "#### ANSWER" format
    numeric_answer = extract_answer(full_answer)

    # Sample requires non-None target, use empty string if extraction fails
    target = numeric_answer if numeric_answer is not None else ""

    return Sample(
        input=question,
        target=target,
        id=f"gsm8k_{index}",
        metadata={
            "full_answer": full_answer,
        },
    )


def load_gsm8k(tier: str = "smoke") -> list[Sample]:
    """
    Load GSM8K samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If GSM8K dataset file not found
        json.JSONDecodeError: If JSONL file is malformed
        ValueError: If dataset is empty
    """
    # Get sample count from config (respects env overrides)
    sample_count = get_sample_count("gsm8k", tier)

    # Handle zero sample request early
    if sample_count == 0:
        return []

    # Load all records from JSONL
    dataset_path = Path(GSM8K_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"GSM8K dataset not found at {GSM8K_PATH}")

    records = []
    with open(dataset_path, "r") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"GSM8K dataset is empty: {GSM8K_PATH}")

    # Convert to samples (with index for ID generation)
    all_samples = [record_to_sample(record, index=i) for i, record in enumerate(records)]

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


def normalize_number(text: str) -> str | None:
    """
    Normalize a numeric answer for comparison.

    Handles:
    - Removing dollar signs
    - Removing commas
    - Converting to float then back to string for consistent formatting

    Args:
        text: Numeric text to normalize

    Returns:
        Normalized numeric string, or None if not a valid number
    """
    if not text:
        return None

    # Remove common formatting
    cleaned = text.strip()
    cleaned = cleaned.replace("$", "")
    cleaned = cleaned.replace(",", "")

    # Try to parse as number
    try:
        # Handle integers and floats
        if "." in cleaned or "e" in cleaned.lower():
            # Float or scientific notation
            num = float(cleaned)
            # Return as string, removing unnecessary decimal points
            if num == int(num):
                return str(int(num))
            return str(num)
        else:
            # Integer
            return str(int(cleaned))
    except (ValueError, TypeError):
        # Not a valid number, return as-is
        return text.strip()


@scorer(metrics=[mean()])
def gsm8k_scorer() -> Scorer:
    """
    Score GSM8K responses by extracting and comparing numeric answers.

    Extracts numeric answers from both the expected answer (target) and
    model response, then compares them after normalization.

    Returns:
        Scorer that handles numeric answer matching
    """

    async def score(state: TaskState, target: Target) -> Score:
        """
        Score a single GSM8K response.

        Args:
            state: Task state containing model output
            target: Expected answer

        Returns:
            Score indicating correct/incorrect with explanation
        """
        # Get model output
        model_output = state.output.completion

        # Extract answer from model output (look for #### format first)
        model_answer = extract_answer(model_output)
        if model_answer is None:
            # If no #### separator, try to extract last number from response
            # This handles cases where model doesn't use exact format
            numbers = re.findall(r"-?\$?\d+(?:,\d{3})*(?:\.\d+)?", model_output)
            if numbers:
                model_answer = numbers[-1]
            else:
                model_answer = ""

        # Get expected answer
        expected_answer = target.text if isinstance(target.text, str) else str(target.text)

        # Normalize both answers for comparison
        normalized_model = normalize_number(model_answer)
        normalized_expected = normalize_number(expected_answer)

        # Compare normalized answers
        is_correct = (
            normalized_model is not None
            and normalized_expected is not None
            and normalized_model == normalized_expected
        )

        return Score(
            value="C" if is_correct else "I",
            answer=model_answer,
            explanation=f"Expected: {expected_answer}, Got: {model_answer}"
            + (f" (normalized: {normalized_expected} vs {normalized_model})" if not is_correct else ""),
        )

    return score


@task
def gsm8k(tier: str = "smoke") -> Task:
    """
    GSM8K grade school math benchmark.

    Evaluates model's ability to solve math word problems from grade school.
    Uses 1,319 problems from the GSM8K dataset.

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples (~2 minutes)
            - "quick": 75 samples (~8 minutes)
            - "full": 1,319 samples (all, ~45 minutes)

    Returns:
        Task configured for GSM8K evaluation

    Example:
        >>> task = gsm8k(tier="smoke")
        >>> # Run with: inspect eval gsm8k.py --model ollama/llama3.2:3b
    """
    return Task(
        dataset=load_gsm8k(tier),
        solver=[
            system_message(
                "You are a math problem solver. "
                "Solve the problem step by step. "
                'After showing your work, provide the final numeric answer on a new line after "####".\n'
                "Example format:\n"
                "Step 1: ...\n"
                "Step 2: ...\n"
                "#### 42"
            ),
            generate(),
        ],
        scorer=gsm8k_scorer(),
        name="gsm8k",
    )
