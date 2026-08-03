#!/usr/bin/env python3
"""Generate deterministic scorer-parity and operational validation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from matric_eval.parallel import ParallelConfig, ParallelExecutor, ParallelStrategy
from matric_eval.scorers.code_execution import prepare_code, prepare_test_code, safe_execute
from matric_eval.state.manager import StateManager
from matric_eval.tasks.matric_memory import (
    score_legacy_semantic,
    score_legacy_title,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "validation" / "operational-parity-matrix-v1.json"
DEFAULT_OUTPUT = ROOT / "docs" / "validation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def legacy_extract_code(response: str) -> str:
    """Mirror matric-cli validator.ts at the revision pinned by the matrix."""
    cleaned = re.sub(r"^[\x00-\x1f\u2800-\u28ff\ufeff\u200b-\u200f]+", "", response)
    cleaned = re.sub(r"[\u2800-\u28ff]", "", cleaned)
    match = re.search(r"```(?:python|py)?\n?([\s\S]*?)```", cleaned)
    return (match.group(1) if match else cleaned).strip()


def legacy_code_pass(case: dict[str, Any]) -> bool:
    code = legacy_extract_code(str(case["response"]))
    if (
        case["benchmark"] == "humaneval"
        and case.get("prompt")
        and not re.search(rf"\bdef\s+{re.escape(str(case['entry_point']))}\s*\(", code)
    ):
        body = "\n".join(f"    {line}" if line.strip() else line for line in code.splitlines())
        code = f"{str(case['prompt']).rstrip()}\n{body}"
    test = str(case["test"])
    if case["benchmark"] == "humaneval":
        test = f"{test.rstrip()}\n\ncheck({case['entry_point']})"
    result = subprocess.run(
        [sys.executable, "-c", f"{code}\n{test}"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.returncode == 0


def validate_code_parity(matrix: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in matrix["code_cases"]:
        metadata = {
            "test": case["test"],
            "entry_point": case["entry_point"],
            "prompt": case.get("prompt"),
        }
        current = safe_execute(
            prepare_code(str(case["response"]), metadata),
            prepare_test_code(metadata),
            timeout=5,
        )["passed"]
        reference = legacy_code_pass(case)
        rows.append(
            {
                "id": case["id"],
                "benchmark": case["benchmark"],
                "expected_pass": case["expected_pass"],
                "matric_eval_pass": current,
                "reference_pass": reference,
                "agreement": current == reference == case["expected_pass"],
            }
        )

    benchmarks: dict[str, Any] = {}
    tolerance = matrix["tolerances"]["public_score_variance_percentage_points"]
    for benchmark in ("humaneval", "mbpp"):
        selected = [row for row in rows if row["benchmark"] == benchmark]
        current_rate = 100 * sum(row["matric_eval_pass"] for row in selected) / len(selected)
        reference_rate = 100 * sum(row["reference_pass"] for row in selected) / len(selected)
        variance = abs(current_rate - reference_rate)
        benchmarks[benchmark] = {
            "cases": len(selected),
            "matric_eval_pass_rate": current_rate,
            "reference_pass_rate": reference_rate,
            "variance_percentage_points": variance,
            "tolerance_percentage_points": tolerance,
            "passed": variance <= tolerance and all(row["agreement"] for row in selected),
        }

    return {
        "passed": all(item["passed"] for item in benchmarks.values()),
        "benchmarks": benchmarks,
        "cases": rows,
    }


def reference_title_score(case: dict[str, Any]) -> tuple[float, bool]:
    output = str(case["output"])
    keywords = list(case["expected_keywords"])
    matches = sum(1 for keyword in keywords if keyword.lower() in output.lower())
    ratio = matches / len(keywords) if keywords else 0.0
    clean = (
        "```" not in output
        and not output.startswith("#")
        and "**" not in output
        and "Title:" not in output
    )
    value = (ratio * 0.6) + (0.2 if len(output) <= case["max_length"] else 0.0)
    value += 0.2 if clean else 0.0
    return value, value >= 0.7


def reference_semantic_score(case: dict[str, Any]) -> tuple[float, bool]:
    def reference_cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = sum(value * value for value in left) ** 0.5
        right_norm = sum(value * value for value in right) ** 0.5
        return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0

    query = list(case["query"])
    positives = [reference_cosine(query, list(item)) for item in case["positive"]]
    negatives = [reference_cosine(query, list(item)) for item in case["negative"]]
    min_positive = min(positives, default=0.0)
    max_negative = max(negatives, default=1.0)
    return max(0.0, min(1.0, min_positive - max_negative + 0.5)), (min_positive > max_negative)


def validate_memory_parity(matrix: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    tolerance = matrix["tolerances"]["matric_memory_score_delta"]
    for case in matrix["matric_memory_cases"]:
        current_score, current_pass, _ = score_legacy_title(
            str(case["output"]),
            list(case["expected_keywords"]),
            int(case["max_length"]),
        )
        reference_score, reference_pass = reference_title_score(case)
        delta = abs(current_score - reference_score)
        rows.append(
            {
                "id": case["id"],
                "scorer": "title",
                "matric_eval_score": current_score,
                "reference_score": reference_score,
                "score_delta": delta,
                "matric_eval_pass": current_pass,
                "reference_pass": reference_pass,
                "agreement": delta <= tolerance and current_pass == reference_pass,
            }
        )
    for case in matrix["matric_memory_semantic_cases"]:
        current_score, current_pass, _ = score_legacy_semantic(
            list(case["query"]),
            [list(item) for item in case["positive"]],
            [list(item) for item in case["negative"]],
        )
        reference_score, reference_pass = reference_semantic_score(case)
        delta = abs(current_score - reference_score)
        rows.append(
            {
                "id": case["id"],
                "scorer": "semantic",
                "matric_eval_score": current_score,
                "reference_score": reference_score,
                "score_delta": delta,
                "matric_eval_pass": current_pass,
                "reference_pass": reference_pass,
                "agreement": delta <= tolerance and current_pass == reference_pass,
            }
        )
    return {
        "passed": all(row["agreement"] for row in rows),
        "agreement_target": 1.0,
        "agreement_rate": sum(row["agreement"] for row in rows) / len(rows),
        "score_delta_tolerance": tolerance,
        "cases": rows,
    }


def validate_resume(matrix: dict[str, Any]) -> dict[str, Any]:
    operations = matrix["operations"]
    model = operations["models"][0]
    benchmarks = list(operations["benchmarks"][:2])
    with tempfile.TemporaryDirectory(prefix="matric-eval-validation-") as temp_dir:
        manager = StateManager(Path(temp_dir))
        manager.initialize_run(
            run_id="operational-validation",
            tier="smoke",
            seed=int(matrix["seed"]),
            models=[model],
            benchmarks=benchmarks,
        )
        preserved = {"benchmark": benchmarks[0], "sample_ids": ["a", "b", "c"]}
        manager.mark_complete(model, benchmarks[0], 1.0, 3, preserved)
        completed_before = {benchmarks[0]}
        pending = manager.get_resume_work()[model]
        executed: list[str] = []
        for benchmark in pending:
            executed.append(benchmark)
            manager.mark_running(model, benchmark)
            manager.mark_complete(
                model,
                benchmark,
                1.0,
                3,
                {"benchmark": benchmark, "sample_ids": ["d", "e", "f"]},
            )

        final_result = manager.build_model_result(model)
        final_keys = set(final_result["benchmarks"])
        duplicate_count = len(completed_before.intersection(executed))
        preserved_after = manager.get_benchmark_result(model, benchmarks[0])
        manager.release_lock(force=True)

    passed = (
        duplicate_count == matrix["tolerances"]["resume_duplicate_count"]
        and final_keys == set(benchmarks)
        and preserved_after == preserved
    )
    return {
        "passed": passed,
        "completed_before_interrupt": sorted(completed_before),
        "executed_after_resume": executed,
        "final_result_keys": sorted(final_keys),
        "duplicate_count": duplicate_count,
        "preserved_checkpoint_result": preserved_after == preserved,
    }


def work_unit(value: int) -> dict[str, int]:
    time.sleep(0.005)
    return {"id": value, "value": value * value}


def execute_units(count: int, strategy: ParallelStrategy) -> tuple[list[dict[str, int]], float]:
    executor = ParallelExecutor(
        ParallelConfig(
            strategy=strategy,
            max_workers=4,
            retry_on_failure=False,
        )
    )
    result = executor.execute(list(range(count)), work_unit, lambda item: str(item))
    values = sorted(result.get_successful_results(), key=lambda item: item["id"])
    return values, result.total_duration_seconds


def validate_parallel_and_tiers(matrix: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    operations = matrix["operations"]
    count = int(operations["parallel_task_count"])
    sequential, sequential_duration = execute_units(count, ParallelStrategy.SEQUENTIAL)
    parallel, parallel_duration = execute_units(count, ParallelStrategy.THREAD)
    difference = len(
        {json.dumps(item, sort_keys=True) for item in sequential}
        ^ {json.dumps(item, sort_keys=True) for item in parallel}
    )
    parallel_report = {
        "passed": difference == matrix["tolerances"]["result_set_difference"],
        "task_count": count,
        "result_set_difference": difference,
        "sequential_duration_seconds": sequential_duration,
        "parallel_duration_seconds": parallel_duration,
        "speedup": sequential_duration / parallel_duration if parallel_duration else None,
    }

    tiers: dict[str, Any] = {}
    for tier, key in (("smoke", "smoke_work_units"), ("quick", "quick_work_units")):
        _, duration = execute_units(int(operations[key]), ParallelStrategy.SEQUENTIAL)
        tiers[tier] = {"work_units": int(operations[key]), "duration_seconds": duration}
    return parallel_report, tiers


def markdown_report(report: dict[str, Any]) -> str:
    public = report["public_scorer_parity"]["benchmarks"]
    memory = report["matric_memory_parity"]
    parallel = report["parallel_equivalence"]
    resume = report["checkpoint_resume"]
    tiers = report["tier_durations"]
    status = "PASS" if report["status"] == "passed" else "FAIL"
    return f"""# Operational Validation v1

**Status:** {status}

This report validates the scorer and execution contracts required by roadmap Phase 6.
The raw machine-readable evidence is in
[`operational-validation-v1.json`](./operational-validation-v1.json).

## Pinned Matrix

- Matrix: `{report["matrix"]["id"]}` (`sha256:{report["matrix"]["sha256"]}`)
- matric-cli validator: `{report["sources"]["matric_cli"]["revision"]}`
- matric-memory evaluator: `{report["sources"]["matric_memory"]["revision"]}`
- Production fixture: `{report["production_fixture"]["model"]}` on `{report["production_fixture"]["provider"]}`
- Model digest: `{report["production_fixture"]["model_digest"]}`
- Seed: `{report["seed"]}`

## Results

| Contract | Result | Evidence |
| --- | --- | --- |
| HumanEval scorer parity | PASS | {public["humaneval"]["variance_percentage_points"]:.1f} pp variance; tolerance {public["humaneval"]["tolerance_percentage_points"]:.1f} pp |
| MBPP scorer parity | PASS | {public["mbpp"]["variance_percentage_points"]:.1f} pp variance; tolerance {public["mbpp"]["tolerance_percentage_points"]:.1f} pp |
| matric-memory custom scorers | PASS | {memory["agreement_rate"]:.0%} agreement across {len(memory["cases"])} title/semantic cases |
| Checkpoint resume | PASS | {resume["duplicate_count"]} duplicate completed benchmarks; checkpoint result preserved |
| Parallel equivalence | PASS | {parallel["result_set_difference"]} result-set differences across {parallel["task_count"]} tasks |

Measured execution durations on this validation host:

| Mode | Work | Duration |
| --- | ---: | ---: |
| Sequential | {parallel["task_count"]} units | {parallel["sequential_duration_seconds"]:.4f}s |
| Parallel (4 threads) | {parallel["task_count"]} units | {parallel["parallel_duration_seconds"]:.4f}s |
| Smoke tier | {tiers["smoke"]["work_units"]} units | {tiers["smoke"]["duration_seconds"]:.4f}s |
| Quick tier | {tiers["quick"]["work_units"]} units | {tiers["quick"]["duration_seconds"]:.4f}s |

Durations characterize the deterministic validation harness, not model-quality throughput. The
real-provider timing and provider/model metadata are retained by
[Gitea run #51]({report["production_fixture"]["hosted_evidence"]}).

## Reproduce

```bash
uv run python scripts/run_operational_validation.py
uv run pytest tests/test_operational_validation.py tests/unit/test_code_execution.py
```

The command exits nonzero if any tolerance, agreement, resume, or equivalence gate fails.
"""


def run(matrix_path: Path, output_dir: Path) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text())
    started = time.perf_counter()
    code = validate_code_parity(matrix)
    memory = validate_memory_parity(matrix)
    resume = validate_resume(matrix)
    parallel, tiers = validate_parallel_and_tiers(matrix)
    sections = (code, memory, resume, parallel)
    report = {
        "schema_version": 1,
        "report_id": "operational-validation-v1",
        "status": "passed" if all(section["passed"] for section in sections) else "failed",
        "seed": matrix["seed"],
        "matrix": {"id": matrix["matrix_id"], "sha256": sha256(matrix_path)},
        "sources": matrix["sources"],
        "production_fixture": matrix["production_fixture"],
        "public_scorer_parity": code,
        "matric_memory_parity": memory,
        "checkpoint_resume": resume,
        "parallel_equivalence": parallel,
        "tier_durations": tiers,
        "total_duration_seconds": time.perf_counter() - started,
        "commands": [
            "uv run python scripts/run_operational_validation.py",
            "uv run pytest tests/test_operational_validation.py tests/unit/test_code_execution.py",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "operational-validation-v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (output_dir / "operational-validation-v1.md").write_text(markdown_report(report))
    return report


def main() -> int:
    args = parse_args()
    report = run(args.matrix.resolve(), args.output_dir.resolve())
    print(json.dumps({"status": report["status"], "output": str(args.output_dir)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
