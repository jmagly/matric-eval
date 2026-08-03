"""InfiniteBench 2-A wrapper around the maintained Inspect Evals implementation."""

from __future__ import annotations

from collections.abc import Callable

from inspect_ai import Task, task
from inspect_evals.infinite_bench.infinite_bench import (
    INFINITE_BENCH_DATASET_REVISION,
    infinite_bench_code_debug,
    infinite_bench_code_run,
    infinite_bench_kv_retrieval,
    infinite_bench_longbook_choice_eng,
    infinite_bench_longdialogue_qa_eng,
    infinite_bench_math_calc,
    infinite_bench_math_find,
    infinite_bench_number_string,
    infinite_bench_passkey,
)

from matric_eval.tasks.registry import register_benchmark
from matric_eval.tasks.upstream import INSPECT_EVALS_REVISION, adapt_upstream_task

INFINITE_BENCH_REPOSITORY = "OpenBMB/InfiniteBench"
INFINITE_BENCH_REVISION = "51d9b37b0f1790ead936df2243abbf7f0420e439"
INFINITE_BENCH_PROTOCOL = "2-A"
INFINITE_BENCH_TASKS = (
    "code_debug",
    "code_run",
    "kv_retrieval",
    "longbook_choice_eng",
    "longdialogue_qa_eng",
    "math_calc",
    "math_find",
    "number_string",
    "passkey",
)
INFINITE_BENCH_FACTORIES: dict[str, Callable[[], Task]] = {
    "code_debug": infinite_bench_code_debug,
    "code_run": infinite_bench_code_run,
    "kv_retrieval": infinite_bench_kv_retrieval,
    "longbook_choice_eng": infinite_bench_longbook_choice_eng,
    "longdialogue_qa_eng": infinite_bench_longdialogue_qa_eng,
    "math_calc": infinite_bench_math_calc,
    "math_find": infinite_bench_math_find,
    "number_string": infinite_bench_number_string,
    "passkey": infinite_bench_passkey,
}
INFINITE_BENCH_TASK_COUNTS = {
    "code_debug": 394,
    "code_run": 400,
    "kv_retrieval": 500,
    "longbook_choice_eng": 229,
    "longdialogue_qa_eng": 200,
    "math_calc": 50,
    "math_find": 350,
    "number_string": 590,
    "passkey": 590,
}
INFINITE_BENCH_TOTAL = sum(INFINITE_BENCH_TASK_COUNTS.values())
INFINITE_BENCH_TRUNCATION_POLICY = (
    "reserve 500 model tokens; use tiktoken for GPT models, otherwise estimate "
    "3.5 characters/token; preserve equal prefix and suffix halves"
)


def create_infinite_bench_task(task_name: str, tier: str = "smoke") -> Task:
    """Create one of the nine protocol 2-A tasks without collapsing task identity."""
    try:
        upstream = INFINITE_BENCH_FACTORIES[task_name]()
    except KeyError as exc:
        raise ValueError(f"Unknown InfiniteBench task: {task_name}") from exc
    return adapt_upstream_task(
        upstream,
        benchmark="infinite_bench",
        tier=tier,
        task_name=f"infinite_bench_{task_name}",
        protocol_metadata={
            "protocol_version": INFINITE_BENCH_PROTOCOL,
            "infinite_bench_task": task_name,
            "dataset_revision": INFINITE_BENCH_DATASET_REVISION,
            "evaluator_revision": INSPECT_EVALS_REVISION,
            "upstream_evaluator_revision": INFINITE_BENCH_REVISION,
            "truncation_policy": INFINITE_BENCH_TRUNCATION_POLICY,
        },
    )


@register_benchmark(
    name="infinite_bench",
    description="InfiniteBench 2-A - nine long-context tasks beyond 100K",
    category="reasoning",
    tier_samples={"smoke": 5, "quick": 50, "full": INFINITE_BENCH_TOTAL},
    total_samples=INFINITE_BENCH_TOTAL,
    scoring_type="upstream_task_specific_scorers",
    protocol_version=INFINITE_BENCH_PROTOCOL,
    dataset_source="xinrongzhang2022/InfiniteBench",
    dataset_revision=INFINITE_BENCH_DATASET_REVISION,
    dataset_configs=("default",),
    dataset_splits=INFINITE_BENCH_TASKS,
    evaluator_source="inspect-evals/infinite_bench",
    evaluator_revision=INSPECT_EVALS_REVISION,
    prompt_revision=INSPECT_EVALS_REVISION,
    license="Apache-2.0",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
)
@task
def infinite_bench(tier: str = "smoke", task_name: str = "kv_retrieval") -> Task:
    return create_infinite_bench_task(task_name, tier)
