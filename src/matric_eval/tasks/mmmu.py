"""
MMMU — Massive Multi-discipline Multimodal Understanding.

College-level questions requiring both image and text reasoning across
30+ subjects (art, science, engineering, medicine, etc.).

Dataset: MMMU/MMMU (HuggingFace) — ~11,500 questions.
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
from matric_eval.multimodal import ModalInput, build_multimodal_content
from matric_eval.tasks.registry import register_benchmark


MMMU_SYSTEM_PROMPT = """\
You are answering college-level multiple choice questions that may include \
images. Analyze both the text and any images provided carefully.

Answer with ONLY the letter of the correct option (A, B, C, D, or E). \
Do not include explanations.\
"""

# Valid answer letters
VALID_ANSWERS = frozenset("ABCDE")


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert an MMMU HuggingFace record to an Inspect AI Sample.

    MMMU schema:
        - id: str
        - question: str
        - options: list[str] (e.g., ["A. ...", "B. ...", ...])
        - answer: str (e.g., "A")
        - image_1 through image_7: PIL.Image or None
        - subject: str
        - subfield: str
        - question_type: str ("multiple-choice" or "open")
    """
    question_id = record.get("id", "")
    question = record.get("question", "")
    options = record.get("options", [])
    answer = record.get("answer", "")
    subject = record.get("subject", "")
    subfield = record.get("subfield", "")

    # Build options text
    if isinstance(options, list):
        options_text = "\n".join(options)
    else:
        options_text = str(options)

    prompt_text = f"{question}\n\n{options_text}"

    # Collect images from image_1 through image_7
    image_keys = []
    for i in range(1, 8):
        img = record.get(f"image_{i}")
        if img is not None:
            image_keys.append(f"image_{i}")

    return Sample(
        input=prompt_text,
        target=str(answer).strip().upper(),
        id=str(question_id),
        metadata={
            "subject": subject,
            "subfield": subfield,
            "question_type": record.get("question_type", "multiple-choice"),
            "has_images": len(image_keys) > 0,
            "image_count": len(image_keys),
            "requires_vision": len(image_keys) > 0,
        },
    )


def _extract_answer(text: str) -> str:
    """Extract the answer letter from model output.

    Handles formats like:
        - "A"
        - "A."
        - "The answer is A"
        - "(A)"
    """
    text = text.strip().upper()

    # Direct single letter
    if len(text) == 1 and text in VALID_ANSWERS:
        return text

    # Letter with period
    if len(text) == 2 and text[0] in VALID_ANSWERS and text[1] == ".":
        return text[0]

    # Parenthesized
    for letter in VALID_ANSWERS:
        if f"({letter})" in text:
            return letter

    # "The answer is X" pattern
    for letter in VALID_ANSWERS:
        if f"ANSWER IS {letter}" in text or f"ANSWER: {letter}" in text:
            return letter

    # Last single letter on its own
    words = text.split()
    for word in reversed(words):
        clean = word.strip("().,;:")
        if len(clean) == 1 and clean in VALID_ANSWERS:
            return clean

    return ""


@scorer(metrics=[mean()])
def mmmu_scorer() -> Scorer:
    """Multiple choice accuracy scorer for MMMU."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion
        if not completion or not completion.strip():
            return Score(value=0.0, explanation="No answer provided")

        predicted = _extract_answer(completion)
        expected = str(target.text).strip().upper()

        correct = predicted == expected
        return Score(
            value=1.0 if correct else 0.0,
            explanation=f"Predicted: {predicted}, Expected: {expected}",
            metadata={
                "predicted": predicted,
                "expected": expected,
                "subject": (state.metadata or {}).get("subject", ""),
            },
        )

    return score


def load_mmmu(tier: str = "smoke") -> list[Sample]:
    """Load MMMU samples for the given tier."""
    benchmark_name = "mmmu"
    sample_count = get_sample_count(benchmark_name, tier)

    local_path = get_dataset_path("mmmu_multimodal")
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
            "MMMU/MMMU",
            split="validation",
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
    name="mmmu",
    description="MMMU - multimodal college-level QA across 30+ subjects (~11,500 questions)",
    category="multimodal",
    tier_samples={"smoke": 5, "quick": 100, "full": 900},
    total_samples=11500,
    requires_vision=True,
    scoring_type="standard",
)
@task
def mmmu(tier: str = "smoke") -> Task:
    """MMMU benchmark — multimodal multi-discipline understanding.

    First multimodal benchmark — validates the entire multimodal pipeline.
    Gracefully skips for text-only providers (image questions get SKIPPED).

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples
            - "quick": 100 samples
            - "full": 900 samples (validation set)

    Returns:
        Task configured for MMMU evaluation
    """
    return Task(
        dataset=load_mmmu(tier),
        solver=[
            system_message(MMMU_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=mmmu_scorer(),
        name="mmmu",
    )
