"""Tests for preregistered paired study statistics and publication output."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import matric_eval.studies.analysis as analysis_module
import matric_eval.studies.analysis_cli as analysis_cli
from matric_eval.studies import (
    StudyObservation,
    StudyProtocol,
    analyze_observations,
    bootstrap_mean_ci,
    exact_mcnemar_pvalue,
    holm_adjust,
    load_observations,
    paired_bootstrap_delta_ci,
    stratified_paired_bootstrap_ci,
    wilson_interval,
)

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"


def _study(replicates: int = 25) -> StudyProtocol:
    payload = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    changed = copy.deepcopy(payload)
    changed["study"]["analysis"]["bootstrap_replicates"] = replicates
    return StudyProtocol.from_dict(changed)


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


def _observations(
    study: StudyProtocol,
    manifest: dict[str, Any],
) -> list[StudyObservation]:
    rows: list[dict[str, Any]] = []
    manifest_sha256 = str(manifest["manifest_sha256"])
    for allocation in manifest["allocations"]:
        allocation_id = str(allocation["allocation_id"])
        for model_index, model in enumerate(study.models):
            for sample_index, sample_id in enumerate(allocation["selected_ids"]):
                source_value = float(sample_index % 2)
                if model_index == 0:
                    value = source_value
                elif model_index == 1:
                    value = 1.0 if sample_index % 4 == 0 else source_value
                else:
                    value = 0.0 if sample_index % 4 == 1 else source_value
                rows.append(
                    {
                        "study_id": study.id,
                        "protocol_sha256": study.canonical_sha256,
                        "manifest_sha256": manifest_sha256,
                        "model_id": model.id,
                        "allocation_id": allocation_id,
                        "sample_id": str(sample_id),
                        "metric_id": f"{allocation_id}-primary",
                        "status": "observed",
                        "value": value,
                    }
                )
    return load_observations(reversed(rows))


def _observation(
    sample_id: str,
    status: str,
    value: float | None,
) -> StudyObservation:
    return StudyObservation.from_dict(
        {
            "study_id": "study",
            "protocol_sha256": "p" * 64,
            "manifest_sha256": "m" * 64,
            "model_id": "model",
            "allocation_id": "allocation",
            "sample_id": sample_id,
            "metric_id": "metric",
            "status": status,
            "value": value,
        },
        1,
    )


def test_statistical_primitives_are_deterministic_and_bounded() -> None:
    bootstrap = bootstrap_mean_ci([0.1, 0.3, 0.7, 0.9], seed=7, replicates=200)
    assert bootstrap == bootstrap_mean_ci([0.1, 0.3, 0.7, 0.9], seed=7, replicates=200)
    assert 0.1 <= bootstrap[0] <= bootstrap[1] <= 0.9

    paired = [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)]
    assert paired_bootstrap_delta_ci(paired, seed=9, replicates=200)[1] >= 0.0
    assert (
        stratified_paired_bootstrap_ci([paired[:2], paired[2:]], seed=9, replicates=200)[1] >= 0.0
    )

    low, high = wilson_interval(5, 10)
    assert 0.0 < low < 0.5 < high < 1.0
    assert exact_mcnemar_pvalue([(0.0, 1.0)] * 5 + [(1.0, 0.0)]) == pytest.approx(0.21875)
    assert exact_mcnemar_pvalue([(0.0, 0.0), (1.0, 1.0)]) == 1.0
    assert holm_adjust({"a": 0.01, "b": 0.03, "c": 0.5}) == {
        "a": 0.03,
        "b": 0.06,
        "c": 0.5,
    }


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"status": "unknown", "value": None}, "missingness state"),
        ({"status": "observed", "value": None}, "observed value"),
        ({"status": "observed", "value": 2.0}, "within"),
        ({"status": "model-timeout", "value": None}, "must have value 0"),
        ({"status": "infrastructure-error", "value": 0.0}, "must have null"),
    ],
)
def test_observation_rejects_invalid_status_value_combinations(
    row: dict[str, Any],
    message: str,
) -> None:
    payload: dict[str, Any] = {
        "study_id": "study",
        "protocol_sha256": "protocol",
        "manifest_sha256": "manifest",
        "model_id": "model",
        "allocation_id": "allocation",
        "sample_id": "sample",
        "metric_id": "metric",
        **row,
    }
    with pytest.raises(ValueError, match=message):
        StudyObservation.from_dict(payload, 3)


def test_load_observations_rejects_empty_and_duplicate_rows() -> None:
    with pytest.raises(ValueError, match="at least one"):
        load_observations([])
    row = {
        "study_id": "study",
        "protocol_sha256": "protocol",
        "manifest_sha256": "manifest",
        "model_id": "model",
        "allocation_id": "allocation",
        "sample_id": "sample",
        "metric_id": "metric",
        "status": "observed",
        "value": 1,
    }
    with pytest.raises(ValueError, match="duplicate"):
        load_observations([row, row])


def test_missingness_policy_excludes_infrastructure_and_bounds_judge_failures() -> None:
    source = [
        _observation("a", "observed", 1.0),
        _observation("b", "observed", 0.0),
        _observation("c", "infrastructure-error", None),
    ]
    intervention = [
        _observation("a", "judge-parse-failure", None),
        _observation("b", "model-timeout", 0.0),
        _observation("c", "observed", 1.0),
    ]

    summary, pairs = analysis_module._paired_summary(
        source,
        intervention,
        root_seed=1,
        label="missingness",
        replicates=10,
    )

    assert pairs == [(0.0, 0.0)]
    assert summary["infrastructure_excluded_pairs"] == 1
    assert summary["judge_unresolved_pairs"] == 1
    assert summary["missingness_delta_bounds"] == [-0.5, 0.0]


def test_full_analysis_validates_matrix_and_builds_declared_outputs() -> None:
    study = _study()
    manifest = study.selection_manifest(_catalog(study), "full")
    observations = _observations(study, manifest)

    result = analyze_observations(study, manifest, observations)

    assert result["cohort"] == "full"
    assert result["bootstrap_replicates"] == 25
    assert len(result["allocations"]) == 11
    assert set(result["axes"]) == {
        "agentic",
        "benign_overrefusal",
        "capability",
        "capability_and_agentic",
        "harmful_compliance",
    }
    e03 = "qwen38-27b-e03-bf16"
    assert result["axes"]["capability"]["comparisons_to_source"][e03]["noninferior"]
    first = next(iter(result["allocations"].values()))
    assert first["models"][result["source_model_id"]]["interval_method"] == "wilson-95"
    assert "mcnemar_holm_adjusted_p" in first["comparisons_to_source"][e03]


def test_analysis_rejects_pilot_tampering_and_incomplete_matrix() -> None:
    study = _study(2)
    pilot = study.selection_manifest(_catalog(study), "pilot")
    with pytest.raises(ValueError, match="full cohort"):
        analyze_observations(study, pilot, _observations(study, pilot))

    full = study.selection_manifest(_catalog(study), "full")
    observations = _observations(study, full)
    with pytest.raises(ValueError, match="exactly match full IDs"):
        analyze_observations(study, full, observations[1:])

    tampered = copy.deepcopy(full)
    tampered["seed"] += 1
    with pytest.raises(ValueError, match="manifest_sha256"):
        analyze_observations(study, tampered, observations)


def test_analysis_cli_writes_non_overwriting_content_free_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeStudy:
        id = "study"
        raw = {"study": {"execution": {"expected_hostname": "basilisk"}}}

    protocol = tmp_path / "protocol.yaml"
    manifest = tmp_path / "manifest.json"
    observations = tmp_path / "observations.jsonl"
    output = tmp_path / "public" / "aggregate-results.json"
    protocol.write_text("study: {}\n", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    observations.write_text('{"status":"observed"}\n', encoding="utf-8")
    monkeypatch.setattr(
        analysis_cli.StudyProtocol,
        "from_yaml",
        staticmethod(lambda *args, **kwargs: FakeStudy()),
    )
    monkeypatch.setattr(analysis_cli.platform, "node", lambda: "basilisk")
    monkeypatch.setattr(analysis_cli, "load_observations", lambda rows: [])
    monkeypatch.setattr(
        analysis_cli,
        "analyze_observations",
        lambda study, manifest, rows: {"schema_version": "1", "study_id": "study"},
    )
    monkeypatch.setattr(analysis_cli, "_code_revision", lambda: "a" * 40)

    assert (
        analysis_cli.main(
            [str(protocol), str(manifest), str(observations), "--output", str(output)]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["analysis_code_revision"] == "a" * 40
    assert len(payload["observations_sha256"]) == 64
    assert output.stat().st_mode & 0o777 == 0o644
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        analysis_cli.main(
            [str(protocol), str(manifest), str(observations), "--output", str(output)]
        )


def test_analysis_cli_rejects_non_a100_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStudy:
        raw = {"study": {"execution": {"expected_hostname": "basilisk"}}}

    protocol = tmp_path / "protocol.yaml"
    manifest = tmp_path / "manifest.json"
    observations = tmp_path / "observations.jsonl"
    protocol.write_text("study: {}\n", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    observations.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        analysis_cli.StudyProtocol,
        "from_yaml",
        staticmethod(lambda *args, **kwargs: FakeStudy()),
    )
    monkeypatch.setattr(analysis_cli.platform, "node", lambda: "workstation")

    with pytest.raises(RuntimeError, match="must run on basilisk"):
        analysis_cli.main(
            [
                str(protocol),
                str(manifest),
                str(observations),
                "--output",
                str(tmp_path / "out.json"),
            ]
        )


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: bootstrap_mean_ci([], seed=1, replicates=1), "cannot be empty"),
        (lambda: bootstrap_mean_ci([1.0], seed=1, replicates=0), "positive"),
        (lambda: wilson_interval(2, 1), "Wilson counts"),
        (lambda: exact_mcnemar_pvalue([(0.5, 1.0)]), "binary"),
        (lambda: holm_adjust({"bad": 2.0}), "p-values"),
        (lambda: stratified_paired_bootstrap_ci([], seed=1, replicates=1), "stratum"),
    ],
)
def test_statistical_primitives_reject_invalid_inputs(call: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call()
