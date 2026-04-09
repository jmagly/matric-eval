"""
GPQA (Graduate-Level Google-Proof Q&A) benchmark task.

PhD-level science questions across physics, chemistry, and biology.
Uses the Diamond subset (198 questions) — the hardest and most validated subset.

Based on Rein et al. (2023): https://arxiv.org/abs/2311.12022
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
from matric_eval.tasks.registry import register_benchmark

# Local dataset path (downloaded from HuggingFace)
GPQA_PATH = "/home/roctinam/data/evals/gpqa"

ANSWER_LETTERS = ["A", "B", "C", "D"]


def format_gpqa_prompt(question: str, choices: list[str]) -> str:
    """
    Format a GPQA question as a multiple-choice prompt.

    Args:
        question: The question text
        choices: List of answer choices (4 options)

    Returns:
        Formatted prompt string
    """
    lines = [
        "Answer the following graduate-level science question.",
        "Choose the single best answer from the options below.",
        "",
        f"Question: {question}",
        "",
    ]

    for i, choice in enumerate(choices):
        label = ANSWER_LETTERS[i]
        lines.append(f"{label}) {choice}")

    lines.append("")
    lines.append("Answer with just the letter (A, B, C, or D):")

    return "\n".join(lines)


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert a GPQA record to an Inspect AI Sample.

    Handles both HuggingFace format and local JSONL format.

    Args:
        record: Dictionary with question, choices, and correct answer

    Returns:
        Sample with formatted multiple-choice input and target answer letter
    """
    question = record.get("Question", record.get("question", ""))

    # Handle different data formats
    if "Correct Answer" in record:
        # HuggingFace/original format
        correct = record["Correct Answer"]
        choices = [
            record.get("Correct Answer", ""),
            record.get("Incorrect Answer 1", ""),
            record.get("Incorrect Answer 2", ""),
            record.get("Incorrect Answer 3", ""),
        ]
        # Shuffle choices deterministically based on question
        rng = random.Random(hash(question))
        rng.shuffle(choices)
        correct_idx = choices.index(correct)
        answer_key = ANSWER_LETTERS[correct_idx]
    elif "choices" in record:
        # JSONL format with pre-formatted choices
        choices = record["choices"]
        answer_key = record.get("answer", record.get("answerKey", "A"))
    else:
        raise KeyError(f"Unrecognized GPQA record format: {list(record.keys())}")

    prompt = format_gpqa_prompt(question, choices)

    return Sample(
        input=prompt,
        target=answer_key,
        id=record.get("id", str(hash(question))),
        metadata={
            "question": question,
            "choices": choices,
            "answer_key": answer_key,
            "domain": record.get("High-level domain", record.get("domain", "unknown")),
            "subdomain": record.get("Subdomain", record.get("subdomain", "")),
        },
    )


def load_gpqa(tier: str = "smoke", subset: str = "diamond") -> list[Sample]:
    """
    Load GPQA samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")
        subset: GPQA subset ("diamond", "main", "extended")
            - diamond: 198 questions (hardest, expert-validated)
            - main: 448 questions
            - extended: All questions

    Returns:
        List of Sample objects

    Raises:
        FileNotFoundError: If GPQA dataset not found
    """
    sample_count = get_sample_count("gpqa", tier)
    if sample_count == 0:
        return []

    # Try local JSONL file first
    gpqa_dir = Path(GPQA_PATH)
    jsonl_path = gpqa_dir / f"gpqa_{subset}.jsonl"

    if not jsonl_path.exists():
        # Try alternative naming
        jsonl_path = gpqa_dir / f"{subset}.jsonl"

    if not jsonl_path.exists():
        raise FileNotFoundError(
            f"GPQA dataset not found at {jsonl_path}. "
            f"Download the GPQA Diamond subset to {GPQA_PATH}/gpqa_diamond.jsonl. "
            f"See: https://huggingface.co/datasets/Idavidrein/gpqa"
        )

    records = []
    with open(jsonl_path, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"GPQA dataset is empty: {jsonl_path}")

    all_samples = [record_to_sample(record) for record in records]

    if sample_count >= len(all_samples):
        return all_samples

    seed = get_seed()
    rng = random.Random(seed)
    return rng.sample(all_samples, sample_count)


@task
def gpqa(tier: str = "smoke", subset: str = "diamond", thinking: bool = False) -> Task:
    """
    GPQA benchmark task — PhD-level science questions.

    Tests deep domain knowledge across physics, chemistry, and biology.
    Uses chain-of-thought prompting for better reasoning.

    Args:
        tier: Evaluation tier
        subset: GPQA subset (diamond, main, extended)
        thinking: Whether model has thinking enabled

    Returns:
        Inspect AI Task for GPQA evaluation
    """
    samples = load_gpqa(tier, subset)

    system_msg = (
        "You are an expert scientist. Answer the following multiple-choice question. "
        "Think through the problem step by step, then provide your final answer as a single letter."
        if thinking
        else "You are an expert scientist. Answer with just the letter of the correct choice."
    )

    return Task(
        dataset=samples,
        solver=[
            system_message(system_msg),
            generate(),
        ],
        scorer=match(),
        name=f"gpqa_{subset}",
    )


register_benchmark(
    name="gpqa",
    description="GPQA Diamond — 198 PhD-level science questions (physics, chemistry, biology)",
    category="reasoning",
    total_samples=198,
)
