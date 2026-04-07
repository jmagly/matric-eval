"""
RealWorldQA — image-based practical reasoning benchmark.

Tests visual understanding with real-world photographs and practical
questions (reading signs, understanding scenes, spatial reasoning).

Dataset: xai-org/RealWorldQA or similar (~700 questions).
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


REALWORLDQA_SYSTEM_PROMPT = """\
You are answering questions about real-world images. Look at the image \
carefully and answer the question.

If the question is multiple choice, answer with ONLY the letter of the \
correct option. If it requires a short answer, provide a brief response.\
"""


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a RealWorldQA record to an Inspect AI Sample.

    Expected schema:
        - id: str
        - question: str
        - image: PIL.Image or image path
        - answer: str
        - options: list[str] (optional, for multiple choice)
    """
    question_id = record.get("id", "")
    question = record.get("question", record.get("input", ""))
    answer = record.get("answer", record.get("target", ""))
    options = record.get("options", [])

    if options and isinstance(options, list):
        options_text = "\n".join(options)
        prompt_text = f"{question}\n\n{options_text}"
    else:
        prompt_text = question

    return Sample(
        input=prompt_text,
        target=str(answer).strip(),
        id=str(question_id),
        metadata={
            "has_images": True,
            "requires_vision": True,
        },
    )


@scorer(metrics=[mean()])
def realworldqa_scorer() -> Scorer:
    """Accuracy scorer for RealWorldQA."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion
        if not completion or not completion.strip():
            return Score(value=0.0, explanation="No answer provided")

        predicted = completion.strip()
        expected = str(target.text).strip()

        # Case-insensitive comparison, strip whitespace
        correct = predicted.upper() == expected.upper()
        return Score(
            value=1.0 if correct else 0.0,
            explanation=f"Predicted: {predicted!r}, Expected: {expected!r}",
        )

    return score


def load_realworldqa(tier: str = "smoke") -> list[Sample]:
    """Load RealWorldQA samples for the given tier."""
    benchmark_name = "realworldqa"
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
            "xai-org/RealWorldQA",
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
    name="realworldqa",
    description="RealWorldQA - image-based practical reasoning (~700 questions)",
    category="multimodal",
    tier_samples={"smoke": 5, "quick": 70, "full": 700},
    total_samples=700,
    requires_vision=True,
    scoring_type="standard",
)
@task
def realworldqa(tier: str = "smoke") -> Task:
    """RealWorldQA benchmark — practical visual reasoning.

    Simple multimodal benchmark for validating the image pipeline.
    Gracefully skips for text-only providers.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for RealWorldQA evaluation
    """
    return Task(
        dataset=load_realworldqa(tier),
        solver=[
            system_message(REALWORLDQA_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=realworldqa_scorer(),
        name="realworldqa",
    )
