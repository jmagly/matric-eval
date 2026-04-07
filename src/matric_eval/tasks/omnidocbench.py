"""
OmniDocBench v1.5 — document recognition and understanding benchmark.

Tests OCR, layout analysis, table extraction, and document comprehension
across diverse document types.

Dataset: OmniDocBench v1.5 (TBD — version confirmation needed).
"""

from __future__ import annotations

import random
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState, generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, load_hf_dataset
from matric_eval.tasks.registry import register_benchmark


OMNIDOCBENCH_SYSTEM_PROMPT = """\
You are a document understanding expert. You will be given a document image \
and a question about it. The question may involve OCR (reading text), layout \
analysis, table extraction, or document comprehension.

Provide a precise answer to the question based on the document.\
"""

# Task types for per-category scoring
TASK_TYPES = frozenset({"ocr", "layout", "table", "comprehension"})


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert an OmniDocBench record to an Inspect AI Sample.

    Expected schema:
        - id: str
        - question: str
        - image: PIL.Image or path
        - answer: str
        - task_type: str (ocr, layout, table, comprehension)
        - document_type: str
    """
    doc_id = record.get("id", "")
    question = record.get("question", record.get("input", ""))
    answer = record.get("answer", record.get("target", ""))
    task_type = record.get("task_type", "comprehension")

    return Sample(
        input=question,
        target=str(answer).strip(),
        id=str(doc_id),
        metadata={
            "task_type": task_type,
            "document_type": record.get("document_type", ""),
            "has_images": True,
            "requires_vision": True,
        },
    )


@scorer(metrics=[mean()])
def omnidocbench_scorer() -> Scorer:
    """Accuracy scorer for OmniDocBench with per-task-type metadata."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion
        if not completion or not completion.strip():
            return Score(value=0.0, explanation="No answer provided")

        predicted = completion.strip()
        expected = str(target.text).strip()

        # Normalized comparison (case-insensitive, strip whitespace)
        correct = predicted.lower() == expected.lower()
        task_type = (state.metadata or {}).get("task_type", "unknown")

        return Score(
            value=1.0 if correct else 0.0,
            explanation=f"Predicted: {predicted!r}, Expected: {expected!r}",
            metadata={
                "task_type": task_type,
                "predicted": predicted,
                "expected": expected,
            },
        )

    return score


def load_omnidocbench(tier: str = "smoke") -> list[Sample]:
    """Load OmniDocBench samples for the given tier."""
    benchmark_name = "omnidocbench"
    sample_count = get_sample_count(benchmark_name, tier)

    local_path = get_dataset_path(benchmark_name)
    if local_path:
        import json
        from pathlib import Path

        records = []
        with open(Path(local_path)) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        all_samples = [record_to_sample(r) for r in records]
    else:
        all_samples = load_hf_dataset(
            "OmniDocBench/OmniDocBench",
            split="test",
            sample_count=sample_count,
            seed=get_seed(),
            record_to_sample=record_to_sample,
        )
        return all_samples

    if sample_count >= len(all_samples):
        return all_samples

    rng = random.Random(get_seed())
    sampled = rng.sample(all_samples, sample_count)
    sampled.sort(key=lambda s: s.id or "")
    return sampled


@register_benchmark(
    name="omnidocbench",
    description="OmniDocBench v1.5 - document understanding (OCR, layout, tables)",
    category="multimodal",
    tier_samples={"smoke": 5, "quick": 50, "full": 0},
    total_samples=0,  # TBD — version needs confirmation
    requires_vision=True,
    scoring_type="standard",
)
@task
def omnidocbench(tier: str = "smoke") -> Task:
    """OmniDocBench v1.5 benchmark — document understanding.

    Multi-task scoring across OCR, layout, table extraction, and comprehension.
    Gracefully skips for text-only providers.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for OmniDocBench evaluation
    """
    return Task(
        dataset=load_omnidocbench(tier),
        solver=[
            system_message(OMNIDOCBENCH_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=omnidocbench_scorer(),
        name="omnidocbench",
    )
