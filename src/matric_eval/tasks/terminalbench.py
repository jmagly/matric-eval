"""Terminal-Bench 2.1 adapter for the canonical Harbor task definitions."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.agent import AgentPrompt, AgentSubmit, react
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState
from inspect_ai.tool import bash_session
from inspect_ai.util import sandbox

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, seeded_sample
from matric_eval.tasks.registry import BenchmarkStatus, register_benchmark
from matric_eval.tasks.swebench.factory import _sandbox

TERMINALBENCH_REPOSITORY = "harbor-framework/terminal-bench-2-1"
TERMINALBENCH_REVISION = "5c8eadf1f393183288fa08b8f73ca9a469cc5e00"
TERMINALBENCH_DATASET = "terminal-bench/terminal-bench-2-1"
TERMINALBENCH_TASKS = 89
HARBOR_VERSION = "0.20.0"


def _task_files(directory: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    tests = directory / "tests"
    if tests.exists():
        for path in tests.rglob("*"):
            if path.is_file():
                files[str(path.relative_to(directory))] = str(path)
    return files


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert a parsed Harbor task manifest to an Inspect sample."""
    task_id = str(record.get("task_id", record.get("id", "")))
    sample = Sample(
        input=str(record.get("instruction", record.get("description", ""))),
        target="",
        id=task_id,
        metadata={
            "task_id": task_id,
            "verification": "bash /tests/test.sh",
            "timeout_sec": int(record.get("verifier_timeout", 900)),
            "test_files": record.get("test_files", {}),
            "dataset_revision": TERMINALBENCH_REVISION,
        },
    )
    image = str(record.get("docker_image", ""))
    if image:
        sample.sandbox = _sandbox(
            image,
            f"terminalbench-{task_id}",
            working_dir="/root",
            allow_internet=bool(record.get("allow_internet", False)),
        )
    return sample


def load_terminalbench(tier: str = "smoke") -> list[Sample]:
    """Load the pinned 2.1 task tree from an explicit local snapshot."""
    root_value = get_dataset_path("terminalbench")
    if not root_value:
        raise FileNotFoundError(
            "Terminal-Bench 2.1 requires a local canonical snapshot. Set "
            "MATRIC_EVAL_TERMINALBENCH_DATA_PATH to the repository checkout at "
            f"{TERMINALBENCH_REVISION}."
        )
    root = Path(root_value)
    tasks_root = root / "tasks" if (root / "tasks").is_dir() else root
    records = []
    for directory in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        manifest_path = directory / "task.toml"
        instruction_path = directory / "instruction.md"
        if not manifest_path.exists() or not instruction_path.exists():
            continue
        with manifest_path.open("rb") as source:
            manifest = tomllib.load(source)
        environment = manifest.get("environment", {})
        verifier = manifest.get("verifier", {})
        records.append(
            {
                "task_id": directory.name,
                "instruction": instruction_path.read_text(encoding="utf-8"),
                "docker_image": environment.get("docker_image", ""),
                "allow_internet": environment.get("allow_internet", False),
                "verifier_timeout": verifier.get("timeout_sec", 900),
                "test_files": _task_files(directory),
            }
        )
    if len(records) != TERMINALBENCH_TASKS:
        raise ValueError(
            f"Expected {TERMINALBENCH_TASKS} Terminal-Bench 2.1 tasks at "
            f"revision {TERMINALBENCH_REVISION}, found {len(records)}"
        )
    samples = [record_to_sample(record) for record in records]
    sample_count = get_sample_count("terminalbench", tier)
    if 0 < sample_count < len(samples):
        samples = seeded_sample(samples, sample_count, get_seed())
    return samples


def build_harbor_command(
    *,
    agent: str,
    model: str,
    environment: str,
    trials: int = 5,
    concurrency: int = 8,
) -> list[str]:
    """Build the official Harbor 0.20 command for leaderboard-compatible runs."""
    return [
        "harbor",
        "run",
        "-d",
        TERMINALBENCH_DATASET,
        "-a",
        agent,
        "-m",
        model,
        "-e",
        environment,
        "-k",
        str(trials),
        "-n",
        str(concurrency),
    ]


@scorer(metrics=[mean()])
def terminal_task_scorer() -> Scorer:
    """Install hidden verifier files after the run and execute Harbor's test.sh."""

    async def score(state: TaskState, target: Target) -> Score:
        del target
        environment = sandbox()
        for relative, host_path in state.metadata.get("test_files", {}).items():
            destination = f"/tests/{Path(relative).relative_to('tests')}"
            await environment.exec(["mkdir", "-p", str(Path(destination).parent)])
            await environment.write_file(
                destination,
                Path(host_path).read_bytes(),
            )
        result = await environment.exec(
            ["bash", "/tests/test.sh"],
            timeout=int(state.metadata.get("timeout_sec", 900)),
        )
        return Score(
            value=1.0 if result.returncode == 0 else 0.0,
            explanation=f"Official Harbor verifier exited {result.returncode}",
            metadata={"verifier_output": (result.stdout + result.stderr)[-4000:]},
        )

    return score


def _terminal_agent():
    return react(
        prompt=AgentPrompt(
            instructions=(
                "Complete the terminal task in the provided container. Inspect the environment, "
                "make all required changes, and submit only when the task is complete."
            ),
        ),
        tools=[bash_session(timeout=900)],
        submit=AgentSubmit(answer_only=True, keep_in_messages=True),
    )


@register_benchmark(
    name="terminalbench",
    description="Terminal-Bench 2.1 - 89 verified Harbor terminal tasks",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": TERMINALBENCH_TASKS},
    total_samples=TERMINALBENCH_TASKS,
    requires_sandbox=True,
    sandbox_profile="docker",
    scoring_type="official_harbor_verifier",
    provider_requirements=("docker",),
    status=BenchmarkStatus.GATED,
    status_reason="Requires the pinned task snapshot and its per-task Docker images.",
    protocol_version="2.1",
    dataset_source=TERMINALBENCH_DATASET,
    dataset_revision=TERMINALBENCH_REVISION,
    dataset_configs=("terminal-bench-2.1",),
    dataset_splits=("test",),
    license="Apache-2.0",
    access="gated",
    source_kind="github",
    release_policy="versioned",
    evaluator_source="harbor-framework/harbor",
    evaluator_revision=HARBOR_VERSION,
)
@task
def terminalbench(tier: str = "smoke") -> Task:
    return Task(
        dataset=load_terminalbench(tier),
        solver=_terminal_agent(),
        scorer=terminal_task_scorer(),
        message_limit=100,
        name="terminalbench_2_1",
        metadata={
            "protocol_version": "2.1",
            "dataset_revision": TERMINALBENCH_REVISION,
            "evaluator_revision": TERMINALBENCH_REVISION,
        },
    )
