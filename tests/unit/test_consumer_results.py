"""Hand-authored consumer expectations; original golden bytes are immutable."""

import hashlib
import json
from pathlib import Path

import pytest

from matric_eval.results.consumer import (
    ConsumerError,
    ConsumerFailure,
    LegacyImport,
    ResultCollection,
    convert_legacy_artifact,
    project_legacy,
    read_consumer_result,
    strict_json,
    write_consumer_result,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/results/consumer"
MANIFEST = json.loads((FIXTURES / "expectations.json").read_text())


def pointer(value, path):
    for key in path.lstrip("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


@pytest.mark.parametrize(
    "case",
    [item for item in MANIFEST["cases"] if item["kind"] != "parser_cases"],
    ids=lambda item: item["id"],
)
def test_shared_golden_expectations(case):
    path = FIXTURES / case["source"]
    before = path.read_bytes()
    assert hashlib.sha256(before).hexdigest() == case["source_sha256"]
    result = read_consumer_result(before.decode())
    raw = result.payload if isinstance(result, LegacyImport) else result.model_dump()
    for assertion in case.get("raw_assertions", []):
        assert pointer(raw, assertion["pointer"]) == assertion["equals"]
    if "metric_ids" in case:
        assert sorted(raw["benchmarks"][0]["metrics"]) == case["metric_ids"]
    if "sample_observation_count" in case:
        assert len(raw["benchmarks"][0]["observations"]) == case["sample_observation_count"]
    if "per_metric_outcome_counts" in case:
        assert all(
            metric["outcome_counts"] == case["per_metric_outcome_counts"]
            for metric in raw["benchmarks"][0]["metrics"].values()
        )
    assert read_consumer_result(write_consumer_result(result)).model_dump() == result.model_dump()
    if "legacy_numeric_projection" in case:
        with pytest.raises(ConsumerError, match="legacy_projection_unrepresentable"):
            project_legacy(result)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "case",
    json.loads((FIXTURES / "strict-json-cases.json").read_text())["cases"],
    ids=lambda item: item["id"],
)
def test_shared_strict_json(case):
    if case["strict_json"] == "reject":
        with pytest.raises(ConsumerError, match=case["reason"]):
            strict_json(case["source"])
    else:
        strict_json(case["source"])
        if case.get("consumer") == "reject":
            with pytest.raises(ConsumerError, match=case["reason"]):
                read_consumer_result(case["source"])


def test_conversion_exclusive_deterministic_and_mutation_refused(tmp_path):
    source = FIXTURES / "legacy-null.json"
    before = source.read_bytes()
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    result = convert_legacy_artifact(source, first)
    convert_legacy_artifact(source, second)
    assert first.read_bytes() == second.read_bytes()
    alias = tmp_path / "source-alias.json"
    alias.symlink_to(source.resolve())
    for target in [source, first, alias]:
        with pytest.raises(ConsumerError, match="output_requires_new_path"):
            convert_legacy_artifact(source, target)
    assert source.read_bytes() == before
    result.payload["overall_score"] = 0.0
    with pytest.raises(ConsumerError):
        project_legacy(result)


def test_collection_failure_identity_and_foreign_markers():
    source = read_consumer_result((FIXTURES / "../v2/named-metrics.json").read_text())
    failure = ConsumerFailure(
        run_id=source.run_id,
        model_id=source.model_id,
        execution="unknown",
        reason="result_projection_unavailable",
    )
    for results, failures in [([source], [failure]), ([], [failure, failure])]:
        with pytest.raises(ValueError):
            ResultCollection(results=results, failures=failures)
    for marker in ["schema_version", "recovery_schema_version"]:
        with pytest.raises(ConsumerError, match="unsupported_schema"):
            read_consumer_result(json.dumps({marker: "99", "model": "m", "benchmarks": {}}))


@pytest.mark.parametrize(
    "change", json.loads((FIXTURES / "invalid-legacy-projections.json").read_text())["changes"]
)
def test_legacy_projection_rejects_coercible_invalid_fields(change):
    value = json.loads((FIXTURES / "legacy-zero.json").read_text())
    value.update(change)
    with pytest.raises(ConsumerError, match="legacy_projection_unrepresentable"):
        project_legacy(read_consumer_result(json.dumps(value)))
