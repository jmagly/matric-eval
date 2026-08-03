"""EvalPlus 0.3.1 HumanEval+ and MBPP+ sandboxed adapters."""

from __future__ import annotations

import json
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Metric, SampleScore, Score, Scorer, Target, metric, scorer
from inspect_ai.solver import TaskState, generate
from inspect_ai.util import SandboxEnvironmentSpec, sandbox

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import seeded_sample
from matric_eval.scorers.code_execution import extract_code
from matric_eval.tasks.registry import register_benchmark

EVALPLUS_VERSION = "0.3.1"
EVALPLUS_REPOSITORY = "evalplus/evalplus"
EVALPLUS_REVISION = "e5d0ed0bab96280b60b637ec7f15b5e4841b0cb2"
EVALPLUS_IMAGE_REVISION = (
    "python:3.12.11-slim-bookworm@"
    "sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"
    "+evalplus-0.3.1"
)
HUMANEVAL_PLUS_VERSION = "v0.1.10"
HUMANEVAL_PLUS_HASH = "fe585eb4df8c88d844eeb463ea4d0302"
MBPP_PLUS_VERSION = "v0.2.0"
MBPP_PLUS_HASH = "ee43ecabebf20deef4bb776a405ac5b1"
HUMANEVAL_PLUS_TOTAL = 164
MBPP_PLUS_TOTAL = 378

_RUNNER = r"""import json
import pickle

from evalplus.evaluate import untrusted_check

with open("/tmp/evalplus_payload.pkl", "rb") as source:
    payload = pickle.load(source)

results = {}
for suite in ("base", "plus"):
    status, details = untrusted_check(
        payload["dataset"],
        payload["code"],
        payload[f"{suite}_input"],
        payload["entry_point"],
        payload[f"{suite}_expected"],
        payload["atol"],
        payload[f"{suite}_time"],
        fast_check=True,
    )
    results[f"{suite}_status"] = status
    results[f"{suite}_details"] = list(details)
print("MATRIC_EVALPLUS_RESULT=" + json.dumps(results))
"""


def _require_evalplus() -> None:
    try:
        import evalplus  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "EvalPlus tasks require the optional dependency: uv sync --extra evalplus"
        ) from exc


@lru_cache(maxsize=2)
def _suite(dataset: Literal["humaneval", "mbpp"]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load versioned problems and trusted reference outputs on the host."""
    _require_evalplus()
    from evalplus.data import (
        get_human_eval_plus,
        get_human_eval_plus_hash,
        get_mbpp_plus,
        get_mbpp_plus_hash,
    )
    from evalplus.evaluate import MBPP_OUTPUT_NOT_NONE_TASKS, get_groundtruth

    if dataset == "humaneval":
        problems = get_human_eval_plus()
        dataset_hash = get_human_eval_plus_hash()
        if dataset_hash != HUMANEVAL_PLUS_HASH:
            raise ValueError(f"HumanEval+ schema/content changed: {dataset_hash}")
        expected = get_groundtruth(problems, dataset_hash, [])
    else:
        problems = get_mbpp_plus()
        dataset_hash = get_mbpp_plus_hash()
        if dataset_hash != MBPP_PLUS_HASH:
            raise ValueError(f"MBPP+ schema/content changed: {dataset_hash}")
        expected = get_groundtruth(problems, dataset_hash, MBPP_OUTPUT_NOT_NONE_TASKS)
    return problems, expected


def record_to_sample(record: dict[str, Any], *, dataset: Literal["humaneval", "mbpp"]) -> Sample:
    required = {
        "task_id",
        "prompt",
        "entry_point",
        "canonical_solution",
        "base_input",
        "plus_input",
        "atol",
    }
    missing = required - record.keys()
    if missing:
        raise ValueError(f"EvalPlus schema missing fields: {', '.join(sorted(missing))}")
    revision = HUMANEVAL_PLUS_VERSION if dataset == "humaneval" else MBPP_PLUS_VERSION
    content_hash = HUMANEVAL_PLUS_HASH if dataset == "humaneval" else MBPP_PLUS_HASH
    return Sample(
        id=str(record["task_id"]),
        input=(
            "Complete the following Python function. Return only executable Python code.\n\n"
            + str(record["prompt"])
        ),
        target=str(record["canonical_solution"]),
        metadata={
            "evalplus_dataset": dataset,
            "entry_point": str(record["entry_point"]),
            "dataset_revision": revision,
            "dataset_hash": content_hash,
            "evaluator_version": EVALPLUS_VERSION,
            "base_test_count": len(record["base_input"]),
            "plus_test_count": len(record["plus_input"]),
            "sandbox": "docker-network-none",
        },
    )


def load_evalplus(dataset: Literal["humaneval", "mbpp"], tier: str = "smoke") -> list[Sample]:
    problems, _ = _suite(dataset)
    benchmark = f"{dataset}_plus"
    samples = [record_to_sample(problem, dataset=dataset) for problem in problems.values()]
    return seeded_sample(samples, get_sample_count(benchmark, tier), get_seed())


def _problem_payload(dataset: str, task_id: str, code: str) -> dict[str, Any]:
    problems, expected = _suite(dataset)  # type: ignore[arg-type]
    if task_id not in problems or task_id not in expected:
        raise ValueError(f"Unknown EvalPlus task or schema mismatch: {task_id}")
    problem = problems[task_id]
    oracle = expected[task_id]
    return {
        "dataset": dataset,
        "code": str(problem["prompt"]) + code,
        "entry_point": problem["entry_point"],
        "atol": problem["atol"],
        "base_input": problem["base_input"],
        "plus_input": problem["plus_input"],
        "base_expected": oracle["base"],
        "plus_expected": oracle["plus"],
        "base_time": oracle["base_time"],
        "plus_time": oracle["plus_time"],
    }


def parse_evalplus_output(stdout: str) -> dict[str, Any]:
    marker = "MATRIC_EVALPLUS_RESULT="
    for line in reversed(stdout.splitlines()):
        if line.startswith(marker):
            try:
                result = json.loads(line[len(marker) :])
            except json.JSONDecodeError as exc:
                raise ValueError("EvalPlus runner returned malformed output") from exc
            required = {"base_status", "plus_status", "base_details", "plus_details"}
            if required <= result.keys():
                return result
    raise ValueError("EvalPlus runner returned malformed output")


@metric
def evalplus_rates() -> Metric:
    def calculate(scores: list[SampleScore]) -> dict[str, float]:
        values = [score.score.value for score in scores if isinstance(score.score.value, dict)]
        total = len(values)
        return {
            "base_pass_rate": (
                sum(float(value["base_pass"]) for value in values) / total if total else 0.0
            ),
            "plus_pass_rate": (
                sum(float(value["plus_pass"]) for value in values) / total if total else 0.0
            ),
        }

    return calculate


@scorer(metrics=[evalplus_rates()])
def evalplus_scorer(timeout: int = 130) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        del target
        code = extract_code(state.output.completion)
        if not code:
            return Score(
                value={"base_pass": 0.0, "plus_pass": 0.0},
                explanation="EvalPlus malformed code: empty completion",
            )
        payload = _problem_payload(
            str(state.metadata["evalplus_dataset"]), str(state.sample_id), code
        )
        environment = sandbox()
        await environment.write_file("/tmp/evalplus_payload.pkl", pickle.dumps(payload))
        await environment.write_file("/tmp/evalplus_runner.py", _RUNNER)
        result = await environment.exec(
            ["python", "/tmp/evalplus_runner.py"],
            timeout=timeout,
        )
        try:
            statuses = parse_evalplus_output(result.stdout)
        except ValueError:
            failure = "timeout" if result.returncode == 124 else "malformed-runner-output"
            return Score(
                value={"base_pass": 0.0, "plus_pass": 0.0},
                explanation=f"EvalPlus {failure}: {(result.stdout + result.stderr)[-2000:]}",
                metadata={"failure_class": failure, "returncode": result.returncode},
            )
        base_pass = statuses["base_status"] == "pass"
        plus_pass = base_pass and statuses["plus_status"] == "pass"
        return Score(
            value={"base_pass": float(base_pass), "plus_pass": float(plus_pass)},
            explanation=(
                f"EvalPlus base={statuses['base_status']}, plus={statuses['plus_status']}"
            ),
            metadata={
                **statuses,
                "failure_class": None if plus_pass else statuses["plus_status"],
                "sandbox": "docker-network-none",
            },
        )

    return score


def _sandbox_spec() -> SandboxEnvironmentSpec:
    root = Path(__file__).resolve().parents[3]
    return SandboxEnvironmentSpec(
        type="docker", config=str(root / "docker" / "evalplus" / "compose.yaml")
    )


def _evalplus_task(dataset: Literal["humaneval", "mbpp"], tier: str) -> Task:
    version = HUMANEVAL_PLUS_VERSION if dataset == "humaneval" else MBPP_PLUS_VERSION
    return Task(
        dataset=load_evalplus(dataset, tier),
        solver=generate(temperature=0),
        scorer=evalplus_scorer(),
        sandbox=_sandbox_spec(),
        name=f"{dataset}_plus_{version.lstrip('v').replace('.', '_')}",
        metadata={
            "protocol": f"EvalPlus {EVALPLUS_VERSION}",
            "test_suite": "base+plus",
            "dataset_revision": version,
            "evaluator_revision": EVALPLUS_VERSION,
            "container_revision": EVALPLUS_IMAGE_REVISION,
        },
    )


@register_benchmark(
    name="humaneval_plus",
    description="HumanEval+ v0.1.10 - 164 problems with expanded EvalPlus tests",
    category="code",
    tier_samples={"smoke": 5, "quick": 75, "full": HUMANEVAL_PLUS_TOTAL},
    total_samples=HUMANEVAL_PLUS_TOTAL,
    requires_sandbox=True,
    sandbox_profile="evalplus-docker",
    scoring_type="base_and_plus_pass_rate",
    provider_requirements=("docker",),
    protocol_version=f"EvalPlus-{EVALPLUS_VERSION}",
    dataset_source=EVALPLUS_REPOSITORY,
    dataset_revision=EVALPLUS_REVISION,
    dataset_configs=(f"HumanEvalPlus-{HUMANEVAL_PLUS_VERSION}",),
    dataset_splits=("base", "plus"),
    evaluator_source=EVALPLUS_REPOSITORY,
    evaluator_revision=EVALPLUS_REVISION,
    container_revision=EVALPLUS_IMAGE_REVISION,
    license="Apache-2.0",
    access="public",
    source_kind="github",
    release_policy="versioned",
)
@task
def humaneval_plus(tier: str = "smoke") -> Task:
    return _evalplus_task("humaneval", tier)


@register_benchmark(
    name="mbpp_plus",
    description="MBPP+ v0.2.0 - 378 problems with expanded EvalPlus tests",
    category="code",
    tier_samples={"smoke": 5, "quick": 75, "full": MBPP_PLUS_TOTAL},
    total_samples=MBPP_PLUS_TOTAL,
    requires_sandbox=True,
    sandbox_profile="evalplus-docker",
    scoring_type="base_and_plus_pass_rate",
    provider_requirements=("docker",),
    protocol_version=f"EvalPlus-{EVALPLUS_VERSION}",
    dataset_source=EVALPLUS_REPOSITORY,
    dataset_revision=EVALPLUS_REVISION,
    dataset_configs=(f"MbppPlus-{MBPP_PLUS_VERSION}",),
    dataset_splits=("base", "plus"),
    evaluator_source=EVALPLUS_REPOSITORY,
    evaluator_revision=EVALPLUS_REVISION,
    container_revision=EVALPLUS_IMAGE_REVISION,
    license="Apache-2.0",
    access="public",
    source_kind="github",
    release_policy="versioned",
)
@task
def mbpp_plus(tier: str = "smoke") -> Task:
    return _evalplus_task("mbpp", tier)
