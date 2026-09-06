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
    scale = offline_full / offline_pilot
    models: dict[str, Any] = {}
    for model in study.models:
        prefix = MODEL_FILES[model.id]
        result_path = args.result_root / f"{prefix}-pilot-offline.jsonl"
        score_path = args.result_root / f"{prefix}-pilot-scores.jsonl"
        repeat_path = args.result_root / f"{prefix}-pilot-scores-repeat.jsonl"
        receipt_path = args.result_root / f"{prefix}-pilot-scores-receipt.json"
        repeat_receipt_path = args.result_root / f"{prefix}-pilot-scores-repeat-receipt.json"
        results = _jsonl(result_path)
        receipt = _json(receipt_path)
        repeat_receipt = _json(repeat_receipt_path)
        if len(results) != offline_pilot:
            raise ValueError(f"{model.id} does not contain {offline_pilot} direct pilot rows")
        if any(row.get("model_id") != model.id for row in results):
            raise ValueError(f"{model.id} result identity mismatch")
        if any(row.get("protocol_sha256") != study.canonical_sha256 for row in results):
            raise ValueError(f"{model.id} protocol hash mismatch")
        if _sha256(score_path) != _sha256(repeat_path):
            raise ValueError(f"{model.id} deterministic score repeat is not byte-identical")
        if receipt.get("scores_sha256") != repeat_receipt.get("scores_sha256"):
            raise ValueError(f"{model.id} score receipts disagree")
        runtime = results[0]["runtime"]
        initialization = float(runtime["initialization_seconds"])
        generation = float(runtime["generation_seconds"])
        publication_metrics = {
            allocation: values
            for allocation, values in receipt["aggregates"].items()
            if values.get("publication_eligible") is True
        }
        models[model.id] = {
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
            "generation_code_revision": runtime["matric_eval_revision"],
            "scoring_code_revision": receipt["scoring_code_revision"],
            "direct_pilot_samples": len(results),
            "prompt_tokens": sum(int(row["prompt_tokens"]) for row in results),
            "completion_tokens": sum(int(row["completion_tokens"]) for row in results),
            "finish_reasons": dict(sorted(Counter(row["finish_reason"] for row in results).items())),
            "initialization_seconds": initialization,
            "generation_seconds": generation,
            "estimated_full_direct_seconds_from_scratch": initialization + generation * scale,
            "pipeline_validation_metrics": publication_metrics,
            "result_sha256": _sha256(result_path),
            "scores_sha256": _sha256(score_path),
        }

    summary = {
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "study_seed": study.seed,
        "status": "direct-pilot-pipeline-validated-agentic-and-judged-lanes-pending",
        "interpretation": "Pilot metrics validate the pipeline and estimate runtime only; they are not confirmatory results.",
        "direct_samples_per_model": {"pilot": offline_pilot, "full": offline_full},
        "full_direct_runtime_estimate_method": "pilot generation wall time multiplied by full/pilot direct sample ratio, plus one cold initialization",
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
