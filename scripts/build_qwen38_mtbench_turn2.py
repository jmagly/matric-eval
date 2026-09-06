#!/usr/bin/env python3
"""Materialize manifest-locked MT-Bench second-turn requests from first-turn evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from matric_eval.studies import (
    StudyBatchRequest,
    StudyProtocol,
    load_batch_requests,
    validate_batch_contract,
)

ALLOCATION_ID = "mtbench"
JsonObject = dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _load_objects(path: Path, label: str) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{label} line {line_number} must contain a JSON object")
        rows.append(payload)
    if not rows:
        raise ValueError(f"{label} must contain at least one row")
    return rows


def _git_revision(checkout: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    revision = result.stdout.strip()
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise RuntimeError(f"{checkout} did not report a full lowercase Git revision")
    return revision


def _write_json(path: Path, payload: JsonObject) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite MT-Bench evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return _sha256_file(path)


def _write_jsonl(path: Path, rows: list[JsonObject]) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite MT-Bench evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return _sha256_file(path)


def _mtbench_questions(path: Path) -> dict[str, JsonObject]:
    questions: dict[str, JsonObject] = {}
    for row in _load_objects(path, "MT-Bench questions"):
        question_id = row.get("question_id")
        turns = row.get("turns")
        if not isinstance(question_id, (str, int)) or isinstance(question_id, bool):
            raise ValueError("MT-Bench question_id must be a string or integer")
        sample_id = str(question_id)
        if sample_id in questions:
            raise ValueError(f"MT-Bench contains duplicate question_id {sample_id}")
        if (
            not isinstance(turns, list)
            or len(turns) != 2
            or not all(isinstance(turn, str) and turn for turn in turns)
        ):
            raise ValueError(f"MT-Bench question {sample_id} must contain exactly two turns")
        questions[sample_id] = row
    return questions


def build_turn2(args: argparse.Namespace) -> JsonObject:
    if args.output.exists() or args.receipt.exists():
        existing = args.output if args.output.exists() else args.receipt
        raise ValueError(f"refusing to overwrite MT-Bench evidence: {existing}")
    study = StudyProtocol.from_yaml(args.protocol)
    manifest = _load_object(args.manifest, "study manifest")
    requests = load_batch_requests(args.first_turn_requests)
    validate_batch_contract(study, manifest, requests)
    model = next((candidate for candidate in study.models if candidate.id == args.model_id), None)
    if model is None:
        raise ValueError(f"unknown study model id: {args.model_id}")

    allocation = next(
        (candidate for candidate in study.benchmarks if candidate.id == ALLOCATION_ID), None
    )
    if allocation is None or allocation.execution_mode != "offline-batch":
        raise ValueError("protocol must contain an offline-batch MT-Bench allocation")
    fastchat_revision = _git_revision(args.fastchat_checkout)
    if fastchat_revision != allocation.dataset_revision:
        raise ValueError("FastChat checkout does not match the protocol-pinned revision")

    results = _load_objects(args.first_turn_results, "first-turn results")
    if len(results) != len(requests):
        raise ValueError("first-turn results must contain exactly one row per request")
    request_sha256 = _sha256_file(args.first_turn_requests)
    result_by_id: dict[str, JsonObject] = {}
    for request, result in zip(requests, results, strict=True):
        if result.get("request_id") != request.request_id:
            raise ValueError("first-turn result order does not match the request batch")
        expected_identity = {
            "study_id": study.id,
            "protocol_sha256": study.canonical_sha256,
            "manifest_sha256": manifest.get("manifest_sha256"),
            "model_id": model.id,
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
            "allocation_id": request.allocation_id,
            "sample_id": request.sample_id,
            "generation_seed": study.generation_seed(request.allocation_id, request.sample_id),
        }
        if any(result.get(key) != value for key, value in expected_identity.items()):
            raise ValueError(f"first-turn result identity mismatch for {request.request_id}")
        runtime = result.get("runtime")
        if not isinstance(runtime, dict) or runtime.get("request_batch_sha256") != request_sha256:
            raise ValueError("first-turn result does not attest the supplied request batch")
        completion = result.get("completion")
        if not isinstance(completion, str):
            raise ValueError(f"first-turn result {request.request_id} has no string completion")
        if request.request_id in result_by_id:
            raise ValueError(f"first-turn results repeat request_id {request.request_id}")
        result_by_id[request.request_id] = result

    questions_path = args.fastchat_checkout / "fastchat/llm_judge/data/mt_bench/question.jsonl"
    questions = _mtbench_questions(questions_path)
    mtbench_requests = [request for request in requests if request.allocation_id == ALLOCATION_ID]
    if not mtbench_requests:
        raise ValueError("first-turn request batch does not contain MT-Bench")

    turn2_rows: list[JsonObject] = []
    parsed_turn2: list[StudyBatchRequest] = []
    for line_number, request in enumerate(mtbench_requests, start=1):
        question = questions.get(request.sample_id)
        if question is None:
            raise ValueError(f"pinned MT-Bench data is missing sample {request.sample_id}")
        turns = question["turns"]
        if request.messages[-1] != {"role": "user", "content": turns[0]}:
            raise ValueError(
                f"first-turn prompt does not match pinned MT-Bench sample {request.sample_id}"
            )
        first_result = result_by_id[request.request_id]
        row: JsonObject = {
            "request_id": f"{ALLOCATION_ID}:{request.sample_id}:turn-2",
            "allocation_id": ALLOCATION_ID,
            "sample_id": request.sample_id,
            "messages": [
                *[dict(message) for message in request.messages],
                {"role": "assistant", "content": first_result["completion"]},
                {"role": "user", "content": turns[1]},
            ],
        }
        turn2_rows.append(row)
        parsed_turn2.append(StudyBatchRequest.from_dict(row, line_number))
    validate_batch_contract(study, manifest, parsed_turn2)

    output_sha256 = _write_jsonl(args.output, turn2_rows)
    receipt: JsonObject = {
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest.get("manifest_sha256"),
        "cohort": manifest.get("cohort"),
        "model_id": model.id,
        "model_source": model.source,
        "model_revision": model.checkpoint_revision,
        "allocation_id": ALLOCATION_ID,
        "turn": 2,
        "requests": len(turn2_rows),
        "ordered_sample_ids_sha256": hashlib.sha256(
            "\n".join(request.sample_id for request in mtbench_requests).encode()
        ).hexdigest(),
        "fastchat_revision": fastchat_revision,
        "first_turn_requests_sha256": request_sha256,
        "first_turn_results_sha256": _sha256_file(args.first_turn_results),
        "output_sha256": output_sha256,
        "matric_eval_revision": _git_revision(Path(__file__).resolve().parents[1]),
    }
    _write_json(args.receipt, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--first-turn-requests", type=Path, required=True)
    parser.add_argument("--first-turn-results", type=Path, required=True)
    parser.add_argument("--fastchat-checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_turn2(args)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
