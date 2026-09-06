"""Tests for complete Qwen3.8 pilot runtime and artifact accounting."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from matric_eval.studies import StudyProtocol

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
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest["manifest_sha256"],
        "cohort": "pilot",
        "judges": {
            "primary": {
                "provider": "provider-a",
                "model": "judge-a",
                "snapshot": "judge-a-2026-09-01",
            },
            "adjudicator": {
                "provider": "provider-b",
                "model": "judge-b",
                "snapshot": "judge-b-2026-09-01",
            },
        },
        "controls": {
            "blinded_model_labels": True,
            "order_randomized": True,
            "target_models_may_not_judge": True,
            "disagreement_policy": "adjudicate-all",
        },
        "runtime": {
            "primary_calls": len(outcomes),
            "adjudicator_calls": 0,
            "retries": 0,
            "primary_seconds": 90.0,
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
    assert result["manifest_sha256"] == manifest["manifest_sha256"]
    assert result["judge"]["outcomes"] == 135
    assert result["runtime_totals"] == {
        "direct_initialization_seconds": 60.0,
        "direct_generation_seconds": 300.0,
        "deterministic_scoring_seconds_including_repeat": 12.0,
        "agentic_seconds": 615.0,
        "judge_seconds": 90.0,
    }
    for model in result["models"].values():
        assert model["agentic"]["pilot_seconds"] == 205.0
        assert model["pilot_gpu_hours"] == pytest.approx(325.0 / 3600.0)


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
