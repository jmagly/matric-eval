"""Deterministic accepted-observation and explicitly declared suite reducers."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict

from matric_eval.results.contract import BenchmarkResult, Eligibility, Estimate
from matric_eval.results.policies import MissingnessPolicy, SuiteAggregation


class AggregationReport(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    estimate: Estimate
    requested: int
    completed: int
    scored: int
    included: list[str]
    excluded: dict[str, list[str]]


def _missing(reason: str, method: str) -> Estimate:
    return Estimate(
        value=None,
        reason=reason,
        numerator=None,
        denominator=None,
        method=method,
        eligibility=Eligibility(eligible=False, reasons=[reason]),
    )


def _mean(values: list[float], weights: list[float], method: str, reasons: list[str]) -> Estimate:
    if not values:
        return _missing("zero_denominator", method)
    try:
        numerator = math.fsum(value * weight for value, weight in zip(values, weights, strict=True))
        denominator = math.fsum(weights)
        value = numerator / denominator
    except (OverflowError, ValueError, ZeroDivisionError):
        return _missing("nonfinite_aggregation", method)
    if not all(math.isfinite(item) for item in (numerator, denominator, value)):
        return _missing("nonfinite_aggregation", method)
    return Estimate(
        value=value,
        reason=None,
        numerator=numerator,
        denominator=denominator,
        method=method,
        eligibility=Eligibility(eligible=not reasons, reasons=reasons),
    )


def reduce_observations(
    benchmark: BenchmarkResult,
    metric_id: str,
    missingness_policy: MissingnessPolicy = "require-complete",
) -> Estimate:
    """Mean accepted numeric outcomes under an explicit exclusion policy."""
    if missingness_policy not in ("require-complete", "exclude-unavailable"):
        raise ValueError("unsupported missingness policy")
    benchmark = BenchmarkResult.model_validate(benchmark.model_dump())
    method = f"accepted-mean/1:{missingness_policy}"
    if metric_id not in benchmark.metrics:
        return _missing("metric_unavailable", method)
    if benchmark.metrics[metric_id].observation_metric_id is not None:
        raise ValueError("derived metric requires its declared estimator, not observation mean")
    rows = sorted(
        (
            row
            for row in benchmark.observations
            if row.accepted and row.identity.metric_id == metric_id
        ),
        key=lambda row: row.identity.selection_key(),
    )
    values = [row.value for row in rows if row.value is not None]
    reasons = []
    if (
        benchmark.execution != "completed"
        or benchmark.coverage.completed != benchmark.coverage.requested
    ):
        reasons.append("incomplete_execution")
    if len(values) != benchmark.coverage.requested:
        reasons.append("unavailable_observations")
    if not benchmark.eligibility.eligible:
        reasons.append("benchmark_ineligible")
    if not benchmark.metrics[metric_id].estimate.eligibility.eligible:
        reasons.append("metric_ineligible")
    if not values:
        return _missing("zero_denominator", method)
    if reasons and missingness_policy == "require-complete":
        return _missing("incomplete_or_ineligible_observations", method)
    return _mean(values, [1.0] * len(values), method, reasons)


def aggregate_benchmarks(
    benchmarks: list[BenchmarkResult],
    requested: list[str],
    declaration: SuiteAggregation,
) -> AggregationReport:
    """Aggregate only declared primary metrics with matching scales and scope.

    Invalid declarations raise; unavailable measurements return explicit reports.
    Excluded terms never produce an eligible full-suite comparison.
    """
    declaration = SuiteAggregation.model_validate(declaration.model_dump())
    ids = [benchmark.benchmark_id for benchmark in benchmarks]
    if len(ids) != len(set(ids)) or len(requested) != len(set(requested)):
        raise ValueError("benchmark and requested identities must be unique")
    if set(requested) != {term.benchmark_id for term in declaration.terms}:
        raise ValueError("requested scope differs from declared terms")
    if not set(ids) <= set(requested):
        raise ValueError("result outside requested benchmark scope")
    indexed = {
        benchmark.benchmark_id: BenchmarkResult.model_validate(benchmark.model_dump())
        for benchmark in benchmarks
    }
    terms = {term.benchmark_id: term for term in declaration.terms}
    excluded: dict[str, list[str]] = {}
    transformed: dict[str, tuple[float, float]] = {}
    completed = sum(benchmark.execution == "completed" for benchmark in indexed.values())
    scored = 0
    for name in requested:
        benchmark = indexed.get(name)
        if benchmark is None:
            excluded[name] = ["benchmark_unavailable"]
            continue
        term = terms[name]
        metric = benchmark.metrics.get(term.metric_id)
        if benchmark.primary_metric_id != term.metric_id or metric is None:
            excluded[name] = ["declared_primary_unavailable"]
            continue
        if metric.estimate.value is not None:
            scored += 1
        transform = term.transform
        descriptor = metric.descriptor
        if (
            descriptor.units != transform.source_units
            or descriptor.minimum != transform.source_minimum
            or descriptor.maximum != transform.source_maximum
            or descriptor.direction != transform.source_direction
        ):
            excluded[name] = ["metric_transform_mismatch"]
            continue
        if metric.estimate.value is None:
            excluded[name] = ["estimate_unavailable"]
            continue
        if (descriptor.minimum is not None and metric.estimate.value < descriptor.minimum) or (
            descriptor.maximum is not None and metric.estimate.value > descriptor.maximum
        ):
            excluded[name] = ["source_estimate_out_of_range"]
            continue
        reasons = []
        if (
            benchmark.execution != "completed"
            or benchmark.coverage.completed != benchmark.coverage.requested
        ):
            reasons.append("incomplete_execution")
        if not benchmark.eligibility.eligible or not metric.estimate.eligibility.eligible:
            reasons.append("ineligible_measurement")
        if reasons:
            excluded[name] = reasons
            continue
        value = metric.estimate.value * transform.scale + transform.offset
        if not math.isfinite(value):
            excluded[name] = ["nonfinite_transform"]
            continue
        transformed[name] = value, term.weight
    method = f"declared-weighted-mean/1:{declaration.aggregation_id}"
    if excluded and declaration.missingness_policy == "require-complete":
        estimate = _missing("incomplete_or_ineligible_suite", method)
    else:
        ordered = [transformed[name] for name in sorted(transformed)]
        estimate = _mean(
            [item[0] for item in ordered],
            [item[1] for item in ordered],
            method,
            ["partial_suite_excluded"] if excluded else [],
        )
    return AggregationReport(
        estimate=estimate,
        requested=len(requested),
        completed=completed,
        scored=scored,
        included=[name for name in requested if name in transformed],
        excluded=excluded,
    )
