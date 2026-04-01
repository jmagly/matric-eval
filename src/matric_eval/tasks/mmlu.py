"""
MMLU (Massive Multitask Language Understanding) benchmark task.

Loads the MMLU dataset (14,042 multiple-choice questions across 57 subjects)
and provides tiered evaluation support (smoke/quick/full).

Based on Hendrycks et al. (2021): https://arxiv.org/abs/2009.03300
"""

import csv
import random
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import match
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed

# Path to MMLU test dataset directory
MMLU_TEST_PATH = "/home/roctinam/data/evals/mmlu/data/test"
MMLU_DEV_PATH = "/home/roctinam/data/evals/mmlu/data/dev"

# Answer letter mapping
ANSWER_LETTERS = ["A", "B", "C", "D"]


def format_subject_name(subject: str) -> str:
    """
    Format a subject slug into a human-readable name.

    Args:
        subject: Underscore-separated subject name (e.g., "abstract_algebra")

    Returns:
        Human-readable name (e.g., "Abstract Algebra")
    """
    return subject.replace("_", " ").title()


def format_mmlu_prompt(
    question: str,
    choices: list[str],
    subject: str | None = None,
) -> str:
    """
    Format an MMLU question as a multiple-choice prompt.

    Args:
        question: The question text
        choices: List of 4 answer choices
        subject: Optional subject name for context

    Returns:
        Formatted prompt string
    """
    lines = []
    if subject:
        lines.append(f"Subject: {format_subject_name(subject)}")
        lines.append("")
    lines.append(f"Question: {question}")
    lines.append("")

    for i, choice in enumerate(choices):
        lines.append(f"{ANSWER_LETTERS[i]}) {choice}")

    lines.append("")
    lines.append("Answer:")

    return "\n".join(lines)


def record_to_sample(record: dict[str, Any], index: int = 0) -> Sample:
    """
    Convert an MMLU record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys:
            - question: Question text
            - choices: List of 4 answer choices
            - answer: Correct answer letter (A/B/C/D)
            - subject: Subject name
        index: Global index for sample ID

    Returns:
        Sample with formatted multiple-choice input, target=answer letter, and metadata
    """
    prompt = format_mmlu_prompt(
        record["question"],
        record["choices"],
        record.get("subject"),
    )

    return Sample(
        input=prompt,
        target=record["answer"],
        id=f"mmlu_{index}",
        metadata={
            "question": record["question"],
            "choices": record["choices"],
            "answer": record["answer"],
            "subject": record.get("subject", "unknown"),
        },
    )


def load_mmlu_csv(data_dir: str | Path) -> list[dict[str, Any]]:
    """
    Load all MMLU records from CSV files in a directory.

    Each CSV file has no header and columns:
        question, choice_A, choice_B, choice_C, choice_D, answer_letter

    Args:
        data_dir: Path to directory containing *_test.csv files

    Returns:
        List of record dicts with question, choices, answer, subject keys

    Raises:
        FileNotFoundError: If data directory doesn't exist
        ValueError: If no CSV files found or dataset is empty
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"MMLU dataset directory not found at {data_dir}")

    csv_files = sorted(data_path.glob("*_test.csv"))
    if not csv_files:
        raise ValueError(f"No MMLU CSV files found in {data_dir}")

    records: list[dict[str, Any]] = []

    for csv_file in csv_files:
        # Extract subject name from filename (e.g., "abstract_algebra_test.csv" -> "abstract_algebra")
        subject = csv_file.stem.rsplit("_", 1)[0]

        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 6:
                    continue  # Skip malformed rows

                records.append({
                    "question": row[0],
                    "choices": [row[1], row[2], row[3], row[4]],
                    "answer": row[5].strip(),
                    "subject": subject,
                })

    if not records:
        raise ValueError(f"MMLU dataset is empty: {data_dir}")

    return records


def load_mmlu(tier: str = "smoke") -> list[Sample]:
    """
    Load MMLU samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If MMLU dataset directory not found
        ValueError: If dataset is empty
    """
    sample_count = get_sample_count("mmlu", tier)

    if sample_count == 0:
        return []

    # Load all records from CSV files
    records = load_mmlu_csv(MMLU_TEST_PATH)

    # Convert to samples with global indices
    all_samples = [record_to_sample(record, i) for i, record in enumerate(records)]

    # Apply tiered sampling with reproducible seed
    if sample_count >= len(all_samples):
        return all_samples

    seed = get_seed()
    rng = random.Random(seed)
    sampled = rng.sample(all_samples, sample_count)

    # Sort by ID for consistent order
    sampled.sort(key=lambda s: s.id)

    return sampled


@task
def mmlu(tier: str = "smoke") -> Task:
    """
    MMLU (Massive Multitask Language Understanding) benchmark.

    Evaluates model's knowledge across 57 academic subjects including
    STEM, humanities, social sciences, and professional domains.
    Uses 14,042 multiple-choice questions from Hendrycks et al. (2021).

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples (~30 seconds)
            - "quick": 75 samples (~4 minutes)
            - "full": 14,042 samples (all, ~9 hours)

    Returns:
        Task configured for MMLU evaluation

    References:
        - Paper: https://arxiv.org/abs/2009.03300
        - Dataset: https://github.com/hendrycks/test
    """
    return Task(
        dataset=load_mmlu(tier),
        solver=[
            system_message(
                "You are a knowledgeable AI assistant answering multiple-choice questions. "
                "Read the question carefully and select the best answer. "
                "Respond with only the letter of your choice (A, B, C, or D), "
                "no explanations or additional text."
            ),
            generate(),
        ],
        scorer=match(),
        name="mmlu",
    )
