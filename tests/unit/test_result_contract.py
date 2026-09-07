"""Independent semantic fixtures for the opt-in evaluation result contract."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, get_args

import pytest

from matric_eval.results.contract import (
    DataReference,
    ObservationIdentity,
    PartitionRole,
    ResultEnvelope,
    read_result,
    write_result,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/results"


def payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "v2/mixed.json").read_text())  # type: ignore[no-any-return]


def test_golden_round_trip_preserves_complete_wire_record() -> None:
    original = payload()
    result = read_result(json.dumps(original))
    assert json.loads(write_result(result)) == original
    benchmark = result.benchmarks[0]
    assert benchmark.coverage.requested == 9
    assert benchmark.coverage.terminal == 7
    assert benchmark.metrics["exact/accuracy"].scored == 3
    assert benchmark.metrics["rubric/points"].estimate.value == 5 / 3
    assert result.overall_estimate.value is None
    assert benchmark.observations[0].value == 0


@pytest.mark.parametrize("version", ["1", "3", "2.1", 2, None])
def test_version_discriminator_fails_explicitly(version: Any) -> None:
    data = payload()
    data["result_schema_version"] = version
    with pytest.raises(ValueError, match="result_schema_version"):
        read_result(json.dumps(data))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "0.5"])
def test_nonfinite_or_coerced_values_are_rejected(value: Any) -> None:
    data = payload()
    data["benchmarks"][0]["observations"][0]["value"] = value
    with pytest.raises(ValueError):
        read_result(json.dumps(data))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_writer_revalidates_mutated_nested_models(value: float) -> None:
    result = read_result(json.dumps(payload()))
    result.benchmarks[0].metrics["exact/accuracy"].estimate.value = value
    with pytest.raises(ValueError):
        write_result(result)


@pytest.mark.parametrize("field", ["requested", "attempted", "terminal", "completed"])
def test_counts_reconcile_to_manifest_and_observations(field: str) -> None:
    data = payload()
    data["benchmarks"][0]["coverage"][field] += 1
    with pytest.raises(ValueError):
        read_result(json.dumps(data))


def test_json_integer_spelling_agrees_with_javascript() -> None:
    data = payload()
    data["benchmarks"][0]["coverage"]["requested"] = 9.0
    assert read_result(json.dumps(data)).benchmarks[0].coverage.requested == 9
    data["benchmarks"][0]["coverage"]["requested"] = 9.5
    with pytest.raises(ValueError):
        read_result(json.dumps(data))


def test_estimate_obeys_declared_metric_range() -> None:
    data = payload()
    data["benchmarks"][0]["metrics"]["rubric/points"]["estimate"]["value"] = 6.0
    with pytest.raises(ValueError, match="maximum"):
        read_result(json.dumps(data))


def test_retry_keeps_one_logical_observation_and_scored_denominator() -> None:
    data = payload()
    rows = data["benchmarks"][0]["observations"]
    previous = copy.deepcopy(rows[0])
    previous.update(
        accepted=False,
        attempt_id="attempt-0",
        execution="failed",
        outcome="infrastructure_error",
        value=None,
        reason="transient_failure",
    )
    rows[0]["previous_attempt_id"] = "attempt-0"
    rows.insert(0, previous)
    result = read_result(json.dumps(data))
    assert result.benchmarks[0].coverage.requested == 9
    assert result.benchmarks[0].metrics["exact/accuracy"].scored == 3
    assert (
        result.benchmarks[0].observations[0].observation_id
        == result.benchmarks[0].observations[1].observation_id
    )
    rows[0]["accepted"] = True
    with pytest.raises(ValueError):
        read_result(json.dumps(data))


def test_duplicate_and_missing_logical_records_fail() -> None:
    for mutation in ("duplicate", "missing", "wrong_identity", "missing_predecessor"):
        data = payload()
        rows = data["benchmarks"][0]["observations"]
        if mutation == "duplicate":
            rows.append(copy.deepcopy(rows[0]))
        elif mutation == "missing":
            rows.pop()
        elif mutation == "wrong_identity":
            rows[0]["identity"]["sample_id"] = "different"
        else:
            rows[0]["previous_attempt_id"] = "missing"
        with pytest.raises(ValueError):
            read_result(json.dumps(data))


def test_null_unscored_cannot_become_midpoint_or_eligible() -> None:
    data = payload()
    row = data["benchmarks"][0]["observations"][4]
    assert row["outcome"] == "grader_failed"
    row["value"] = 0.5
    with pytest.raises(ValueError):
        read_result(json.dumps(data))
    data = payload()
    data["overall_estimate"]["eligibility"] = {"eligible": True, "reasons": []}
    with pytest.raises(ValueError):
        read_result(json.dumps(data))


def test_missing_primary_does_not_select_secondary_metric() -> None:
    data = payload()
    benchmark = data["benchmarks"][0]
    benchmark["primary_metric_id"] = "missing"
    benchmark["primary_estimate"] = copy.deepcopy(data["overall_estimate"])
    result = read_result(json.dumps(data))
    assert result.benchmarks[0].primary_estimate.value is None
    benchmark["primary_estimate"] = benchmark["metrics"]["rubric/points"]["estimate"]
    with pytest.raises(ValueError):
        read_result(json.dumps(data))


def test_metric_and_run_identity_constraints() -> None:
    data = payload()
    data["benchmarks"][0]["metrics"]["exact/accuracy"]["descriptor"]["metric_id"] = "other"
    with pytest.raises(ValueError):
        read_result(json.dumps(data))
    data = payload()
    data["run_id"] = "another-run"
    with pytest.raises(ValueError):
        read_result(json.dumps(data))


def test_study_timeout_policy_must_be_declared() -> None:
    data = payload()
    data["benchmarks"][0]["metrics"]["exact/accuracy"]["descriptor"]["timeout_value"] = None
    with pytest.raises(ValueError, match="timeout"):
        read_result(json.dumps(data))


def test_partition_roles_are_shared_by_calibration_and_export() -> None:
    fixture = json.loads((FIXTURES / "partition-roles.json").read_text())
    assert fixture["calibration_input"] == fixture["export_input"]
    assert {row["role"] for row in fixture["calibration_input"]} == set(get_args(PartitionRole))
    for row in fixture["calibration_input"]:
        assert DataReference.model_validate(row).model_dump() == row
    row["partition_schema_version"] = "2"
    with pytest.raises(ValueError):
        DataReference.model_validate(row)


def test_published_json_schema_matches_python_source() -> None:
    schema = json.loads((ROOT / "schemas/evaluation-result-v2.schema.json").read_text())
    schema.pop("$schema")
    schema.pop("$id")
    assert schema == ResultEnvelope.model_json_schema()


def test_identity_uses_structured_fields_instead_of_delimiters() -> None:
    raw = payload()["benchmarks"][0]["observations"][0]["identity"]
    first = ObservationIdentity.model_validate({**raw, "sample_id": "a/b", "trial_id": "c"})
    second = ObservationIdentity.model_validate({**raw, "sample_id": "a", "trial_id": "b/c"})
    assert first.logical_id() != second.logical_id()
