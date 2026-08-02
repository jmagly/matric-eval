"""MMMU with public test answers, real image inputs, and official parsing."""

from __future__ import annotations

import ast
import json
import random
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, ContentText, GenerateConfig
from inspect_ai.scorer import Score, Scorer, Target, accuracy, scorer, stderr
from inspect_ai.solver import TaskState, generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, seeded_sample
from matric_eval.multimodal import ordered_image_content
from matric_eval.tasks.registry import register_benchmark

MMMU_DATASET = "MMMU/MMMU"
MMMU_DATASET_REVISION = "98e6ac0cb9b7b2cd2c991b85a50762edc4aedc68"
MMMU_EVALUATOR_REVISION = "268471d0d488258990025331c7528359c324aa25"
VALID_ANSWERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
SUBJECTS = (
    "Accounting",
    "Agriculture",
    "Architecture_and_Engineering",
    "Art",
    "Art_Theory",
    "Basic_Medical_Science",
    "Biology",
    "Chemistry",
    "Clinical_Medicine",
    "Computer_Science",
    "Design",
    "Diagnostics_and_Laboratory_Medicine",
    "Economics",
    "Electronics",
    "Energy_and_Power",
    "Finance",
    "Geography",
    "History",
    "Literature",
    "Manage",
    "Marketing",
    "Materials",
    "Math",
    "Mechanical_Engineering",
    "Music",
    "Pharmacy",
    "Physics",
    "Psychology",
    "Public_Health",
    "Sociology",
)

MMMU_SYSTEM_PROMPT = (
    "Answer multiple-choice questions with only the option letter. "
    "Answer open questions with a single word or short phrase."
)


def _options(record: dict[str, Any]) -> list[str]:
    options = record.get("options", [])
    if isinstance(options, str):
        options = ast.literal_eval(options) if options.strip() else []
    return [str(option) for option in options]


def record_to_sample(record: dict[str, Any], *, split: str = "validation") -> Sample:
    """Convert an MMMU record while retaining every image in order."""
    options = _options(record)
    content = [ContentText(text=str(record.get("question", "")))]
    content.extend(ordered_image_content(record))
    if options:
        content.append(
            ContentText(
                text="\n".join(
                    f"{chr(65 + index)}. {option}" for index, option in enumerate(options)
                )
            )
        )

    question_type = str(record.get("question_type", "multiple-choice"))
    subject = str(record.get("subject") or _subject_from_id(str(record.get("id", ""))))
    return Sample(
        input=[ChatMessageUser(content=content)],
        choices=options or None,
        target=str(record.get("answer", "")).strip(),
        id=str(record.get("id", "")),
        metadata={
            "subject": subject,
            "discipline": _discipline(subject),
            "subfield": record.get("subfield", ""),
            "question_type": question_type,
            "options": options,
            "image_count": len(content) - 1 - int(bool(options)),
            "requires_vision": any(record.get(f"image_{i}") is not None for i in range(1, 8)),
            "split": split,
            "dataset_source": MMMU_DATASET,
            "dataset_revision": MMMU_DATASET_REVISION,
            "evaluator_revision": MMMU_EVALUATOR_REVISION,
        },
    )


def _subject_from_id(question_id: str) -> str:
    if not question_id:
        return ""
    parts = question_id.split("_")
    return "_".join(parts[1:-1])


def _discipline(subject: str) -> str:
    if subject in {
        "Art",
        "Art_Theory",
        "Design",
        "History",
        "Literature",
        "Music",
        "Psychology",
        "Sociology",
    }:
        if subject in {"Art", "Art_Theory", "Design", "Music"}:
            return "Art and Design"
        return "Humanities and Social Science"
    if subject in {
        "Accounting",
        "Economics",
        "Finance",
        "Manage",
        "Marketing",
    }:
        return "Business"
    if subject in {
        "Basic_Medical_Science",
        "Clinical_Medicine",
        "Diagnostics_and_Laboratory_Medicine",
        "Pharmacy",
        "Public_Health",
    }:
        return "Health and Medicine"
    if subject in {
        "Agriculture",
        "Biology",
        "Chemistry",
        "Geography",
        "Materials",
        "Math",
        "Physics",
    }:
        return "Science"
    return "Tech and Engineering"


def _extract_answer(text: str, options: list[str] | None = None) -> str:
    """Port the official MMMU last-mentioned multiple-choice parser."""
    response = " " + text.strip(" ,.!?;:'").upper() + " "
    choices = [chr(65 + index) for index in range(len(options or []))] or list("ABCD")
    bracketed = [choice for choice in choices if f"({choice})" in response]
    candidates = bracketed or [choice for choice in choices if f" {choice} " in response]
    if not candidates and options and len(response.split()) > 5:
        matched = [
            choice for choice, option in zip(choices, options) if option.lower() in response.lower()
        ]
        if matched:
            return max(
                matched,
                key=lambda choice: response.lower().rfind(options[choices.index(choice)].lower()),
            )
    if not candidates:
        return random.Random(get_seed()).choice(choices)
    pattern = "({})" if bracketed else " {} "
    return max(candidates, key=lambda choice: response.rfind(pattern.format(choice)))


def _normalize_open(value: str) -> list[str | float]:
    value = value.strip()
    try:
        return [round(float(value.replace(",", "")), 2)]
    except ValueError:
        lowered = value.lower()
        if len(lowered) == 1:
            return [" " + lowered, lowered + " "]
        return [lowered]


def _parse_open_response(response: str) -> list[str | float]:
    response = response.strip().strip(".").lower()
    subresponses = re.split(r"\.\s(?=[A-Z])|\n", response)
    indicators = ("could be ", "so ", "is ", "thus ", "therefore ", "final ", "answer ", "result ")
    keys = []
    for index, subresponse in enumerate(subresponses):
        tails = [
            subresponse.split(indicator)[-1].strip()
            for indicator in indicators + (("=",) if index == len(subresponses) - 1 else ())
            if indicator in subresponse
        ]
        if tails:
            keys.append(min(tails, key=len))
    keys = keys or [response]
    candidates: list[str] = list(keys)
    number_pattern = (
        r"-?\b\d{1,3}(?:,\d{3})+\b|-?\d+(?:\.\d+)?[eE][+-]?\d+|"
        r"-?(?:\d+\.\d+|\.\d+|\d+\b)"
    )
    for key in keys:
        candidates.extend(re.findall(number_pattern, key))
    normalized = [item for candidate in candidates for item in _normalize_open(candidate)]
    return list(dict.fromkeys(normalized))


def _open_correct(expected: str, predictions: list[str | float]) -> bool:
    normalized_answers = _normalize_open(expected)
    for prediction in predictions:
        if isinstance(prediction, float):
            if prediction in normalized_answers:
                return True
        elif any(isinstance(answer, str) and answer in prediction for answer in normalized_answers):
            return True
    return False


@scorer(metrics=[accuracy(), stderr()])
def mmmu_scorer() -> Scorer:
    """Score with MMMU's official multiple-choice and open-answer semantics."""

    async def score(state: TaskState, target: Target) -> Score:
        question_type = str((state.metadata or {}).get("question_type", "multiple-choice"))
        expected = target.text
        if question_type == "multiple-choice":
            options = list((state.metadata or {}).get("options", []))
            predicted: str | list[str | float] = _extract_answer(state.output.completion, options)
            correct = predicted == expected
        else:
            predicted = _parse_open_response(state.output.completion)
            correct = _open_correct(expected, predicted)
        return Score(
            value=1.0 if correct else 0.0,
            answer=state.output.completion,
            explanation=f"Parsed {predicted!r}; expected {expected!r}",
            metadata={
                "parsed_prediction": predicted,
                "question_type": question_type,
                "subject": (state.metadata or {}).get("subject", ""),
                "discipline": (state.metadata or {}).get("discipline", ""),
                "split": (state.metadata or {}).get("split", ""),
            },
        )

    return score


def _load_local(path: Path, split: str) -> list[Sample]:
    if path.is_dir():
        path = path / f"{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"MMMU local override not found: {path}")
    with path.open(encoding="utf-8") as source:
        return [record_to_sample(json.loads(line), split=split) for line in source if line.strip()]


def load_mmmu(
    tier: str = "smoke",
    *,
    split: str = "validation",
    subjects: list[str] | None = None,
) -> list[Sample]:
    """Load a pinned MMMU split; validation and public test remain explicit."""
    if split not in {"dev", "validation", "test"}:
        raise ValueError("MMMU split must be dev, validation, or test")
    local_path = get_dataset_path("mmmu") or get_dataset_path("mmmu_multimodal")
    if local_path:
        samples = _load_local(Path(local_path), split)
    else:
        from datasets import concatenate_datasets, load_dataset

        selected_subjects = subjects or list(SUBJECTS)
        datasets = [
            load_dataset(
                MMMU_DATASET,
                subject,
                split=split,
                revision=MMMU_DATASET_REVISION,
            ).map(lambda row, subject=subject: {**row, "subject": subject})
            for subject in selected_subjects
        ]
        samples = [
            record_to_sample(record, split=split) for record in concatenate_datasets(datasets)
        ]
    sample_count = get_sample_count("mmmu", tier)
    if sample_count > 0 and sample_count < len(samples):
        samples = seeded_sample(samples, sample_count, get_seed())
    return samples


@register_benchmark(
    name="mmmu",
    description="MMMU - validation or public-answer test protocol with real images (11,400 items)",
    category="multimodal",
    tier_samples={"smoke": 5, "quick": 100, "full": 10500},
    total_samples=11400,
    requires_vision=True,
    scoring_type="official_accuracy",
    protocol_version="2026-public-test",
    dataset_source=MMMU_DATASET,
    dataset_revision=MMMU_DATASET_REVISION,
    dataset_configs=SUBJECTS,
    dataset_splits=("dev", "validation", "test"),
    license="Apache-2.0",
    access="public",
    source_kind="huggingface",
    release_policy="immutable",
    evaluator_source="MMMU-Benchmark/MMMU",
    evaluator_revision=MMMU_EVALUATOR_REVISION,
)
@task
def mmmu(tier: str = "smoke", split: str = "validation") -> Task:
    """Run one explicitly named MMMU split."""
    return Task(
        dataset=load_mmmu(tier, split=split),
        solver=[system_message(MMMU_SYSTEM_PROMPT), generate()],
        scorer=mmmu_scorer(),
        config=GenerateConfig(temperature=0),
        name=f"mmmu_{split}",
        metadata={
            "protocol_version": "2026-public-test",
            "split": split,
            "dataset_source": MMMU_DATASET,
            "dataset_revision": MMMU_DATASET_REVISION,
            "evaluator_revision": MMMU_EVALUATOR_REVISION,
        },
    )
