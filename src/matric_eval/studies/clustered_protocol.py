"""New opt-in clustered design declarations; historical study protocols are untouched."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from matric_eval.results.contract import Count, Digest, Number, Record, Text

PositiveCount = Annotated[Count, Field(gt=0)]


def canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Hypothesis(Record):
    hypothesis_id: Text
    source_model: Text
    intervention_model: Text
    metric_id: Text
    metric_version: Text
    units: Text
    minimum: Number
    maximum: Number
    primary: bool
    direction: Literal["two_sided_difference", "noninferiority"]
    practical_effect: Number
    planning_true_difference: Number
    noninferiority_margin: Number | None

    @model_validator(mode="after")
    def defined_scale(self) -> Self:
        if (
            self.source_model == self.intervention_model
            or not 0 < self.maximum - self.minimum < math.inf
        ):
            raise ValueError("distinct model roles and a finite nonempty score range are required")
        score_range = self.maximum - self.minimum
        if not 0 < self.practical_effect <= score_range:
            raise ValueError(
                "practical effect must be positive and within the declared score range"
            )
        if not -score_range <= self.planning_true_difference <= score_range:
            raise ValueError("planning difference is impossible under the declared score bounds")
        if (self.direction == "noninferiority") != (self.noninferiority_margin is not None):
            raise ValueError("only noninferiority hypotheses require an explicit signed margin")
        if (
            self.noninferiority_margin is not None
            and not -score_range <= self.noninferiority_margin <= 0
        ):
            raise ValueError(
                "noninferiority margin must lie between minus the score range and zero"
            )
        return self


class Stratum(Record):
    stratum_id: Text
    weight: Annotated[Number, Field(ge=0, le=1)]
    weight_source: Text


class TaskMembership(Record):
    task_id: Text
    cluster_id: Text
    stratum_id: Text


class PlanningDeclaration(Record):
    assumptions: list[Text] = Field(min_length=1)
    sensitivity_variances: list[Annotated[Number, Field(gt=0)]] = Field(min_length=1)
    sensitivity_correlations: list[Annotated[Number, Field(ge=0, le=1)]] = Field(min_length=1)
    tasks_per_cluster: PositiveCount
    target_power: Annotated[Number, Field(gt=0.5, lt=1)]
    target_half_width: Annotated[Number, Field(gt=0)]


class ClusteredProtocol(Record):
    protocol_version: Literal["2"]
    study_id: Text
    estimand: Text
    target_population: Text
    sampling_frame_sha256: Digest
    target: Literal["superpopulation"]
    sampling: Literal["equal_probability_exchangeable_clusters"]
    independence_status: Literal["declared_not_proven"]
    independent_unit: Text
    task_unit: Text
    weighting: Literal["equal_task", "equal_cluster"]
    within_cluster_weights: Literal["equal_task"]
    within_task_rule: Text
    repetition_interpretation: Text
    pairing_keys: list[Text] = Field(min_length=1)
    trial_alignment: Text
    hypotheses: list[Hypothesis] = Field(min_length=1)
    primary_family: list[Text] = Field(min_length=1)
    family_alpha: Annotated[Number, Field(gt=0, lt=1)]
    multiplicity: Literal["holm_declared_tests_unavailable"]
    strata: list[Stratum] = Field(min_length=1)
    manifest: list[TaskMembership]
    missingness: Literal["requested_target_bounds_complete_pair_conditional/1"]
    inference_method: Literal["paired_whole_cluster_percentile/1"]
    confidence_level: Annotated[Number, Field(gt=0, lt=1)]
    bootstrap_replicates: Annotated[PositiveCount, Field(le=100000)]
    analysis_seed: Count
    sufficiency_rule: Text
    qualification: Literal["unqualified"]
    planning: PlanningDeclaration
    task_budget: Count
    cluster_budget: Count
    stopping_rule: Literal["fixed_budget/1"]
    outcome_access: Literal["after_enrollment_closed"]
    deviation_log_location: Text

    @model_validator(mode="after")
    def frozen_scope(self) -> Self:
        hypothesis_ids = [item.hypothesis_id for item in self.hypotheses]
        if len(set(hypothesis_ids)) != len(hypothesis_ids):
            raise ValueError("duplicate hypotheses")
        primary = {item.hypothesis_id for item in self.hypotheses if item.primary}
        if set(self.primary_family) != primary or len(set(self.primary_family)) != len(
            self.primary_family
        ):
            raise ValueError(
                "primary family must retain every and only declared primary hypothesis"
            )
        for hypothesis in self.hypotheses:
            if hypothesis.primary and any(
                math.sqrt(variance) > hypothesis.maximum - hypothesis.minimum
                for variance in self.planning.sensitivity_variances
            ):
                raise ValueError(
                    "assumed paired-difference variance exceeds its bounded-score maximum"
                )
        stratum_ids = [item.stratum_id for item in self.strata]
        if len(set(stratum_ids)) != len(stratum_ids) or not math.isclose(
            math.fsum(item.weight for item in self.strata), 1, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("unique strata with fixed weights summing to one are required")
        tasks: set[str] = set()
        clusters: dict[str, str] = {}
        for row in self.manifest:
            if row.task_id in tasks or row.stratum_id not in stratum_ids:
                raise ValueError("duplicate task or unknown stratum")
            if row.cluster_id in clusters and clusters[row.cluster_id] != row.stratum_id:
                raise ValueError("crossed clusters or clusters split across strata are unsupported")
            tasks.add(row.task_id)
            clusters[row.cluster_id] = row.stratum_id
        if len(tasks) != self.task_budget or len(clusters) != self.cluster_budget:
            raise ValueError("fixed budgets must equal the requested task/cluster manifest")
        return self

    @property
    def sha256(self) -> str:
        return content_hash(self.model_dump())


def freeze_protocol(path: Path, protocol: ClusteredProtocol) -> str:
    """Publish a new plan once; callers must do this before outcome access."""
    validated = ClusteredProtocol.model_validate(protocol.model_dump())
    with path.open("x", encoding="utf-8") as output:
        output.write(canonical(validated.model_dump()) + "\n")
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return validated.sha256


def legacy_compatibility_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the old loader while preserving the supplied protocol document."""
    from matric_eval.studies.protocol import StudyProtocol

    StudyProtocol.from_dict(payload)
    return {
        "compatibility_view_version": "1",
        "assumptions": [
            "legacy_sample_independence_assumed",
            "legacy_infrastructure_exclusion_and_remaining_cohort_bounds",
        ],
        "source_sha256": content_hash(payload),
        "protocol": json.loads(canonical(payload)),
    }
