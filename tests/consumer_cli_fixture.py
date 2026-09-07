"""Test-only entry module: register a real fixed Task, then call the real CLI.

It neither substitutes transport output nor patches Inspect dispatch.
"""

from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import match
from inspect_ai.solver import generate

from matric_eval.results.contract import MetricDescriptor
from matric_eval.tasks.registry import BenchmarkCategory, BenchmarkMetadata, get_registry


def fixed_task(tier: str = "smoke") -> Task:
    return Task(
        dataset=[
            Sample(
                id="correct",
                input="plain fixture prompt",
                target="Default output from mockllm/model",
            ),
            Sample(id="wrong", input="plain fixture prompt", target="different"),
        ],
        solver=generate(),
        scorer=match(),
    )


def main() -> None:
    import sys
    from types import ModuleType

    from matric_eval.cli import cli

    module = ModuleType("matric_eval.tasks._consumer_fixture")
    module.fixed_task = fixed_task
    sys.modules[module.__name__] = module

    descriptor = MetricDescriptor(
        metric_id="match/accuracy",
        version="fixture/1",
        scorer_id="match",
        value_kind="binary",
        units="fraction",
        direction="higher",
        minimum=0.0,
        maximum=1.0,
        independent_unit="task",
        missingness_policy="exclude-unmeasured/1",
        aggregation_id="accuracy/1",
        timeout_value=None,
    )
    get_registry().register(
        BenchmarkMetadata(
            name="consumer_fixture",
            description="Offline consumer boundary fixture",
            category=BenchmarkCategory.REASONING,
            module_path="matric_eval.tasks._consumer_fixture.fixed_task",
            tier_samples={"smoke": 2},
            total_samples=2,
            primary_metric_id="match/accuracy",
            metric_descriptors=(descriptor,),
        )
    )
    cli()


if __name__ == "__main__":
    main()
