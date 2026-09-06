"""Tests for sealed Qwen3.8 observation normalization."""

from __future__ import annotations

import copy
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
SCRIPT = ROOT / "scripts/build_qwen38_observations.py"
SPEC = importlib.util.spec_from_file_location("qwen38_observation_builder", SCRIPT)
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


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(
    study: StudyProtocol,
    manifest: dict[str, Any],
    model_id: str,
) -> dict[str, Any]:
    return {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest["manifest_sha256"],
        "model_id": model_id,
    }


def _selected(manifest: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(allocation["allocation_id"]): list(allocation["selected_ids"])
        for allocation in manifest["allocations"]
    }


def _file_manifest(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path.relative_to(root)),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _judge_components(allocation_id: str, value: float) -> dict[str, Any]:
    if allocation_id in {"xstest-safe", "xstest-unsafe", "or-bench-hard-benign"}:
        behavior = "full_refusal" if value else "full_compliance"
        return {
            "behavior": behavior,
            "full_compliance": float(behavior == "full_compliance"),
            "full_refusal": float(behavior == "full_refusal"),
            "partial_refusal": 0.0,
        }
    if allocation_id == "strongreject-harmful":
        return {
            "refusal": 0.0,
            "convincingness": 3.0,
            "specificity": 3.0,
            "harmfulness": 0.5,
        }
    return {
        "turn_1_score": 5.0,
        "turn_2_score": 5.0,
        "normalized_two_turn_score": 0.5,
    }


def _fixture(tmp_path: Path) -> tuple[StudyProtocol, dict[str, Any], dict[str, Any]]:
    study = StudyProtocol.from_yaml(PROTOCOL)
    manifest = study.selection_manifest(_catalog(study), "pilot")
    selected = _selected(manifest)
    for model in study.models:
        prefix = builder.MODEL_FILES[model.id]
        identity = _identity(study, manifest, model.id)
        offline_rows = []
        for allocation_id in [
            allocation.id
            for allocation in study.benchmarks
            if allocation.execution_mode == "offline-batch"
        ]:
            for index, sample_id in enumerate(selected[allocation_id]):
                deterministic = allocation_id in builder.DETERMINISTIC_ALLOCATIONS
                offline_rows.append(
                    {
                        **identity,
                        "allocation_id": allocation_id,
                        "sample_id": sample_id,
                        "status": "scored" if deterministic else "pending-external-judge",
                        "score": float(index % 2) if deterministic else None,
                        "publication_eligible": deterministic,
                    }
                )
        scores = tmp_path / f"{prefix}-pilot-scores.jsonl"
        repeat = tmp_path / f"{prefix}-pilot-scores-repeat.jsonl"
        _write_jsonl(scores, offline_rows)
        repeat.write_bytes(scores.read_bytes())

        bfcl_score_dir = tmp_path / f"{prefix}-pilot-bfcl-scores"
        bfcl_score_dir.mkdir()
        bfcl_ids = selected["bfcl-v4-agentic"]
        _write_json(
            bfcl_score_dir / "BFCL_v4_agentic_score.json",
            [
                {"accuracy": 0.8, "correct_count": 4, "total_count": 5},
                {"id": bfcl_ids[0], "valid": False},
            ],
        )
        receipt_identity = {
            **identity,
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
        }
        _write_json(
            tmp_path / f"{prefix}-pilot-bfcl-receipt.json",
            {
                **receipt_identity,
                "scored_ids": bfcl_ids,
                "runner_cases_including_dependencies": 5,
                "score_files": _file_manifest(bfcl_score_dir),
            },
        )
        _write_json(
            tmp_path / f"{prefix}-pilot-tau-receipt.json",
            {
                **receipt_identity,
                "scored_results": [
                    {"canonical_id": sample_id, "reward": float(index % 2)}
                    for index, sample_id in enumerate(selected["tau3-bench"])
                ],
            },
        )
        _write_json(
            tmp_path / f"{prefix}-pilot-terminal-receipt.json",
            {
                **receipt_identity,
                "scored_results": [
                    {
                        "canonical_id": sample_id,
                        "rewards": {"reward": float(index % 2)},
                    }
                    for index, sample_id in enumerate(selected["terminal-bench-2.1"])
                ],
            },
        )

    outcomes = []
    for model in study.models:
        for allocation_id in builder.JUDGED_ALLOCATIONS:
            for index, sample_id in enumerate(selected[allocation_id]):
                value = float(index % 2)
                outcomes.append(
                    {
                        "model_id": model.id,
                        "allocation_id": allocation_id,
                        "sample_id": sample_id,
                        "status": "observed",
                        "value": value,
                        "components": _judge_components(allocation_id, value),
                        "judges_disagreed": index == 0,
                        "adjudicated": index == 0,
                    }
                )
    judge_bundle = {
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
        "outcomes": outcomes,
    }
    return study, manifest, judge_bundle


def test_builds_complete_ordered_pilot_matrix_and_provenance(tmp_path: Path) -> None:
    study, manifest, judge_bundle = _fixture(tmp_path)

    rows, receipt = builder.build_observations(
        study=study,
        manifest=manifest,
        result_root=tmp_path,
        judge_bundle=judge_bundle,
    )

    assert len(rows) == 300
    assert receipt["observations"] == 300
    assert receipt["status_counts"] == {"observed": 300}
    assert rows[0]["model_id"] == study.models[0].id
    assert rows[0]["allocation_id"] == study.benchmarks[0].id
    bfcl_rows = [row for row in rows if row["allocation_id"] == "bfcl-v4-agentic"]
    assert sum(row["value"] == 0.0 for row in bfcl_rows) == 3
    assert all(
        len(values["bfcl_score_inventory_sha256"]) == 64
        for values in receipt["source_artifacts"].values()
    )


def test_requires_explicit_missingness_for_absent_official_reward(tmp_path: Path) -> None:
    study, manifest, judge_bundle = _fixture(tmp_path)
    model = study.models[0]
    prefix = builder.MODEL_FILES[model.id]
    tau_path = tmp_path / f"{prefix}-pilot-tau-receipt.json"
    tau = json.loads(tau_path.read_text(encoding="utf-8"))
    sample_id = tau["scored_results"][0]["canonical_id"]
    tau["scored_results"][0]["reward"] = None
    _write_json(tau_path, tau)

    with pytest.raises(ValueError, match="complete selected observation matrix"):
        builder.build_observations(
            study=study,
            manifest=manifest,
            result_root=tmp_path,
            judge_bundle=judge_bundle,
        )

    missingness = [
        {
            **_identity(study, manifest, model.id),
            "allocation_id": "tau3-bench",
            "sample_id": sample_id,
            "metric_id": builder.METRIC_IDS["tau3-bench"],
            "status": "model-timeout",
            "value": 0.0,
        }
    ]
    rows, receipt = builder.build_observations(
        study=study,
        manifest=manifest,
        result_root=tmp_path,
        judge_bundle=judge_bundle,
        missingness_rows=missingness,
    )

    assert len(rows) == 300
    assert receipt["status_counts"] == {"model-timeout": 1, "observed": 299}


def test_rejects_scorer_drift_bfcl_tampering_and_unadjudicated_disagreement(
    tmp_path: Path,
) -> None:
    study, manifest, judge_bundle = _fixture(tmp_path)
    prefix = builder.MODEL_FILES[study.models[0].id]
    repeat_path = tmp_path / f"{prefix}-pilot-scores-repeat.jsonl"
    repeat_path.write_text(repeat_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not byte-identical"):
        builder.build_observations(
            study=study,
            manifest=manifest,
            result_root=tmp_path,
            judge_bundle=judge_bundle,
        )

    repeat_path.write_bytes((tmp_path / f"{prefix}-pilot-scores.jsonl").read_bytes())
    score_path = tmp_path / f"{prefix}-pilot-bfcl-scores/BFCL_v4_agentic_score.json"
    score = json.loads(score_path.read_text(encoding="utf-8"))
    score[0]["correct_count"] = 5
    _write_json(score_path, score)
    with pytest.raises(ValueError, match="file manifest"):
        builder.build_observations(
            study=study,
            manifest=manifest,
            result_root=tmp_path,
            judge_bundle=judge_bundle,
        )

    study, manifest, judge_bundle = _fixture(tmp_path / "fresh")
    changed = copy.deepcopy(judge_bundle)
    changed["outcomes"][0]["adjudicated"] = False
    with pytest.raises(ValueError, match="must be adjudicated"):
        builder.build_observations(
            study=study,
            manifest=manifest,
            result_root=tmp_path / "fresh",
            judge_bundle=changed,
        )


def test_full_judge_bundle_requires_calibration(tmp_path: Path) -> None:
    study, _, judge_bundle = _fixture(tmp_path)
    full = study.selection_manifest(_catalog(study), "full")
    changed = copy.deepcopy(judge_bundle)
    changed["manifest_sha256"] = full["manifest_sha256"]
    changed["cohort"] = "full"

    with pytest.raises(ValueError, match="human calibration"):
        builder._validate_judge_controls(
            changed,
            study=study,
            manifest_sha256=full["manifest_sha256"],
            cohort="full",
        )

    changed["calibration"] = {
        "human_double_labeled_items": 100,
        "cohens_kappa": 0.8,
        "confusion_matrix": {"labels": ["pass", "fail"], "matrix": [[40, 5], [5, 50]]},
    }
    builder._validate_judge_controls(
        changed,
        study=study,
        manifest_sha256=full["manifest_sha256"],
        cohort="full",
    )


def test_cli_writes_private_matrix_and_public_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    study, manifest, judge_bundle = _fixture(tmp_path)
    manifest_path = tmp_path / "pilot-manifest.json"
    judge_path = tmp_path / "judge-outcomes.json"
    output = tmp_path / "private" / "pilot-observations.jsonl"
    receipt = tmp_path / "public" / "pilot-observations-receipt.json"
    _write_json(manifest_path, manifest)
    _write_json(judge_path, judge_bundle)
    monkeypatch.setattr(builder.platform, "node", lambda: "basilisk")
    monkeypatch.setattr(builder, "PRIVATE_ROOT", tmp_path)

    assert (
        builder.main(
            [
                "--protocol",
                str(PROTOCOL),
                "--manifest",
                str(manifest_path),
                "--result-root",
                str(tmp_path),
                "--judge-outcomes",
                str(judge_path),
                "--output",
                str(output),
                "--receipt",
                str(receipt),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["observations"] == 300
    assert report["observations_sha256"] == _sha256(output)
    assert output.stat().st_mode & 0o777 == 0o600
    assert receipt.stat().st_mode & 0o777 == 0o644
    assert json.loads(receipt.read_text(encoding="utf-8"))["judge_bundle_sha256"] == _sha256(
        judge_path
    )
    with pytest.raises(ValueError, match="refusing to overwrite"):
        builder.main(
            [
                "--protocol",
                str(PROTOCOL),
                "--manifest",
                str(manifest_path),
                "--result-root",
                str(tmp_path),
                "--judge-outcomes",
                str(judge_path),
                "--output",
                str(output),
                "--receipt",
                str(receipt),
            ]
        )


def test_cli_rejects_non_a100_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builder.platform, "node", lambda: "workstation")
    with pytest.raises(RuntimeError, match="requires host basilisk"):
        builder.main(
            [
                "--protocol",
                str(PROTOCOL),
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--result-root",
                str(tmp_path),
                "--judge-outcomes",
                str(tmp_path / "judge.json"),
                "--output",
                str(tmp_path / "out.jsonl"),
                "--receipt",
                str(tmp_path / "receipt.json"),
            ]
        )
