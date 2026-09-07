"""Versioned, domain-specific calibration evidence for binary grader decisions.

Labels, partitions and human review are supplied evidence, never inferred from
agreement. This module does not run a judge or modify historical study records.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any, Literal, Self
from urllib.parse import unquote, urlparse

from pydantic import Field, model_validator

from matric_eval.contamination.diagnostics import strict_json
from matric_eval.results.contract import ArtifactReference, DataReference, Digest, Record, Text
from matric_eval.studies.analysis import wilson_interval


def digest(value: Record) -> str:
    payload = json.dumps(value.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("calibration times require an explicit timezone")
    return parsed


def _verified_local_artifact(reference: ArtifactReference) -> bool:
    if reference.sha256 is None:
        return False
    parsed = urlparse(reference.uri)
    if parsed.scheme not in {"", "file"} or parsed.netloc:
        return False
    path = Path(unquote(parsed.path))
    if not path.is_absolute() or not path.is_file():
        return False
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == reference.sha256
    except OSError:
        return False


class JudgeSnapshot(Record):
    domain: Text
    task: Text
    rubric_version: Text
    rubric_sha256: Digest
    judge_id: Text
    judge_snapshot_sha256: Digest
    model_snapshot_sha256: Digest
    prompt_sha256: Digest
    configuration_sha256: Digest
    positive_label: Text
    positive_meaning: Text


class CalibrationRow(Record):
    data: DataReference
    content_sha256: Digest
    rubric_version: Text
    purpose: Literal["rubric_discovery", "prompt_example", "development_tuning", "final_assessment"]
    access: Literal["permitted", "restricted"]
    access_owner: Text
    license_id: Text
    consent: ArtifactReference
    human_label: bool
    label_source: Literal["human", "synthetic"]
    annotators: list[Text] = Field(min_length=1)
    critique: ArtifactReference
    adjudication: ArtifactReference
    slices: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def partition_boundary(self) -> Self:
        if self.purpose == "final_assessment" and self.data.role != "final_test":
            raise ValueError("final assessment requires the shared final_test partition role")
        if self.purpose != "final_assessment" and self.data.role == "final_test":
            raise ValueError("final-test material cannot become a prompt example or tuning row")
        if self.data.role in {"unknown", "training"}:
            raise ValueError(
                "calibration use requires an explicitly permitted evaluation partition"
            )
        if len(set(self.annotators)) != len(self.annotators):
            raise ValueError("annotator identities must be unique")
        return self


class CalibrationSet(Record):
    calibration_schema_version: Literal["1"] = "1"
    snapshot: JudgeSnapshot
    sampling_frame: Text
    independent_unit: Text
    rows: list[CalibrationRow] = Field(min_length=1)

    @model_validator(mode="after")
    def identities(self) -> Self:
        if any(row.rubric_version != self.snapshot.rubric_version for row in self.rows):
            raise ValueError("row rubric differs from the frozen snapshot")
        keys = [(row.data.source_id, row.data.row_id) for row in self.rows]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate calibration row identity")
        groups: dict[str, set[str]] = {}
        for row in self.rows:
            groups.setdefault(row.content_sha256, set()).add(row.purpose)
        if any("final_assessment" in roles and len(roles) > 1 for roles in groups.values()):
            raise ValueError("cross-partition duplicate would disclose final assessment material")
        final_hashes = [
            row.content_sha256 for row in self.rows if row.purpose == "final_assessment"
        ]
        if len(set(final_hashes)) != len(final_hashes):
            raise ValueError("duplicate final content cannot count as independent evidence")
        return self


class QualificationPolicy(Record):
    version: Literal["1"] = "1"
    application: Text
    snapshot_sha256: Digest
    calibration_set_sha256: Digest
    frozen_at: Text
    confidence: float = Field(gt=0, lt=1)
    minimum_positive_recall_lower: float = Field(ge=0, le=1)
    maximum_false_positive_upper: float = Field(ge=0, le=1)
    minimum_coverage_lower: float = Field(ge=0, le=1)
    maximum_order_inconsistency_upper: float = Field(ge=0, le=1)
    require_reversal: bool
    rationale: Text

    @model_validator(mode="after")
    def time(self) -> Self:
        instant(self.frozen_at)
        return self


class Judgment(Record):
    label: bool | None
    reason: Text | None
    raw: ArtifactReference

    @model_validator(mode="after")
    def abstention(self) -> Self:
        if (self.label is None) != (self.reason is not None):
            raise ValueError("unavailable judgments require a reason; measured labels do not")
        return self


def parse_binary_judgment(payload: str, raw: ArtifactReference) -> Judgment:
    """A narrow import adapter: malformed output is an abstention, never midpoint."""
    try:
        value = strict_json(payload)
        if (
            not isinstance(value, dict)
            or set(value) != {"label"}
            or type(value["label"]) is not bool
        ):
            raise ValueError("expected one boolean label")
        return Judgment(label=value["label"], reason=None, raw=raw)
    except (ValueError, TypeError):
        return Judgment(label=None, reason="malformed_judgment", raw=raw)


class AssessmentItem(Record):
    source_id: Text
    row_id: Text
    forward: Judgment
    reverse: Judgment | None
    reverse_mapping: Literal["same-candidate-rubric-label/1"]


class Assessment(Record):
    assessment_schema_version: Literal["1"] = "1"
    snapshot_sha256: Digest
    calibration_set_sha256: Digest
    policy_sha256: Digest
    started_at: Text
    items: list[AssessmentItem]

    @model_validator(mode="after")
    def identities(self) -> Self:
        instant(self.started_at)
        keys = [(item.source_id, item.row_id) for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate assessment identity")
        return self


class DomainReview(Record):
    """Human-authored receipt claims; caller access control authenticates the author."""

    version: Literal["1"] = "1"
    reviewer: Text
    reviewer_domain: Text
    representative_labels_reviewed: Literal[True]
    untouched_final_set_reviewed: Literal[True]
    snapshot_sha256: Digest
    calibration_set_sha256: Digest
    policy_sha256: Digest
    assessment_sha256: Digest
    approved_at: Text
    access_owner: Text

    @model_validator(mode="after")
    def time(self) -> Self:
        instant(self.approved_at)
        return self


def _rate(numerator: int, denominator: int, confidence: float) -> dict[str, Any]:
    if not denominator:
        return {
            "numerator": numerator,
            "denominator": 0,
            "value": None,
            "interval": None,
            "reason": "no_independent_items",
        }
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    lower, upper = wilson_interval(numerator, denominator, z=z)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator,
        "interval": {"lower": lower, "upper": upper},
        "reason": None,
    }


def assess_calibration(
    calibration: CalibrationSet,
    policy: QualificationPolicy,
    assessment: Assessment,
    *,
    current_snapshot: JudgeSnapshot,
    review_path: Path | None = None,
) -> dict[str, Any]:
    """Reconcile the entire frozen final cohort, with class-conditional intervals.

    One row per declared independent unit is required for this Wilson profile.
    Arbitrary repeated labels are not independent Bernoulli evidence.
    """
    calibration = CalibrationSet.model_validate(calibration.model_dump())
    policy = QualificationPolicy.model_validate(policy.model_dump())
    assessment = Assessment.model_validate(assessment.model_dump())
    snapshot_hash, set_hash, policy_hash = (
        digest(calibration.snapshot),
        digest(calibration),
        digest(policy),
    )
    if (policy.snapshot_sha256, policy.calibration_set_sha256) != (snapshot_hash, set_hash):
        raise ValueError("qualification policy is not bound to this snapshot and set")
    if (
        assessment.snapshot_sha256,
        assessment.calibration_set_sha256,
        assessment.policy_sha256,
    ) != (snapshot_hash, set_hash, policy_hash):
        raise ValueError("assessment differs from the frozen qualification policy")
    if instant(policy.frozen_at) >= instant(assessment.started_at):
        raise ValueError("policy must be frozen before final assessment")
    rows = [row for row in calibration.rows if row.purpose == "final_assessment"]
    if any(row.access != "permitted" for row in rows):
        raise PermissionError("restricted calibration labels require their access owner")
    units = [row.data.independent_unit_id for row in rows]
    if len(set(units)) != len(units):
        raise ValueError(
            "repeated independent units require a separately qualified clustered method"
        )
    supplied = {(item.source_id, item.row_id): item for item in assessment.items}
    selected = {(row.data.source_id, row.data.row_id) for row in rows}
    if set(supplied) - selected:
        raise ValueError("assessment contains unplanned or non-final items")
    records: list[dict[str, Any]] = []
    for row in rows:
        item = supplied.get((row.data.source_id, row.data.row_id))
        label: bool | None = None
        reason: str | None = "not_assessed"
        order = "unavailable"
        if item:
            label, reason = item.forward.label, item.forward.reason
            if policy.require_reversal:
                if item.reverse is None or item.reverse.label is None or item.forward.label is None:
                    label, reason = None, "order_check_unavailable"
                elif item.forward.label != item.reverse.label:
                    label, reason, order = None, "order_inconsistent", "inconsistent"
                else:
                    order = "consistent"
            else:
                order = "not_required"
        records.append(
            {
                "source_id": row.data.source_id,
                "row_id": row.data.row_id,
                "independent_unit_id": row.data.independent_unit_id,
                "expected": row.human_label,
                "predicted": label,
                "reason": reason,
                "order_status": order,
                "slices": row.slices,
                "position_outcomes": item.model_dump() if item else None,
            }
        )

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        positives = sum(item["expected"] for item in items)
        negatives = len(items) - positives
        measured = [item for item in items if item["predicted"] is not None]
        tp = sum(item["expected"] and item["predicted"] is True for item in items)
        fp = sum(not item["expected"] and item["predicted"] is True for item in items)
        tn = sum(not item["expected"] and item["predicted"] is False for item in items)
        fn = sum(item["expected"] and item["predicted"] is False for item in items)
        orders = [item for item in items if item["order_status"] in {"consistent", "inconsistent"}]
        return {
            "planned": len(items),
            "scored": len(measured),
            "abstained": len(items) - len(measured),
            "confusion": {
                "true_positive": tp,
                "false_positive": fp,
                "true_negative": tn,
                "false_negative": fn,
                "positive_abstention": positives - tp - fn,
                "negative_abstention": negatives - tn - fp,
            },
            "positive_prevalence": _rate(positives, len(items), policy.confidence),
            "positive_recall": _rate(tp, positives, policy.confidence),
            "false_positive_rate": _rate(fp, negatives, policy.confidence),
            "false_negative_rate": _rate(fn, positives, policy.confidence),
            "coverage": _rate(len(measured), len(items), policy.confidence),
            "agreement_among_scored": _rate(tp + tn, len(measured), policy.confidence),
            "order_inconsistency": _rate(
                sum(item["order_status"] == "inconsistent" for item in orders),
                len(orders),
                policy.confidence,
            ),
        }

    summary = summarize(records)
    reasons = []
    if digest(current_snapshot) != snapshot_hash:
        reasons.append("snapshot_or_criteria_drift")
    if not rows:
        reasons.append("no_final_assessment_rows")
    if any(row.label_source != "human" for row in rows):
        reasons.append("synthetic_labels_do_not_qualify_a_domain")
    if any(
        not all(
            _verified_local_artifact(ref) for ref in (row.consent, row.adjudication, row.critique)
        )
        for row in rows
    ):
        reasons.append("label_access_or_adjudication_unverified")
    decisions = [
        decision
        for item in assessment.items
        for decision in (
            [item.forward, item.reverse] if policy.require_reversal else [item.forward]
        )
        if decision is not None and decision.label is not None
    ]
    if any(not _verified_local_artifact(decision.raw) for decision in decisions):
        reasons.append("raw_judge_evidence_unverified")
    checks = [
        ("positive_recall", "lower", policy.minimum_positive_recall_lower, True),
        ("false_positive_rate", "upper", policy.maximum_false_positive_upper, False),
        ("coverage", "lower", policy.minimum_coverage_lower, True),
    ]
    if policy.require_reversal:
        checks.append(
            ("order_inconsistency", "upper", policy.maximum_order_inconsistency_upper, False)
        )
    for name, bound, threshold, minimum in checks:
        interval = summary[name]["interval"]
        if interval is None or (
            interval[bound] < threshold if minimum else interval[bound] > threshold
        ):
            reasons.append(f"qualification_check_failed:{name}:{bound}")
    review_evidence = None
    if review_path is None:
        reasons.append("human_domain_review_required")
    else:
        payload = review_path.read_bytes()
        review = DomainReview.model_validate(strict_json(payload.decode("utf-8")))
        expected = (snapshot_hash, set_hash, policy_hash, digest(assessment))
        if (
            review.snapshot_sha256,
            review.calibration_set_sha256,
            review.policy_sha256,
            review.assessment_sha256,
        ) != expected or review.reviewer_domain != calibration.snapshot.domain:
            reasons.append("human_review_scope_mismatch")
        if instant(review.approved_at) <= instant(assessment.started_at):
            reasons.append("human_review_precedes_assessment")
        review_evidence = {
            "uri": str(review_path.resolve()),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "reviewer": review.reviewer,
            "authentication": "external_access_owner_responsibility",
        }
    return {
        "qualification_schema_version": "1",
        "status": "unqualified" if reasons else "qualified_by_declared_human_review",
        "domain": calibration.snapshot.domain,
        "application": policy.application,
        "positive_label": calibration.snapshot.positive_label,
        "positive_meaning": calibration.snapshot.positive_meaning,
        "snapshot_sha256": snapshot_hash,
        "current_snapshot_sha256": digest(current_snapshot),
        "calibration_set_sha256": set_hash,
        "policy_sha256": policy_hash,
        "assessment_sha256": digest(assessment),
        "policy": policy.model_dump(),
        "eligibility": {"eligible": not reasons, "reasons": reasons},
        "summary": summary,
        "records": records,
        "slices": {
            name: summarize([item for item in records if name in item["slices"]])
            for name in sorted({name for item in records for name in item["slices"]})
        },
        "human_review": review_evidence,
        "limits": [
            "declared_independence_not_empirically_proven",
            "wilson_marginal_intervals_not_simultaneous",
            "human_identity_authenticated_by_access_owner",
            "domain_and_snapshot_specific",
        ],
    }


def prompt_example_manifest(calibration: CalibrationSet) -> dict[str, Any]:
    """Reference-only manifest; reject disallowed requests without exporting text."""
    calibration = CalibrationSet.model_validate(calibration.model_dump())
    rows = []
    for row in calibration.rows:
        if row.purpose != "prompt_example":
            continue
        if (
            row.data.role == "final_test"
            or row.access != "permitted"
            or not _verified_local_artifact(row.consent)
        ):
            raise ValueError("prompt example access or partition is not permitted")
        rows.append(
            {
                "data": row.data.model_dump(),
                "content_sha256": row.content_sha256,
                "rubric_version": row.rubric_version,
            }
        )
    return {
        "example_manifest_version": "1",
        "calibration_set_sha256": digest(calibration),
        "rows": rows,
    }
