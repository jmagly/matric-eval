"""Tests for complete Qwen3.8 pilot runtime and artifact accounting."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from matric_eval.studies import GpuAllocation, StudyProtocol
from matric_eval.studies.batch import parallelism_attestation
from matric_eval.studies.gpu import GpuExecutionBinding

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
SCRIPT = ROOT / "scripts/build_qwen38_complete_pilot_summary.py"
SPEC = importlib.util.spec_from_file_location("qwen38_complete_pilot_summary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


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


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(
    tmp_path: Path,
) -> tuple[StudyProtocol, dict[str, Any], dict[str, Any], dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    study = StudyProtocol.from_yaml(PROTOCOL)
    gpu_uuid = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    binding = GpuExecutionBinding(GpuAllocation((gpu_uuid,), 75_000), study.parallelism_profile)
    parallelism = parallelism_attestation(
        binding,
        tensor_parallel_size=1,
        pipeline_parallel_size=1,
        visible_gpu_uuids=(gpu_uuid,),
    )
    manifest = study.selection_manifest(_catalog(study), "pilot")
    selected = {
        allocation["allocation_id"]: allocation["selected_ids"]
        for allocation in manifest["allocations"]
    }
    direct = {
        "schema_version": "2",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest["manifest_sha256"],
        "study_seed": study.seed,
        "status": "direct-pilot-pipeline-validated-agentic-and-judged-lanes-pending",
        "models": {
            model.id: {
                "total_initialization_seconds": 20.0,
                "total_generation_seconds": 100.0,
                "total_deterministic_scoring_seconds": 4.0,
                "estimated_full_direct_seconds_from_scratch": 1200.0,
                "parallelism": parallelism,
            }
            for model in study.models
        },
    }
    for model in study.models:
        identity = {
            "schema_version": "1",
            "study_id": study.id,
            "protocol_sha256": study.canonical_sha256,
            "manifest_sha256": manifest["manifest_sha256"],
            "model_id": model.id,
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
        }
        prefix = builder.MODEL_FILES[model.id]
        _write(
            tmp_path / f"{prefix}-pilot-bfcl-receipt.json",
            {
                **identity,
                "scored_ids": selected["bfcl-v4-agentic"],
                "runner_cases_including_dependencies": 30,
                "generation_seconds": 50.0,
                "evaluation_seconds": 5.0,
            },
        )
        _write(
            tmp_path / f"{prefix}-pilot-tau-receipt.json",
            {
                **identity,
                "scored_results": [
                    {"canonical_id": sample_id} for sample_id in selected["tau3-bench"]
                ],
                "scored_samples": len(selected["tau3-bench"]),
                "execution_seconds": 70.0,
                "reward_count": len(selected["tau3-bench"]),
                "termination_counts": {"stop": len(selected["tau3-bench"])},
            },
        )
        _write(
            tmp_path / f"{prefix}-pilot-terminal-receipt.json",
            {
                **identity,
                "scored_results": [
                    {"canonical_id": sample_id} for sample_id in selected["terminal-bench-2.1"]
                ],
                "scored_samples": len(selected["terminal-bench-2.1"]),
                "execution_seconds": 80.0,
                "primary_reward_count": len(selected["terminal-bench-2.1"]),
                "exception_counts": {},
            },
        )
    outcomes = [
        {
            "model_id": model.id,
            "allocation_id": allocation.id,
            "sample_id": sample_id,
            "status": "observed",
            "value": 0.5,
            "judges_disagreed": False,
            "adjudicated": False,
        }
        for model in study.models
        for allocation in study.benchmarks
        if allocation.id in builder.JUDGED_ALLOCATIONS
        for sample_id in selected[allocation.id]
    ]
    judge = {
        "schema_version": "2",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest["manifest_sha256"],
        "cohort": "pilot",
        "judge_plan_sha256": "d" * 64,
        "judges": {
            "primary": {
                "provider": "provider-a",
                "model": "judge-a",
                "snapshot": "judge-a-2026-09-01",
            },
            "secondary": {
                "provider": "provider-b",
                "model": "judge-b",
                "snapshot": "judge-b-2026-09-01",
            },
            "adjudicator": {
                "provider": "provider-c",
                "model": "judge-c",
                "snapshot": "judge-c-2026-09-01",
            },
        },
        "controls": {
            "blinded_model_labels": True,
            "order_randomized": True,
            "target_models_may_not_judge": True,
            "first_pass_judges_per_outcome": 2,
            "first_pass_independent": True,
            "disagreement_policy": "adjudicate-all",
        },
        "runtime": {
            "primary_calls": len(outcomes),
            "secondary_calls": len(outcomes),
            "adjudicator_calls": 0,
            "retries": 0,
            "primary_seconds": 90.0,
            "secondary_seconds": 80.0,
            "adjudication_seconds": 0.0,
        },
        "outcomes": outcomes,
    }
    return study, manifest, direct, judge


def test_builds_complete_content_free_runtime_summary(tmp_path: Path) -> None:
    study, manifest, direct, judge = _fixture(tmp_path)

    result = builder.build_summary(
        study=study,
        manifest=manifest,
        direct=direct,
        result_root=tmp_path,
        judge_bundle=judge,
        judge_bundle_sha256="a" * 64,
        code_revision="b" * 40,
    )

    assert result["status"] == "complete"
    assert result["scale_gate"]["decision"] == "go"
    assert result["scale_gate"]["incomplete_tau_runtime_models"] == []
    assert result["manifest_sha256"] == manifest["manifest_sha256"]
    assert result["judge"]["outcomes"] == 135
    assert result["runtime_totals"] == {
        "direct_initialization_seconds": 60.0,
        "direct_generation_seconds": 300.0,
        "deterministic_scoring_seconds_including_repeat": 12.0,
        "agentic_seconds": 615.0,
        "judge_seconds": 170.0,
    }
    for model in result["models"].values():
        assert model["agentic"]["pilot_seconds"] == 205.0
        assert model["pilot_gpu_hours"] == pytest.approx(325.0 / 3600.0)
        assert model["parallelism"]["effective"]["visible_gpu_uuids"] == [
            "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        ]


def test_direct_model_mapping_order_is_not_semantic(tmp_path: Path) -> None:
    study, manifest, direct, judge = _fixture(tmp_path)
    direct["models"] = dict(reversed(list(direct["models"].items())))

    result = builder.build_summary(
        study=study,
        manifest=manifest,
        direct=direct,
        result_root=tmp_path,
        judge_bundle=judge,
        judge_bundle_sha256="a" * 64,
        code_revision="b" * 40,
    )

    assert set(result["models"]) == {model.id for model in study.models}


def test_accepts_and_labels_one_shared_amended_tau_contract(tmp_path: Path) -> None:
    study, manifest, direct, judge = _fixture(tmp_path)
    amendment = {
        "status": "operator-authorized-local-simulator-pilot",
        "comparability": "Within-cohort only.",
    }
    for model in study.models:
        prefix = builder.MODEL_FILES[model.id]
        default_path = tmp_path / f"{prefix}-pilot-tau-receipt.json"
        receipt = json.loads(default_path.read_text(encoding="utf-8"))
        receipt["protocol_amendment"] = amendment
        _write(tmp_path / f"{prefix}-pilot-tau-local-receipt.json", receipt)
        default_path.unlink()

    result = builder.build_summary(
        study=study,
        manifest=manifest,
        direct=direct,
        result_root=tmp_path,
        judge_bundle=judge,
        judge_bundle_sha256="a" * 64,
        code_revision="b" * 40,
        tau_receipt_variant="local-amended",
        incomplete_tau_runtime_models=frozenset({study.models[0].id}),
    )

    assert result["protocol_amendments"]["tau3-bench"] == amendment
    assert (
        result["models"][study.models[0].id]["agentic"]["lanes"]["tau3-bench"][
            "runtime_accounting_complete"
        ]
        is False
    )
    assert result["models"][study.models[0].id]["estimated_full_gpu_hours"] is None
    assert result["scale_gate"]["decision"] == "no-go"
    assert result["status"] == "evidence-complete-scale-no-go"


def test_scale_gate_blocks_runner_exceptions_and_terminal_timeouts(tmp_path: Path) -> None:
    study, manifest, direct, judge = _fixture(tmp_path)
    source_tau = tmp_path / "source-pilot-tau-receipt.json"
    tau = json.loads(source_tau.read_text(encoding="utf-8"))
    tau["termination_counts"] = {"runner_error": 2}
    _write(source_tau.with_suffix(".replacement"), tau)
    source_tau.unlink()
    source_tau.with_suffix(".replacement").rename(source_tau)
    source_terminal = tmp_path / "source-pilot-terminal-receipt.json"
    terminal = json.loads(source_terminal.read_text(encoding="utf-8"))
    terminal["exception_counts"] = {"AgentTimeoutError": 5}
    _write(source_terminal.with_suffix(".replacement"), terminal)
    source_terminal.unlink()
    source_terminal.with_suffix(".replacement").rename(source_terminal)

    result = builder.build_summary(
        study=study,
        manifest=manifest,
        direct=direct,
        result_root=tmp_path,
        judge_bundle=judge,
        judge_bundle_sha256="a" * 64,
        code_revision="b" * 40,
    )

    assert result["scale_gate"] == {
        "decision": "no-go",
        "tau_runner_exceptions": 2,
        "terminal_agent_timeouts": 5,
        "incomplete_tau_runtime_models": [],
        "blockers": [
            "Repair and replay Tau runner exceptions for every model in affected paired blocks.",
            "Repair Terminal-Bench execution and replay the complete paired pilot lane.",
        ],
    }
    assert result["status"] == "evidence-complete-scale-no-go"


def test_rejects_agentic_id_drift_and_incomplete_judge_runtime(tmp_path: Path) -> None:
    study, manifest, direct, judge = _fixture(tmp_path)
    source_path = tmp_path / "source-pilot-bfcl-receipt.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["scored_ids"][0] = "wrong"
    _write(source_path, source)
    with pytest.raises(ValueError, match="does not match selected"):
        builder.build_summary(
            study=study,
            manifest=manifest,
            direct=direct,
            result_root=tmp_path,
            judge_bundle=judge,
            judge_bundle_sha256="a" * 64,
            code_revision="b" * 40,
        )

    study, manifest, direct, judge = _fixture(tmp_path / "fresh")
    changed = copy.deepcopy(judge)
    del changed["runtime"]
    with pytest.raises(ValueError, match="runtime accounting"):
        builder.build_summary(
            study=study,
            manifest=manifest,
            direct=direct,
            result_root=tmp_path / "fresh",
            judge_bundle=changed,
            judge_bundle_sha256="a" * 64,
            code_revision="b" * 40,
        )
