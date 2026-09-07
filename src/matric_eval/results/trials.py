"""Aligned task trials with separate any-success and observed all-success estimands."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from matric_eval.results.contract import (
    ArtifactReference,
    BenchmarkResult,
    Count,
    Digest,
    Eligibility,
    Estimate,
    Number,
    Record,
    Selection,
    Text,
)
from matric_eval.scorers.pass_k import pass_at_k, pass_power_k

SafeInteger = Count
PositiveInteger = Annotated[Count, Field(gt=0)]


class PassPredicate(Record):
    version: Literal["1"]
    kind: Literal["equals", "at_least"]
    threshold: Number
    units: Text

    def passes(self, value: float) -> bool:
        return value == self.threshold if self.kind == "equals" else value >= self.threshold


class TrialProtocol(Record):
    version: Literal["1"]
    n: PositiveInteger
    k: PositiveInteger
    metric_id: Text
    metric_version: Text
    predicate: PassPredicate
    generation_seeds: list[SafeInteger]
    root_generation_seed: SafeInteger
    selection_seed: SafeInteger
    task_content_sha256: Digest
    independence: Literal["unverified"]
    statistical_claim: Literal["descriptive_only"] = "descriptive_only"

    @model_validator(mode="after")
    def valid_trials(self) -> Self:
        if self.k > self.n:
            raise ValueError("trial protocol requires k <= n")
        if len(self.generation_seeds) != self.n or len(set(self.generation_seeds)) != self.n:
            raise ValueError("generation seeds must contain n distinct values")
        return self


class GenerationEvidence(Record):
    requested_seed: SafeInteger
    recorded_seed: SafeInteger | None
    temperature: Number | None
    provider_id: Text
    forwarding: Literal["recorded", "unverified"]
    honored: Literal["unverified"]
    limitations: list[Text]

    @model_validator(mode="after")
    def recorded_forwarding(self) -> Self:
        if self.forwarding == "recorded" and self.recorded_seed != self.requested_seed:
            raise ValueError("recorded forwarding requires matching requested and recorded seeds")
        return self


class TrialRecord(Record):
    trial_id: Text
    generation_seed: SafeInteger
    benchmark: BenchmarkResult | None
    unavailable_reason: Text | None
    native_trial_id: Text = "epoch-1"
    generation_evidence: GenerationEvidence | None = None
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    failure_code: Text | None = None

    @model_validator(mode="after")
    def availability(self) -> Self:
        if (self.benchmark is None) != (self.unavailable_reason is not None):
            raise ValueError("missing trial benchmark requires an unavailable reason")
        if (
            self.generation_evidence is not None
            and self.generation_evidence.requested_seed != self.generation_seed
        ):
            raise ValueError("generation evidence seed differs from trial")
        return self


class PerTaskResult(Record):
    allocation_id: Text
    sample_id: Text
    n_requested: PositiveInteger
    n_observed: SafeInteger
    c: SafeInteger
    pass_at_k: Estimate
    all_n_success: Estimate


class TrialEvaluation(Record):
    trial_schema_version: Literal["1"]
    run_id: Text
    model_id: Text
    benchmark_id: Text
    protocol: TrialProtocol
    manifest: list[Selection]
    manifest_sha256: Digest
    trials: list[TrialRecord]
    per_task: list[PerTaskResult]
    macro_pass_at_k: Estimate
    macro_all_n_success: Estimate
    execution: Literal["completed", "partial", "failed"]
    eligibility: Eligibility
    limitations: list[Text]

    @model_validator(mode="after")
    def verify_derived_fields(self) -> Self:
        if self.manifest_sha256 != manifest_digest(self.manifest):
            raise ValueError("trial manifest digest differs from selected task manifest")
        expected = _calculate(
            self.trials, self.manifest, self.run_id, self.model_id, self.benchmark_id, self.protocol
        )
        for field, value in expected.items():
            actual = getattr(self, field)
            if isinstance(value, Estimate):
                matches = _estimates_equal(actual, value)
            elif field == "per_task" and isinstance(value, list):
                matches = len(actual) == len(value) and all(
                    left.model_dump(exclude={"pass_at_k", "all_n_success"})
                    == right.model_dump(exclude={"pass_at_k", "all_n_success"})
                    and _estimates_equal(left.pass_at_k, right.pass_at_k)
                    and _estimates_equal(left.all_n_success, right.all_n_success)
                    for left, right in zip(actual, value, strict=True)
                )
            else:
                matches = actual == value
            if not matches:
                raise ValueError(f"trial report {field} differs from aligned observations")
        return self


def _estimates_equal(left: Estimate, right: Estimate) -> bool:
    """Allow only floating-point evaluation differences across wire implementations."""
    numbers = {"value", "numerator", "denominator"}
    if left.model_dump(exclude=numbers) != right.model_dump(exclude=numbers):
        return False
    for field in numbers:
        actual, expected = getattr(left, field), getattr(right, field)
        if actual is None or expected is None:
            if actual != expected:
                return False
        elif not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
            return False
    return True


def manifest_digest(manifest: list[Selection]) -> str:
    """Hash ordered, explicit task references without collapsing integer/string encodings."""
    return hashlib.sha256(
        json.dumps(
            [row.model_dump() for row in manifest],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _missing(reason: str, method: str) -> Estimate:
    return Estimate(
        value=None,
        reason=reason,
        numerator=None,
        denominator=None,
        method=method,
        eligibility=Eligibility(eligible=False, reasons=[reason]),
    )


def _estimate(
    value: float,
    numerator: float | None,
    denominator: float | None,
    method: str,
    reasons: list[str],
) -> Estimate:
    return Estimate(
        value=value,
        reason=None,
        numerator=numerator,
        denominator=denominator,
        method=method,
        eligibility=Eligibility(eligible=not reasons, reasons=reasons),
    )


def _task_key(selection: Selection) -> tuple[str, str]:
    return selection.allocation_id, selection.sample_id


def _calculate(
    records: list[TrialRecord],
    manifest: list[Selection],
    run_id: str,
    model_id: str,
    benchmark_id: str,
    protocol: TrialProtocol,
) -> dict[str, object]:
    keys = [_task_key(row) for row in manifest]
    if not keys or len(set(keys)) != len(keys):
        raise ValueError("trial manifest must contain unique nonempty task identities")
    if len({row.trial_id for row in manifest}) != 1:
        raise ValueError("task manifest must use one selection trial marker")
    expected_trials = [f"trial-{index}" for index in range(protocol.n)]
    if [record.trial_id for record in records] != expected_trials:
        raise ValueError("trial records must exactly match ordered protocol trial identities")
    flags: dict[tuple[str, str], list[bool]] = {key: [] for key in keys}
    complete_executions = 0
    descriptor_baseline = None
    benchmark_measurement_ineligible = False
    limitations = ["statistical_independence_unverified", "descriptive_statistics_only"]
    for index, record in enumerate(records):
        if record.generation_seed != protocol.generation_seeds[index]:
            raise ValueError("trial generation seed differs from protocol")
        if record.generation_evidence is None:
            limitations.append(f"generation_evidence_unavailable:{record.trial_id}")
        else:
            limitations.extend(
                f"{record.trial_id}:{item}" for item in record.generation_evidence.limitations
            )
            limitations.append(f"generation_seed_honoring_unverified:{record.trial_id}")
        benchmark = record.benchmark
        if benchmark is None:
            continue
        if benchmark.benchmark_id != benchmark_id:
            raise ValueError("trial benchmark identity differs from evaluation")
        benchmark_measurement_ineligible |= not benchmark.eligibility.eligible
        if [_task_key(row) for row in benchmark.selection] != keys:
            raise ValueError("trial selected task manifest differs in identity or order")
        if any(row.trial_id != record.trial_id for row in benchmark.selection):
            raise ValueError("inner selection trial identity differs from outer trial")
        for selected, native in zip(manifest, benchmark.selection, strict=True):
            if selected.data != native.data:
                raise ValueError("trial data references differ from fixed task manifest")
        if benchmark.execution == "completed":
            complete_executions += 1
        for row in benchmark.observations:
            if row.identity.trial_id != record.trial_id:
                raise ValueError("inner observation trial identity differs from outer trial")
            if row.identity.run_id != run_id or row.identity.model_id != model_id:
                raise ValueError("trial observation run/model differs from evaluation")
        metric = benchmark.metrics.get(protocol.metric_id)
        if metric is None:
            continue
        if metric.observation_metric_id is not None:
            raise ValueError("trial pass predicate requires a direct observation metric")
        if (
            metric.descriptor.version != protocol.metric_version
            or metric.descriptor.units != protocol.predicate.units
        ):
            raise ValueError("trial metric version or units differ from pass predicate")
        if descriptor_baseline is None:
            descriptor_baseline = metric.descriptor
        elif descriptor_baseline != metric.descriptor:
            raise ValueError("trial metric descriptor differs across trials")
        for row in benchmark.observations:
            if not row.accepted or row.identity.metric_id != protocol.metric_id:
                continue
            if row.outcome not in ("observed", "model_timeout") or row.value is None:
                continue
            # Contract validation already enforces timeout values against the
            # declared metric policy. Preserve observed rows even in failed logs;
            # execution reasons below prevent claiming qualified full trials.
            if math.isfinite(row.value):
                flags[(row.identity.allocation_id, row.identity.sample_id)].append(
                    protocol.predicate.passes(row.value)
                )
    execution = (
        "completed"
        if complete_executions == protocol.n
        else "partial"
        if any(
            record.benchmark is not None and record.benchmark.execution in {"completed", "partial"}
            for record in records
        )
        else "failed"
    )
    execution_reasons = [] if execution == "completed" else ["incomplete_trial_execution"]
    if benchmark_measurement_ineligible:
        execution_reasons.append("benchmark_measurement_ineligible")
    tasks = []
    for key in keys:
        outcomes = flags[key]
        observed = len(outcomes)
        correct = sum(outcomes)
        if observed != protocol.n:
            any_success = _missing("missing_task_trials", f"pass-at-{protocol.k}/1")
            all_success = _missing("missing_task_trials", "all-n-success/1")
        else:
            any_success = _estimate(
                pass_at_k(protocol.n, correct, protocol.k),
                None,
                None,
                f"pass-at-{protocol.k}/1",
                execution_reasons,
            )
            all_success = _estimate(
                pass_power_k(outcomes), None, None, "all-n-success/1", execution_reasons
            )
        tasks.append(
            PerTaskResult(
                allocation_id=key[0],
                sample_id=key[1],
                n_requested=protocol.n,
                n_observed=observed,
                c=correct,
                pass_at_k=any_success,
                all_n_success=all_success,
            )
        )
    incomplete = any(task.n_observed != protocol.n for task in tasks)
    reasons = [*execution_reasons, *(["missing_task_trials"] if incomplete else [])]
    if incomplete:
        macro_pass = _missing("missing_task_trials", "task-macro-pass-at-k/1")
        macro_all = _missing("missing_task_trials", "task-macro-all-n-success/1")
    else:
        pass_sum = math.fsum(
            task.pass_at_k.value for task in tasks if task.pass_at_k.value is not None
        )
        all_sum = math.fsum(
            task.all_n_success.value for task in tasks if task.all_n_success.value is not None
        )
        denominator = float(len(tasks))
        macro_pass = _estimate(
            pass_sum / denominator, pass_sum, denominator, "task-macro-pass-at-k/1", reasons
        )
        macro_all = _estimate(
            all_sum / denominator, all_sum, denominator, "task-macro-all-n-success/1", reasons
        )
    return {
        "per_task": tasks,
        "macro_pass_at_k": macro_pass,
        "macro_all_n_success": macro_all,
        "execution": execution,
        "eligibility": Eligibility(eligible=not reasons, reasons=reasons),
        "limitations": list(dict.fromkeys(limitations)),
    }


def evaluate_trials(
    records: list[TrialRecord],
    manifest: list[Selection],
    *,
    run_id: str,
    model_id: str,
    benchmark_id: str,
    protocol: TrialProtocol,
) -> TrialEvaluation:
    """Reconcile records to every declared trial; absent trials stay explicitly missing."""
    protocol = TrialProtocol.model_validate(protocol.model_dump())
    records = [TrialRecord.model_validate(record.model_dump()) for record in records]
    manifest = [Selection.model_validate(row.model_dump()) for row in manifest]
    indexed = {record.trial_id: record for record in records}
    if len(indexed) != len(records):
        raise ValueError("duplicate trial identity")
    expected = {f"trial-{index}" for index in range(protocol.n)}
    if not set(indexed) <= expected:
        raise ValueError("unknown trial identity")
    ordered = [
        indexed.get(f"trial-{index}")
        or TrialRecord(
            trial_id=f"trial-{index}",
            generation_seed=protocol.generation_seeds[index],
            benchmark=None,
            unavailable_reason="trial_not_returned",
        )
        for index in range(protocol.n)
    ]
    calculated = _calculate(ordered, manifest, run_id, model_id, benchmark_id, protocol)
    return TrialEvaluation.model_validate(
        {
            "trial_schema_version": "1",
            "run_id": run_id,
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "protocol": protocol,
            "manifest": manifest,
            "manifest_sha256": manifest_digest(manifest),
            "trials": ordered,
            **calculated,
        }
    )
