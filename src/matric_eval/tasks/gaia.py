"""
GAIA (General AI Assistants) benchmark task.

Complex multi-step real-world tasks requiring web browsing, file handling,
and multi-step reasoning. Uses exact match scoring on final answers.

Based on Mialon et al. (2023): https://arxiv.org/abs/2311.12983

Dataset: https://huggingface.co/datasets/gaia-benchmark/GAIA
"""

import json
import random
import re
from pathlib import Path
from typing import Any, Optional

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState, generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.tasks.registry import register_benchmark

# Local dataset path
GAIA_PATH = "/home/roctinam/data/evals/gaia"

# GAIA difficulty levels
LEVELS = {1: "simple", 2: "moderate", 3: "complex"}


def normalize_answer(answer: str) -> str:
    """
    Normalize an answer for comparison.

    Strips whitespace, lowercases, removes articles and punctuation.

    Args:
        answer: Raw answer string

    Returns:
        Normalized answer
    """
    answer = answer.strip().lower()
    # Remove leading articles
    answer = re.sub(r"^(the|a|an)\s+", "", answer)
    # Remove trailing punctuation
    answer = re.sub(r"[.\,;:!?]+$", "", answer)
    # Collapse whitespace
    answer = " ".join(answer.split())
    return answer


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert a GAIA record to an Inspect AI Sample.

    Args:
        record: Dict with Question, Final answer, Level, etc.

    Returns:
        Sample with the question as input and expected answer as target
    """
    question = record.get("Question", record.get("question", ""))
    answer = record.get("Final answer", record.get("answer", record.get("final_answer", "")))
    level = record.get("Level", record.get("level", 1))
    task_id = record.get("task_id", record.get("id", str(hash(question))))

    # Build the prompt with context about what's expected
    prompt = f"""{question}

Provide your final answer as a short, direct response. Do not explain your reasoning — just give the answer."""

    return Sample(
        input=prompt,
        target=str(answer),
        id=task_id,
        metadata={
            "level": level,
            "level_name": LEVELS.get(level, "unknown"),
            "question": question,
            "annotator_metadata": record.get("Annotator Metadata", {}),
            "tools_needed": record.get("tools", []),
        },
    )


def load_gaia(
    tier: str = "smoke",
    levels: Optional[list[int]] = None,
) -> list[Sample]:
    """
    Load GAIA samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")
        levels: Optional filter for difficulty levels (1, 2, 3)

    Returns:
        List of Sample objects

    Raises:
        FileNotFoundError: If dataset not found
    """
    sample_count = get_sample_count("gaia", tier)
    if sample_count == 0:
        return []

    data_dir = Path(GAIA_PATH)

    # Try multiple file patterns
    jsonl_candidates = [
        data_dir / "gaia.jsonl",
        data_dir / "gaia_validation.jsonl",
        data_dir / "validation.jsonl",
    ]

    jsonl_path = None
    for candidate in jsonl_candidates:
        if candidate.exists():
            jsonl_path = candidate
            break

    if jsonl_path is None:
        raise FileNotFoundError(
            f"GAIA dataset not found in {data_dir}. "
            f"Download from https://huggingface.co/datasets/gaia-benchmark/GAIA "
            f"and save as {data_dir}/gaia.jsonl"
        )

    records = []
    with open(jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            # Filter by level if specified
            record_level = record.get("Level", record.get("level", 1))
            if levels and record_level not in levels:
                continue
            records.append(record)

    if not records:
        raise ValueError(f"No GAIA records found in {jsonl_path}")

    all_samples = [record_to_sample(r) for r in records]

    if sample_count >= len(all_samples):
        return all_samples

    seed = get_seed()
    rng = random.Random(seed)
    return rng.sample(all_samples, sample_count)


@scorer(metrics=[mean()])
def gaia_scorer() -> Scorer:
    """
    Score GAIA responses using normalized exact match.

    GAIA uses exact match on the final answer after normalization.
    This is stricter than fuzzy matching but accounts for minor
    formatting differences.

    Returns:
        Scorer function
    """

    async def score(state: TaskState, target: Target) -> Score:
        response = state.output.completion
        expected = target.text or ""

        # Extract the final answer from the response
        # Models often include explanations despite instructions
        final_answer = _extract_final_answer(response)

        # Normalize both for comparison
        norm_response = normalize_answer(final_answer)
        norm_expected = normalize_answer(expected)

        # Exact match after normalization
        is_match = norm_response == norm_expected

        # Also check if expected is contained in response (partial credit)
        contains_answer = norm_expected in normalize_answer(response)

        if is_match:
            score_value = 1.0
            explanation = "Exact match"
        elif contains_answer:
            score_value = 0.5
            explanation = "Answer present but not exact format"
        else:
            score_value = 0.0
            explanation = f"No match. Expected: '{expected}', Got: '{final_answer}'"

        return Score(
            value=score_value,
            explanation=explanation,
            metadata={
                "expected": expected,
                "extracted_answer": final_answer,
                "exact_match": is_match,
                "contains_answer": contains_answer,
                "level": state.metadata.get("level", 0),
            },
        )

    return score


def _extract_final_answer(response: str) -> str:
    """
    Extract the final answer from a model response.

    Looks for common answer patterns or takes the last line.

    Args:
        response: Full model response

    Returns:
        Extracted answer string
    """
    # Look for explicit answer markers
    patterns = [
        r"(?:final answer|answer):\s*(.+?)(?:\n|$)",
        r"(?:the answer is|result is)\s*\*\*(.+?)\*\*",  # Bold after "the answer is"
        r"(?:the answer is|result is)\s*(.+?)(?:\n|$)",
        r"\*\*(.+?)\*\*",  # Standalone bold text (often the answer)
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Fall back to the last non-empty line
    lines = [l.strip() for l in response.strip().split("\n") if l.strip()]
    return lines[-1] if lines else response.strip()


@task
def gaia(
    tier: str = "smoke",
    levels: Optional[list[int]] = None,
) -> Task:
    """
    GAIA benchmark task — complex multi-step reasoning.

    Tests end-to-end assistant capability with real-world questions
    requiring web browsing, calculation, and file handling.

    Args:
        tier: Evaluation tier
        levels: Optional difficulty level filter (1=simple, 2=moderate, 3=complex)

    Returns:
        Inspect AI Task
    """
    samples = load_gaia(tier, levels)

    return Task(
        dataset=samples,
        solver=[
            system_message(
                "You are a helpful assistant. Answer the question as precisely "
                "as possible. Give only the final answer with no explanation."
            ),
            generate(),
        ],
        scorer=gaia_scorer(),
        name="gaia",
    )


register_benchmark(
    name="gaia",
    description="GAIA — 466 complex multi-step real-world tasks requiring reasoning and tool use",
    category="agentic",
    total_samples=466,
)
