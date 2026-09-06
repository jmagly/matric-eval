"""Tests for the Qwen3.8 blinded human-calibration workflow."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
PLAN = ROOT / "studies/qwen38-obliteration-2026-09/judge-plan.yaml"
SCRIPT_DIR = ROOT / "scripts"
SCRIPT = SCRIPT_DIR / "run_qwen38_calibration.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("qwen38_calibration_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _fixture() -> tuple[StudyProtocol, dict[str, Any], dict[str, Any], list[Any]]:
    study = StudyProtocol.from_yaml(PROTOCOL)
    plan = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    assert isinstance(plan, dict)
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
    manifest = study.selection_manifest(catalog, "full")
    items = [
        runner.JudgeItem(
            model_id=model.id,
            allocation_id=allocation["allocation_id"],
            sample_id=sample_id,
            prompt=f"private prompt {sample_id}",
            response=f"private response {sample_id}",
        )
        for model in study.models
        for allocation in manifest["allocations"]
        if allocation["allocation_id"] in runner.CALIBRATION_ALLOCATIONS
        for sample_id in allocation["selected_ids"]
    ]
    return study, plan, manifest, items


def test_packet_is_deterministic_balanced_and_blinded() -> None:
    study, plan, manifest, items = _fixture()
    packet = runner.build_packet(
        study=study,
        manifest=manifest,
        plan=plan,
        plan_sha256="a" * 64,
        items=items,
        code_revision="b" * 40,
    )
    repeat = runner.build_packet(
        study=study,
        manifest=manifest,
        plan=plan,
        plan_sha256="a" * 64,
        items=list(reversed(items)),
        code_revision="b" * 40,
    )

    assert packet == repeat
    assert packet["human_double_labeled_items"] == 100
    assert len(packet["items"]) == 100
    assert len({item["calibration_id"] for item in packet["items"]}) == 100
    serialized = json.dumps(packet)
    assert "qwen38-27b-source-bf16" not in serialized
    assert all(set(item) == {"calibration_id", "conversation"} for item in packet["items"])


def test_summary_computes_content_free_kappa_and_confusion_matrix() -> None:
    study, plan, manifest, items = _fixture()
    packet = runner.build_packet(
        study=study,
        manifest=manifest,
        plan=plan,
        plan_sha256="a" * 64,
        items=items,
        code_revision="b" * 40,
    )
    first = runner.build_label_template(packet, "c" * 64)
    second = runner.build_label_template(packet, "c" * 64)
    first["annotator_id"] = "annotator-a"
    second["annotator_id"] = "annotator-b"
    for index, (left, right) in enumerate(zip(first["labels"], second["labels"], strict=True)):
        left["behavior"] = runner.BEHAVIOR_LABELS[index % 3]
        right["behavior"] = runner.BEHAVIOR_LABELS[index % 3 if index < 90 else (index + 1) % 3]

    summary = runner.build_summary(
        packet=packet,
        packet_sha256="c" * 64,
        labels_a=first,
        labels_a_sha256="d" * 64,
        labels_b=second,
        labels_b_sha256="e" * 64,
        code_revision="f" * 40,
    )

    assert summary["human_double_labeled_items"] == 100
    assert summary["agreement_rate"] == pytest.approx(0.9)
    assert -1.0 <= summary["cohens_kappa"] <= 1.0
    assert sum(sum(row) for row in summary["confusion_matrix"]["matrix"]) == 100
    assert "annotator-a" not in json.dumps(summary)
    assert "private prompt" not in json.dumps(summary)


def test_summary_rejects_incomplete_or_nonindependent_labels() -> None:
    study, plan, manifest, items = _fixture()
    packet = runner.build_packet(
        study=study,
        manifest=manifest,
        plan=plan,
        plan_sha256="a" * 64,
        items=items,
        code_revision="b" * 40,
    )
    template = runner.build_label_template(packet, "c" * 64)
    template["annotator_id"] = "same"
    for row in template["labels"]:
        row["behavior"] = "full_refusal"
    with pytest.raises(ValueError, match="distinct annotator"):
        runner.build_summary(
            packet=packet,
            packet_sha256="c" * 64,
            labels_a=template,
            labels_a_sha256="d" * 64,
            labels_b=template,
            labels_b_sha256="e" * 64,
            code_revision="f" * 40,
        )
