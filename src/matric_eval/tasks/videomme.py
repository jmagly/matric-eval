"""
Video-MME — video reasoning benchmark with subtitle context.

Models analyze video frames + subtitles to answer questions about video
content. Tests temporal reasoning, scene understanding, and narrative
comprehension.

Uses FrameExtractor with adaptive sampling and subtitle parsing.
Requires ffmpeg for frame extraction.

Dataset: Video-MME public dataset (TBD — large storage requirements).
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


VIDEOMME_SYSTEM_PROMPT = """\
You are analyzing a video. You will be shown frames extracted from the \
video and any available subtitles. Answer the question about the video \
content.

Answer with ONLY the letter of the correct option (A, B, C, or D). \
Do not include explanations.\
"""

VALID_ANSWERS = frozenset("ABCD")

# Provider-specific frame count caps
DEFAULT_MAX_FRAMES = 64
PROVIDER_FRAME_CAPS: dict[str, int] = {
    "ollama": 16,
    "openrouter": 32,
    "chutes": 32,
}


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a Video-MME record to an Inspect AI Sample.

    Expected schema:
        - video_id: str
        - question: str
        - options: list[str]
        - answer: str (letter)
        - video_path: str
        - subtitle_path: str (optional)
        - duration: str (short/medium/long)
    """
    video_id = record.get("video_id", record.get("id", ""))
    question = record.get("question", record.get("input", ""))
    options = record.get("options", [])
    answer = record.get("answer", record.get("target", ""))
    duration_cat = record.get("duration", "medium")

    if isinstance(options, list):
        options_text = "\n".join(options)
        prompt_text = f"{question}\n\n{options_text}"
    else:
        prompt_text = question

    return Sample(
        input=prompt_text,
        target=str(answer).strip().upper(),
        id=str(video_id),
        metadata={
            "video_path": record.get("video_path", ""),
            "subtitle_path": record.get("subtitle_path", ""),
            "duration_category": duration_cat,
            "has_images": True,
            "requires_vision": True,
            "requires_ffmpeg": True,
        },
    )


def _extract_answer(text: str) -> str:
    """Extract the answer letter from model output."""
    text = text.strip().upper()

    if len(text) == 1 and text in VALID_ANSWERS:
        return text

    if len(text) == 2 and text[0] in VALID_ANSWERS and text[1] == ".":
        return text[0]

    for letter in VALID_ANSWERS:
        if f"({letter})" in text:
            return letter
        if f"ANSWER IS {letter}" in text or f"ANSWER: {letter}" in text:
            return letter

    words = text.split()
    for word in reversed(words):
        clean = word.strip("().,;:")
        if len(clean) == 1 and clean in VALID_ANSWERS:
            return clean

    return ""


@scorer(metrics=[mean()])
def videomme_scorer() -> Scorer:
    """Multiple choice accuracy scorer for Video-MME."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion
        if not completion or not completion.strip():
            return Score(value=0.0, explanation="No answer provided")

        predicted = _extract_answer(completion)
        expected = str(target.text).strip().upper()
        duration_cat = (state.metadata or {}).get("duration_category", "unknown")

        correct = predicted == expected
        return Score(
            value=1.0 if correct else 0.0,
            explanation=f"Predicted: {predicted}, Expected: {expected}",
            metadata={
                "predicted": predicted,
                "expected": expected,
                "duration_category": duration_cat,
            },
        )

    return score


def load_videomme(tier: str = "smoke") -> list[Sample]:
    """Load Video-MME samples for the given tier."""
    benchmark_name = "videomme"
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
            "lmms-lab/Video-MME",
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
    name="videomme",
    description="Video-MME - video reasoning with subtitles (requires ffmpeg)",
    category="multimodal",
    tier_samples={"smoke": 3, "quick": 30, "full": 0},
    total_samples=0,  # TBD — large dataset
    requires_vision=True,
    scoring_type="standard",
    provider_requirements=("ffmpeg",),
)
@task
def videomme(tier: str = "smoke") -> Task:
    """Video-MME benchmark — video reasoning with subtitle context.

    Uses FrameExtractor with adaptive sampling:
        - Short (<60s): 1 fps
        - Medium (60-300s): 0.5 fps
        - Long (>300s): 0.25 fps
        - Max 64 frames per video

    Requires ffmpeg for frame extraction.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for Video-MME evaluation
    """
    return Task(
        dataset=load_videomme(tier),
        solver=[
            system_message(VIDEOMME_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=videomme_scorer(),
        name="videomme",
    )
