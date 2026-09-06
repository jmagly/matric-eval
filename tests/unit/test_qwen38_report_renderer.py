"""Tests for the sealed Qwen3.8 publication renderer."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from matric_eval.studies import StudyObservation, StudyProtocol, analyze_observations

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
SCRIPT = ROOT / "scripts/render_qwen38_report.py"
SPEC = importlib.util.spec_from_file_location("qwen38_report_renderer", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = renderer
SPEC.loader.exec_module(renderer)


def _study() -> StudyProtocol:
    payload = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    changed = copy.deepcopy(payload)
    changed["study"]["analysis"]["bootstrap_replicates"] = 2
    return StudyProtocol.from_dict(changed, validate_registry=False)


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


def _evidence() -> tuple[
    StudyProtocol,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    study = _study()
    manifest = study.selection_manifest(_catalog(study), "full")
    observations: list[StudyObservation] = []
    for allocation in manifest["allocations"]:
        for model_index, model in enumerate(study.models):
            for sample_index, sample_id in enumerate(allocation["selected_ids"]):
                source = float(sample_index % 2)
                value = source if model_index == 0 else float((sample_index + model_index) % 2)
                observations.append(
                    StudyObservation.from_dict(
                        {
                            "study_id": study.id,
                            "protocol_sha256": study.canonical_sha256,
                            "manifest_sha256": manifest["manifest_sha256"],
                            "model_id": model.id,
                            "allocation_id": allocation["allocation_id"],
                            "sample_id": sample_id,
                            "metric_id": f"{allocation['allocation_id']}-primary",
                            "status": "observed",
                            "value": value,
                        },
                        len(observations) + 1,
                    )
                )
    analysis = analyze_observations(study, manifest, observations)
    analysis["analysis_code_revision"] = "a" * 40
    analysis["observations_sha256"] = "b" * 64
    receipt = {
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest["manifest_sha256"],
        "cohort": "full",
        "models": [model.id for model in study.models],
        "observations": study.full_samples_per_model * len(study.models),
        "observations_sha256": analysis["observations_sha256"],
        "judge_bundle_sha256": "c" * 64,
        "missingness_outcomes_sha256": None,
        "source_artifacts": {},
        "status_counts": {"observed": study.full_samples_per_model * len(study.models)},
    }
    pilot = {
        "schema_version": "2",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "study_seed": study.seed,
        "status": "complete",
        "models": {
            model.id: {
                "direct_pilot_generation_calls": 85,
                "total_generation_seconds": 600.0,
                "estimated_full_direct_seconds_from_scratch": 7200.0,
            }
            for model in study.models
        },
    }
    return study, manifest, analysis, receipt, pilot


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_validates_hash_join_and_requires_complete_pilot() -> None:
    study, manifest, analysis, receipt, pilot = _evidence()
    assert not renderer.validate_evidence(
        study=study,
        manifest=manifest,
        analysis=analysis,
        receipt=receipt,
        pilot=pilot,
        allow_incomplete_pilot=False,
    )

    pilot["status"] = "agentic-pending"
    with pytest.raises(ValueError, match="status 'complete'"):
        renderer.validate_evidence(
            study=study,
            manifest=manifest,
            analysis=analysis,
            receipt=receipt,
            pilot=pilot,
            allow_incomplete_pilot=False,
        )
    assert renderer.validate_evidence(
        study=study,
        manifest=manifest,
        analysis=analysis,
        receipt=receipt,
        pilot=pilot,
        allow_incomplete_pilot=True,
    )

    receipt["observations_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="does not join"):
        renderer.validate_evidence(
            study=study,
            manifest=manifest,
            analysis=analysis,
            receipt=receipt,
            pilot=pilot,
            allow_incomplete_pilot=True,
        )


def test_renders_aggregate_only_site_pdf_and_content_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study, manifest, analysis, receipt, pilot = _evidence()
    paths = {
        "protocol": tmp_path / "protocol.yaml",
        "manifest": tmp_path / "manifest.json",
        "analysis": tmp_path / "analysis.json",
        "normalization_receipt": tmp_path / "receipt.json",
        "pilot_summary": tmp_path / "pilot.json",
    }
    paths["protocol"].write_text(PROTOCOL.read_text(encoding="utf-8"), encoding="utf-8")
    for label, payload in (
        ("manifest", manifest),
        ("analysis", analysis),
        ("normalization_receipt", receipt),
        ("pilot_summary", pilot),
    ):
        _write(paths[label], payload)

    def fake_pdf(chromium: Path, html_path: Path, pdf_path: Path, profile: Path) -> None:
        del chromium, html_path, profile
        pdf_path.write_bytes(b"%PDF-1.7\n" + b"x" * 2048)

    monkeypatch.setattr(renderer, "_render_pdf", fake_pdf)
    output = tmp_path / "report"
    result = renderer.render_bundle(
        study=study,
        manifest=manifest,
        analysis=analysis,
        receipt=receipt,
        pilot=pilot,
        revision="d" * 40,
        input_paths=paths,
        output_dir=output,
        chromium=tmp_path / "chromium",
        draft=False,
    )

    assert result["publication_status"] == "final"
    assert (output / "report.pdf").read_bytes().startswith(b"%PDF-")
    index = (output / "index.html").read_text(encoding="utf-8")
    methods = (output / "methods.html").read_text(encoding="utf-8")
    for section in renderer.REQUIRED_SECTIONS:
        assert f'id="{section}"' in index + methods
    assert "Raw prompts and completions are not included" in index
    assert (output / "aggregate-results.json").read_bytes() == paths["analysis"].read_bytes()
    manifest_payload = json.loads((output / "bundle-manifest.json").read_text(encoding="utf-8"))
    published = {item["path"] for item in manifest_payload["files"]}
    assert {
        "index.html",
        "methods.html",
        "report.pdf",
        "aggregate-results.json",
        "sample-manifest.json",
        "protocol.yaml",
        "normalization-receipt.json",
        "pilot-summary.json",
        "reproducibility.json",
        "assets/report.css",
    } == published
    with pytest.raises(ValueError, match="refusing to overwrite"):
        renderer.render_bundle(
            study=study,
            manifest=manifest,
            analysis=analysis,
            receipt=receipt,
            pilot=pilot,
            revision="d" * 40,
            input_paths=paths,
            output_dir=output,
            chromium=tmp_path / "chromium",
            draft=False,
        )


def test_html_escapes_untrusted_labels() -> None:
    page = renderer._page(
        title='<script>alert("x")</script>',
        body="<p>trusted renderer body</p>",
        draft=False,
        active="results",
    )
    assert "&lt;script&gt;" in page
    assert '<script>alert("x")</script>' not in page
