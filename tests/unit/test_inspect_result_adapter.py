"""Pinned native Inspect records retain failures and denominators without providers."""

from typing import Any

import pytest
from inspect_ai.log import EvalLog, EvalSample
from inspect_ai.scorer import Score

from matric_eval.results.contract import (
    BenchmarkResult,
    MetricDescriptor,
    read_result,
    write_result,
)
from matric_eval.results.inspect_adapter import adapt_log, envelope

ERROR = {
    "message": "synthetic backend failure",
    "traceback": "synthetic",
    "traceback_ansi": "synthetic",
}


def sample(sid: int | str, value: Any = "C", *, epoch: int = 1, **extra: Any) -> EvalSample:
    score = value if isinstance(value, Score) else Score(value=value)
    return EvalSample.model_validate(
        {
            "id": sid,
            "epoch": epoch,
            "input": "synthetic",
            "target": "synthetic",
            "scores": {"exact": score},
            **extra,
        }
    )


def native_log(
    samples: list[EvalSample],
    *,
    ids: list[int | str] | None = None,
    status: str = "success",
    epochs: int = 1,
    value: float = 1.0,
) -> EvalLog:
    selected = ids if ids is not None else [s.id for s in samples]
    return EvalLog.model_validate(
        {
            "status": status,
            "eval": {
                "eval_id": "native-fixture",
                "created": "2026-09-06T00:00:00Z",
                "task": "fixture",
                "model": "mockllm/model",
                "dataset": {
                    "name": "synthetic/1",
                    "sample_ids": selected,
                    "samples": len(selected),
                },
                "config": {"epochs": epochs},
            },
            "samples": samples,
            "results": {
                "total_samples": len(selected) * epochs,
                "completed_samples": sum(s.error is None for s in samples),
                "scores": [
                    {
                        "name": "exact",
                        "scorer": "exact",
                        "metrics": {
                            "accuracy": {"name": "accuracy", "value": value},
                        },
                    }
                ],
            },
            "error": ERROR if status == "error" else None,
        }
    )


def descriptor() -> MetricDescriptor:
    return MetricDescriptor(
        metric_id="exact/accuracy",
        version="1",
        scorer_id="exact",
        value_kind="binary",
        units="fraction",
        direction="higher",
        minimum=0.0,
        maximum=1.0,
        independent_unit="task",
        missingness_policy="exclude-unmeasured/1",
        aggregation_id="accuracy/1",
        timeout_value=None,
    )


def convert(log: EvalLog, *, declared: bool = True) -> BenchmarkResult:
    return adapt_log(
        log,
        run_id="run",
        model_id="model",
        benchmark_id="benchmark",
        primary_metric_id="exact/accuracy" if declared else None,
        descriptors={"exact/accuracy": descriptor()} if declared else None,
    )


@pytest.mark.parametrize(
    ("native", "execution", "eligible"),
    [
        ("success", "completed", True),
        ("error", "failed", False),
        ("cancelled", "cancelled", False),
        ("started", "partial", False),
    ],
)
def test_native_terminal_status_is_preserved(native: str, execution: str, eligible: bool) -> None:
    result = convert(native_log([sample("a")], status=native))
    assert result.execution == execution
    assert result.eligibility.eligible is eligible
    assert result.coverage.requested == result.coverage.completed == 1
    strict = write_result(envelope(result, "run", "model"))
    assert read_result(strict).benchmarks[0] == result


def test_mixed_observed_unscored_error_and_missing_reconcile() -> None:
    log = native_log(
        [
            sample("a", "C"),
            sample(
                "b",
                Score.unscored(reason="grader_failed", metadata={"judge_status": "parse_failure"}),
            ),
            sample("c", error=ERROR),
        ],
        ids=["a", "b", "c", "d"],
    )
    result = convert(log)
    assert result.execution == "partial"
    assert result.coverage.model_dump() == {
        "requested": 4,
        "attempted": 3,
        "terminal": 3,
        "completed": 2,
        "failed": 1,
        "cancelled": 0,
        "not_attempted": 0,
        "unknown": 1,
    }
    metric = result.metrics["exact/accuracy"]
    assert metric.scored == 1
    assert metric.outcome_counts == {
        "observed": 1,
        "grader_failed": 1,
        "infrastructure_error": 1,
        "unavailable": 1,
    }
    assert [o.value for o in result.observations] == [1.0, None, None, None]
    assert result.observations[1].reason == "grader_failed"
    assert not result.eligibility.eligible
    assert read_result(write_result(envelope(result, "run", "model"))).benchmarks[0] == result


def test_all_wrong_remains_measured_while_all_unscored_is_null() -> None:
    wrong = convert(native_log([sample("a", "I"), sample("b", "I")], value=0.0))
    unscored = convert(
        native_log(
            [
                sample("a", Score.unscored(reason="grader_failed")),
                sample("b", Score.unscored(reason="grader_failed")),
            ],
            value=float("nan"),
        )
    )
    assert wrong.execution == unscored.execution == "completed"
    assert wrong.primary_estimate.value == 0.0
    assert wrong.eligibility.eligible
    assert wrong.metrics["exact/accuracy"].scored == 2
    assert unscored.primary_estimate.value is None
    assert unscored.metrics["exact/accuracy"].scored == 0
    assert not unscored.eligibility.eligible
    strict = write_result(envelope(unscored, "run", "model"))
    assert "NaN" not in strict
    assert "Infinity" not in strict
    assert read_result(strict).benchmarks[0].primary_estimate.value is None


def test_selected_epochs_and_typed_ids_do_not_collide() -> None:
    result = convert(
        native_log(
            [sample(sid, epoch=epoch) for sid in [1, "1"] for epoch in [1, 2]],
            ids=[1, "1"],
            epochs=2,
        )
    )
    assert result.coverage.requested == 4
    assert {s.sample_id for s in result.selection} == {"1", '"1"'}
    assert {s.trial_id for s in result.selection} == {"epoch-1", "epoch-2"}
    assert len({o.observation_id for o in result.observations}) == 4


@pytest.mark.parametrize(
    "mutation", ["selected", "sample", "unselected", "count", "missing_manifest"]
)
def test_ambiguous_manifest_or_duplicate_records_are_rejected(mutation: str) -> None:
    log = native_log([sample("a")])
    if mutation == "selected":
        log.eval.dataset.sample_ids = ["a", "a"]
    elif mutation == "sample":
        log.samples = [sample("a"), sample("a")]
    elif mutation == "unselected":
        log.samples = [sample("other")]
    elif mutation == "count":
        assert log.results is not None
        log.results.total_samples = 2
    else:
        log.eval.dataset.sample_ids = None
    with pytest.raises(ValueError):
        convert(log)


def test_retry_history_keeps_attempt_lineage_without_inflating_counts() -> None:
    result = convert(native_log([sample("a", error_retries=[ERROR, ERROR])]))
    assert result.coverage.requested == result.coverage.completed == 1
    assert result.metrics["exact/accuracy"].scored == 1
    assert len(result.observations) == 3
    assert len({o.observation_id for o in result.observations}) == 1
    assert [o.accepted for o in result.observations] == [False, False, True]
    assert [o.previous_attempt_id for o in result.observations] == [
        None,
        "inspect-attempt-0",
        "inspect-attempt-1",
    ]
    assert read_result(write_result(envelope(result, "run", "model"))).benchmarks[0] == result


@pytest.mark.parametrize("value", ["non-numeric", {"dimension": 1.0}, [1.0, 0.0], True])
def test_unsupported_score_shapes_remain_unavailable(value: Any) -> None:
    result = convert(native_log([sample("a", value)]))
    assert result.observations[0].outcome == "unavailable"
    assert result.observations[0].value is None
    assert result.primary_estimate.value is None
    assert not result.eligibility.eligible


def test_primary_requires_declared_identity_and_semantics() -> None:
    log = native_log([sample("a")])
    declared = convert(log)
    absent = convert(log, declared=False)
    assert declared.primary_estimate.value == 1.0
    assert declared.eligibility.eligible
    assert absent.primary_estimate.value is None
    assert not absent.eligibility.eligible
    assert absent.metrics["exact/accuracy"].estimate.value == 1.0
    assert (
        "metric_semantics_undeclared"
        in absent.metrics["exact/accuracy"].estimate.eligibility.reasons
    )


def test_logged_sample_count_discrepancy_is_rejected() -> None:
    log = native_log([sample("a")])
    assert log.results is not None
    log.results.logged_samples = 0
    with pytest.raises(ValueError, match="logged_sample_count_mismatch"):
        convert(log)


def test_declared_scorer_identity_overrides_native_metric_prefix() -> None:
    row = sample("a", "I")
    assert row.scores is not None
    row.scores["custom"] = Score(value="C")
    declared = descriptor()
    declared.scorer_id = "custom"
    result = adapt_log(
        native_log([row]),
        run_id="run",
        model_id="model",
        benchmark_id="benchmark",
        primary_metric_id="exact/accuracy",
        descriptors={"exact/accuracy": declared},
    )
    assert result.observations[0].value == 1.0
    assert result.metrics["exact/accuracy"].descriptor.scorer_id == "custom"


def test_operator_limit_records_cancelled_sample_without_measured_value() -> None:
    log = native_log(
        [sample("a", limit={"type": "operator", "limit": 0, "reason": "operator stopped sample"})]
    )
    result = convert(log)
    assert result.coverage.cancelled == 1
    assert result.coverage.completed == 0
    assert result.observations[0].execution == "cancelled"
    assert result.observations[0].outcome == "cancelled"
    assert result.observations[0].value is None
    assert result.observations[0].reason == "operator stopped sample"
    assert not result.eligibility.eligible


def test_unscored_time_limit_preserves_reason_without_guessing_model_fault() -> None:
    row = sample("a", limit={"type": "time", "limit": 10, "reason": "elapsed wall time"})
    row.scores = None
    result = convert(native_log([row]))
    assert result.observations[0].outcome == "unavailable"
    assert result.observations[0].value is None
    assert result.observations[0].reason == "inspect_limit:time:elapsed wall time"


def test_judge_identity_preserves_native_status_without_inventing_calibration() -> None:
    score = Score.unscored(
        reason="grader_failed",
        metadata={
            "judge_model": "fixture-judge",
            "judge_status": "parse_failure",
        },
    )
    result = convert(native_log([sample("a", score)]))
    row = result.observations[0]
    assert row.native_status == "parse_failure"
    assert row.reason == "grader_failed"
    assert row.judge is not None
    assert row.judge.judge_id == "fixture-judge"
    assert "unknown" in row.judge.reversal_policy
    assert "unknown" in row.judge.retry_policy
    assert row.judge.calibration is None
    assert read_result(write_result(envelope(result, "run", "model"))).benchmarks[0] == result
