"""
NL2Repo benchmark — long-horizon code generation from natural language specs.

Models generate entire repositories from NL specifications. Tests project-level
code generation beyond single-function tasks.

Scored via project_scorer: 40% build success + 60% test pass rate.

Dataset: TBD (RISK-008)
"""

from __future__ import annotations

import random
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, load_hf_dataset
from matric_eval.scorers.project import project_scorer
from matric_eval.tasks.registry import register_benchmark


NL2REPO_SYSTEM_PROMPT = """\
You are an expert software engineer. You will be given a natural language \
specification for a software project. Your task is to generate a complete, \
working project that satisfies the specification.

Generate all necessary files including source code, tests, and build \
configuration. The project must build successfully and pass its test suite.\
"""


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert an NL2Repo record to an Inspect AI Sample.

    Expected schema:
        - id: str
        - specification: str (natural language project spec)
        - expected_structure: dict (expected file tree)
        - build_command: str
        - test_command: str
        - language: str
    """
    task_id = record.get("id", "")
    spec = record.get("specification", record.get("input", ""))
    build_cmd = record.get("build_command", "")
    test_cmd = record.get("test_command", "")
    language = record.get("language", "python")

    return Sample(
        input=spec,
        target="",  # No single target — evaluated by build + tests
        id=str(task_id),
        metadata={
            "build_command": build_cmd,
            "test_command": test_cmd,
            "language": language,
            "expected_structure": record.get("expected_structure", {}),
        },
    )


def load_nl2repo(tier: str = "smoke") -> list[Sample]:
    """Load NL2Repo samples for the given tier."""
    benchmark_name = "nl2repo"
    sample_count = get_sample_count(benchmark_name, tier)

    local_path = get_dataset_path(benchmark_name)
    if local_path:
        import json
        from pathlib import Path

        records = []
        with open(Path(local_path)) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        all_samples = [record_to_sample(r) for r in records]
    else:
        all_samples = load_hf_dataset(
            "nl2repo/nl2repo",
            split="test",
            sample_count=sample_count,
            seed=get_seed(),
            record_to_sample=record_to_sample,
        )
        return all_samples

    if sample_count >= len(all_samples):
        return all_samples

    rng = random.Random(get_seed())
    sampled = rng.sample(all_samples, sample_count)
    sampled.sort(key=lambda s: s.id or "")
    return sampled


@register_benchmark(
    name="nl2repo",
    description="NL2Repo - full repository generation from specifications",
    category="agentic",
    tier_samples={"smoke": 3, "quick": 20, "full": 0},
    total_samples=0,  # TBD
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="project",
)
@task
def nl2repo(tier: str = "smoke") -> Task:
    """NL2Repo benchmark — generate entire projects from NL specs.

    Scored via project_scorer: 40% build + 60% tests.

    Args:
        tier: Evaluation tier

    Returns:
        Task configured for NL2Repo evaluation
    """
    return Task(
        dataset=load_nl2repo(tier),
        solver=[
            system_message(NL2REPO_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=project_scorer(),
        name="nl2repo",
    )
