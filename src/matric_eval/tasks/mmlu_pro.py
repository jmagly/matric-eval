"""MMLU-Pro protocol 2-A with deterministic category-stratified tiers."""

from __future__ import annotations

import random
import re
from collections import defaultdict
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Scorer,
    Target,
    accuracy,
    grouped,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState
from inspect_evals.mmlu_pro.mmlu_pro import mmlu_pro_solver

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import load_hf_dataset
from matric_eval.tasks.registry import register_benchmark
from matric_eval.tasks.upstream import INSPECT_EVALS_REVISION

MMLU_PRO_DATASET = "TIGER-Lab/MMLU-Pro"
MMLU_PRO_DATASET_REVISION = "527feea0afed1de15a8c115abf7be4c912123315"
MMLU_PRO_PROTOCOL = "2-A"
MMLU_PRO_TOTAL = 12032


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert the canonical schema while retaining protocol provenance."""
    options = [str(option) for option in record["options"] if option != "N/A"]
    if not 1 <= len(options) <= 10:
        raise ValueError(f"MMLU-Pro requires 1-10 options, found {len(options)}")
    return Sample(
        input=str(record["question"]),
        choices=options,
        target=str(record["answer"]),
        id=str(record["question_id"]),
        metadata={
            "category": str(record["category"]).lower(),
            "cot_content": str(record.get("cot_content", "")),
            "source": str(record.get("src", "")),
            "dataset_source": MMLU_PRO_DATASET,
            "dataset_revision": MMLU_PRO_DATASET_REVISION,
            "protocol_version": MMLU_PRO_PROTOCOL,
            "evaluator_revision": INSPECT_EVALS_REVISION,
        },
    )


def stratified_sample(samples: list[Sample], count: int, seed: int) -> list[Sample]:
    """Sample round-robin across categories after deterministic per-group shuffling."""
    if count <= 0 or count >= len(samples):
        return list(samples)
    groups: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        groups[str((sample.metadata or {}).get("category", "other"))].append(sample)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)
    selected: list[Sample] = []
    categories = sorted(groups)
    while len(selected) < count:
        advanced = False
        for category in categories:
            if groups[category] and len(selected) < count:
                selected.append(groups[category].pop())
                advanced = True
        if not advanced:
            break
    return sorted(selected, key=lambda sample: str(sample.id))


def load_mmlu_pro(tier: str = "smoke", categories: list[str] | None = None) -> list[Sample]:
    samples = load_hf_dataset(
        MMLU_PRO_DATASET,
        split="test",
        revision=MMLU_PRO_DATASET_REVISION,
        require_immutable_revision=True,
        record_to_sample=record_to_sample,
    )
    if categories:
        selected = {category.lower() for category in categories}
        samples = [
            sample
            for sample in samples
            if str((sample.metadata or {}).get("category", "")).lower() in selected
        ]
    return stratified_sample(samples, get_sample_count("mmlu_pro", tier), get_seed())


def extract_mmlu_pro_answer(text: str) -> str | None:
    """Apply the official final-answer hierarchy without random fallback."""
    for pattern in (
        r"(?i)answer\s+is\s*\(?([A-J])\)?",
        r"(?i)answer\s*:\s*\(?([A-J])\)?",
        r"\b([A-J])\b(?!.*\b[A-J]\b)",
    ):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).upper()
    return None


@scorer(metrics=[grouped(accuracy(), "category"), stderr()])
def mmlu_pro_scorer() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        answer = extract_mmlu_pro_answer(state.output.completion)
        expected = target.text.strip().upper()
        return Score(
            value=CORRECT if answer == expected else INCORRECT,
            answer=answer,
            explanation=state.output.completion,
        )

    return score


@register_benchmark(
    name="mmlu_pro",
    description="MMLU-Pro protocol 2-A - 12,032 expert-reviewed ten-option questions",
    category="reasoning",
    tier_samples={"smoke": 14, "quick": 140, "full": MMLU_PRO_TOTAL},
    total_samples=MMLU_PRO_TOTAL,
    scoring_type="category_and_aggregate_accuracy",
    protocol_version=MMLU_PRO_PROTOCOL,
    dataset_source=MMLU_PRO_DATASET,
    dataset_revision=MMLU_PRO_DATASET_REVISION,
    dataset_configs=("default",),
    dataset_splits=("test", "validation"),
    evaluator_source="inspect-evals/mmlu_pro",
    evaluator_revision=INSPECT_EVALS_REVISION,
    license="MIT",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
)
@task
def mmlu_pro(
    tier: str = "smoke",
    categories: list[str] | None = None,
    fewshot: int = 0,
) -> Task:
    return Task(
        dataset=load_mmlu_pro(tier, categories),
        solver=mmlu_pro_solver(fewshot=fewshot),
        scorer=mmlu_pro_scorer(),
        name="mmlu_pro_2_a",
        version=MMLU_PRO_PROTOCOL,
        metadata={
            "protocol_version": MMLU_PRO_PROTOCOL,
            "dataset_revision": MMLU_PRO_DATASET_REVISION,
            "evaluator_revision": INSPECT_EVALS_REVISION,
        },
    )
