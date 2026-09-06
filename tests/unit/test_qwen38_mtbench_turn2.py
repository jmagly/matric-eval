"""Tests for manifest-locked MT-Bench second-turn materialization."""

from __future__ import annotations

import argparse
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
SCRIPT = ROOT / "scripts/build_qwen38_mtbench_turn2.py"
SPEC = importlib.util.spec_from_file_location("qwen38_mtbench_turn2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
turn2_builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = turn2_builder
SPEC.loader.exec_module(turn2_builder)


def _catalog(study: StudyProtocol) -> dict[str, list[object]]:
    catalog: dict[str, list[object]] = {}
    for allocation in study.benchmarks:
        if allocation.id == "mtbench":
            catalog[allocation.id] = [str(question_id) for question_id in range(81, 161)]
            continue
        ids = [f"{allocation.id}-{index:05d}" for index in range(allocation.available_samples)]
        if allocation.selection_strategy == "sha256-stratified-round-robin-v1":
            catalog[allocation.id] = [
                {"id": sample_id, "stratum": f"stratum-{index % 5}"}
                for index, sample_id in enumerate(ids)
            ]
        else:
            catalog[allocation.id] = ids
    return catalog


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> tuple[argparse.Namespace, list[dict[str, Any]], StudyProtocol]:
    study = StudyProtocol.from_yaml(PROTOCOL)
    manifest = study.selection_manifest(_catalog(study), "pilot")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    selected_mtbench = next(
        allocation["selected_ids"]
        for allocation in manifest["allocations"]
        if allocation["allocation_id"] == "mtbench"
    )

    fastchat = tmp_path / "fastchat"
    questions_path = fastchat / "fastchat/llm_judge/data/mt_bench/question.jsonl"
    questions_path.parent.mkdir(parents=True)
    questions = [
        {
            "question_id": int(sample_id),
            "category": "writing",
            "turns": [f"first {sample_id}", f"second {sample_id}"],
        }
        for sample_id in selected_mtbench
    ]
    _write_jsonl(questions_path, questions)
    question_by_id = {str(row["question_id"]): row for row in questions}

    offline_ids = {
        allocation.id
        for allocation in study.benchmarks
        if allocation.execution_mode == "offline-batch"
    }
    requests: list[dict[str, Any]] = []
    for allocation in manifest["allocations"]:
        allocation_id = allocation["allocation_id"]
        if allocation_id not in offline_ids:
            continue
        for sample_id in allocation["selected_ids"]:
            prompt = (
                question_by_id[sample_id]["turns"][0]
                if allocation_id == "mtbench"
                else f"prompt {allocation_id} {sample_id}"
            )
            requests.append(
                {
                    "request_id": f"{allocation_id}:{sample_id}:turn-1",
                    "allocation_id": allocation_id,
                    "sample_id": sample_id,
                    "messages": [{"role": "user", "content": prompt}],
                }
            )
    requests_path = tmp_path / "requests.jsonl"
    _write_jsonl(requests_path, requests)
    request_sha256 = hashlib.sha256(requests_path.read_bytes()).hexdigest()
    model = study.models[0]
    results = [
        {
            "schema_version": "1",
            "study_id": study.id,
            "protocol_sha256": study.canonical_sha256,
            "manifest_sha256": manifest["manifest_sha256"],
            "model_id": model.id,
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
            "request_id": request["request_id"],
            "allocation_id": request["allocation_id"],
            "sample_id": request["sample_id"],
            "generation_seed": study.generation_seed(
                request["allocation_id"], request["sample_id"]
            ),
            "completion": f"completion {request['sample_id']}",
            "runtime": {"request_batch_sha256": request_sha256},
        }
        for request in requests
    ]
    results_path = tmp_path / "results.jsonl"
    _write_jsonl(results_path, results)
    args = argparse.Namespace(
        protocol=PROTOCOL,
        manifest=manifest_path,
        model_id=model.id,
        first_turn_requests=requests_path,
        first_turn_results=results_path,
        fastchat_checkout=fastchat,
        output=tmp_path / "turn2.jsonl",
        receipt=tmp_path / "turn2-receipt.json",
    )
    return args, questions, study


def test_builds_private_ordered_turn2_and_content_free_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, questions, study = _fixture(tmp_path)
    mtbench_revision = next(
        allocation.dataset_revision for allocation in study.benchmarks if allocation.id == "mtbench"
    )
    monkeypatch.setattr(
        turn2_builder,
        "_git_revision",
        lambda path: mtbench_revision if path == args.fastchat_checkout else "a" * 40,
    )

    receipt = turn2_builder.build_turn2(args)

    rows = [json.loads(line) for line in args.output.read_text().splitlines()]
    assert len(rows) == 5
    assert [row["sample_id"] for row in rows] == [str(row["question_id"]) for row in questions]
    assert rows[0]["request_id"].endswith(":turn-2")
    assert [message["role"] for message in rows[0]["messages"]] == [
        "user",
        "assistant",
        "user",
    ]
    assert rows[0]["messages"][2]["content"] == questions[0]["turns"][1]
    assert receipt["requests"] == 5
    assert receipt["turn"] == 2
    assert "completion" not in json.dumps(receipt)
    assert receipt["output_sha256"] == hashlib.sha256(args.output.read_bytes()).hexdigest()
    assert args.output.stat().st_mode & 0o777 == 0o600
    assert args.receipt.stat().st_mode & 0o777 == 0o600


def test_rejects_result_batch_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _questions, study = _fixture(tmp_path)
    rows = [json.loads(line) for line in args.first_turn_results.read_text().splitlines()]
    rows[0]["runtime"]["request_batch_sha256"] = "0" * 64
    _write_jsonl(args.first_turn_results, rows)
    mtbench_revision = next(
        allocation.dataset_revision for allocation in study.benchmarks if allocation.id == "mtbench"
    )
    monkeypatch.setattr(turn2_builder, "_git_revision", lambda _path: mtbench_revision)

    with pytest.raises(ValueError, match="does not attest"):
        turn2_builder.build_turn2(args)


def test_refuses_to_overwrite_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _questions, study = _fixture(tmp_path)
    args.output.write_text("existing", encoding="utf-8")
    mtbench_revision = next(
        allocation.dataset_revision for allocation in study.benchmarks if allocation.id == "mtbench"
    )
    monkeypatch.setattr(turn2_builder, "_git_revision", lambda _path: mtbench_revision)

    with pytest.raises(ValueError, match="refusing to overwrite"):
        turn2_builder.build_turn2(args)
