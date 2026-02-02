"""
MBPP (Mostly Basic Python Problems) code generation benchmark task.

Loads the MBPP dataset (974 Python coding problems) and provides
tiered evaluation support (smoke/quick/full).

CRITICAL FIX: Extracts function name from test assertions and includes it
in the prompt to improve model performance (from matric-cli commit 51382e2).

Based on https://github.com/google-research/google-research/tree/master/mbpp
"""

import json
import random
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.prompts import get_prompt
from matric_eval.scorers.code_execution import code_execution_scorer

# Path to MBPP dataset
MBPP_PATH = "/home/roctinam/data/evals/mbpp/mbpp.jsonl"


def extract_function_name(test_list: list[str]) -> str:
    """
    Extract function name from test assertions.

    This was a critical bug fix in matric-cli (commit 51382e2). MBPP prompts
    were too vague without the function name, causing models to write correct
    code but with wrong function names, leading to all tests failing.

    Args:
        test_list: List of test assertions like ["assert min_cost(...) == 8"]

    Returns:
        Function name extracted from first test, or "solution" as fallback

    Examples:
        >>> extract_function_name(["assert min_cost([[1, 2, 3]], 2, 2) == 8"])
        'min_cost'
        >>> extract_function_name(["assert is_even(2) == True"])
        'is_even'
        >>> extract_function_name([])
        'solution'
    """
    if not test_list:
        return "solution"

    # Extract first function call from first assertion
    # Pattern: "assert <function_name>(...)"
    for test in test_list:
        match = re.search(r"assert\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", test)
        if match:
            return match.group(1)

    # Fallback if no match
    return "solution"


def extract_function_signature(code: str) -> str:
    """
    Extract function signature from reference code.

    Extracts the function definition line (def ...) from the reference
    implementation to include in the prompt.

    Args:
        code: Reference Python code containing function definition

    Returns:
        Function signature like "func_name(arg1, arg2)" or "solution(...)" as fallback

    Examples:
        >>> extract_function_signature("def min_cost(cost, m, n):\\n    return 0")
        'min_cost(cost, m, n)'
        >>> extract_function_signature("# Just a comment")
        'solution(...)'
    """
    # Pattern: "def <function_name>(<params>):"
    # Match single-line function definitions
    match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\))", code)
    if match:
        return match.group(1)

    # Fallback if no match
    return "solution(...)"


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert an MBPP JSONL record to an Inspect AI Sample.

    CRITICAL: Includes function name and signature in the prompt to improve
    model performance (bug fix from matric-cli commit 51382e2).

    Args:
        record: Dictionary with keys: task_id, text, code, test_list,
                test_setup_code

    Returns:
        Sample with input containing function name/signature, target=code,
        and metadata with entry_point, test_list, test_setup_code

    Example:
        Before fix: "Write a function to find the triplet..."
        After fix:  "Write a Python function named `check_triplet` with signature:
                     `def check_triplet(array, size, target, sum)`"
    """
    # Extract function name from test assertions (CRITICAL FIX)
    func_name = extract_function_name(record["test_list"])

    # Extract function signature from reference code if available
    func_signature = extract_function_signature(record["code"])

    # Build enhanced prompt with function name and signature
    prompt = (
        f"{record['text']}\n\n"
        f"Write a Python function named `{func_name}` with signature: "
        f"`def {func_signature}`\n\n"
        f"Provide the complete function implementation."
    )

    # Build executable test code for code_execution_scorer
    # Combines setup code (if any) with test assertions
    test_setup = record.get("test_setup_code", "")
    test_assertions = "\n".join(record["test_list"])
    test_code = f"{test_setup}\n{test_assertions}" if test_setup else test_assertions

    return Sample(
        input=prompt,
        target=record["code"],
        id=f"MBPP/{record['task_id']}",
        metadata={
            "entry_point": func_name,
            "test_list": record["test_list"],
            "test_setup_code": record.get("test_setup_code", ""),
            "test": test_code,  # Pre-built test code for code_execution_scorer
        },
    )


def load_mbpp(tier: str = "smoke") -> list[Sample]:
    """
    Load MBPP samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If MBPP dataset file not found
        json.JSONDecodeError: If JSONL file is malformed
        ValueError: If dataset is empty
    """
    # Get sample count from config (respects env overrides)
    sample_count = get_sample_count("mbpp", tier)

    # Handle zero sample request early
    if sample_count == 0:
        return []

    # Load all records from JSONL
    dataset_path = Path(MBPP_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"MBPP dataset not found at {MBPP_PATH}")

    records = []
    with open(dataset_path, "r") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"MBPP dataset is empty: {MBPP_PATH}")

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
def mbpp(tier: str = "smoke", thinking: bool = True) -> Task:
    """
    MBPP (Mostly Basic Python Problems) code generation benchmark.

    Evaluates model's ability to generate Python code from problem descriptions.
    Uses 974 Python programming problems focused on basic programming concepts.

    IMPORTANT: Prompts include function names and signatures extracted from
    test assertions (critical fix from matric-cli to improve pass rates).

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples (~30 seconds)
            - "quick": 100 samples (~12 minutes)
            - "full": 974 samples (all, ~2 hours)
        thinking: Use thinking-aware prompts to reduce reasoning cycles (default: True)

    Returns:
        Task configured for MBPP evaluation

    Example:
        >>> task = mbpp(tier="smoke")
        >>> # Run with: inspect eval mbpp.py --model ollama/llama3.2:3b
    """
    return Task(
        dataset=load_mbpp(tier),
        solver=[
            system_message(get_prompt("mbpp", thinking=thinking)),
            generate(),
        ],
        scorer=code_execution_scorer(),
        name="mbpp",
    )
