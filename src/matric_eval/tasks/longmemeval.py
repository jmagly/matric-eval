"""
LongMemEval benchmark task.

Evaluates long-term interactive memory in chat assistants using 500 curated
questions across scalable chat histories.

Based on Wu et al. (ICLR 2025): https://arxiv.org/abs/2407.15975
HuggingFace: xiaowu0162/longmemeval-cleaned
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
LONGMEMEVAL_PATH = "/home/roctinam/data/evals/longmemeval"

# Valid question types in the dataset
QUESTION_TYPES = [
    "single-session-user",
    "single-session-assistant",
    "single-session-preference",
    "multi-session",
    "temporal-reasoning",
    "knowledge-update",
    "abstention",
]

# Valid scale configurations
VALID_SCALES = ("s", "m")


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert a LongMemEval record to an Inspect AI Sample.

    Handles both HuggingFace format and simplified JSONL format.

    Args:
        record: Dictionary with question, answer, and metadata fields

    Returns:
        Sample with question input, answer target, and rich metadata
    """
    # Handle both field naming conventions
    question = record.get("question", "")
    answer = record.get("answer", "")
    question_id = record.get("question_id", record.get("id", str(hash(question))))
    question_type = record.get("question_type", record.get("type", "unknown"))
    question_date = record.get("question_date", record.get("date", ""))

    # Session-level metadata for future Recall@K integration
    haystack_session_ids = record.get("haystack_session_ids", [])
    haystack_dates = record.get("haystack_dates", [])
    answer_session_ids = record.get("answer_session_ids", [])

    prompt = (
        "You are a helpful chat assistant with access to previous conversation history. "
        "Answer the following question based on the conversation history.\n\n"
        f"Question: {question}\n\n"
        "Provide a concise, factual answer:"
    )

    return Sample(
        input=prompt,
        target=str(answer),
        id=str(question_id),
        metadata={
            "question": question,
            "answer": answer,
            "question_type": question_type,
            "question_date": question_date,
            "haystack_session_ids": haystack_session_ids,
            "haystack_dates": haystack_dates,
            "answer_session_ids": answer_session_ids,
        },
    )


def load_longmemeval(tier: str = "smoke", scale: str = "s") -> list[Sample]:
    """
    Load LongMemEval samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")
        scale: Dataset scale ("s" for 115K tokens/~40 sessions,
               "m" for 1.5M tokens/500 sessions)

    Returns:
        List of Sample objects

    Raises:
        FileNotFoundError: If LongMemEval dataset not found
        ValueError: If scale is invalid or dataset is empty
    """
    if scale not in VALID_SCALES:
        raise ValueError(
            f"Invalid scale '{scale}'. Must be one of: {', '.join(VALID_SCALES)}"
        )

    sample_count = get_sample_count("longmemeval", tier)
    if sample_count == 0:
        return []

    # Try local JSONL file
    data_dir = Path(LONGMEMEVAL_PATH)
    jsonl_path = data_dir / f"longmemeval_{scale}.jsonl"

    if not jsonl_path.exists():
        # Try alternative naming
        jsonl_path = data_dir / f"{scale}.jsonl"

    if not jsonl_path.exists():
        raise FileNotFoundError(
            f"LongMemEval dataset not found at {jsonl_path}. "
            f"Download the LongMemEval dataset to {LONGMEMEVAL_PATH}/longmemeval_s.jsonl. "
            f"See: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned"
        )

    records = []
    with open(jsonl_path, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"LongMemEval dataset is empty: {jsonl_path}")

    all_samples = [record_to_sample(record) for record in records]

    if sample_count >= len(all_samples):
        return all_samples

    seed = get_seed()
    rng = random.Random(seed)
    return rng.sample(all_samples, sample_count)


@task
def longmemeval(tier: str = "smoke", scale: str = "s", thinking: bool = False) -> Task:
    """
    LongMemEval benchmark task - long-term interactive memory evaluation.

    Tests a model's ability to recall information from extended conversation
    histories across multiple question types: single-session, multi-session,
    temporal reasoning, knowledge updates, and abstention.

    Args:
        tier: Evaluation tier
        scale: Dataset scale ("s" or "m")
        thinking: Whether model has thinking enabled

    Returns:
        Inspect AI Task for LongMemEval evaluation
    """
    samples = load_longmemeval(tier, scale)

    system_msg = (
        "You are a helpful chat assistant with long-term memory of previous conversations. "
        "Answer questions based on conversation history. "
        "Think step by step about which conversations are relevant before answering."
        if thinking
        else "You are a helpful chat assistant with long-term memory of previous conversations. "
        "Answer questions based on conversation history. Provide concise, factual answers."
    )

    return Task(
        dataset=samples,
        solver=[
            system_message(system_msg),
            generate(),
        ],
        scorer=match(),
        name=f"longmemeval_{scale}",
    )


register_benchmark(
    name="longmemeval",
    description=(
        "LongMemEval - 500 long-term memory questions across scalable chat histories "
        "(ICLR 2025)"
    ),
    category="conversation",
    total_samples=500,
)
