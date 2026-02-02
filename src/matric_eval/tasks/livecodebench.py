"""
LiveCodeBench competitive programming benchmark task.

Loads the LiveCodeBench dataset (880+ competitive programming problems from
AtCoder, CodeForces, LeetCode) and provides tiered evaluation support
(smoke/quick/full).

Based on https://livecodebench.github.io/
"""

import json
import random
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.prompts import get_prompt
from matric_eval.scorers.io_execution import io_execution_scorer

# Path to LiveCodeBench dataset
LIVECODEBENCH_PATH = "/home/roctinam/data/evals/livecodebench/livecodebench.jsonl"


def parse_test_cases(test_cases_str: str | list) -> list:
    """
    Parse test cases from JSON string or return as-is if already a list.

    Args:
        test_cases_str: Either a JSON string or list of test cases

    Returns:
        List of test case dictionaries
    """
    if isinstance(test_cases_str, list):
        return test_cases_str

    if not test_cases_str or test_cases_str.strip() == "":
        return []

    try:
        return json.loads(test_cases_str)
    except json.JSONDecodeError:
        # If not valid JSON, might be compressed or invalid format
        # Return empty list for now (private tests are often compressed)
        return []


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert a LiveCodeBench JSONL record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys: question_title, question_content,
                platform, question_id, contest_id, starter_code,
                public_test_cases, private_test_cases, difficulty, metadata

    Returns:
        Sample with input=formatted_prompt, target=first_test_output,
        and metadata with platform, test_cases, difficulty
    """
    # Parse test cases (they are stored as JSON strings in the dataset)
    public_tests = parse_test_cases(record.get("public_test_cases", "[]"))
    private_tests = parse_test_cases(record.get("private_test_cases", "[]"))

    # Build prompt with question title and content
    prompt_parts = [
        f"# {record['question_title']}",
        "",
        record["question_content"],
    ]

    # Include starter code if provided
    if record.get("starter_code", "").strip():
        prompt_parts.extend([
            "",
            "## Starter Code",
            "```python",
            record["starter_code"],
            "```",
        ])

    # Include sample test case if available
    if public_tests:
        first_test = public_tests[0]
        prompt_parts.extend([
            "",
            "## Example",
            f"Input: {first_test.get('input', '')}",
            f"Output: {first_test.get('output', '')}",
        ])

    prompt = "\n".join(prompt_parts)

    # Target is the first public test case output (or empty if none)
    target = ""
    if public_tests:
        target = public_tests[0].get("output", "")

    # If no public tests, try private tests
    if not target and private_tests:
        target = private_tests[0].get("output", "")

    # Build ID from platform and question_id
    sample_id = f"{record['platform']}/{record['question_id']}"

    return Sample(
        input=prompt,
        target=target,
        id=sample_id,
        metadata={
            "platform": record["platform"],
            "difficulty": record.get("difficulty", "unknown"),
            "contest_id": record.get("contest_id", ""),
            "contest_date": record.get("contest_date", ""),
            "public_test_cases": public_tests,
            "private_test_cases": private_tests,
            "starter_code": record.get("starter_code", ""),
        },
    )


def load_livecodebench(tier: str = "smoke") -> list[Sample]:
    """
    Load LiveCodeBench samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If LiveCodeBench dataset file not found
        json.JSONDecodeError: If JSONL file is malformed
        ValueError: If dataset is empty
    """
    # Get sample count from config (respects env overrides)
    sample_count = get_sample_count("livecodebench", tier)

    # Handle zero sample request early
    if sample_count == 0:
        return []

    # Load all records from JSONL
    dataset_path = Path(LIVECODEBENCH_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"LiveCodeBench dataset not found at {LIVECODEBENCH_PATH}"
        )

    records = []
    with open(dataset_path, "r") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"LiveCodeBench dataset is empty: {LIVECODEBENCH_PATH}")

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
def livecodebench(tier: str = "smoke", thinking: bool = True) -> Task:
    """
    LiveCodeBench competitive programming benchmark.

    Evaluates model's ability to solve competitive programming problems from
    real contests on AtCoder, CodeForces, and LeetCode. Uses 880+ problems
    with test cases for validation.

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples (~1 minute)
            - "quick": 50 samples (~10 minutes)
            - "full": 880+ samples (all, ~3 hours)
        thinking: Use thinking-aware prompts to reduce reasoning cycles (default: True)

    Returns:
        Task configured for LiveCodeBench evaluation

    Example:
        >>> task = livecodebench(tier="smoke")
        >>> # Run with: inspect eval livecodebench.py --model ollama/llama3.2:3b
    """
    return Task(
        dataset=load_livecodebench(tier),
        solver=[
            system_message(get_prompt("livecodebench", thinking=thinking)),
            generate(),
        ],
        scorer=io_execution_scorer(),
        name="livecodebench",
    )
