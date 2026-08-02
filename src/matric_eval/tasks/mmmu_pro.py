"""Official MMMU-Pro standard and vision-only multiple-choice settings."""

from __future__ import annotations

import ast
import re
from typing import Any, Literal

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, ContentText, GenerateConfig
from inspect_ai.scorer import Score, Scorer, Target, accuracy, grouped, scorer, stderr
from inspect_ai.solver import TaskState, generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import load_hf_dataset, seeded_sample
from matric_eval.multimodal import image_content
from matric_eval.tasks.mmmu import _discipline, _extract_answer
from matric_eval.tasks.registry import register_benchmark

MMMU_PRO_DATASET = "MMMU/MMMU_Pro"
MMMU_PRO_DATASET_REVISION = "563f3e84bb3b90893083a1f039cfa13077f2302b"
MMMU_PRO_EVALUATOR_REVISION = "268471d0d488258990025331c7528359c324aa25"
MMMU_PRO_TOTAL = 1730
MMMU_PRO_SETTINGS = {
    "standard": "standard (10 options)",
    "vision": "vision",
}


def _options(value: Any) -> list[str]:
    parsed = ast.literal_eval(value) if isinstance(value, str) else value
    return [str(option) for option in parsed or []]


def _interleaved_content(text: str, record: dict[str, Any]) -> list[Any]:
    """Replace official image tokens in encounter order with their exact images."""
    content: list[Any] = []
    position = 0
    for match in re.finditer(r"<image\s+(\d+)>", text, re.IGNORECASE):
        if match.start() > position:
            content.append(ContentText(text=text[position : match.start()]))
        key = f"image_{int(match.group(1))}"
        if record.get(key) is None:
            raise ValueError(f"MMMU-Pro references missing {key}")
        content.append(image_content(record[key]))
        position = match.end()
    if position < len(text):
        content.append(ContentText(text=text[position:]))
    return content or [ContentText(text=text)]


def record_to_sample(
    record: dict[str, Any], *, setting: Literal["standard", "vision"] = "standard"
) -> Sample:
    options = _options(record.get("options", []))
    if not options:
        raise ValueError(
            "Official MMMU-Pro contains only multiple-choice records; open-answer input "
            "does not match the published schema"
        )
    if setting == "vision":
        if record.get("image") is None:
            raise ValueError("MMMU-Pro vision record has no rendered image")
        content = [
            image_content(record["image"]),
            ContentText(text="Answer using only the option letter shown in the image."),
        ]
        image_count = 1
    elif setting == "standard":
        question = str(record.get("question", ""))
        option_text = "\nOptions:\n" + "\n".join(
            f"{chr(65 + index)}. {option}" for index, option in enumerate(options)
        )
        content = _interleaved_content(question + option_text, record)
        image_count = sum(not isinstance(item, ContentText) for item in content)
        if image_count == 0:
            raise ValueError("MMMU-Pro standard record contains no referenced image")
    else:
        raise ValueError("MMMU-Pro setting must be 'standard' or 'vision'")

    subject = str(record.get("subject", ""))
    return Sample(
        input=[ChatMessageUser(content=content)],
        choices=options,
        target=str(record["answer"]),
        id=str(record["id"]),
        metadata={
            "setting": setting,
            "subject": subject,
            "discipline": _discipline(subject),
            "question_type": "multiple-choice",
            "options": options,
            "image_count": image_count,
            "requires_vision": True,
            "split": "test",
            "dataset_revision": MMMU_PRO_DATASET_REVISION,
            "evaluator_revision": MMMU_PRO_EVALUATOR_REVISION,
        },
    )


def load_mmmu_pro(
    tier: str = "smoke", *, setting: Literal["standard", "vision"] = "standard"
) -> list[Sample]:
    try:
        config = MMMU_PRO_SETTINGS[setting]
    except KeyError as exc:
        raise ValueError("MMMU-Pro setting must be 'standard' or 'vision'") from exc
    samples = load_hf_dataset(
        MMMU_PRO_DATASET,
        subset=config,
        split="test",
        revision=MMMU_PRO_DATASET_REVISION,
        require_immutable_revision=True,
        record_to_sample=lambda record: record_to_sample(record, setting=setting),
    )
    return seeded_sample(samples, get_sample_count("mmmu_pro", tier), get_seed())


@scorer(metrics=[grouped(accuracy(), "discipline"), stderr()])
def mmmu_pro_scorer() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        options = list((state.metadata or {}).get("options", []))
        predicted = _extract_answer(state.output.completion, options)
        return Score(
            value=1.0 if predicted == target.text else 0.0,
            answer=predicted,
            explanation=f"Parsed {predicted!r}; expected {target.text!r}",
        )

    return score


@register_benchmark(
    name="mmmu_pro",
    description="MMMU-Pro - 1,730 vision-required questions in standard and vision settings",
    category="multimodal",
    tier_samples={"smoke": 6, "quick": 100, "full": MMMU_PRO_TOTAL},
    total_samples=MMMU_PRO_TOTAL,
    requires_vision=True,
    scoring_type="official_discipline_accuracy",
    provider_requirements=("vision",),
    protocol_version="ACL-2025-standard-and-vision",
    dataset_source=MMMU_PRO_DATASET,
    dataset_revision=MMMU_PRO_DATASET_REVISION,
    dataset_configs=tuple(MMMU_PRO_SETTINGS.values()),
    dataset_splits=("test",),
    evaluator_source="MMMU-Benchmark/MMMU/mmmu-pro",
    evaluator_revision=MMMU_PRO_EVALUATOR_REVISION,
    license="Apache-2.0",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
)
@task
def mmmu_pro(
    tier: str = "smoke",
    setting: Literal["standard", "vision"] = "standard",
    prompt_mode: Literal["cot", "direct"] = "cot",
) -> Task:
    prompt = (
        "Think step by step. End with 'Answer: $LETTER'."
        if prompt_mode == "cot"
        else "Answer directly with the option letter."
    )
    return Task(
        dataset=load_mmmu_pro(tier, setting=setting),
        solver=[system_message(prompt), generate()],
        scorer=mmmu_pro_scorer(),
        config=GenerateConfig(temperature=0),
        name=f"mmmu_pro_{setting}_{prompt_mode}",
        metadata={
            "setting": setting,
            "prompt_protocol": prompt_mode,
            "dataset_revision": MMMU_PRO_DATASET_REVISION,
            "evaluator_revision": MMMU_PRO_EVALUATOR_REVISION,
        },
    )
