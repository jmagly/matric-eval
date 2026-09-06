"""Tests for complete direct-pilot accounting in the Qwen3.8 study summary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
SCRIPT = ROOT / "scripts/build_qwen38_pilot_summary.py"
SPEC = importlib.util.spec_from_file_location("qwen38_pilot_summary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
pilot_summary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pilot_summary
SPEC.loader.exec_module(pilot_summary)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _fixture(
    tmp_path: Path,
) -> tuple[StudyProtocol, Any, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    study = StudyProtocol.from_yaml(PROTOCOL)
    model = study.models[0]
    manifest_sha256 = "b" * 64
    request_batch_sha256 = "c" * 64
    sample_ids = [str(question_id) for question_id in range(81, 86)]
    first_results = [
        {
            "manifest_sha256": manifest_sha256,
            "allocation_id": "mtbench",
            "sample_id": sample_id,
        }
        for sample_id in sample_ids
    ]
    first_result_path = tmp_path / "first.jsonl"
    _write_jsonl(first_result_path, first_results)
    turn2_results = [
        {
            "study_id": study.id,
            "protocol_sha256": study.canonical_sha256,
            "manifest_sha256": manifest_sha256,
            "model_id": model.id,
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
            "request_id": f"mtbench:{sample_id}:turn-2",
            "allocation_id": "mtbench",
            "sample_id": sample_id,
            "generation_seed": study.generation_seed("mtbench", sample_id),
            "runtime": {
                "request_batch_sha256": request_batch_sha256,
                "initialization_seconds": 10,
                "generation_seconds": 20,
            },
        }
        for sample_id in sample_ids
    ]
    turn2_result_path = tmp_path / "turn2.jsonl"
    _write_jsonl(turn2_result_path, turn2_results)
    receipt = {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest_sha256,
        "model_id": model.id,
        "model_source": model.source,
        "model_revision": model.checkpoint_revision,
        "allocation_id": "mtbench",
        "turn": 2,
        "requests": 5,
        "first_turn_results_sha256": hashlib.sha256(first_result_path.read_bytes()).hexdigest(),
        "output_sha256": request_batch_sha256,
    }
    return study, model, first_results, turn2_results, receipt


def test_validates_turn2_lineage_and_runtime(tmp_path: Path) -> None:
    study, model, first_results, turn2_results, receipt = _fixture(tmp_path)
    first_result_path = tmp_path / "first.jsonl"
    turn2_result_path = tmp_path / "turn2.jsonl"
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    evidence = pilot_summary._validate_turn2(
        study=study,
        model=model,
        first_results=first_results,
        first_result_path=first_result_path,
        turn2_results=turn2_results,
        turn2_result_path=turn2_result_path,
        input_receipt=receipt,
        input_receipt_path=receipt_path,
        expected_count=5,
    )

    assert evidence["runtime"]["generation_seconds"] == 20
    assert evidence["result_sha256"] == hashlib.sha256(turn2_result_path.read_bytes()).hexdigest()
    assert evidence["input_receipt_sha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest()


def test_rejects_turn2_batch_hash_drift(tmp_path: Path) -> None:
    study, model, first_results, turn2_results, receipt = _fixture(tmp_path)
    first_result_path = tmp_path / "first.jsonl"
    turn2_result_path = tmp_path / "turn2.jsonl"
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    turn2_results[0]["runtime"]["request_batch_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="batch hash mismatch"):
        pilot_summary._validate_turn2(
            study=study,
            model=model,
            first_results=first_results,
            first_result_path=first_result_path,
            turn2_results=turn2_results,
            turn2_result_path=turn2_result_path,
            input_receipt=receipt,
            input_receipt_path=receipt_path,
            expected_count=5,
        )
