"""Tests for the locked Qwen3.8 external dual-judge runner."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
PLAN = ROOT / "studies/qwen38-obliteration-2026-09/judge-plan.yaml"
SCRIPT = ROOT / "scripts/run_qwen38_judges.py"
SPEC = importlib.util.spec_from_file_location("qwen38_judge_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _catalog(study: StudyProtocol) -> dict[str, list[object]]:
    catalog: dict[str, list[object]] = {}
    for allocation in study.benchmarks:
        ids = [f"{allocation.id}-{index:05d}" for index in range(allocation.available_samples)]
        if allocation.selection_strategy == "sha256-stratified-round-robin-v1":
            catalog[allocation.id] = [
                {"id": sample_id, "stratum": f"stratum-{index % 5}"}
                for index, sample_id in enumerate(ids)
            ]
        else:
            catalog[allocation.id] = ids
    return catalog


def _study_plan() -> tuple[StudyProtocol, dict[str, Any]]:
    study = StudyProtocol.from_yaml(PROTOCOL)
    plan = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    assert isinstance(plan, dict)
    return study, plan


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_locked_plan_and_declared_disagreement_thresholds() -> None:
    study, plan = _study_plan()
    runner.validate_plan(plan, study, "pilot")

    assert runner.judges_disagree(
        "refusal_three_way",
        {"behavior": "full_refusal", "rationale": "a"},
        {"behavior": "partial_refusal", "rationale": "b"},
    )
    assert not runner.judges_disagree(
        "strongreject",
        {"refusal": 0, "convincingness": 5, "specificity": 4, "rationale": "a"},
        {"refusal": 0, "convincingness": 4, "specificity": 3, "rationale": "b"},
    )
    assert runner.judges_disagree(
        "mtbench",
        {"turn_1_score": 8, "turn_2_score": 9},
        {"turn_1_score": 6, "turn_2_score": 9},
    )

    changed = json.loads(json.dumps(plan))
    changed["judges"]["secondary"] = changed["judges"]["primary"]
    with pytest.raises(ValueError, match="primary and secondary"):
        runner.validate_plan(changed, study, "pilot")


def test_builds_resumable_content_free_dual_judge_bundle(tmp_path: Path) -> None:
    study, plan = _study_plan()
    manifest = study.selection_manifest(_catalog(study), "pilot")
    selected = {
        allocation["allocation_id"]: allocation["selected_ids"]
        for allocation in manifest["allocations"]
    }
    model = study.models[0]
    items = [
        runner.JudgeItem(
            model_id=model.id,
            allocation_id="xstest-safe",
            sample_id=selected["xstest-safe"][0],
            prompt="private refusal prompt marker",
            response="private refusal response marker",
        ),
        runner.JudgeItem(
            model_id=model.id,
            allocation_id="strongreject-harmful",
            sample_id=selected["strongreject-harmful"][0],
            prompt="private harmful prompt marker",
            response="private harmful response marker",
        ),
        runner.JudgeItem(
            model_id=model.id,
            allocation_id="mtbench",
            sample_id=selected["mtbench"][0],
            prompt="private first question marker",
            response="private first response marker",
            second_prompt="private second question marker",
            second_response="private second response marker",
        ),
    ]
    calls: list[tuple[str, str]] = []

    def fake_call(
        model_name: str,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> Any:
        calls.append((model_name, input_text))
        properties = schema["properties"]
        adjudicating = instructions.startswith("Independently apply")
        if "behavior" in properties:
            behavior = (
                "full_compliance"
                if adjudicating
                else ("full_refusal" if "gpt-5.4" in model_name else "partial_refusal")
            )
            value = {"behavior": behavior, "rationale": "brief"}
        elif "refusal" in properties:
            value = {
                "refusal": 0,
                "convincingness": 5 if "gpt-5.4" in model_name else 4,
                "specificity": 5 if "gpt-5.4" in model_name else 4,
                "rationale": "brief",
            }
        else:
            value = {
                "turn_1_score": 8 if "gpt-5.4" in model_name else 7,
                "turn_2_score": 7 if "gpt-5.4" in model_name else 8,
                "turn_1_rationale": "brief",
                "turn_2_rationale": "brief",
            }
        return runner.CallResult(
            value=value,
            response_id=f"response-{len(calls)}",
            response_model=model_name,
            usage={"input_tokens": 10, "output_tokens": 4},
            seconds=0.25,
            attempts=1,
        )

    journal = tmp_path / "journal.jsonl"
    kwargs = {
        "study": study,
        "manifest": manifest,
        "cohort": "pilot",
        "plan": plan,
        "plan_sha256": "a" * 64,
        "items": items,
        "artifacts": {},
        "journal_path": journal,
        "call": fake_call,
        "code_revision": "b" * 40,
    }
    bundle = runner.build_bundle(**kwargs)

    assert len(calls) == 7
    assert bundle["schema_version"] == "2"
    assert bundle["runtime"] == {
        "primary_calls": 3,
        "secondary_calls": 3,
        "adjudicator_calls": 1,
        "primary_seconds": 0.75,
        "secondary_seconds": 0.75,
        "adjudication_seconds": 0.25,
        "retries": 0,
    }
    outcomes = {item["allocation_id"]: item for item in bundle["outcomes"]}
    assert outcomes["xstest-safe"]["judges_disagreed"] is True
    assert outcomes["xstest-safe"]["adjudicated"] is True
    assert outcomes["xstest-safe"]["value"] == 0.0
    assert outcomes["strongreject-harmful"]["value"] == pytest.approx(0.875)
    assert outcomes["mtbench"]["value"] == pytest.approx(0.75)
    serialized = json.dumps(bundle)
    assert "private refusal prompt marker" not in serialized
    assert "private harmful response marker" not in serialized
    assert journal.stat().st_mode & 0o777 == 0o600

    def unexpected_call(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("resume should reuse every sealed journal record")

    resumed = runner.build_bundle(**{**kwargs, "call": unexpected_call})
    assert resumed == bundle


def test_api_key_is_read_once_from_inherited_descriptor() -> None:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"test-secret-value\n")
    os.close(write_fd)

    assert runner._read_secret_fd(read_fd) == "test-secret-value"
    with pytest.raises(OSError):
        os.read(read_fd, 1)
    with pytest.raises(ValueError, match="3 or greater"):
        runner._read_secret_fd(0)


def test_load_items_verifies_generation_and_request_batch_hashes(tmp_path: Path) -> None:
    study, _plan = _study_plan()
    manifest = study.selection_manifest(_catalog(study), "pilot")
    (tmp_path / "pilot-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    selected = {
        allocation["allocation_id"]: allocation["selected_ids"]
        for allocation in manifest["allocations"]
    }
    offline_allocations = [
        allocation
        for allocation in study.benchmarks
        if allocation.execution_mode == "offline-batch"
    ]
    requests = [
        {
            "request_id": f"{allocation.id}:{sample_id}:turn-1",
            "allocation_id": allocation.id,
            "sample_id": sample_id,
            "messages": [{"role": "user", "content": f"question {sample_id}"}],
        }
        for allocation in offline_allocations
        for sample_id in selected[allocation.id]
    ]
    scoring = [
        {
            "request_id": request["request_id"],
            "allocation_id": request["allocation_id"],
            "sample_id": request["sample_id"],
        }
        for request in requests
    ]
    request_path = tmp_path / "pilot-inputs/offline-requests.jsonl"
    _write_jsonl(request_path, requests)
    _write_jsonl(tmp_path / "pilot-inputs/offline-scoring.jsonl", scoring)
    request_sha256 = hashlib.sha256(request_path.read_bytes()).hexdigest()
    request_index = {request["request_id"]: request for request in requests}
    for model in study.models:
        prefix = runner.MODEL_FILES[model.id]
        results = [
            {
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
                "completion": f"answer {request['sample_id']}",
                "runtime": {"request_batch_sha256": request_sha256},
            }
            for request in requests
        ]
        _write_jsonl(tmp_path / f"{prefix}-pilot-offline.jsonl", results)
        result_index = {result["request_id"]: result for result in results}
        turn2_requests = []
        for sample_id in selected["mtbench"]:
            first_id = f"mtbench:{sample_id}:turn-1"
            turn2_requests.append(
                {
                    "request_id": f"mtbench:{sample_id}:turn-2",
                    "allocation_id": "mtbench",
                    "sample_id": sample_id,
                    "messages": [
                        *request_index[first_id]["messages"],
                        {"role": "assistant", "content": result_index[first_id]["completion"]},
                        {"role": "user", "content": f"follow-up {sample_id}"},
                    ],
                }
            )
        turn2_request_path = tmp_path / f"{prefix}-pilot-mtbench-turn2-requests.jsonl"
        _write_jsonl(turn2_request_path, turn2_requests)
        turn2_sha256 = hashlib.sha256(turn2_request_path.read_bytes()).hexdigest()
        turn2_results = [
            {
                "study_id": study.id,
                "protocol_sha256": study.canonical_sha256,
                "manifest_sha256": manifest["manifest_sha256"],
                "model_id": model.id,
                "model_source": model.source,
                "model_revision": model.checkpoint_revision,
                "request_id": request["request_id"],
                "allocation_id": "mtbench",
                "sample_id": request["sample_id"],
                "generation_seed": study.generation_seed("mtbench", request["sample_id"]),
                "completion": f"follow-up answer {request['sample_id']}",
                "runtime": {"request_batch_sha256": turn2_sha256},
            }
            for request in turn2_requests
        ]
        _write_jsonl(tmp_path / f"{prefix}-pilot-mtbench-turn2.jsonl", turn2_results)

    items, artifacts = runner.load_items(
        study=study,
        manifest=manifest,
        cohort="pilot",
        result_root=tmp_path,
    )
    assert len(items) == 135
    assert set(artifacts["models"]) == {model.id for model in study.models}

    source_path = tmp_path / "source-pilot-offline.jsonl"
    changed = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines()]
    changed[0]["runtime"]["request_batch_sha256"] = "0" * 64
    _write_jsonl(source_path, changed)
    with pytest.raises(ValueError, match="does not attest"):
        runner.load_items(
            study=study,
            manifest=manifest,
            cohort="pilot",
            result_root=tmp_path,
        )
