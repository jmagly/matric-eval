"""
MemoryAgentBench benchmark task.

Evaluates agent memory capabilities grounded in cognitive science.
Four competencies: Accurate Retrieval (AR), Test-Time Learning (TTL),
Long-Range Understanding (LRU), and Conflict Resolution (CR).

Uses incremental multi-turn format where information arrives piece by piece.
Includes EventQA and FactConsolidation sub-datasets.

Based on ICLR 2026 paper: https://huggingface.co/datasets/ai-hyz/MemoryAgentBench
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
MEMORYAGENTBENCH_PATH = "/home/roctinam/data/evals/memoryagentbench"

VALID_COMPETENCIES = {"AR", "TTL", "LRU", "CR"}


def format_context_turns(context_turns: list[str]) -> str:
    """
    Format conversation context turns as a numbered list.

    Args:
        context_turns: List of conversation turn strings

    Returns:
        Formatted numbered list of turns
    """
    lines = []
    for i, turn in enumerate(context_turns, 1):
        lines.append(f"{i}. {turn}")
    return "\n".join(lines)


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert a MemoryAgentBench record to an Inspect AI Sample.

    Args:
        record: Dictionary with question, answer, context_turns, competency, metadata

    Returns:
        Sample with formatted multi-turn input and target answer
    """
    question = record.get("question", "")
    answer = record.get("answer", "")
    context_turns = record.get("context_turns", [])
    competency = record.get("competency", "unknown")
    metadata = record.get("metadata", {})

    formatted_context = format_context_turns(context_turns)

    prompt = (
        "Based on the following conversation context, answer the question.\n\n"
        "Conversation context:\n"
        f"{formatted_context}\n\n"
        f"Question: {question}\n\n"
        "Answer concisely:"
    )

    return Sample(
        input=prompt,
        target=answer,
        id=record.get("id", str(hash(question))),
        metadata={
            "question": question,
            "answer": answer,
            "competency": competency,
            "num_turns": len(context_turns),
            "dataset_source": metadata.get("dataset_source", "unknown"),
        },
    )


def load_memoryagentbench(tier: str = "smoke", competency: str | None = None) -> list[Sample]:
    """
    Load MemoryAgentBench samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")
        competency: Optional competency filter ("AR", "TTL", "LRU", "CR")
            None loads all competencies.

    Returns:
        List of Sample objects

    Raises:
        FileNotFoundError: If dataset not found
        ValueError: If invalid competency specified or dataset is empty
    """
    if competency is not None and competency not in VALID_COMPETENCIES:
        raise ValueError(
            f"Invalid competency '{competency}'. "
            f"Must be one of: {', '.join(sorted(VALID_COMPETENCIES))}"
        )

    sample_count = get_sample_count("memoryagentbench", tier)
    if sample_count == 0:
        return []

    # Try local JSONL file
    mab_dir = Path(MEMORYAGENTBENCH_PATH)
    jsonl_path = mab_dir / "memoryagentbench.jsonl"

    if not jsonl_path.exists():
        raise FileNotFoundError(
            f"MemoryAgentBench dataset not found at {jsonl_path}. "
            f"Download the dataset to {MEMORYAGENTBENCH_PATH}/memoryagentbench.jsonl. "
            f"See: https://huggingface.co/datasets/ai-hyz/MemoryAgentBench"
        )

    records = []
    with open(jsonl_path, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"MemoryAgentBench dataset is empty: {jsonl_path}")

    # Filter by competency if specified
    if competency is not None:
        records = [r for r in records if r.get("competency") == competency]
        if not records:
            raise ValueError(f"No records found for competency '{competency}' in {jsonl_path}")

    all_samples = [record_to_sample(record) for record in records]

    if sample_count >= len(all_samples):
        return all_samples

    seed = get_seed()
    rng = random.Random(seed)
    return rng.sample(all_samples, sample_count)


@task
def memoryagentbench(
    tier: str = "smoke",
    competency: str | None = None,
    thinking: bool = False,
) -> Task:
    """
    MemoryAgentBench benchmark task - agent memory evaluation.

    Tests memory capabilities across four cognitive competencies:
    AR (Accurate Retrieval), TTL (Test-Time Learning),
    LRU (Long-Range Understanding), CR (Conflict Resolution).

    Args:
        tier: Evaluation tier
        competency: Optional competency filter (AR, TTL, LRU, CR)
        thinking: Whether model has thinking enabled

    Returns:
        Inspect AI Task for MemoryAgentBench evaluation
    """
    samples = load_memoryagentbench(tier, competency)

    system_msg = (
        "You are a helpful assistant with excellent memory. "
        "You will be given a conversation context consisting of multiple turns. "
        "Read the entire context carefully and answer the question based on "
        "the information provided. Think step by step before answering."
        if thinking
        else "You are a helpful assistant with excellent memory. "
        "Answer the question based only on the provided conversation context. "
        "Be concise and accurate."
    )

    name = "memoryagentbench"
    if competency:
        name = f"memoryagentbench_{competency.lower()}"

    return Task(
        dataset=samples,
        solver=[
            system_message(system_msg),
            generate(),
        ],
        scorer=match(),
        name=name,
    )


register_benchmark(
    name="memoryagentbench",
    description=(
        "MemoryAgentBench - agent memory evaluation across 4 cognitive competencies "
        "(AR, TTL, LRU, CR)"
    ),
    category="reasoning",
    total_samples=0,
)
