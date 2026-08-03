"""BABILong 1K protocol adapter with the official constrained-label scorer."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, accuracy, scorer, stderr
from inspect_ai.solver import TaskState, generate

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import load_hf_dataset, seeded_sample
from matric_eval.tasks.registry import register_benchmark

BABILONG_DATASET = "RMT-team/babilong-1k-samples"
BABILONG_DATASET_REVISION = "fc4d1a584dfc498c37578753bee4cdd91b987ae2"
BABILONG_EVALUATOR = "booydar/babilong"
BABILONG_EVALUATOR_REVISION = "7a6efee29f5cac03c3c410e6799c80fd2ffe3610"
BABILONG_TASKS = tuple(f"qa{i}" for i in range(1, 21))
BABILONG_CONTEXTS = ("0k", "1k", "2k", "4k", "8k", "16k", "32k", "64k", "128k")
BABILONG_TASKS_BY_CONTEXT = {
    context: BABILONG_TASKS if context == "0k" else BABILONG_TASKS[:5]
    for context in BABILONG_CONTEXTS
}
BABILONG_LABELS = {
    **{
        f"qa{i}": ("bathroom", "bedroom", "garden", "hallway", "kitchen", "office")
        for i in (1, 2, 3, 4, 11, 12, 13)
    },
    "qa5": ("Bill", "Fred", "Jeff", "Mary", "apple", "football", "milk"),
    "qa6": ("no", "yes"),
    "qa7": ("none", "one", "three", "two"),
    "qa8": ("apple", "football", "milk", "nothing"),
    "qa9": ("no", "yes"),
    "qa10": ("maybe", "no", "yes"),
    "qa14": ("bedroom", "cinema", "kitchen", "office", "park", "school"),
    "qa15": ("cat", "mouse", "sheep", "wolf"),
    "qa16": ("gray", "green", "white", "yellow"),
    "qa17": ("no", "yes"),
    "qa18": ("no", "yes"),
    "qa19": ("e,e", "e,n", "e,s", "n,e", "n,n", "n,w", "s,e", "s,s", "s,w", "w,n", "w,s", "w,w"),
    "qa20": ("bedroom", "bored", "garden", "hungry", "kitchen", "thirsty", "tired"),
}
# Number of supporting facts in the original bAbI task family.
BABILONG_COMPLEXITY = {
    name: (
        1
        if name
        in {"qa1", "qa6", "qa9", "qa10", "qa11", "qa14", "qa15", "qa16", "qa17", "qa18", "qa20"}
        else 2
        if name in {"qa2", "qa4", "qa5", "qa7", "qa12", "qa13"}
        else 3
    )
    for name in BABILONG_TASKS
}


def compare_babilong_answer(target: str, output: str, question: str, task_name: str) -> bool:
    """Match the official BABILong task-label semantics."""
    if task_name not in BABILONG_LABELS:
        raise ValueError(f"Unknown BABILong task: {task_name}")
    normalized = output.lower().split(".")[0].split("<context>")[0].split("<example>")[0]
    normalized = normalized.split("Question")[0]
    labels = {label.lower() for label in BABILONG_LABELS[task_name]}
    labels_in_question = {label for label in labels if label in question.lower()}
    labels_in_output = {label for label in labels if label in normalized} - labels_in_question
    expected = target.lower()
    if "," in expected and len(expected) > 3:
        parts = expected.split(",")
        return all(part in labels_in_output for part in parts) and len(labels_in_output) == len(
            parts
        )
    return expected in labels_in_output and len(labels_in_output) == 1


def record_to_sample(record: dict[str, Any], *, task_name: str, context_length: str) -> Sample:
    question = str(record["question"])
    return Sample(
        id=str(record.get("id", "")),
        input=f"<context>\n{record['input']}\n</context>\n\nQuestion: {question}\nAnswer:",
        target=str(record["target"]),
        metadata={
            "question": question,
            "task": task_name,
            "context_length": context_length,
            "reasoning_complexity": BABILONG_COMPLEXITY[task_name],
            "dataset_revision": BABILONG_DATASET_REVISION,
            "evaluator_revision": BABILONG_EVALUATOR_REVISION,
        },
    )


def load_babilong(
    tier: str = "smoke",
    *,
    tasks: tuple[str, ...] = ("qa1", "qa2", "qa3", "qa4", "qa5"),
    context_length: str = "16k",
) -> list[Sample]:
    if context_length not in BABILONG_CONTEXTS:
        raise ValueError(f"Unknown BABILong context length: {context_length}")
    unknown = set(tasks) - set(BABILONG_TASKS)
    if unknown:
        raise ValueError(f"Unknown BABILong tasks: {', '.join(sorted(unknown))}")
    unavailable = set(tasks) - set(BABILONG_TASKS_BY_CONTEXT[context_length])
    if unavailable:
        raise ValueError(
            f"BABILong {context_length} only releases qa1-qa5; unavailable: "
            f"{', '.join(sorted(unavailable))}"
        )
    samples: list[Sample] = []
    for task_name in tasks:
        samples.extend(
            load_hf_dataset(
                BABILONG_DATASET,
                subset=context_length,
                split=task_name,
                revision=BABILONG_DATASET_REVISION,
                require_immutable_revision=True,
                record_to_sample=lambda row, name=task_name: record_to_sample(
                    row, task_name=name, context_length=context_length
                ),
            )
        )
    return seeded_sample(samples, get_sample_count("babilong", tier), get_seed())


@scorer(metrics=[accuracy(), stderr()])
def babilong_scorer() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        task_name = str(state.metadata["task"])
        correct = compare_babilong_answer(
            target.text, state.output.completion, str(state.metadata["question"]), task_name
        )
        return Score(value=1 if correct else 0)

    return score


def summarize_babilong_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tasks: dict[str, list[float]] = defaultdict(list)
    levels: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        name = str(row["task"])
        value = float(row["accuracy"])
        tasks[name].append(value)
        levels[BABILONG_COMPLEXITY[name]].append(value)
    return {
        "by_task": {k: sum(v) / len(v) for k, v in tasks.items()},
        "by_reasoning_complexity": {k: sum(v) / len(v) for k, v in levels.items()},
        "dataset_revision": BABILONG_DATASET_REVISION,
        "evaluator_revision": BABILONG_EVALUATOR_REVISION,
    }


@register_benchmark(
    name="babilong",
    description="BABILong 1K - bAbI reasoning in contexts through 128K",
    category="reasoning",
    tier_samples={"smoke": 5, "quick": 100, "full": 5000},
    total_samples=5000,
    scoring_type="official_task_constrained_accuracy",
    protocol_version="1k-samples",
    dataset_source=BABILONG_DATASET,
    dataset_revision=BABILONG_DATASET_REVISION,
    dataset_configs=BABILONG_CONTEXTS,
    dataset_splits=BABILONG_TASKS,
    evaluator_source=BABILONG_EVALUATOR,
    evaluator_revision=BABILONG_EVALUATOR_REVISION,
    prompt_revision=BABILONG_EVALUATOR_REVISION,
    license="Apache-2.0",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
)
@task
def babilong(tier: str = "smoke", context_length: str = "16k") -> Task:
    return Task(
        dataset=load_babilong(tier, context_length=context_length),
        solver=generate(),
        scorer=babilong_scorer(),
    )
