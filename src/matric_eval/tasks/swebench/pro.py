"""SWE-bench Pro with its pinned images, run scripts, and parsers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, std
from inspect_ai.solver import TaskState
from inspect_ai.util import sandbox
from inspect_evals.swe_bench.solvers import swe_bench_agent_with_inspect_tool_support

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import seeded_sample
from matric_eval.tasks.registry import register_benchmark
from matric_eval.tasks.swebench.factory import (
    SWEBENCH_SYSTEM_PROMPT,
    VARIANT_CONFIG,
    _records,
    _sandbox,
    parse_pro_test_list,
)

PRO_HARNESS_REPOSITORY = "scaleapi/SWE-bench_Pro-os"
PRO_HARNESS_REVISION = "ca10a60a5fcae51e6948ffe1485d4153d421e6c5"


def _harness_script(instance_id: str, filename: str) -> str:
    local = os.environ.get("SWE_BENCH_PRO_HARNESS_PATH")
    if local:
        return (Path(local) / "run_scripts" / instance_id / filename).read_text(encoding="utf-8")
    url = (
        f"https://raw.githubusercontent.com/{PRO_HARNESS_REPOSITORY}/"
        f"{PRO_HARNESS_REVISION}/run_scripts/{instance_id}/{filename}"
    )
    with urlopen(url, timeout=30) as response:  # noqa: S310 - pinned HTTPS source
        return response.read().decode("utf-8")


def pro_record_to_sample(record: dict[str, Any]) -> Sample:
    instance_id = str(record["instance_id"])
    metadata = dict(record)
    metadata.update(
        {
            "FAIL_TO_PASS": parse_pro_test_list(record.get("fail_to_pass")),
            "PASS_TO_PASS": parse_pro_test_list(record.get("pass_to_pass")),
            "run_script": _harness_script(instance_id, "run_script.sh"),
            "parser_script": _harness_script(instance_id, "parser.py"),
            "image_name": f"jefzda/sweap-images:{record['dockerhub_tag']}",
            "dataset_revision": VARIANT_CONFIG["pro"]["revision"],
            "evaluator_revision": PRO_HARNESS_REVISION,
        }
    )
    sample = Sample(
        input=SWEBENCH_SYSTEM_PROMPT.format(issue_text=record["problem_statement"]),
        target=str(record.get("patch", "")),
        id=instance_id,
        metadata=metadata,
    )
    sample.sandbox = _sandbox(metadata["image_name"], instance_id, working_dir="/app")
    return sample


def load_swebench_pro(tier: str = "smoke") -> list[Sample]:
    records = _records("pro")
    sample_count = get_sample_count("swebench_pro", tier)
    if 0 < sample_count < len(records):
        records = seeded_sample(records, sample_count, get_seed())
    return [pro_record_to_sample(record) for record in records]


@scorer(metrics=[mean(), std()])
def swebench_pro_scorer() -> Scorer:
    """Run and parse the exact per-instance SWE-bench Pro evaluator."""

    async def score(state: TaskState, target: Target) -> Score:
        del target
        environment = sandbox()
        base_commit = str(state.metadata["base_commit"])
        patch_result = await environment.exec(
            ["bash", "-c", f"cd /app && git diff {base_commit}"], timeout=60
        )
        if patch_result.returncode != 0:
            raise RuntimeError(f"Could not collect model patch: {patch_result.stderr}")
        model_patch = patch_result.stdout
        await environment.write_file("/workspace/patch.diff", model_patch)
        await environment.write_file("/workspace/run_script.sh", state.metadata["run_script"])
        await environment.write_file("/workspace/parser.py", state.metadata["parser_script"])
        selected = str(state.metadata.get("selected_test_files_to_run", ""))
        before = str(state.metadata.get("before_repo_set_cmd", ""))
        command = f"""
cd /app
git reset --hard {base_commit}
git checkout {base_commit}
git apply -v /workspace/patch.diff
{before}
bash /workspace/run_script.sh {selected} > /workspace/stdout.log 2> /workspace/stderr.log
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
"""
        result = await environment.exec(["bash", "-c", command], timeout=1800)
        try:
            payload = json.loads(await environment.read_file("/workspace/output.json"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "SWE-bench Pro evaluator produced no gradeable output; "
                f"exit={result.returncode}, stderr={result.stderr[-2000:]}"
            ) from exc
        passed = {
            str(test["name"]) for test in payload.get("tests", []) if test.get("status") == "PASSED"
        }
        required = set(state.metadata["FAIL_TO_PASS"]) | set(state.metadata["PASS_TO_PASS"])
        resolved = required <= passed
        return Score(
            value=1.0 if resolved else 0.0,
            explanation=f"{len(passed & required)}/{len(required)} required tests passed",
            metadata={"model_patch": model_patch, "required_tests": sorted(required)},
        )

    return score


@register_benchmark(
    name="swebench_pro",
    description="SWE-bench Pro - 731 long-horizon repository tasks",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 731},
    total_samples=731,
    requires_sandbox=True,
    sandbox_profile="agentic-dev",
    scoring_type="official_resolved",
    protocol_version="2026-05",
    dataset_source="ScaleAI/SWE-bench_Pro",
    dataset_revision=VARIANT_CONFIG["pro"]["revision"],
    dataset_configs=("default",),
    dataset_splits=("test",),
    license="upstream dataset terms",
    access="public",
    source_kind="huggingface",
    release_policy="versioned",
    evaluator_source=PRO_HARNESS_REPOSITORY,
    evaluator_revision=PRO_HARNESS_REVISION,
)
@task
def swebench_pro(tier: str = "smoke") -> Task:
    return Task(
        dataset=load_swebench_pro(tier),
        solver=swe_bench_agent_with_inspect_tool_support(),
        scorer=swebench_pro_scorer(),
        message_limit=250,
        name="swebench_pro",
        metadata={
            "protocol_version": "2026-05",
            "dataset_revision": VARIANT_CONFIG["pro"]["revision"],
            "evaluator_revision": PRO_HARNESS_REVISION,
        },
    )
