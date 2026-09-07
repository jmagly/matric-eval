"""Synthetic declared comparison fixtures, not provider/model qualification."""

import sqlite3
from pathlib import Path

import pytest

from matric_eval.recommendation import RecommendationEngine
from matric_eval.results.comparison import attach_comparison
from matric_eval.results.consumer import ConsumerError, canonical_json, read_consumer_result
from matric_eval.results.contract import ResultEnvelope
from matric_eval.results.ranking import RecommendationPolicy, recommend_consumers
from matric_eval.trends.analyzer import TrendAnalyzer
from matric_eval.trends.consumer_store import ConsumerTrendStore
from matric_eval.trends.regression import RegressionDetector
from matric_eval.trends.store import EvalStore

FIXTURE = Path(__file__).parents[1] / "fixtures/results/v2/named-metrics.json"


def declared_source(run="run", model="ollama/a", timestamp="2026-01-01T00:00:00Z"):
    source = read_consumer_result(FIXTURE.read_text())
    source.comparability = None
    source.run_id, source.model_id, source.created_at = run, model, timestamp
    source.configuration_sha256 = "b" * 64
    for benchmark in source.benchmarks:
        benchmark.protocol_sha256 = "a" * 64
        for selection in benchmark.selection:
            selection.data.role = "final_test"
        for row in benchmark.observations:
            row.identity.run_id, row.identity.model_id = run, model
            row.observation_id = row.identity.logical_id()
    return attach_comparison(ResultEnvelope.model_validate(source.model_dump()))


def policy(source):
    return RecommendationPolicy.model_validate(
        {
            "version": "1",
            "comparison_sha256": source.comparability.sha256,
            "capabilities": {
                "accuracy": {
                    "version": "1",
                    "aggregation_id": "fixture-complete/1",
                    "target_units": "fraction",
                    "target_direction": "higher",
                    "missingness_policy": "require-complete",
                    "terms": [
                        {
                            "benchmark_id": "benchmark",
                            "metric_id": "exact/accuracy",
                            "weight": 1.0,
                            "transform": {
                                "version": "1",
                                "kind": "identity",
                                "source_units": "fraction",
                                "source_minimum": 0.0,
                                "source_maximum": 1.0,
                                "source_direction": "higher",
                                "scale": 1.0,
                                "offset": 0.0,
                            },
                        }
                    ],
                }
            },
        }
    )


def test_ranking_requires_explicit_policy_and_preserves_sources():
    first, second = declared_source(), declared_source("other", "openai/a")
    report = recommend_consumers([first, second], policy(first))
    assert report["status"] == "recommended"
    assert set(report["model_scores"]) == {"ollama/a", "openai/a"}
    assert report["recommendations"]["accuracy"]["score"] == 0.5
    assert report["best_overall"] is None
    assert (
        report["sources"][0]["benchmarks"][0]["metrics"]["exact/stderr"]["estimate"]["value"] == 0.5
    )
    excluded = recommend_consumers([first], None)
    assert excluded["status"] == "no_recommendation"
    assert excluded["exclusions"][0]["reasons"] == ["recommendation_policy_undeclared"]


def test_unknown_comparison_changed_scope_and_repeated_models_are_excluded():
    first = declared_source()
    unknown = read_consumer_result(FIXTURE.read_text())
    changed = declared_source("changed", "other")
    changed.comparability = None
    changed.benchmarks[0].protocol_sha256 = "c" * 64
    changed = attach_comparison(changed)
    report = recommend_consumers([unknown, changed], policy(first))
    assert report["status"] == "no_recommendation"
    assert any("comparison_scope_mismatch" in item["reasons"] for item in report["exclusions"])
    assert (
        recommend_consumers([first, declared_source("repeat")], policy(first))["status"]
        == "no_recommendation"
    )


def test_legacy_ranking_and_trends_refuse_by_default(tmp_path):
    raw = {
        "model": "m",
        "status": "success",
        "tier": "smoke",
        "overall_score": 1.0,
        "benchmarks": {"b": {"score": 1.0}},
    }
    report = RecommendationEngine().recommend([raw])
    assert report.recommendations == {}
    assert report.metadata["status"] == "no_recommendation"
    store = EvalStore(tmp_path / "legacy.sqlite")
    try:
        with pytest.raises(ValueError, match="legacy_trend_unverified"):
            TrendAnalyzer(store).analyze("m", "b")
        with pytest.raises(ValueError, match="legacy_trend_unverified"):
            RegressionDetector(store).check("m", {"b": 0.0})
    finally:
        store.close()


def test_nullable_immutable_store_and_timestamp_order(tmp_path):
    path = tmp_path / "history.sqlite"
    # Existing legacy table is retained byte-for-byte at the row level.
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE evaluations (marker TEXT)")
    connection.execute("INSERT INTO evaluations VALUES ('retained')")
    connection.commit()
    connection.close()
    store = ConsumerTrendStore(path)
    try:
        early = declared_source("early", timestamp="2026-01-01T01:00:00+02:00")
        late = declared_source("late", timestamp="2025-12-31T23:30:00Z")
        naive = declared_source("naive", timestamp="2026-01-02T00:00:00")
        for source in [late, early, naive]:
            text = canonical_json(source.model_dump())
            assert store.ingest(text) == store.ingest(text)
        history = store.history("ollama/a", "benchmark", "exact/accuracy")
        assert [item["source"]["run_id"] for item in history] == ["early", "late", "naive"]
        assert (
            store.comparable_series(
                "ollama/a", "benchmark", "exact/accuracy", early.comparability.sha256
            )["points"]
            == []
        )
        series = store.comparable_series(
            "ollama/a",
            "benchmark",
            "exact/accuracy",
            early.comparability.sha256,
            require_unchanged_model=False,
        )
        assert len(series["points"]) == 2
        assert series["excluded"][0]["reasons"] == ["timestamp_unverified"]
        altered = early.model_copy(deep=True, update={"created_at": "2026-01-03T00:00:00Z"})
        with pytest.raises(ConsumerError, match="conflicting_source_identity"):
            store.ingest(canonical_json(altered.model_dump()))
        assert store.connection.execute("SELECT marker FROM evaluations").fetchall() == [
            ("retained",)
        ]
        assert (
            store.connection.execute("SELECT count(*) FROM consumer_sources_v1").fetchone()[0] == 3
        )
    finally:
        store.close()


def test_consumer_store_refuses_recovery_schema_without_mutation(tmp_path):
    path = tmp_path / "journal.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE intents (marker TEXT)")
    connection.commit()
    connection.close()
    before = path.read_bytes()
    with pytest.raises(ConsumerError, match="unsupported_database_schema"):
        ConsumerTrendStore(path)
    assert path.read_bytes() == before


def test_first_profile_refuses_capability_scope_outside_full_suite():
    source = declared_source()
    extra = source.benchmarks[0].model_copy(deep=True)
    extra.benchmark_id = "additional-benchmark"
    for row in extra.observations:
        row.identity.benchmark_id = extra.benchmark_id
        row.observation_id = row.identity.logical_id()
    source.benchmarks.append(extra)
    source.comparability = None
    source = attach_comparison(ResultEnvelope.model_validate(source.model_dump()))
    declaration = policy(source)
    report = recommend_consumers([source], declaration)
    assert report["status"] == "no_recommendation"
    assert report["model_scores"][source.model_id]["capability_scores"]["accuracy"] is None
    assert report["exclusions"][0]["reasons"] == ["capability_scope_mismatch"]
