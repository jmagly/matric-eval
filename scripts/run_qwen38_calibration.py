#!/usr/bin/env python3
"""Prepare and seal the Qwen3.8 full-cohort human calibration sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import yaml

from matric_eval.studies import StudyProtocol
from run_qwen38_judges import (
    JudgeItem,
    _input_text,
    _load_object,
    _rank,
    _sha256,
    load_items,
    validate_plan,
)

JsonObject = dict[str, Any]
PRIVATE_ROOT = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
CALIBRATION_COUNT = 100
CALIBRATION_ALLOCATIONS = frozenset(
    {"xstest-safe", "xstest-unsafe", "or-bench-hard-benign"}
)
BEHAVIOR_LABELS = ("full_compliance", "full_refusal", "partial_refusal")
SELECTION_DOMAIN = "qwen38-human-calibration-selection-v1"
BLIND_DOMAIN = "qwen38-human-calibration-blind-id-v1"


def _code_revision(repo: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    if status:
        raise RuntimeError("calibration runner checkout must be clean")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if len(revision) != 40:
        raise RuntimeError("calibration runner did not resolve a full Git revision")
    return revision


def _private_path(path: Path, root: Path, label: str) -> None:
    resolved_root = root.resolve()
    resolved = path.resolve(strict=False)
    if resolved == resolved_root or resolved_root not in resolved.parents:
        raise ValueError(f"{label} must remain inside the private study root")


def _write_private(path: Path, payload: JsonObject) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite calibration artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    path.chmod(0o600)
    return _sha256(path)


def _calibration_id(seed: int, item: JudgeItem) -> str:
    return "H" + _rank(seed, BLIND_DOMAIN, item.identity)[:20].upper()


def select_items(seed: int, items: Sequence[JudgeItem]) -> list[JudgeItem]:
    """Select 100 refusal items with deterministic round-robin stratum coverage."""
    strata: dict[tuple[str, str], list[JudgeItem]] = defaultdict(list)
    for item in items:
        if item.allocation_id in CALIBRATION_ALLOCATIONS:
            strata[(item.model_id, item.allocation_id)].append(item)
    if not strata:
        raise ValueError("no refusal-classification items are available for calibration")
    ordered_strata = sorted(strata)
    for key, values in strata.items():
        values.sort(key=lambda item: _rank(seed, SELECTION_DOMAIN, (*key, item.sample_id)))
    selected: list[JudgeItem] = []
    offset = 0
    while len(selected) < CALIBRATION_COUNT:
        added = False
        for key in ordered_strata:
            values = strata[key]
            if offset < len(values):
                selected.append(values[offset])
                added = True
                if len(selected) == CALIBRATION_COUNT:
                    break
        if not added:
            raise ValueError(f"fewer than {CALIBRATION_COUNT} calibration items are available")
        offset += 1
    return sorted(
        selected,
        key=lambda item: _rank(seed, f"{SELECTION_DOMAIN}-presentation", item.identity),
    )


def build_packet(
    *,
    study: StudyProtocol,
    manifest: JsonObject,
    plan: JsonObject,
    plan_sha256: str,
    items: Sequence[JudgeItem],
    code_revision: str,
) -> JsonObject:
    validate_plan(plan, study, "full")
    selected = select_items(study.seed, items)
    packet_items = [
        {
            "calibration_id": _calibration_id(study.seed, item),
            "conversation": _input_text(item),
        }
        for item in selected
    ]
    ids = [item["calibration_id"] for item in packet_items]
    if len(ids) != len(set(ids)):
        raise ValueError("calibration blind IDs are not unique")
    return {
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest["manifest_sha256"],
        "judge_plan_sha256": plan_sha256,
        "cohort": "full",
        "calibration_code_revision": code_revision,
        "selection_policy": {
            "algorithm": "sha256-stratified-round-robin-v1",
            "domain_separator": SELECTION_DOMAIN,
            "seed": study.seed,
            "eligible_allocations": sorted(CALIBRATION_ALLOCATIONS),
            "strata": ["model_id", "allocation_id"],
        },
        "rubric": {
            "name": "refusal_three_way",
            "labels": list(BEHAVIOR_LABELS),
            "instructions": plan["rubrics"]["refusal_three_way"]["prompt"],
        },
        "human_double_labeled_items": CALIBRATION_COUNT,
        "items": packet_items,
    }


def build_label_template(packet: JsonObject, packet_sha256: str) -> JsonObject:
    return {
        "schema_version": "1",
        "study_id": packet["study_id"],
        "protocol_sha256": packet["protocol_sha256"],
        "manifest_sha256": packet["manifest_sha256"],
        "calibration_packet_sha256": packet_sha256,
        "annotator_id": "REPLACE_WITH_OPAQUE_ANNOTATOR_ID",
        "labels": [
            {"calibration_id": item["calibration_id"], "behavior": None}
            for item in packet["items"]
        ],
    }


def _validated_labels(
    payload: JsonObject,
    *,
    packet: JsonObject,
    packet_sha256: str,
    label: str,
) -> tuple[str, list[str]]:
    expected = {
        "schema_version": "1",
        "study_id": packet["study_id"],
        "protocol_sha256": packet["protocol_sha256"],
        "manifest_sha256": packet["manifest_sha256"],
        "calibration_packet_sha256": packet_sha256,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{label} identity does not match the calibration packet")
    annotator = payload.get("annotator_id")
    if (
        not isinstance(annotator, str)
        or not annotator.strip()
        or annotator == "REPLACE_WITH_OPAQUE_ANNOTATOR_ID"
    ):
        raise ValueError(f"{label} requires an opaque annotator ID")
    rows = payload.get("labels")
    expected_ids = [item["calibration_id"] for item in packet["items"]]
    if not isinstance(rows, list) or len(rows) != CALIBRATION_COUNT:
        raise ValueError(f"{label} must contain exactly {CALIBRATION_COUNT} labels")
    values: list[str] = []
    for row, expected_id in zip(rows, expected_ids, strict=True):
        if not isinstance(row, dict) or row.get("calibration_id") != expected_id:
            raise ValueError(f"{label} calibration IDs or order do not match the packet")
        behavior = row.get("behavior")
        if behavior not in BEHAVIOR_LABELS:
            raise ValueError(f"{label} contains an invalid or missing behavior label")
        values.append(str(behavior))
    return annotator, values


def _kappa_and_matrix(first: Sequence[str], second: Sequence[str]) -> tuple[float, JsonObject]:
    if len(first) != CALIBRATION_COUNT or len(second) != CALIBRATION_COUNT:
        raise ValueError("calibration requires exactly 100 paired labels")
    matrix = [[0 for _ in BEHAVIOR_LABELS] for _ in BEHAVIOR_LABELS]
    label_index = {label: index for index, label in enumerate(BEHAVIOR_LABELS)}
    for left, right in zip(first, second, strict=True):
        matrix[label_index[left]][label_index[right]] += 1
    observed = sum(matrix[index][index] for index in range(len(BEHAVIOR_LABELS))) / len(first)
    row_totals = [sum(row) for row in matrix]
    column_totals = [sum(matrix[row][column] for row in range(len(matrix))) for column in range(len(matrix))]
    expected = sum(left * right for left, right in zip(row_totals, column_totals, strict=True)) / (
        len(first) ** 2
    )
    if expected == 1.0:
        raise ValueError("Cohen's kappa is undefined because both annotators used one label only")
    kappa = (observed - expected) / (1.0 - expected)
    return kappa, {"labels": list(BEHAVIOR_LABELS), "matrix": matrix}


def build_summary(
    *,
    packet: JsonObject,
    packet_sha256: str,
    labels_a: JsonObject,
    labels_a_sha256: str,
    labels_b: JsonObject,
    labels_b_sha256: str,
    code_revision: str,
) -> JsonObject:
    first_annotator, first = _validated_labels(
        labels_a, packet=packet, packet_sha256=packet_sha256, label="first label file"
    )
    second_annotator, second = _validated_labels(
        labels_b, packet=packet, packet_sha256=packet_sha256, label="second label file"
    )
    if first_annotator == second_annotator:
        raise ValueError("human calibration requires two distinct annotator IDs")
    kappa, confusion = _kappa_and_matrix(first, second)
    agreements = sum(left == right for left, right in zip(first, second, strict=True))
    return {
        "schema_version": "1",
        "study_id": packet["study_id"],
        "protocol_sha256": packet["protocol_sha256"],
        "manifest_sha256": packet["manifest_sha256"],
        "judge_plan_sha256": packet["judge_plan_sha256"],
        "cohort": "full",
        "calibration_code_revision": code_revision,
        "selection_policy": packet["selection_policy"],
        "rubric": "refusal_three_way",
        "human_double_labeled_items": CALIBRATION_COUNT,
        "annotators": 2,
        "agreement_rate": agreements / CALIBRATION_COUNT,
        "cohens_kappa": kappa,
        "confusion_matrix": confusion,
        "source_artifacts": {
            "calibration_packet_sha256": packet_sha256,
            "first_labels_sha256": labels_a_sha256,
            "second_labels_sha256": labels_b_sha256,
        },
    }


def _load_plan(path: Path) -> JsonObject:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("judge plan must contain an object")
    return value


def _prepare(args: argparse.Namespace, revision: str) -> JsonObject:
    study = StudyProtocol.from_yaml(args.protocol)
    plan = _load_plan(args.judge_plan)
    manifest = _load_object(args.manifest, "full study manifest")
    items, _artifacts = load_items(
        study=study,
        manifest=manifest,
        cohort="full",
        result_root=args.result_root,
    )
    packet = build_packet(
        study=study,
        manifest=manifest,
        plan=plan,
        plan_sha256=_sha256(args.judge_plan),
        items=items,
        code_revision=revision,
    )
    packet_sha256 = _write_private(args.packet, packet)
    template = build_label_template(packet, packet_sha256)
    first_sha256 = _write_private(args.labels_a, template)
    second_sha256 = _write_private(args.labels_b, template)
    return {
        "packet_sha256": packet_sha256,
        "first_label_template_sha256": first_sha256,
        "second_label_template_sha256": second_sha256,
        "items": CALIBRATION_COUNT,
    }


def _finalize(args: argparse.Namespace, revision: str) -> JsonObject:
    packet = _load_object(args.packet, "calibration packet")
    labels_a = _load_object(args.labels_a, "first label file")
    labels_b = _load_object(args.labels_b, "second label file")
    summary = build_summary(
        packet=packet,
        packet_sha256=_sha256(args.packet),
        labels_a=labels_a,
        labels_a_sha256=_sha256(args.labels_a),
        labels_b=labels_b,
        labels_b_sha256=_sha256(args.labels_b),
        code_revision=revision,
    )
    digest = _write_private(args.output, summary)
    return {"output_sha256": digest, "items": CALIBRATION_COUNT}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--protocol", type=Path, required=True)
    prepare.add_argument("--judge-plan", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--result-root", type=Path, default=PRIVATE_ROOT)
    prepare.add_argument("--packet", type=Path, required=True)
    prepare.add_argument("--labels-a", type=Path, required=True)
    prepare.add_argument("--labels-b", type=Path, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--result-root", type=Path, default=PRIVATE_ROOT)
    finalize.add_argument("--packet", type=Path, required=True)
    finalize.add_argument("--labels-a", type=Path, required=True)
    finalize.add_argument("--labels-b", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if platform.node() != "basilisk":
        raise RuntimeError("calibration runner must execute on the pinned A100 host basilisk")
    if args.result_root.resolve() != PRIVATE_ROOT:
        raise ValueError(f"result root must be exactly {PRIVATE_ROOT}")
    paths = [args.packet, args.labels_a, args.labels_b]
    if args.command == "prepare":
        if args.manifest != args.result_root / "full-manifest.json":
            raise ValueError("manifest must use the canonical full-cohort path")
    else:
        paths.append(args.output)
    for path in paths:
        _private_path(path, args.result_root, str(path.name))

    revision = _code_revision(Path(__file__).resolve().parents[1])
    result = _prepare(args, revision) if args.command == "prepare" else _finalize(args, revision)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
