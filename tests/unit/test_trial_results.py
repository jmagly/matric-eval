"""Aligned trial fixtures have independent hand-calculated expected estimands."""

import json
from pathlib import Path
from typing import Any

import pytest

from matric_eval.results.contract import BenchmarkResult, Selection
from matric_eval.results.trials import (
    GenerationEvidence,
    PassPredicate,
    TrialEvaluation,
    TrialProtocol,
    TrialRecord,
    evaluate_trials,
)
from tests.unit.test_result_reducers import benchmark


def test_shared_trial_fixture_and_schema_are_current() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "tests/fixtures/results/trials/disjoint.json").read_text())
    result = TrialEvaluation.model_validate(payload)
    assert result.model_dump() == payload
    assert result.macro_pass_at_k.value == 1.0
    assert result.macro_all_n_success.value == 0.0
    schema = TrialEvaluation.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://matric.dev/schemas/evaluation-trials-v1.schema.json"
    assert schema == json.loads((root / "schemas/evaluation-trials-v1.schema.json").read_text())


def protocol(n: int, k: int, *, threshold: float = 1.0, kind: str = "equals") -> TrialProtocol:
    return TrialProtocol.model_validate(
        {
            "version": "1",
            "n": n,
            "k": k,
            "metric_id": "metric",
            "metric_version": "1",
            "predicate": {
                "version": "1",
                "kind": kind,
                "threshold": threshold,
                "units": "fraction",
            },
            "generation_seeds": list(range(100, 100 + n)),
            "root_generation_seed": 99,
            "selection_seed": 42,
            "task_content_sha256": "c" * 64,
            "independence": "unverified",
        }
    )


def trial(index: int, values: list[float | None]) -> TrialRecord:
    result = benchmark("benchmark", values)
    for selected in result.selection:
        selected.trial_id = f"trial-{index}"
    for row in result.observations:
        row.identity.trial_id = f"trial-{index}"
        row.observation_id = row.identity.logical_id()
    return TrialRecord(
        trial_id=f"trial-{index}",
        generation_seed=100 + index,
        benchmark=BenchmarkResult.model_validate(result.model_dump()),
        unavailable_reason=None,
    )


def manifest(record: TrialRecord) -> list[Selection]:
    assert record.benchmark is not None
    selected = [row.model_copy(deep=True) for row in record.benchmark.selection]
    for row in selected:
        row.trial_id = "selected"
    return selected


def evaluate(records: list[TrialRecord], specification: TrialProtocol) -> TrialEvaluation:
    return evaluate_trials(
        records,
        manifest(records[0]),
        run_id="run",
        model_id="model",
        benchmark_id="benchmark",
        protocol=specification,
    )


def test_disjoint_successes_distinguish_any_success_from_reliability() -> None:
    records = [trial(0, [1.0, 0.0]), trial(1, [0.0, 1.0])]
    result = evaluate(records, protocol(2, 2))
    assert result.macro_pass_at_k.value == 1.0
    assert result.macro_all_n_success.value == 0.0
    assert [(row.n_requested, row.n_observed, row.c) for row in result.per_task] == [
        (2, 2, 1),
        (2, 2, 1),
    ]
    assert evaluate(records, protocol(2, 1)).macro_pass_at_k.value == 0.5
    assert result.execution == "completed"
    assert result.eligibility.eligible
    assert result.protocol.statistical_claim == "descriptive_only"
    assert "statistical_independence_unverified" in result.limitations
    ids = [
        row.observation_id
        for record in result.trials
        if record.benchmark is not None
        for row in record.benchmark.observations
    ]
    assert len(ids) == len(set(ids))
    assert TrialEvaluation.model_validate_json(result.model_dump_json()) == result


def test_persistent_successes_have_different_any_success_and_reliability() -> None:
    result = evaluate([trial(0, [1.0, 0.0]), trial(1, [1.0, 0.0])], protocol(2, 2))
    assert result.macro_pass_at_k.value == 0.5
    assert result.macro_all_n_success.value == 0.5
    four = evaluate(
        [trial(i, [value]) for i, value in enumerate([1.0, 0.0, 1.0, 0.0])], protocol(4, 2)
    )
    assert four.per_task[0].pass_at_k.value == pytest.approx(5 / 6)
    assert four.per_task[0].all_n_success.value == 0.0


def test_missing_trial_keeps_requested_denominator_and_explicit_record() -> None:
    result = evaluate([trial(0, [1.0])], protocol(2, 2))
    assert result.per_task[0].n_requested == 2
    assert result.per_task[0].n_observed == 1
    assert result.per_task[0].c == 1
    assert result.trials[1].benchmark is None
    assert result.trials[1].unavailable_reason == "trial_not_returned"
    assert result.macro_pass_at_k.value is None
    assert result.macro_all_n_success.value is None
    assert not result.eligibility.eligible
    assert result.execution == "partial"


def test_unscored_task_trials_are_missing_without_erasing_other_task_counts() -> None:
    result = evaluate([trial(0, [None, 0.0]), trial(1, [None, 1.0])], protocol(2, 2))
    assert result.execution == "completed"
    assert result.per_task[0].n_observed == 0
    assert result.per_task[0].pass_at_k.value is None
    assert result.per_task[1].n_observed == 2
    assert result.per_task[1].pass_at_k.value == 1.0
    assert result.macro_pass_at_k.value is None
    assert not result.eligibility.eligible


def test_retry_lineage_is_retained_without_becoming_another_draw() -> None:
    first = trial(0, [1.0])
    assert first.benchmark is not None
    previous = first.benchmark.observations[0].model_copy(deep=True)
    previous.attempt_id = "prior"
    previous.accepted = False
    previous.execution = "failed"
    previous.outcome = "infrastructure_error"
    previous.value = None
    previous.reason = "transient"
    first.benchmark.observations[0].previous_attempt_id = "prior"
    first.benchmark.observations.insert(0, previous)
    result = evaluate([first, trial(1, [0.0])], protocol(2, 2))
    assert result.per_task[0].n_observed == 2
    assert result.per_task[0].c == 1
    assert result.trials[0].benchmark is not None
    assert len(result.trials[0].benchmark.observations) == 2


def test_declared_predicate_handles_partial_scores_and_wrong_zero() -> None:
    rows = [trial(0, [0.0, 0.5]), trial(1, [0.0, 0.75])]
    exact = evaluate(rows, protocol(2, 2))
    assert [row.c for row in exact.per_task] == [0, 0]
    threshold = evaluate(rows, protocol(2, 2, threshold=0.5, kind="at_least"))
    assert [row.c for row in threshold.per_task] == [0, 2]
    assert threshold.macro_all_n_success.value == 0.5


@pytest.mark.parametrize(
    "mutation",
    ["reordered", "duplicate_task", "wrong_epoch", "wrong_run", "wrong_seed", "wrong_version"],
)
def test_unaligned_identities_and_policies_reject(mutation: str) -> None:
    first, second = trial(0, [1.0, 0.0]), trial(1, [1.0, 0.0])
    assert second.benchmark is not None
    if mutation == "reordered":
        second.benchmark.selection.reverse()
    elif mutation == "duplicate_task":
        second.benchmark.selection[1] = second.benchmark.selection[0].model_copy(deep=True)
    elif mutation == "wrong_epoch":
        for selected in second.benchmark.selection:
            selected.trial_id = "epoch-1"
        for row in second.benchmark.observations:
            row.identity.trial_id = "epoch-1"
            row.observation_id = row.identity.logical_id()
    elif mutation == "wrong_run":
        for row in second.benchmark.observations:
            row.identity.run_id = "different"
            row.observation_id = row.identity.logical_id()
    elif mutation == "wrong_seed":
        second.generation_seed = 999
    else:
        second.benchmark.metrics["metric"].descriptor.version = "2"
    with pytest.raises(ValueError):
        evaluate([first, second], protocol(2, 2))


def test_duplicate_or_unknown_trials_reject() -> None:
    first = trial(0, [1.0])
    with pytest.raises(ValueError, match="duplicate"):
        evaluate([first, first], protocol(2, 2))
    unknown = trial(5, [1.0])
    with pytest.raises(ValueError, match="unknown"):
        evaluate([first, unknown], protocol(2, 2))


@pytest.mark.parametrize(
    "field,value",
    [
        ("n", True),
        ("k", True),
        ("n", 0),
        ("k", 0),
        ("k", 3),
        ("generation_seeds", [100, 100]),
        ("generation_seeds", [100]),
        ("selection_seed", -1),
        ("root_generation_seed", 2**53),
    ],
)
def test_protocol_rejects_invalid_counts_and_seeds(field: str, value: Any) -> None:
    data = protocol(2, 2).model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        TrialProtocol.model_validate(data)


def test_wire_summary_cannot_be_forged_independently_of_trials() -> None:
    data = evaluate([trial(0, [1.0])], protocol(1, 1)).model_dump()
    data["per_task"][0]["c"] = 0
    with pytest.raises(ValueError, match="per_task"):
        TrialEvaluation.model_validate(data)
    data = evaluate([trial(0, [1.0])], protocol(1, 1)).model_dump()
    data["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        TrialEvaluation.model_validate(data)


def test_generation_receipt_records_forwarding_without_claiming_honoring() -> None:
    record = trial(0, [1.0])
    record.generation_evidence = GenerationEvidence(
        requested_seed=100,
        recorded_seed=100,
        temperature=0.0,
        provider_id="fixture",
        forwarding="recorded",
        honored="unverified",
        limitations=["deterministic_generation"],
    )
    result = evaluate([record], protocol(1, 1))
    assert result.macro_pass_at_k.value == 1.0
    assert "trial-0:deterministic_generation" in result.limitations
    assert "generation_seed_honoring_unverified:trial-0" in result.limitations
    invalid = record.generation_evidence.model_dump()
    invalid["recorded_seed"] = 101
    with pytest.raises(ValueError):
        GenerationEvidence.model_validate(invalid)
    invalid["honored"] = "verified"
    with pytest.raises(ValueError):
        GenerationEvidence.model_validate(invalid)


def test_predicate_rejects_nonfinite_thresholds() -> None:
    with pytest.raises(ValueError):
        PassPredicate(version="1", kind="equals", threshold=float("nan"), units="fraction")


def test_typed_sample_id_encodings_remain_distinct_tasks() -> None:
    records = [trial(0, [1.0, 0.0]), trial(1, [1.0, 0.0])]
    for record in records:
        assert record.benchmark is not None
        for selected, row, sid in zip(
            record.benchmark.selection, record.benchmark.observations, ["1", '"1"'], strict=True
        ):
            selected.sample_id = sid
            selected.data.row_id = sid
            selected.data.independent_unit_id = sid
            row.identity.sample_id = sid
            row.observation_id = row.identity.logical_id()
    result = evaluate(records, protocol(2, 2))
    assert [row.sample_id for row in result.per_task] == ["1", '"1"']
    assert [row.c for row in result.per_task] == [2, 0]


def test_all_missing_trials_are_explicit_and_not_perfect_reliability() -> None:
    selected = manifest(trial(0, [1.0]))
    result = evaluate_trials(
        [],
        selected,
        run_id="run",
        model_id="model",
        benchmark_id="benchmark",
        protocol=protocol(2, 2),
    )
    assert result.execution == "failed"
    assert result.per_task[0].n_observed == 0
    assert result.per_task[0].n_requested == 2
    assert result.macro_all_n_success.value is None
    assert all(record.unavailable_reason == "trial_not_returned" for record in result.trials)


@pytest.mark.parametrize(
    "field,value", [("maximum", 2.0), ("missingness_policy", "different-policy/1")]
)
def test_same_metric_version_cannot_hide_descriptor_changes(field: str, value: Any) -> None:
    first, second = trial(0, [1.0]), trial(1, [1.0])
    assert second.benchmark is not None
    setattr(second.benchmark.metrics["metric"].descriptor, field, value)
    with pytest.raises(ValueError, match="descriptor differs"):
        evaluate([first, second], protocol(2, 2))


def test_invalidated_measurement_keeps_descriptive_counts_but_not_eligibility() -> None:
    first, second = trial(0, [1.0]), trial(1, [1.0])
    assert second.benchmark is not None
    second.benchmark.eligibility.eligible = False
    second.benchmark.eligibility.reasons = ["native_samples_invalidated"]
    result = evaluate([first, second], protocol(2, 2))
    assert result.execution == "completed"
    assert result.per_task[0].n_observed == result.per_task[0].c == 2
    assert result.macro_pass_at_k.value == result.macro_all_n_success.value == 1.0
    assert result.eligibility.reasons == ["benchmark_measurement_ineligible"]
    assert not result.per_task[0].pass_at_k.eligibility.eligible
    assert result.macro_all_n_success.eligibility.reasons == ["benchmark_measurement_ineligible"]


def test_wire_integral_number_spellings_match_json_schema_integers() -> None:
    result = evaluate([trial(0, [1.0]), trial(1, [0.0])], protocol(2, 2))
    payload = result.model_dump_json().replace('"n":2', '"n":2.0').replace('"k":2', '"k":2.0')
    payload = payload.replace('"n_requested":2', '"n_requested":2.0')
    payload = payload.replace('"generation_seed":100', '"generation_seed":100.0')
    assert TrialEvaluation.model_validate_json(payload) == result


def test_unavailable_trial_retains_content_free_failure_and_native_references() -> None:
    from matric_eval.results.contract import ArtifactReference

    selected = manifest(trial(0, [1.0]))
    missing = TrialRecord(
        trial_id="trial-0",
        generation_seed=100,
        benchmark=None,
        unavailable_reason="trial_projection_unavailable",
        failure_code="ValueError",
        artifacts=[
            ArtifactReference(
                uri="fixture://ambiguous-log-1", sha256="a" * 64, unavailable_reason=None
            ),
            ArtifactReference(
                uri="fixture://ambiguous-log-2", sha256="b" * 64, unavailable_reason=None
            ),
        ],
    )
    result = evaluate_trials(
        [missing],
        selected,
        run_id="run",
        model_id="model",
        benchmark_id="benchmark",
        protocol=protocol(1, 1),
    )
    restored = TrialEvaluation.model_validate_json(result.model_dump_json())
    assert restored.trials[0].failure_code == "ValueError"
    assert restored.trials[0].artifacts == missing.artifacts
    assert restored.execution == "failed"
    assert restored.macro_all_n_success.value is None


@pytest.mark.parametrize("execution", ["failed", "cancelled", "unknown", "not_attempted"])
def test_all_unsuccessful_native_executions_remain_failed(execution: str) -> None:
    records = [trial(0, [1.0]), trial(1, [0.0])]
    for record in records:
        assert record.benchmark is not None
        raw = record.benchmark.model_dump()
        raw["execution"] = execution
        raw["eligibility"] = {"eligible": False, "reasons": ["native_execution_failed"]}
        record.benchmark = BenchmarkResult.model_validate(raw)
    result = evaluate(records, protocol(2, 2))
    assert result.execution == "failed"
    assert not result.eligibility.eligible
    # Already observed values remain descriptive evidence despite failed logs.
    assert result.per_task[0].n_observed == 2
    assert result.per_task[0].c == 1
    assert result.macro_pass_at_k.value == 1.0


def test_partial_native_execution_remains_partial() -> None:
    record = trial(0, [1.0])
    assert record.benchmark is not None
    record.benchmark.execution = "partial"
    record.benchmark.eligibility.eligible = False
    record.benchmark.eligibility.reasons = ["incomplete_execution"]
    assert evaluate([record], protocol(1, 1)).execution == "partial"
