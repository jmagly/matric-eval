"""Lossless adapter for frozen StudyObservation rows; no statistical policy changes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from matric_eval.results.contract import (
    ArtifactReference,
    DataReference,
    Digest,
    JudgeIdentity,
    Observation,
    ObservationIdentity,
    Record,
)
from matric_eval.studies.analysis import StudyObservation

# The inverse is exact. In particular the study's declared timeout remains zero.
STATUS_MAP = {
    "observed": ("completed", "observed", None),
    "model-timeout": ("completed", "model_timeout", "study:model-timeout"),
    "infrastructure-error": ("failed", "infrastructure_error", "study:infrastructure-error"),
    "judge-parse-failure": ("completed", "grader_failed", "study:judge-parse-failure"),
}


class AdaptedStudyObservation(Record):
    """Study identity sidecar retains original hashes and explicit data-role evidence."""

    result_schema_version: Literal["2"]
    adapter_version: Literal["study-observation/1"]
    protocol_sha256: Digest
    manifest_sha256: Digest
    data: DataReference
    observation: Observation


def from_study(
    source: StudyObservation,
    *,
    trial_id: str,
    attempt_id: str,
    data: DataReference,
    artifacts: list[ArtifactReference],
    judge: JudgeIdentity | None = None,
) -> AdaptedStudyObservation:
    """Require trial/attempt/data references; never invent them from a legacy row."""
    source = StudyObservation.from_dict(asdict(source), 1)
    identity = ObservationIdentity(
        run_id=source.study_id,
        model_id=source.model_id,
        benchmark_id=source.allocation_id,
        allocation_id=source.allocation_id,
        sample_id=source.sample_id,
        trial_id=trial_id,
        metric_id=source.metric_id,
    )
    execution, outcome, reason = STATUS_MAP[source.status]
    return AdaptedStudyObservation.model_validate(
        {
            "result_schema_version": "2",
            "adapter_version": "study-observation/1",
            "protocol_sha256": source.protocol_sha256,
            "manifest_sha256": source.manifest_sha256,
            "data": data.model_dump(),
            "observation": {
                "observation_id": identity.logical_id(),
                "identity": identity.model_dump(),
                "attempt_id": attempt_id,
                "previous_attempt_id": None,
                "accepted": True,
                "execution": execution,
                "outcome": outcome,
                "value": source.value,
                "reason": reason,
                "native_status": source.status,
                "judge": judge.model_dump() if judge else None,
                "artifacts": [item.model_dump() for item in artifacts],
            },
        }
    )


def to_study(adapted: AdaptedStudyObservation) -> StudyObservation:
    """Reject unsupported projections instead of coercing new outcomes into old rows."""
    adapted = AdaptedStudyObservation.model_validate(adapted.model_dump())
    row = adapted.observation
    if adapted.result_schema_version != "2" or adapted.adapter_version != "study-observation/1":
        raise ValueError("unsupported study adapter version")
    if STATUS_MAP.get(row.native_status) != (row.execution, row.outcome, row.reason):
        raise ValueError("observation has no lossless study status projection")
    if not row.accepted or row.previous_attempt_id is not None:
        raise ValueError("legacy study rows cannot represent retry lineage")
    if row.identity.benchmark_id != row.identity.allocation_id:
        raise ValueError("study allocation identity was changed")
    return StudyObservation.from_dict(
        {
            "study_id": row.identity.run_id,
            "protocol_sha256": adapted.protocol_sha256,
            "manifest_sha256": adapted.manifest_sha256,
            "model_id": row.identity.model_id,
            "allocation_id": row.identity.allocation_id,
            "sample_id": row.identity.sample_id,
            "metric_id": row.identity.metric_id,
            "status": row.native_status,
            "value": row.value,
        },
        1,
    )
