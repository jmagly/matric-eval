"""Pinned SWE-bench loaders using the maintained agent and official harness."""

from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.util import SandboxEnvironmentSpec
from inspect_evals.swe_bench.scorers import swe_bench_scorer
from inspect_evals.swe_bench.solvers import swe_bench_agent_with_inspect_tool_support

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, seeded_sample

SWEBENCH_EVALUATOR_REVISION = "6a35510e530f236fd1dbcd9df888f01937c8494a"
SWEBENCH_SYSTEM_PROMPT = (
    "Please solve the following coding issue by editing the repository. "
    "Your changes will be evaluated as a git patch.\n\n{issue_text}"
)

VARIANT_CONFIG: dict[str, dict[str, Any]] = {
    "verified": {
        "dataset_id": "SWE-bench/SWE-bench_Verified",
        "revision": "91aa3ed51b709be6457e12d00300a6a596d4c6a3",
        "split": "test",
        "total_samples": 500,
    },
    "multilingual": {
        "dataset_id": "SWE-bench/SWE-bench_Multilingual",
        "revision": "e5c585e008e2cb5eecc7c64192d855c53279d788",
        "split": "test",
        "total_samples": 300,
    },
    "pro": {
        "dataset_id": "ScaleAI/SWE-bench_Pro",
        "revision": "7ab5114912baf22bb098818e604c02fe7ad2c11f",
        "split": "test",
        "total_samples": 731,
    },
}


def _test_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def _extract_test_path(test_patch: str) -> str:
    for line in test_patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path and path != "/dev/null":
                return path
    return ""


def swebench_record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert both string-list and Arrow-list SWE-bench snapshots."""
    instance_id = str(record.get("instance_id", ""))
    repo = str(record.get("repo", ""))
    issue = str(record.get("problem_statement", ""))
    hints = str(record.get("hints_text", "") or "")
    prompt = f"Repository: {repo}\n\n" + SWEBENCH_SYSTEM_PROMPT.format(issue_text=issue)
    if hints:
        prompt += f"\n\nHints:\n{hints}"
    metadata = {
        key: record.get(key, "")
        for key in (
            "base_commit",
            "patch",
            "test_patch",
            "version",
            "repo",
            "environment_setup_commit",
            "hints_text",
            "created_at",
        )
    }
    metadata.update(
        {
            "instance_id": instance_id,
            "FAIL_TO_PASS": _test_list(record.get("FAIL_TO_PASS")),
            "PASS_TO_PASS": _test_list(record.get("PASS_TO_PASS")),
            "repo_path": f"/workspace/{repo.replace('/', '_')}",
            "test_path": _extract_test_path(str(record.get("test_patch", ""))),
        }
    )
    return Sample(
        input=prompt,
        target=str(record.get("patch", "")),
        id=instance_id,
        metadata=metadata,
    )


def _records(variant: str) -> list[dict[str, Any]]:
    config = VARIANT_CONFIG[variant]
    local_path = get_dataset_path(f"swebench_{variant}")
    if local_path:
        path = Path(local_path)
        if path.is_dir():
            path = path / f"{config['split']}.jsonl"
        with path.open(encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]

    from datasets import load_dataset

    dataset = load_dataset(
        config["dataset_id"],
        split=config["split"],
        revision=config["revision"],
    )
    return [dict(record) for record in dataset]


def _official_image(record: dict[str, Any]) -> str:
    from swebench.harness.test_spec.test_spec import make_test_spec

    image = make_test_spec(record).instance_image_key
    return image if "/" in image else f"swebench/{image}"


def _sandbox(
    image: str,
    instance_id: str,
    working_dir: str = "/testbed",
    *,
    allow_internet: bool = False,
) -> SandboxEnvironmentSpec:
    directory = Path(tempfile.gettempdir()) / "matric-eval-sandboxes" / "swebench"
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / f"{instance_id}.yaml"
    content = (
        "services:\n"
        "  default:\n"
        f"    image: {image}\n"
        '    entrypoint: ["sleep", "infinity"]\n'
        "    command: []\n"
        f"    working_dir: {working_dir}\n"
    )
    if not allow_internet:
        content += "    network_mode: none\n"
    config.write_text(content, encoding="utf-8")
    return SandboxEnvironmentSpec(type="docker", config=str(config))


def load_swebench(
    variant: str,
    tier: str = "smoke",
    record_to_sample_fn: Callable[[dict[str, Any]], Sample] | None = None,
) -> list[Sample]:
    if variant not in VARIANT_CONFIG:
        raise ValueError(
            f"Unknown SWE-bench variant '{variant}'. Available: {', '.join(sorted(VARIANT_CONFIG))}"
        )
    if variant == "pro":
        raise ValueError("SWE-bench Pro uses its dedicated official evaluator adapter")
    converter = record_to_sample_fn or swebench_record_to_sample
    records = _records(variant)
    sample_count = get_sample_count(f"swebench_{variant}", tier)
    if 0 < sample_count < len(records):
        records = seeded_sample(records, sample_count, get_seed())
    samples = []
    for record in records:
        sample = converter(record)
        sample.metadata = sample.metadata or {}
        sample.metadata.update(
            {
                "image_name": _official_image(record),
                "allow_internet": False,
                "dataset_revision": VARIANT_CONFIG[variant]["revision"],
                "evaluator_revision": SWEBENCH_EVALUATOR_REVISION,
            }
        )
        sample.sandbox = _sandbox(sample.metadata["image_name"], str(sample.id))
        samples.append(sample)
    return samples


def create_swebench_task(
    variant: str,
    tier: str = "smoke",
    record_to_sample_fn: Callable[[dict[str, Any]], Sample] | None = None,
) -> Task:
    config = VARIANT_CONFIG[variant]
    return Task(
        dataset=load_swebench(variant, tier, record_to_sample_fn),
        solver=swe_bench_agent_with_inspect_tool_support(),
        scorer=swe_bench_scorer(),
        message_limit=30,
        name=f"swebench_{variant}",
        metadata={
            "protocol_version": "official-harness-2026",
            "dataset_source": config["dataset_id"],
            "dataset_revision": config["revision"],
            "evaluator_revision": SWEBENCH_EVALUATOR_REVISION,
        },
    )


def parse_pro_test_list(value: Any) -> list[str]:
    """Parse SWE-bench Pro's Python-literal test list without eval()."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    parsed = ast.literal_eval(str(value))
    if not isinstance(parsed, list):
        raise ValueError("SWE-bench Pro test list is not a list")
    return [str(item) for item in parsed]
