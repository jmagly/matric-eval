"""Independent calibration counterexamples; synthetic data never qualifies judges."""

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from matric_eval.cli import cli
from matric_eval.results.contract import ArtifactReference
from matric_eval.scorers.calibration import (
    Assessment,
    CalibrationSet,
    DomainReview,
    Judgment,
    QualificationPolicy,
    assess_calibration,
    digest,
    parse_binary_judgment,
    prompt_example_manifest,
)


def reference() -> dict:
    return {"uri": "synthetic:evidence", "sha256": "a" * 64, "unavailable_reason": None}


def cohort(positives=1, negatives=19) -> CalibrationSet:
    return CalibrationSet.model_validate(
        {
            "snapshot": {
                "domain": "synthetic arithmetic",
                "task": "detect incorrect answers",
                "rubric_version": "1",
                "rubric_sha256": "b" * 64,
                "judge_id": "synthetic-judge",
                "judge_snapshot_sha256": "c" * 64,
                "model_snapshot_sha256": "d" * 64,
                "prompt_sha256": "e" * 64,
                "configuration_sha256": "f" * 64,
                "positive_label": "failure",
                "positive_meaning": "The candidate answer violates the rubric",
            },
            "sampling_frame": "hand-written deterministic counterexample",
            "independent_unit": "task",
            "rows": [
                {
                    "data": {
                        "partition_schema_version": "1",
                        "role": "final_test",
                        "row_id": str(i),
                        "source_id": "fixture",
                        "independent_unit_id": str(i),
                    },
                    "content_sha256": f"{i:064x}",
                    "rubric_version": "1",
                    "purpose": "final_assessment",
                    "access": "permitted",
                    "access_owner": "fixture-author",
                    "license_id": "synthetic",
                    "consent": reference(),
                    "human_label": i < positives,
                    "label_source": "synthetic",
                    "annotators": ["fixture-author"],
                    "critique": reference(),
                    "adjudication": reference(),
                    "slices": ["positive" if i < positives else "negative"],
                }
                for i in range(positives + negatives)
            ],
        }
    )


def policy(data: CalibrationSet, reversal=True) -> QualificationPolicy:
    return QualificationPolicy(
        application="synthetic failure screening",
        snapshot_sha256=digest(data.snapshot),
        calibration_set_sha256=digest(data),
        frozen_at="2026-09-01T00:00:00Z",
        confidence=0.95,
        minimum_positive_recall_lower=0.7,
        maximum_false_positive_upper=0.2,
        minimum_coverage_lower=0.8,
        maximum_order_inconsistency_upper=0.2,
        require_reversal=reversal,
        rationale="fixture requirements, not domain recommendations",
    )


def judgment(value: bool | None) -> dict:
    return {
        "label": value,
        "reason": None if value is not None else "malformed_judgment",
        "raw": reference(),
    }


def assessment(data: CalibrationSet, rules: QualificationPolicy, labels=None) -> Assessment:
    labels = labels if labels is not None else [False] * len(data.rows)
    return Assessment.model_validate(
        {
            "snapshot_sha256": digest(data.snapshot),
            "calibration_set_sha256": digest(data),
            "policy_sha256": digest(rules),
            "started_at": "2026-09-02T00:00:00Z",
            "items": [
                {
                    "source_id": "fixture",
                    "row_id": row.data.row_id,
                    "forward": judgment(value),
                    "reverse": judgment(value),
                    "reverse_mapping": "same-candidate-rubric-label/1",
                }
                for row, value in zip(data.rows, labels, strict=True)
            ],
        }
    )


def test_high_agreement_always_pass_judge_fails_failure_detection():
    data = cohort()
    rules = policy(data)
    report = assess_calibration(
        data, rules, assessment(data, rules), current_snapshot=data.snapshot
    )
    assert report["summary"]["agreement_among_scored"]["value"] == 0.95
    assert report["summary"]["positive_recall"]["value"] == 0.0
    assert report["summary"]["positive_prevalence"]["value"] == 0.05
    assert report["summary"]["confusion"] == {
        "true_positive": 0,
        "false_positive": 0,
        "true_negative": 19,
        "false_negative": 1,
        "positive_abstention": 0,
        "negative_abstention": 0,
    }
    assert "qualification_check_failed:positive_recall:lower" in report["eligibility"]["reasons"]
    assert report["status"] == "unqualified"


@pytest.mark.parametrize(
    "payload",
    [
        "nonsense",
        '{"label":NaN}',
        '{"label":null}',
        '{"label":1}',
        '{"label":true,"label":false}',
        '{"label":true,"extra":1}',
    ],
)
def test_malformed_import_stays_abstention(payload):
    parsed = parse_binary_judgment(payload, ArtifactReference.model_validate(reference()))
    assert parsed.label is None
    assert parsed.reason == "malformed_judgment"


def test_valid_boolean_import_preserves_false():
    parsed = parse_binary_judgment('{"label":false}', ArtifactReference.model_validate(reference()))
    assert parsed.label is False and parsed.reason is None


def test_all_planned_items_reconcile_with_missing_reverse_and_inconsistent_orders():
    data = cohort(2, 2)
    rules = policy(data)
    run = assessment(data, rules, [True, None, False, False])
    run.items[2].reverse.label = True
    run.items.pop()
    report = assess_calibration(data, rules, run, current_snapshot=data.snapshot)
    assert (
        report["summary"]["planned"],
        report["summary"]["scored"],
        report["summary"]["abstained"],
    ) == (4, 1, 3)
    assert report["summary"]["order_inconsistency"]["value"] == 0.5
    assert report["records"][1]["reason"] == "order_check_unavailable"
    assert report["records"][2]["position_outcomes"]["forward"]["label"] is False
    assert report["records"][2]["position_outcomes"]["reverse"]["label"] is True
    assert report["records"][3]["reason"] == "not_assessed"
    assert sum(report["summary"]["confusion"].values()) == 4
    assert report["slices"]["positive"]["planned"] == 2


@pytest.mark.parametrize("field", ["rubric_version", "data", "annotators"])
def test_required_calibration_provenance_is_not_guessed(field):
    value = cohort().model_dump()
    del value["rows"][0][field]
    with pytest.raises(ValidationError):
        CalibrationSet.model_validate(value)


def test_final_rows_cannot_be_prompt_examples_and_cross_role_duplicates_reject():
    value = cohort().model_dump()
    value["rows"][0]["purpose"] = "prompt_example"
    with pytest.raises(ValidationError, match="final-test"):
        CalibrationSet.model_validate(value)
    value["rows"][0]["data"]["role"] = "calibration"
    value["rows"][0]["content_sha256"] = value["rows"][1]["content_sha256"]
    with pytest.raises(ValidationError, match="cross-partition"):
        CalibrationSet.model_validate(value)
    assert prompt_example_manifest(cohort())["rows"] == []


def test_restricted_rows_are_not_reported():
    data = cohort()
    data.rows[0].access = "restricted"
    rules = policy(data)
    with pytest.raises(PermissionError, match="access owner"):
        assess_calibration(data, rules, assessment(data, rules), current_snapshot=data.snapshot)


def test_repetition_does_not_inflate_independent_sample_size():
    data = cohort()
    data.rows[1].data.independent_unit_id = data.rows[0].data.independent_unit_id
    rules = policy(data)
    with pytest.raises(ValueError, match="independent units"):
        assess_calibration(data, rules, assessment(data, rules), current_snapshot=data.snapshot)


def test_relabeling_duplicate_final_content_does_not_inflate_evidence():
    data = cohort().model_dump()
    data["rows"][1]["content_sha256"] = data["rows"][0]["content_sha256"]
    with pytest.raises(ValueError, match="duplicate final content"):
        CalibrationSet.model_validate(data)


def test_absent_class_has_null_uncertainty_and_fails_qualification():
    data = cohort(0, 20)
    rules = policy(data)
    report = assess_calibration(
        data, rules, assessment(data, rules), current_snapshot=data.snapshot
    )
    assert report["summary"]["positive_recall"]["interval"] is None
    assert "qualification_check_failed:positive_recall:lower" in report["eligibility"]["reasons"]


def test_frozen_policy_and_current_snapshot_drift_are_checked():
    data = cohort()
    rules = policy(data)
    run = assessment(data, rules)
    changed = data.snapshot.model_copy(update={"rubric_version": "2"})
    report = assess_calibration(data, rules, run, current_snapshot=changed)
    assert "snapshot_or_criteria_drift" in report["eligibility"]["reasons"]
    rules.minimum_positive_recall_lower = 0.0
    with pytest.raises(ValueError, match="frozen"):
        assess_calibration(data, rules, run, current_snapshot=data.snapshot)
    run.policy_sha256 = digest(rules)
    run.started_at = rules.frozen_at
    with pytest.raises(ValueError, match="before final"):
        assess_calibration(data, rules, run, current_snapshot=data.snapshot)


def test_synthetic_perfect_results_never_establish_domain_qualification():
    data = cohort(50, 50)
    rules = policy(data)
    report = assess_calibration(
        data,
        rules,
        assessment(data, rules, [row.human_label for row in data.rows]),
        current_snapshot=data.snapshot,
    )
    assert not any(
        reason.startswith("qualification_check_failed")
        for reason in report["eligibility"]["reasons"]
    )
    assert report["status"] == "unqualified"
    assert set(report["eligibility"]["reasons"]) == {
        "synthetic_labels_do_not_qualify_a_domain",
        "human_domain_review_required",
        "label_access_or_adjudication_unverified",
        "raw_judge_evidence_unverified",
    }


def test_cli_preserves_nulls_and_never_overwrites_inputs(tmp_path: Path):
    data = cohort(0, 3)
    rules = policy(data)
    run = assessment(data, rules)
    paths = []
    for name, value in (
        ("data", data),
        ("policy", rules),
        ("assessment", run),
        ("snapshot", data.snapshot),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(value.model_dump_json())
        paths.append(path)
    args = ["assess-judge-calibration", *map(str, paths[:3]), "--current-snapshot", str(paths[3])]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["summary"]["positive_recall"]["value"] is None
    original = paths[0].read_bytes()
    refusal = CliRunner().invoke(cli, [*args, "--output", str(paths[0])])
    assert refusal.exit_code != 0
    assert paths[0].read_bytes() == original
    private = data.model_dump()
    private["unexpected_private_field"] = "private-sentinel-do-not-echo"
    paths[0].write_text(json.dumps(private))
    refused = CliRunner().invoke(cli, args)
    assert refused.exit_code != 0
    assert "private-sentinel" not in refused.output
    assert "schema validation failed" in refused.output


def test_strict_judgment_cannot_claim_measured_with_missing_reason():
    with pytest.raises(ValidationError):
        Judgment(label=None, reason=None, raw=ArtifactReference.model_validate(reference()))


def test_simulated_receipt_binding_and_artifact_tampering(tmp_path: Path):
    # These are fabricated contract fixtures, not an actual human qualification.
    evidence = tmp_path / "fixture-evidence.txt"
    evidence.write_bytes(b"explicitly synthetic receipt test")
    ref = ArtifactReference(
        uri=str(evidence),
        sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
        unavailable_reason=None,
    )
    data = cohort(50, 50)
    for row in data.rows:
        row.label_source = "human"  # Exercise supplied human-claim boundary only.
        row.consent = ref
        row.critique = ref
        row.adjudication = ref
    rules = policy(data)
    run = assessment(data, rules, [row.human_label for row in data.rows])
    for item in run.items:
        item.forward.raw = ref
        item.reverse.raw = ref
    receipt = DomainReview(
        reviewer="simulated reviewer",
        reviewer_domain=data.snapshot.domain,
        representative_labels_reviewed=True,
        untouched_final_set_reviewed=True,
        snapshot_sha256=digest(data.snapshot),
        calibration_set_sha256=digest(data),
        policy_sha256=digest(rules),
        assessment_sha256=digest(run),
        approved_at="2026-09-03T00:00:00Z",
        access_owner="fixture-author",
    )
    path = tmp_path / "simulated-review.json"
    path.write_text(receipt.model_dump_json())
    report = assess_calibration(data, rules, run, current_snapshot=data.snapshot, review_path=path)
    assert report["status"] == "qualified_by_declared_human_review"
    assert report["human_review"]["authentication"] == "external_access_owner_responsibility"
    evidence.write_bytes(b"changed fixture evidence")
    refused = assess_calibration(data, rules, run, current_snapshot=data.snapshot, review_path=path)
    assert "raw_judge_evidence_unverified" in refused["eligibility"]["reasons"]
    assert "label_access_or_adjudication_unverified" in refused["eligibility"]["reasons"]
    receipt.policy_sha256 = "0" * 64
    path.write_text(receipt.model_dump_json())
    assert (
        "human_review_scope_mismatch"
        in assess_calibration(data, rules, run, current_snapshot=data.snapshot, review_path=path)[
            "eligibility"
        ]["reasons"]
    )
