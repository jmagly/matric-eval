"""Hand-calculated deterministic aggregation, scale and missingness fixtures."""

from typing import Any

import pytest

from matric_eval.results.contract import BenchmarkResult, ObservationIdentity
from matric_eval.results.policies import SuiteAggregation
from matric_eval.results.reducers import aggregate_benchmarks, reduce_observations


def benchmark(
    name: str,
    values: list[float | None],
    *,
    maximum: float = 1.0,
    units: str = "fraction",
    direction: str = "higher",
) -> BenchmarkResult:
    observed = [value for value in values if value is not None]
    eligible = bool(values) and len(observed) == len(values)
    eligibility = {"eligible": eligible, "reasons": [] if eligible else ["unmeasured"]}
    estimate = {
        "value": sum(observed) / len(observed) if observed else None,
        "reason": None if observed else "empty",
        "numerator": sum(observed) if observed else None,
        "denominator": float(len(observed)) if observed else None,
        "method": "fixture/1",
        "eligibility": eligibility,
    }
    selection = []
    observations = []
    for index, value in enumerate(values):
        sid = str(index)
        selection.append(
            {
                "allocation_id": name,
                "sample_id": sid,
                "trial_id": "t",
                "data": {
                    "partition_schema_version": "1",
                    "role": "final_test",
                    "row_id": sid,
                    "source_id": name,
                    "independent_unit_id": sid,
                },
            }
        )
        identity = ObservationIdentity(
            run_id="run",
            model_id="model",
            benchmark_id=name,
            allocation_id=name,
            sample_id=sid,
            trial_id="t",
            metric_id="metric",
        )
        observations.append(
            {
                "observation_id": identity.logical_id(),
                "identity": identity.model_dump(),
                "attempt_id": "a",
                "previous_attempt_id": None,
                "accepted": True,
                "execution": "completed",
                "outcome": "observed" if value is not None else "grader_failed",
                "value": value,
                "reason": None if value is not None else "grader_failed",
                "native_status": "fixture",
                "judge": None,
                "artifacts": [],
            }
        )
    return BenchmarkResult.model_validate(
        {
            "benchmark_id": name,
            "protocol_sha256": None,
            "manifest_sha256": None,
            "execution": "completed",
            "eligibility": eligibility,
            "primary_metric_id": "metric",
            "primary_estimate": estimate,
            "metrics": {
                "metric": {
                    "descriptor": {
                        "metric_id": "metric",
                        "version": "1",
                        "scorer_id": "scorer",
                        "value_kind": "continuous",
                        "units": units,
                        "direction": direction,
                        "minimum": 0.0,
                        "maximum": maximum,
                        "independent_unit": "task",
                        "missingness_policy": "exclude-unmeasured/1",
                        "aggregation_id": "mean/1",
                        "timeout_value": None,
                    },
                    "estimate": estimate,
                    "scored": len(observed),
                    "outcome_counts": {
                        "observed": len(observed),
                        "grader_failed": len(values) - len(observed),
                    },
                }
            },
            "selection": selection,
            "observations": observations,
            "coverage": {
                "requested": len(values),
                "attempted": len(values),
                "terminal": len(values),
                "completed": len(values),
                "failed": 0,
                "cancelled": 0,
                "not_attempted": 0,
                "unknown": 0,
            },
            "artifacts": [],
        }
    )


def term(
    name: str,
    *,
    weight: float = 1.0,
    units: str = "fraction",
    maximum: float = 1.0,
    direction: str = "higher",
    scale: float = 1.0,
    offset: float = 0.0,
    kind: str = "identity",
) -> dict[str, Any]:
    return {
        "benchmark_id": name,
        "metric_id": "metric",
        "weight": weight,
        "transform": {
            "version": "1",
            "kind": kind,
            "source_units": units,
            "source_minimum": 0.0,
            "source_maximum": maximum,
            "source_direction": direction,
            "scale": scale,
            "offset": offset,
        },
    }


def policy(terms: list[dict[str, Any]], missing: str = "require-complete") -> SuiteAggregation:
    return SuiteAggregation.model_validate(
        {
            "version": "1",
            "aggregation_id": "fixture-suite/1",
            "target_units": "fraction",
            "target_direction": "higher",
            "missingness_policy": missing,
            "terms": terms,
        }
    )


def test_unequal_weights_are_explicit_and_order_independent() -> None:
    a, b = benchmark("a", [1.0]), benchmark("b", [0.0])
    declaration = policy([term("a", weight=1.0), term("b", weight=3.0)])
    result = aggregate_benchmarks([a, b], ["a", "b"], declaration)
    assert result.estimate.value == 0.25
    assert result.estimate.numerator == 1.0
    assert result.estimate.denominator == 4.0
    assert result.estimate.eligibility.eligible
    assert (result.requested, result.completed, result.scored) == (2, 2, 2)
    reversed_policy = policy(list(reversed([term("a", weight=1.0), term("b", weight=3.0)])))
    assert aggregate_benchmarks([b, a], ["a", "b"], reversed_policy) == result


def test_mixed_units_need_explicit_affine_transform() -> None:
    a, b = benchmark("a", [1.0]), benchmark("b", [2.5], maximum=5.0, units="points")
    declaration = policy(
        [term("a"), term("b", maximum=5.0, units="points", kind="affine", scale=0.2)]
    )
    result = aggregate_benchmarks([a, b], ["a", "b"], declaration)
    assert result.estimate.value == 0.75
    assert result.estimate.numerator == 1.5
    assert result.estimate.denominator == 2.0
    with pytest.raises(ValueError, match="units"):
        policy([term("b", maximum=5.0, units="points")])
    mismatch = aggregate_benchmarks([a, b], ["a", "b"], policy([term("a"), term("b")]))
    assert mismatch.estimate.value is None
    assert mismatch.excluded == {"b": ["metric_transform_mismatch"]}
    assert mismatch.scored == 2  # Measured scope is distinct from aggregate eligibility.


def test_lower_direction_requires_declared_sign_reversal() -> None:
    risk = benchmark("risk", [0.25], direction="lower")
    declaration = policy([term("risk", direction="lower", kind="affine", scale=-1.0, offset=1.0)])
    result = aggregate_benchmarks([risk], ["risk"], declaration)
    assert result.estimate.value == 0.75
    assert result.estimate.eligibility.eligible
    with pytest.raises(ValueError, match="direction"):
        policy([term("risk", direction="lower")])


def test_partial_suite_never_becomes_an_eligible_full_comparison() -> None:
    a = benchmark("a", [1.0])
    complete = aggregate_benchmarks([a], ["a", "b"], policy([term("a"), term("b")]))
    assert complete.estimate.value is None
    partial = aggregate_benchmarks(
        [a], ["a", "b"], policy([term("a"), term("b")], "exclude-unavailable")
    )
    assert partial.estimate.value == 1.0
    assert not partial.estimate.eligibility.eligible
    assert partial.included == ["a"]
    assert partial.excluded == {"b": ["benchmark_unavailable"]}
    assert (partial.requested, partial.completed, partial.scored) == (2, 1, 1)


def test_missing_primary_cannot_fall_back_to_named_secondary() -> None:
    a = benchmark("a", [1.0])
    raw = a.model_dump()
    raw["primary_metric_id"] = None
    raw["eligibility"] = {"eligible": False, "reasons": ["missing_primary"]}
    raw["primary_estimate"] = {
        "value": None,
        "reason": "missing_primary",
        "numerator": None,
        "denominator": None,
        "method": "none",
        "eligibility": raw["eligibility"],
    }
    a = BenchmarkResult.model_validate(raw)
    result = aggregate_benchmarks([a], ["a"], policy([term("a")]))
    assert result.estimate.value is None
    assert result.excluded == {"a": ["declared_primary_unavailable"]}


def test_empty_and_ineligible_measurements_have_no_eligible_denominator() -> None:
    empty = benchmark("a", [None])
    result = aggregate_benchmarks([empty], ["a"], policy([term("a")], "exclude-unavailable"))
    assert result.estimate.value is None
    assert result.estimate.denominator is None
    assert result.estimate.reason == "zero_denominator"
    mixed = benchmark("a", [1.0, None])
    result = aggregate_benchmarks([mixed], ["a"], policy([term("a")], "exclude-unavailable"))
    assert result.estimate.value is None
    assert result.excluded == {"a": ["ineligible_measurement"]}


def test_observation_mean_reports_missingness_and_excludes_retry_attempts() -> None:
    a = benchmark("a", [1.0, 0.0])
    previous = a.observations[0].model_copy(deep=True)
    previous.accepted = False
    previous.attempt_id = "previous"
    previous.value = 0.0
    a.observations[0].previous_attempt_id = "previous"
    a.observations.insert(0, previous)
    result = reduce_observations(a, "metric")
    assert result.value == 0.5
    assert result.numerator == 1.0
    assert result.denominator == 2.0
    partial = benchmark("a", [1.0, None])
    assert reduce_observations(partial, "metric").value is None
    observed_only = reduce_observations(partial, "metric", "exclude-unavailable")
    assert observed_only.value == 1.0
    assert observed_only.denominator == 1.0
    assert not observed_only.eligibility.eligible
    assert reduce_observations(benchmark("a", [None]), "metric").reason == "zero_denominator"
    assert reduce_observations(a, "missing").value is None


@pytest.mark.parametrize(
    "field,value", [("weight", 0.0), ("weight", float("inf")), ("weight", True)]
)
def test_policy_rejects_invalid_weights(field: str, value: Any) -> None:
    invalid = term("a")
    invalid[field] = value
    with pytest.raises(ValueError):
        policy([invalid])


def test_scope_duplicates_and_overflow_are_explicit() -> None:
    a = benchmark("a", [1.0])
    declaration = policy([term("a")])
    with pytest.raises(ValueError):
        aggregate_benchmarks([a, a], ["a"], declaration)
    with pytest.raises(ValueError):
        aggregate_benchmarks([a], ["a", "a"], declaration)
    with pytest.raises(ValueError):
        aggregate_benchmarks([a], ["a", "b"], declaration)
    with pytest.raises(ValueError):
        policy([term("a"), term("a")])
    b = benchmark("b", [1.0])
    huge = policy([term("a", weight=1e308), term("b", weight=1e308)])
    result = aggregate_benchmarks([a, b], ["a", "b"], huge)
    assert result.estimate.value is None
    assert result.estimate.reason == "nonfinite_aggregation"


def test_derived_metric_cannot_be_reduced_as_observed_mean() -> None:
    a = benchmark("a", [1.0, 0.0])
    raw = a.model_dump()
    derived = a.metrics["metric"].model_dump()
    derived["descriptor"]["metric_id"] = "stderr"
    derived["observation_metric_id"] = "metric"
    raw["metrics"]["stderr"] = derived
    a = BenchmarkResult.model_validate(raw)
    with pytest.raises(ValueError, match="derived metric"):
        reduce_observations(a, "stderr")


def test_partial_execution_is_excluded_even_with_a_finite_primary() -> None:
    a = benchmark("a", [1.0])
    a.execution = "partial"
    a.eligibility.eligible = False
    a.eligibility.reasons = ["incomplete_execution"]
    report = aggregate_benchmarks([a], ["a"], policy([term("a")], "exclude-unavailable"))
    assert report.estimate.value is None
    assert report.completed == 0
    assert "incomplete_execution" in report.excluded["a"]
    assert not reduce_observations(a, "metric", "exclude-unavailable").eligibility.eligible


@pytest.mark.parametrize(
    "change",
    [
        {"scale": 0.0},
        {"scale": float("nan")},
        {"offset": float("inf")},
        {"scale": 2.0},
        {"source_minimum": 2.0},
        {"version": "2"},
    ],
)
def test_invalid_transform_declarations_fail(change: dict[str, Any]) -> None:
    item = term("a")
    item["transform"].update(change)
    with pytest.raises(ValueError):
        policy([item])
