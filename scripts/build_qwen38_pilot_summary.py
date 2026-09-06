#!/usr/bin/env python3
"""Build a content-free pilot timing and pipeline-validation summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from matric_eval.studies import StudyProtocol

MODEL_FILES = {
    "qwen38-27b-source-bf16": "source",
    "qwen38-27b-e03-bf16": "e03",
    "qwen38-27b-pliny-v3-bf16": "pliny",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} must contain JSON objects")
    return rows


def _runtime(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    runtime = rows[0].get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError(f"{label} is missing runtime evidence")
    return runtime


def _validate_turn2(
    *,
    study: StudyProtocol,
    model: Any,
    first_results: list[dict[str, Any]],
    first_result_path: Path,
    turn2_results: list[dict[str, Any]],
    turn2_result_path: Path,
    input_receipt: dict[str, Any],
    input_receipt_path: Path,
    expected_count: int,
) -> dict[str, Any]:
    first_mtbench = [row for row in first_results if row.get("allocation_id") == "mtbench"]
    if len(first_mtbench) != expected_count or len(turn2_results) != expected_count:
        raise ValueError(f"{model.id} does not contain {expected_count} MT-Bench rows per turn")
    first_ids = [row.get("sample_id") for row in first_mtbench]
    turn2_ids = [row.get("sample_id") for row in turn2_results]
    if first_ids != turn2_ids or not all(isinstance(sample_id, str) for sample_id in turn2_ids):
        raise ValueError(f"{model.id} MT-Bench turn order does not match turn 1")
    manifest_sha256 = first_results[0].get("manifest_sha256")
    expected_receipt = {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest_sha256,
        "model_id": model.id,
        "model_source": model.source,
        "model_revision": model.checkpoint_revision,
        "allocation_id": "mtbench",
        "turn": 2,
        "requests": expected_count,
        "first_turn_results_sha256": _sha256(first_result_path),
    }
    if any(input_receipt.get(key) != value for key, value in expected_receipt.items()):
        raise ValueError(f"{model.id} MT-Bench input receipt identity mismatch")
    request_batch_sha256 = input_receipt.get("output_sha256")
    for row in turn2_results:
        expected_identity = {
            "study_id": study.id,
            "protocol_sha256": study.canonical_sha256,
            "manifest_sha256": manifest_sha256,
            "model_id": model.id,
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
            "allocation_id": "mtbench",
        }
        if any(row.get(key) != value for key, value in expected_identity.items()):
            raise ValueError(f"{model.id} MT-Bench turn-2 result identity mismatch")
        sample_id = row["sample_id"]
        if row.get("request_id") != f"mtbench:{sample_id}:turn-2":
            raise ValueError(f"{model.id} MT-Bench turn-2 request identity mismatch")
        if row.get("generation_seed") != study.generation_seed("mtbench", sample_id):
            raise ValueError(f"{model.id} MT-Bench turn-2 generation seed mismatch")
        runtime = row.get("runtime")
        if (
            not isinstance(runtime, dict)
            or runtime.get("request_batch_sha256") != request_batch_sha256
        ):
            raise ValueError(f"{model.id} MT-Bench turn-2 batch hash mismatch")
    return {
        "input_receipt_sha256": _sha256(input_receipt_path),
        "result_sha256": _sha256(turn2_result_path),
        "runtime": _runtime(turn2_results, f"{model.id} MT-Bench turn 2"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    study = StudyProtocol.from_yaml(args.protocol)
    offline_full = sum(
        allocation.full_samples
        for allocation in study.benchmarks
        if allocation.execution_mode == "offline-batch"
    )
    offline_pilot = sum(
        allocation.pilot_samples
        for allocation in study.benchmarks
        if allocation.execution_mode == "offline-batch"
    )
    mtbench = next(allocation for allocation in study.benchmarks if allocation.id == "mtbench")
    first_turn_scale = offline_full / offline_pilot
    second_turn_scale = mtbench.full_samples / mtbench.pilot_samples
    models: dict[str, Any] = {}
    manifest_hashes: set[str] = set()
    for model in study.models:
        prefix = MODEL_FILES[model.id]
        result_path = args.result_root / f"{prefix}-pilot-offline.jsonl"
        score_path = args.result_root / f"{prefix}-pilot-scores.jsonl"
        repeat_path = args.result_root / f"{prefix}-pilot-scores-repeat.jsonl"
        receipt_path = args.result_root / f"{prefix}-pilot-scores-receipt.json"
        repeat_receipt_path = args.result_root / f"{prefix}-pilot-scores-repeat-receipt.json"
        turn2_result_path = args.result_root / f"{prefix}-pilot-mtbench-turn2.jsonl"
        turn2_input_receipt_path = (
            args.result_root / f"{prefix}-pilot-mtbench-turn2-input-receipt.json"
        )
        results = _jsonl(result_path)
        turn2_results = _jsonl(turn2_result_path)
        turn2_input_receipt = _json(turn2_input_receipt_path)
        receipt = _json(receipt_path)
        repeat_receipt = _json(repeat_receipt_path)
        manifest_sha256 = results[0].get("manifest_sha256")
        if (
            not isinstance(manifest_sha256, str)
            or len(manifest_sha256) != 64
            or any(row.get("manifest_sha256") != manifest_sha256 for row in results)
            or receipt.get("manifest_sha256") != manifest_sha256
            or repeat_receipt.get("manifest_sha256") != manifest_sha256
        ):
            raise ValueError(f"{model.id} manifest identity mismatch")
        manifest_hashes.add(manifest_sha256)
        if len(results) != offline_pilot:
            raise ValueError(f"{model.id} does not contain {offline_pilot} direct pilot rows")
        if any(row.get("model_id") != model.id for row in results):
            raise ValueError(f"{model.id} result identity mismatch")
        if any(row.get("protocol_sha256") != study.canonical_sha256 for row in results):
            raise ValueError(f"{model.id} protocol hash mismatch")
        turn2 = _validate_turn2(
            study=study,
            model=model,
            first_results=results,
            first_result_path=result_path,
            turn2_results=turn2_results,
            turn2_result_path=turn2_result_path,
            input_receipt=turn2_input_receipt,
            input_receipt_path=turn2_input_receipt_path,
            expected_count=mtbench.pilot_samples,
        )
        if _sha256(score_path) != _sha256(repeat_path):
            raise ValueError(f"{model.id} deterministic score repeat is not byte-identical")
        if receipt.get("scores_sha256") != repeat_receipt.get("scores_sha256"):
            raise ValueError(f"{model.id} score receipts disagree")
        runtime = _runtime(results, f"{model.id} direct turn 1")
        turn2_runtime = turn2["runtime"]
        initialization = float(runtime["initialization_seconds"])
        generation = float(runtime["generation_seconds"])
        turn2_initialization = float(turn2_runtime["initialization_seconds"])
        turn2_generation = float(turn2_runtime["generation_seconds"])
        publication_metrics = {
            allocation: values
            for allocation, values in receipt["aggregates"].items()
            if values.get("publication_eligible") is True
        }
        scoring_seconds = float(receipt["scoring_seconds"])
        repeat_scoring_seconds = float(repeat_receipt["scoring_seconds"])
        if scoring_seconds < 0 or repeat_scoring_seconds < 0:
            raise ValueError(f"{model.id} scoring durations must be non-negative")
        models[model.id] = {
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
            "generation_code_revision": runtime["matric_eval_revision"],
            "scoring_code_revision": receipt["scoring_code_revision"],
            "direct_pilot_samples": len(results),
            "direct_pilot_generation_calls": len(results) + len(turn2_results),
            "prompt_tokens": sum(int(row["prompt_tokens"]) for row in [*results, *turn2_results]),
            "completion_tokens": sum(
                int(row["completion_tokens"]) for row in [*results, *turn2_results]
            ),
            "finish_reasons": dict(
                sorted(Counter(row["finish_reason"] for row in [*results, *turn2_results]).items())
            ),
            "first_turn_initialization_seconds": initialization,
            "first_turn_generation_seconds": generation,
            "mtbench_turn2_initialization_seconds": turn2_initialization,
            "mtbench_turn2_generation_seconds": turn2_generation,
            "total_initialization_seconds": initialization + turn2_initialization,
            "total_generation_seconds": generation + turn2_generation,
            "scoring_seconds": scoring_seconds,
            "repeat_scoring_seconds": repeat_scoring_seconds,
            "total_deterministic_scoring_seconds": scoring_seconds + repeat_scoring_seconds,
            "estimated_full_direct_seconds_from_scratch": (
                initialization
                + generation * first_turn_scale
                + turn2_initialization
                + turn2_generation * second_turn_scale
            ),
            "pipeline_validation_metrics": publication_metrics,
            "result_sha256": _sha256(result_path),
            "mtbench_turn2_result_sha256": turn2["result_sha256"],
            "mtbench_turn2_input_receipt_sha256": turn2["input_receipt_sha256"],
            "scores_sha256": _sha256(score_path),
        }

    if len(manifest_hashes) != 1:
        raise ValueError("direct pilot models do not share one manifest")

    summary = {
        "schema_version": "2",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "study_seed": study.seed,
        "manifest_sha256": next(iter(manifest_hashes)),
        "status": "direct-pilot-pipeline-validated-agentic-and-judged-lanes-pending",
        "interpretation": "Pilot metrics validate the pipeline and estimate runtime only; they are not confirmatory results.",
        "direct_samples_per_model": {"pilot": offline_pilot, "full": offline_full},
        "direct_generation_calls_per_model": {
            "pilot": offline_pilot + mtbench.pilot_samples,
            "full": offline_full + mtbench.full_samples,
        },
        "full_direct_runtime_estimate_method": "first-turn and MT-Bench second-turn pilot generation wall times scaled separately by their full/pilot ratios, plus both observed cold initializations",
        "models": models,
    }
    if args.output.exists():
        raise ValueError(f"refusing to overwrite pilot summary: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    args.output.chmod(0o644)
    print(json.dumps({"output": str(args.output), "sha256": _sha256(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
