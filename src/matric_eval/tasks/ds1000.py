"""
DS-1000 data science coding benchmark task.

Loads the DS-1000 dataset (1,000 data science coding problems) focusing on
pandas, numpy, matplotlib, sklearn, and other data science libraries.
Provides tiered evaluation support (smoke/quick/full).

Based on https://github.com/xlang-ai/DS-1000
"""

import json
import random
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed

# Path to DS-1000 dataset
DS1000_PATH = "/home/roctinam/data/evals/ds1000/ds1000.jsonl"


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert a DS-1000 JSONL record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys: prompt, reference_code, metadata,
                code_context

    Returns:
        Sample with input=prompt, target=reference_code, and metadata
        with library, problem_id, test info, and code_context
    """
    # Extract metadata
    meta = record.get("metadata", {})
    library = meta.get("library", "Unknown")
    problem_id = meta.get("problem_id", 0)

    # Build comprehensive prompt including the problem and any setup
    # DS-1000 prompts are already well-formatted with problem description
    prompt = record["prompt"]

    # Build ID from library and problem_id
    sample_id = f"DS1000/{library}/{problem_id}"

    return Sample(
        input=prompt,
        target=record["reference_code"],
        id=sample_id,
        metadata={
            "library": library,
            "problem_id": problem_id,
            "library_problem_id": meta.get("library_problem_id", 0),
            "test_case_cnt": meta.get("test_case_cnt", 0),
            "perturbation_type": meta.get("perturbation_type", ""),
            "perturbation_origin_id": meta.get("perturbation_origin_id", 0),
            "code_context": record.get("code_context", ""),
        },
    )


def load_ds1000(tier: str = "smoke") -> list[Sample]:
    """
    Load DS-1000 samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If DS-1000 dataset file not found
        json.JSONDecodeError: If JSONL file is malformed
        ValueError: If dataset is empty
    """
    # Get sample count from config (respects env overrides)
    sample_count = get_sample_count("ds1000", tier)

    # Handle zero sample request early
    if sample_count == 0:
        return []

    # Load all records from JSONL
    dataset_path = Path(DS1000_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"DS-1000 dataset not found at {DS1000_PATH}")

    records = []
    with open(dataset_path, "r") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"DS-1000 dataset is empty: {DS1000_PATH}")

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
def ds1000(tier: str = "smoke") -> Task:
    """
    DS-1000 data science coding benchmark.

    Evaluates model's ability to solve data science coding problems using
    pandas, numpy, matplotlib, sklearn, and other libraries. Uses 1,000
    problems with executable test cases.

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples (~1 minute)
            - "quick": 50 samples (~10 minutes)
            - "full": 1000 samples (all, ~3 hours)

    Returns:
        Task configured for DS-1000 evaluation

    Example:
        >>> task = ds1000(tier="smoke")
        >>> # Run with: inspect eval ds1000.py --model ollama/llama3.2:3b
    """
    return Task(
        dataset=load_ds1000(tier),
        solver=[
            system_message(
                "You are an expert data scientist and Python programmer. "
                "Solve the data science problem using pandas, numpy, matplotlib, "
                "or other appropriate libraries. "
                "Pay attention to the provided code context and setup. "
                "Return only the solution code that assigns the result to the "
                "specified variable."
            ),
            generate(),
        ],
        scorer=includes(),  # Will be replaced with code_execution_scorer in future task
        name="ds1000",
    )
