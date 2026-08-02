"""NL2RepoBench 104-task adapter using the canonical test environments."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.agent import react
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState
from inspect_ai.tool import bash_session, python, text_editor
from inspect_ai.util import sandbox

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, seeded_sample
from matric_eval.tasks.registry import BenchmarkStatus, register_benchmark
from matric_eval.tasks.swebench.factory import _sandbox

NL2REPO_REPOSITORY = "multimodal-art-projection/NL2RepoBench"
NL2REPO_REVISION = "781a1da1ee41fb8edb0bed22f586d69111610edf"
NL2REPO_TASKS = 104
NL2REPO_SYSTEM_PROMPT = (
    "Generate the complete repository described below in /workspace. Use the terminal and "
    "editor tools to create a runnable implementation."
)


def record_to_sample(record: dict[str, Any]) -> Sample:
    task_id = str(record.get("id", record.get("task_id", "")))
    sample = Sample(
        input=f"{NL2REPO_SYSTEM_PROMPT}\n\n{record.get('specification', '')}",
        target="",
        id=task_id,
        metadata={
            "test_commands": record.get("test_commands", []),
            "test_case_count": int(record.get("test_case_count", 0)),
            "dataset_revision": NL2REPO_REVISION,
        },
    )
    sample.sandbox = _sandbox(
        f"ghcr.io/multimodal-art-projection/nl2repobench/{task_id}:1.0",
        f"nl2repo-{task_id}",
        working_dir="/workspace",
    )
    return sample


def load_nl2repo(tier: str = "smoke") -> list[Sample]:
    root_value = get_dataset_path("nl2repo")
    if not root_value:
        raise FileNotFoundError(
            "NL2RepoBench requires a local canonical snapshot. Set "
            "MATRIC_EVAL_NL2REPO_DATA_PATH to the repository checkout at "
            f"{NL2REPO_REVISION}."
        )
    root = Path(root_value)
    tasks_root = root / "test_files" if (root / "test_files").is_dir() else root
    records = []
    for directory in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        records.append(
            {
                "id": directory.name,
                "specification": (directory / "start.md").read_text(encoding="utf-8"),
                "test_commands": json.loads(
                    (directory / "test_commands.json").read_text(encoding="utf-8")
                ),
                "test_case_count": int(
                    (directory / "test_case_count.txt").read_text(encoding="utf-8").strip()
                ),
            }
        )
    if len(records) != NL2REPO_TASKS:
        raise ValueError(
            f"Expected {NL2REPO_TASKS} NL2RepoBench tasks at revision "
            f"{NL2REPO_REVISION}, found {len(records)}"
        )
    samples = [record_to_sample(record) for record in records]
    sample_count = get_sample_count("nl2repo", tier)
    if 0 < sample_count < len(samples):
        samples = seeded_sample(samples, sample_count, get_seed())
    return samples


def _pytest_counts(output: str) -> tuple[int, int]:
    passed = sum(int(value) for value in re.findall(r"(\d+) passed", output))
    failed = sum(int(value) for value in re.findall(r"(\d+) failed", output))
    errors = sum(int(value) for value in re.findall(r"(\d+) errors?", output))
    return passed, failed + errors


@scorer(metrics=[mean()])
def nl2repo_scorer() -> Scorer:
    """Run the benchmark's ordered commands and report canonical test pass rate."""

    async def score(state: TaskState, target: Target) -> Score:
        del target
        environment = sandbox()
        outputs = []
        passed = 0
        failed = 0
        for command in state.metadata["test_commands"]:
            result = await environment.exec(["bash", "-c", command], timeout=1800)
            output = result.stdout + result.stderr
            outputs.append(
                {"command": command, "returncode": result.returncode, "output": output[-4000:]}
            )
            command_passed, command_failed = _pytest_counts(output)
            passed += command_passed
            failed += command_failed
        total = int(state.metadata["test_case_count"])
        if passed + failed == 0:
            raise RuntimeError("NL2RepoBench test commands produced no parseable pytest results")
        return Score(
            value=min(passed / total, 1.0) if total else 0.0,
            explanation=f"{passed}/{total} canonical tests passed",
            metadata={"tests_passed": passed, "tests_total": total, "commands": outputs},
        )

    return score


@register_benchmark(
    name="nl2repo",
    description="NL2RepoBench - 104 zero-to-one repository generation tasks",
    category="agentic",
    tier_samples={"smoke": 3, "quick": 20, "full": NL2REPO_TASKS},
    total_samples=NL2REPO_TASKS,
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="official_test_pass_rate",
    provider_requirements=("docker",),
    status=BenchmarkStatus.GATED,
    status_reason="Requires the pinned task snapshot and published GHCR images.",
    protocol_version="104-task-release",
    dataset_source=NL2REPO_REPOSITORY,
    dataset_revision=NL2REPO_REVISION,
    dataset_splits=("release",),
    license="upstream repository terms",
    access="gated",
    source_kind="github",
    release_policy="versioned",
    evaluator_source=NL2REPO_REPOSITORY,
    evaluator_revision=NL2REPO_REVISION,
)
@task
def nl2repo(tier: str = "smoke") -> Task:
    return Task(
        dataset=load_nl2repo(tier),
        solver=react(tools=[bash_session(timeout=900), python(timeout=900), text_editor()]),
        scorer=nl2repo_scorer(),
        message_limit=200,
        name="nl2repobench_104",
        metadata={
            "protocol_version": "104-task-release",
            "dataset_revision": NL2REPO_REVISION,
            "evaluator_revision": NL2REPO_REVISION,
        },
    )
