"""Clean-checkout coverage for benchmark JSONL loaders."""

import json
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

LOADER_CASES = [
    (
        "matric_eval.tasks.arc",
        "ARC_PATH",
        "load_arc",
        {
            "id": "arc-1",
            "question": {
                "stem": "Which answer is correct?",
                "choices": [
                    {"label": "A", "text": "First"},
                    {"label": "B", "text": "Second"},
                ],
            },
            "answerKey": "A",
        },
    ),
    (
        "matric_eval.tasks.humaneval",
        "HUMANEVAL_PATH",
        "load_humaneval",
        {
            "task_id": "HumanEval/1",
            "prompt": "def answer():",
            "entry_point": "answer",
            "canonical_solution": "\n    return 42",
            "test": "assert answer() == 42",
        },
    ),
    (
        "matric_eval.tasks.mbpp",
        "MBPP_PATH",
        "load_mbpp",
        {
            "task_id": 1,
            "text": "Return the answer.",
            "code": "def answer():\n    return 42",
            "test_list": ["assert answer() == 42"],
            "test_setup_code": "",
        },
    ),
    (
        "matric_eval.tasks.mtbench",
        "MTBENCH_PATH",
        "load_mtbench",
        {"question_id": 1, "category": "reasoning", "turns": ["Why?", "Explain."]},
    ),
    (
        "matric_eval.tasks.gsm8k",
        "GSM8K_PATH",
        "load_gsm8k",
        {"question": "What is 40 + 2?", "answer": "Add the values.\n#### 42"},
    ),
    (
        "matric_eval.tasks.ds1000",
        "DS1000_PATH",
        "load_ds1000",
        {
            "prompt": "Double x.",
            "reference_code": "result = x * 2",
            "metadata": {"library": "numpy", "problem_id": 1},
            "code_context": "x = 21",
        },
    ),
    (
        "matric_eval.tasks.livecodebench",
        "LIVECODEBENCH_PATH",
        "load_livecodebench",
        {
            "question_title": "Add Values",
            "question_content": "Read two integers and print their sum.",
            "platform": "CodeForces",
            "question_id": "1",
            "contest_id": "test",
            "starter_code": "def solve():\n    pass",
            "public_test_cases": json.dumps([{"input": "40 2", "output": "42"}]),
            "private_test_cases": "[]",
            "difficulty": "easy",
        },
    ),
]


def _second_record(record: dict[str, Any]) -> dict[str, Any]:
    duplicate = json.loads(json.dumps(record))
    for key in ("id", "task_id", "question_id"):
        if key in duplicate:
            value = duplicate[key]
            duplicate[key] = value + 1 if isinstance(value, int) else f"{value}-second"
            break
    if "metadata" in duplicate and "problem_id" in duplicate["metadata"]:
        duplicate["metadata"]["problem_id"] = 2
    return duplicate


@pytest.mark.parametrize(("module_name", "path_name", "loader_name", "record"), LOADER_CASES)
def test_jsonl_loaders_work_without_external_datasets(
    module_name: str,
    path_name: str,
    loader_name: str,
    record: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module: ModuleType = import_module(module_name)
    dataset_path = tmp_path / f"{loader_name}.jsonl"
    dataset_path.write_text(
        "\n".join([json.dumps(record), "", json.dumps(_second_record(record))]) + "\n"
    )
    monkeypatch.setattr(module, path_name, str(dataset_path))
    monkeypatch.setattr(module, "get_sample_count", lambda benchmark, tier: 1)
    monkeypatch.setattr(module, "get_seed", lambda: 42)
    loader = getattr(module, loader_name)

    first = loader("smoke")
    second = loader("smoke")

    assert len(first) == 1
    assert first[0].id == second[0].id
    assert first[0].input
