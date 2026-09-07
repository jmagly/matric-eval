"""Version 2 wire contract. Native logs and historical study records remain authoritative.

All fields are explicit on the wire; readers reject unknown versions and fields.
Logical observation IDs exclude attempts so a retry cannot create another trial.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Number = Annotated[float, Field(allow_inf_nan=False, strict=True)]


def _json_integer(value: object) -> object:
    # JSON Schema integers include 9.0; JavaScript cannot distinguish its spelling
    # from 9 after parsing. Preserve numeric agreement without coercing bool/text.
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


Count = Annotated[
    int, Field(ge=0, le=9007199254740991, strict=True), BeforeValidator(_json_integer)
]
Execution = Literal["completed", "partial", "failed", "cancelled", "not_attempted", "unknown"]
Outcome = Literal[
    "observed",
    "model_timeout",
    "infrastructure_error",
    "grader_failed",
    "cancelled",
    "not_attempted",
    "unavailable",
    "legacy_unknown",
]
PartitionRole = Literal[
    "development",
    "validation",
    "calibration",
    "final_test",
    "training",
    "unknown",
]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ArtifactReference(Record):
    uri: Text
    sha256: Digest | None
    unavailable_reason: Text | None

    @model_validator(mode="after")
    def digest_evidence(self) -> Self:
        if (self.sha256 is None) != (self.unavailable_reason is not None):
            raise ValueError("artifact needs either a digest or an unavailable reason")
        return self


class DataReference(Record):
    partition_schema_version: Literal["1"]
    role: PartitionRole
    row_id: Text
    source_id: Text
    independent_unit_id: Text


class Eligibility(Record):
    eligible: bool
    reasons: list[Text]

    @model_validator(mode="after")
    def reasons_match(self) -> Self:
        if self.eligible == bool(self.reasons):
            raise ValueError("eligible results have no reasons; ineligible results require reasons")
        return self


class MetricDescriptor(Record):
    metric_id: Text
    version: Text
    scorer_id: Text
    value_kind: Literal["binary", "continuous", "count"]
    units: Text
    direction: Literal["higher", "lower", "neutral"]
    minimum: Number | None
    maximum: Number | None
    independent_unit: Text
    missingness_policy: Text
    aggregation_id: Text | None
    timeout_value: Number | None

    def check_value(self, value: float) -> None:
        if self.minimum is not None and value < self.minimum:
            raise ValueError("metric value below minimum")
        if self.maximum is not None and value > self.maximum:
            raise ValueError("metric value above maximum")
        if self.value_kind == "binary" and value not in (0.0, 1.0):
            raise ValueError("binary value must be zero or one")
        if self.value_kind == "count" and (value < 0 or not value.is_integer()):
            raise ValueError("count value must be a nonnegative integer")

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("metric minimum exceeds maximum")
        if self.timeout_value is not None:
            self.check_value(self.timeout_value)
        return self


class JudgeIdentity(Record):
    judge_id: Text
    configuration_sha256: Digest
    reversal_policy: Text
    retry_policy: Text
    calibration: ArtifactReference | None


class Selection(Record):
    allocation_id: Text
    sample_id: Text
    trial_id: Text
    data: DataReference

    def key(self) -> tuple[str, str, str]:
        return self.allocation_id, self.sample_id, self.trial_id


class ObservationIdentity(Record):
    run_id: Text
    model_id: Text
    benchmark_id: Text
    allocation_id: Text
    sample_id: Text
    trial_id: Text
    metric_id: Text

    def logical_id(self) -> str:
        """Hash an ordered UTF-8 JSON string array; independent of execution attempts."""
        parts = [
            self.run_id,
            self.model_id,
            self.benchmark_id,
            self.allocation_id,
            self.sample_id,
            self.trial_id,
            self.metric_id,
        ]
        return hashlib.sha256(
            json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def selection_key(self) -> tuple[str, str, str]:
        return self.allocation_id, self.sample_id, self.trial_id


class Observation(Record):
    observation_id: Digest
    identity: ObservationIdentity
    attempt_id: Text
    previous_attempt_id: Text | None
    accepted: bool
    execution: Execution
    outcome: Outcome
    value: Number | None
    reason: Text | None
    native_status: Text
    judge: JudgeIdentity | None
    artifacts: list[ArtifactReference]

    @model_validator(mode="after")
    def measurement(self) -> Self:
        if self.observation_id != self.identity.logical_id():
            raise ValueError("observation_id does not match logical identity")
        if self.previous_attempt_id == self.attempt_id:
            raise ValueError("attempt cannot retry itself")
        if self.outcome == "observed":
            if self.value is None or self.execution != "completed" or self.reason is not None:
                raise ValueError("observed requires completed execution, a value, and no reason")
        else:
            if self.reason is None:
                raise ValueError("non-observed outcome requires a reason")
            if self.outcome != "model_timeout" and self.value is not None:
                raise ValueError("unmeasured outcome must have a null value")
        expected = {
            "infrastructure_error": "failed",
            "cancelled": "cancelled",
            "not_attempted": "not_attempted",
            "legacy_unknown": "unknown",
            "grader_failed": "completed",
        }
        if self.outcome in expected and self.execution != expected[self.outcome]:
            raise ValueError("execution contradicts measurement outcome")
        return self


class Estimate(Record):
    value: Number | None
    reason: Text | None
    numerator: Number | None
    denominator: Number | None
    method: Text
    eligibility: Eligibility

    @model_validator(mode="after")
    def missingness(self) -> Self:
        if (self.value is None) != (self.reason is not None):
            raise ValueError("null estimate requires a reason; measured estimate has no reason")
        if self.value is None and self.eligibility.eligible:
            raise ValueError("null estimate is ineligible")
        if self.denominator is not None and self.denominator <= 0:
            raise ValueError("estimate denominator must be positive")
        return self


class Coverage(Record):
    requested: Count
    attempted: Count
    terminal: Count
    completed: Count
    failed: Count
    cancelled: Count
    not_attempted: Count
    unknown: Count

    @model_validator(mode="after")
    def reconcile(self) -> Self:
        if self.terminal != self.completed + self.failed + self.cancelled:
            raise ValueError("terminal = completed + failed + cancelled")
        if self.requested != self.terminal + self.not_attempted + self.unknown:
            raise ValueError("requested = terminal + not_attempted + unknown")
        if self.attempted != self.terminal:
            raise ValueError("terminal envelope attempted = terminal; unknown is not inferred")
        return self


class MetricResult(Record):
    descriptor: MetricDescriptor
    estimate: Estimate
    scored: Count
    outcome_counts: dict[Outcome, Count]


class BenchmarkResult(Record):
    benchmark_id: Text
    protocol_sha256: Digest | None
    manifest_sha256: Digest | None
    execution: Execution
    eligibility: Eligibility
    primary_metric_id: Text | None
    primary_estimate: Estimate
    metrics: dict[Text, MetricResult]
    selection: list[Selection]
    observations: list[Observation]
    coverage: Coverage
    artifacts: list[ArtifactReference]

    @model_validator(mode="after")
    def identities_and_counts(self) -> Self:
        selected = {row.key() for row in self.selection}
        if len(selected) != len(self.selection) or len(selected) != self.coverage.requested:
            raise ValueError("selection must be unique and match requested count")
        attempts: dict[tuple[str, str], Observation] = {}
        accepted: dict[tuple[tuple[str, str, str], str], Observation] = {}
        executions: dict[tuple[str, str, str], str] = {}
        for row in self.observations:
            key = row.identity.selection_key()
            metric_id = row.identity.metric_id
            if key not in selected or row.identity.benchmark_id != self.benchmark_id:
                raise ValueError("observation outside selected benchmark manifest")
            if metric_id not in self.metrics:
                raise ValueError("observation metric is undeclared")
            attempt_key = row.observation_id, row.attempt_id
            if attempt_key in attempts:
                raise ValueError("duplicate observation attempt")
            if row.previous_attempt_id is not None:
                previous = attempts.get((row.observation_id, row.previous_attempt_id))
                if previous is None or previous.accepted:
                    raise ValueError("retry predecessor must precede retry and be superseded")
            attempts[attempt_key] = row
            descriptor = self.metrics[metric_id].descriptor
            if row.value is not None:
                descriptor.check_value(row.value)
            if row.outcome == "model_timeout" and row.value != descriptor.timeout_value:
                raise ValueError("timeout value must follow declared metric policy")
            if row.accepted:
                accepted_key = key, metric_id
                if accepted_key in accepted:
                    raise ValueError("multiple accepted attempts for one logical observation")
                accepted[accepted_key] = row
                if key in executions and executions[key] != row.execution:
                    raise ValueError("metrics disagree about sample execution")
                executions[key] = row.execution
        if len(accepted) != len(selected) * len(self.metrics):
            raise ValueError("every selected unit requires one accepted outcome per metric")
        if selected and not self.metrics:
            raise ValueError("selected observations require declared metrics")
        for status in ("completed", "failed", "cancelled", "not_attempted", "unknown"):
            if getattr(self.coverage, status) != sum(
                value == status for value in executions.values()
            ):
                raise ValueError("coverage differs from accepted observations")
        for metric_id, metric in self.metrics.items():
            if metric.descriptor.metric_id != metric_id:
                raise ValueError("metric map key differs from descriptor identity")
            rows = [row for (_, mid), row in accepted.items() if mid == metric_id]
            counts = {
                outcome: sum(row.outcome == outcome for row in rows)
                for outcome in metric.outcome_counts
            }
            if counts != metric.outcome_counts or sum(counts.values()) != len(rows):
                raise ValueError("metric outcome counts differ from accepted observations")
            if metric.scored != sum(row.value is not None for row in rows):
                raise ValueError("metric scored count differs from measured observations")
            if metric.scored == 0 and metric.estimate.value is not None:
                raise ValueError("all-unscored metric cannot have an estimate")
            value = metric.estimate.value
            if value is not None:
                if metric.descriptor.minimum is not None and value < metric.descriptor.minimum:
                    raise ValueError("estimate below metric minimum")
                if metric.descriptor.maximum is not None and value > metric.descriptor.maximum:
                    raise ValueError("estimate above metric maximum")
        primary = self.metrics.get(self.primary_metric_id or "")
        if primary is None:
            if self.primary_estimate.value is not None or self.eligibility.eligible:
                raise ValueError("missing primary metric cannot yield eligible estimate")
        elif self.primary_estimate != primary.estimate:
            raise ValueError("primary estimate differs from declared metric")
        if self.execution == "completed" and self.coverage.terminal != self.coverage.requested:
            raise ValueError(
                "completed benchmark requires terminal records for every selected unit"
            )
        if self.eligibility.eligible and (
            self.execution != "completed"
            or not self.primary_estimate.eligibility.eligible
            or self.coverage.completed != self.coverage.requested
        ):
            raise ValueError("eligible benchmark requires completed execution and eligible primary")
        return self


class ResultEnvelope(Record):
    result_schema_version: Literal["2"]
    run_id: Text
    model_id: Text
    created_at: Text
    provenance_schema_version: Text
    configuration_sha256: Digest | None
    execution: Execution
    eligibility: Eligibility
    benchmarks: list[BenchmarkResult]
    aggregation_id: Text | None
    overall_estimate: Estimate
    artifacts: list[ArtifactReference]

    @model_validator(mode="after")
    def envelope_identity(self) -> Self:
        ids = [benchmark.benchmark_id for benchmark in self.benchmarks]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark identities must be unique")
        for benchmark in self.benchmarks:
            for row in benchmark.observations:
                if row.identity.run_id != self.run_id or row.identity.model_id != self.model_id:
                    raise ValueError("observation run/model differs from envelope")
        if self.aggregation_id is None and self.overall_estimate.value is not None:
            raise ValueError("overall estimate requires a declared aggregation")
        if self.execution == "completed" and any(
            benchmark.execution != "completed" for benchmark in self.benchmarks
        ):
            raise ValueError("completed envelope requires completed benchmarks")
        if self.eligibility.eligible and (
            self.execution != "completed"
            or not self.benchmarks
            or any(not benchmark.eligibility.eligible for benchmark in self.benchmarks)
        ):
            raise ValueError("eligible envelope requires completed eligible benchmarks")
        return self


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def read_result(payload: str) -> ResultEnvelope:
    """Validate a v2 preview without coercing legacy records or unknown majors."""
    data = json.loads(payload, parse_constant=_reject_constant)
    return ResultEnvelope.model_validate(data)


def write_result(result: ResultEnvelope) -> str:
    """Revalidate even mutated models, then serialize with strict JSON numbers."""
    data = result.model_dump(mode="python")
    ResultEnvelope.model_validate(data)
    return json.dumps(
        data, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
