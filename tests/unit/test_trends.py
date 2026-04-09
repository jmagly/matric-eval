"""
Tests for historical trend analysis and regression detection (matric_eval.trends).

Covers:
- EvalStore: SQLite storage, querying, history retrieval
- RegressionDetector: regression detection against baseline
- TrendAnalyzer: trend direction, rate, projection
"""

from datetime import datetime, timedelta

import pytest

from matric_eval.trends.store import EvalStore, EvaluationPoint
from matric_eval.trends.regression import RegressionDetector, Regression
from matric_eval.trends.analyzer import TrendAnalyzer, Trend


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def store(tmp_path) -> EvalStore:
    """Create a temporary EvalStore."""
    db_path = tmp_path / "test_evals.db"
    return EvalStore(db_path)


@pytest.fixture
def populated_store(store: EvalStore) -> EvalStore:
    """Create an EvalStore with sample data."""
    base_time = datetime(2026, 1, 1, 12, 0)
    for i in range(5):
        store.add(EvaluationPoint(
            model="llama3.2:3b",
            benchmark="humaneval",
            score=0.65 + i * 0.02,  # Gradually improving: 0.65 -> 0.73
            tier="smoke",
            run_id=f"run-{i}",
            timestamp=base_time + timedelta(days=i),
        ))
        store.add(EvaluationPoint(
            model="llama3.2:3b",
            benchmark="gsm8k",
            score=0.70 - i * 0.01,  # Slightly declining: 0.70 -> 0.66
            tier="smoke",
            run_id=f"run-{i}",
            timestamp=base_time + timedelta(days=i),
        ))
        store.add(EvaluationPoint(
            model="qwen3:8b",
            benchmark="humaneval",
            score=0.80 + i * 0.002,  # Stable: 0.80 -> 0.808
            tier="smoke",
            run_id=f"run-{i}",
            timestamp=base_time + timedelta(days=i),
        ))
    return store


# =============================================================================
# EvalStore Tests
# =============================================================================


@pytest.mark.unit
class TestEvalStore:
    """Tests for SQLite evaluation store."""

    def test_add_and_retrieve(self, store: EvalStore) -> None:
        """Should store and retrieve evaluation points."""
        point = EvaluationPoint(
            model="test-model",
            benchmark="humaneval",
            score=0.85,
            tier="smoke",
            run_id="run-001",
        )
        store.add(point)

        history = store.get_history("test-model", "humaneval")
        assert len(history) == 1
        assert history[0].score == 0.85
        assert history[0].model == "test-model"

    def test_add_batch(self, store: EvalStore) -> None:
        """Should add multiple points at once."""
        points = [
            EvaluationPoint(model="m1", benchmark="b1", score=0.5, run_id="r1"),
            EvaluationPoint(model="m1", benchmark="b2", score=0.6, run_id="r1"),
        ]
        store.add_batch(points)
        assert store.count() == 2

    def test_get_history_ordered_newest_first(self, populated_store: EvalStore) -> None:
        """Should return history newest first."""
        history = populated_store.get_history("llama3.2:3b", "humaneval")
        assert len(history) == 5
        assert history[0].score > history[-1].score  # Newest (highest) first

    def test_get_history_respects_limit(self, populated_store: EvalStore) -> None:
        """Should limit results."""
        history = populated_store.get_history("llama3.2:3b", "humaneval", limit=3)
        assert len(history) == 3

    def test_get_latest_scores(self, populated_store: EvalStore) -> None:
        """Should return latest score per model."""
        scores = populated_store.get_latest_scores(benchmark="humaneval")
        assert "llama3.2:3b" in scores
        assert "qwen3:8b" in scores

    def test_get_models(self, populated_store: EvalStore) -> None:
        """Should return all unique models."""
        models = populated_store.get_models()
        assert "llama3.2:3b" in models
        assert "qwen3:8b" in models
        assert len(models) == 2

    def test_get_benchmarks(self, populated_store: EvalStore) -> None:
        """Should return all unique benchmarks."""
        benchmarks = populated_store.get_benchmarks()
        assert "humaneval" in benchmarks
        assert "gsm8k" in benchmarks

    def test_count(self, populated_store: EvalStore) -> None:
        """Should count all evaluation points."""
        assert populated_store.count() == 15  # 5 runs * 3 model/benchmark combos

    def test_empty_history(self, store: EvalStore) -> None:
        """Should return empty list for unknown model/benchmark."""
        history = store.get_history("nonexistent", "nope")
        assert history == []

    def test_upsert_on_conflict(self, store: EvalStore) -> None:
        """Should update on duplicate run_id/model/benchmark."""
        store.add(EvaluationPoint(
            model="m1", benchmark="b1", score=0.5, run_id="r1"
        ))
        store.add(EvaluationPoint(
            model="m1", benchmark="b1", score=0.9, run_id="r1"
        ))
        history = store.get_history("m1", "b1")
        assert len(history) == 1
        assert history[0].score == 0.9

    def test_metadata_roundtrip(self, store: EvalStore) -> None:
        """Should preserve metadata through store/retrieve."""
        store.add(EvaluationPoint(
            model="m1",
            benchmark="b1",
            score=0.7,
            run_id="r1",
            metadata={"tokens": 1000, "latency_ms": 150},
        ))
        history = store.get_history("m1", "b1")
        assert history[0].metadata["tokens"] == 1000
        assert history[0].metadata["latency_ms"] == 150


# =============================================================================
# RegressionDetector Tests
# =============================================================================


@pytest.mark.unit
class TestRegressionDetector:
    """Tests for regression detection."""

    def test_detects_regression(self, populated_store: EvalStore) -> None:
        """Should detect significant score drops."""
        detector = RegressionDetector(populated_store, threshold=0.05)

        # llama3.2:3b humaneval baseline is ~0.69 avg
        # A drop to 0.50 should be detected
        regressions = detector.check("llama3.2:3b", {"humaneval": 0.50})
        assert len(regressions) == 1
        assert regressions[0].benchmark == "humaneval"
        assert regressions[0].delta < 0

    def test_no_regression_for_improvement(self, populated_store: EvalStore) -> None:
        """Should not flag improvements as regressions."""
        detector = RegressionDetector(populated_store, threshold=0.05)

        regressions = detector.check("llama3.2:3b", {"humaneval": 0.90})
        assert len(regressions) == 0

    def test_no_regression_within_threshold(self, populated_store: EvalStore) -> None:
        """Should not flag minor drops within threshold."""
        detector = RegressionDetector(populated_store, threshold=0.05)

        # Baseline ~0.69, threshold 0.05 → 0.64 is edge
        regressions = detector.check("llama3.2:3b", {"humaneval": 0.66})
        assert len(regressions) == 0

    def test_no_baseline_no_regression(self, populated_store: EvalStore) -> None:
        """Should not flag regression for new benchmarks."""
        detector = RegressionDetector(populated_store, threshold=0.05)

        regressions = detector.check("llama3.2:3b", {"new_benchmark": 0.30})
        assert len(regressions) == 0

    def test_severity_classification(self, populated_store: EvalStore) -> None:
        """Should classify regression severity."""
        detector = RegressionDetector(populated_store, threshold=0.01)

        # Severe drop: 0.69 → 0.20
        regressions = detector.check("llama3.2:3b", {"humaneval": 0.20})
        assert regressions[0].severity == "severe"

    def test_check_point(self, populated_store: EvalStore) -> None:
        """Should check a single EvaluationPoint."""
        detector = RegressionDetector(populated_store, threshold=0.05)

        point = EvaluationPoint(
            model="llama3.2:3b",
            benchmark="humaneval",
            score=0.40,
        )
        regression = detector.check_point(point)
        assert regression is not None
        assert regression.severity in ("minor", "moderate", "severe")

    def test_check_point_no_regression(self, populated_store: EvalStore) -> None:
        """Should return None when no regression."""
        detector = RegressionDetector(populated_store, threshold=0.05)

        point = EvaluationPoint(
            model="llama3.2:3b",
            benchmark="humaneval",
            score=0.90,
        )
        assert detector.check_point(point) is None


# =============================================================================
# TrendAnalyzer Tests
# =============================================================================


@pytest.mark.unit
class TestTrendAnalyzer:
    """Tests for trend analysis."""

    def test_detects_improving_trend(self, populated_store: EvalStore) -> None:
        """Should detect improving trend for llama humaneval."""
        analyzer = TrendAnalyzer(populated_store, min_points=3)
        trend = analyzer.analyze("llama3.2:3b", "humaneval")

        assert trend is not None
        assert trend.direction == "improving"
        assert trend.rate_per_run > 0

    def test_detects_declining_trend(self, populated_store: EvalStore) -> None:
        """Should detect declining trend for llama gsm8k."""
        analyzer = TrendAnalyzer(populated_store, min_points=3)
        trend = analyzer.analyze("llama3.2:3b", "gsm8k")

        assert trend is not None
        assert trend.direction == "declining"
        assert trend.rate_per_run < 0

    def test_detects_stable_trend(self, populated_store: EvalStore) -> None:
        """Should detect stable trend for qwen humaneval."""
        analyzer = TrendAnalyzer(populated_store, min_points=3)
        trend = analyzer.analyze("qwen3:8b", "humaneval")

        assert trend is not None
        assert trend.direction == "stable"

    def test_insufficient_data(self, populated_store: EvalStore) -> None:
        """Should return None with insufficient data points."""
        analyzer = TrendAnalyzer(populated_store, min_points=10)
        trend = analyzer.analyze("llama3.2:3b", "humaneval")
        assert trend is None

    def test_no_data(self, populated_store: EvalStore) -> None:
        """Should return None for unknown model."""
        analyzer = TrendAnalyzer(populated_store)
        trend = analyzer.analyze("nonexistent", "humaneval")
        assert trend is None

    def test_trend_projection(self, populated_store: EvalStore) -> None:
        """Should project future scores."""
        analyzer = TrendAnalyzer(populated_store, min_points=3)
        trend = analyzer.analyze("llama3.2:3b", "humaneval")

        assert trend is not None
        projected = trend.project(runs_ahead=10)
        assert 0.0 <= projected <= 1.0
        # Improving trend should project higher
        assert projected > trend.latest_score

    def test_trend_data_points(self, populated_store: EvalStore) -> None:
        """Should report correct data point count."""
        analyzer = TrendAnalyzer(populated_store, min_points=3)
        trend = analyzer.analyze("llama3.2:3b", "humaneval")

        assert trend is not None
        assert trend.data_points == 5

    def test_compare_trajectories(self, populated_store: EvalStore) -> None:
        """Should compare multiple model trajectories."""
        analyzer = TrendAnalyzer(populated_store, min_points=3)
        comparison = analyzer.compare_trajectories(
            ["llama3.2:3b", "qwen3:8b"],
            "humaneval",
        )
        assert "llama3.2:3b" in comparison
        assert "qwen3:8b" in comparison
        assert comparison["llama3.2:3b"] is not None
        assert comparison["qwen3:8b"] is not None


# =============================================================================
# Regression Dataclass Tests
# =============================================================================


@pytest.mark.unit
class TestRegressionDataclass:
    """Tests for Regression dataclass."""

    def test_pct_change(self) -> None:
        """Should compute percentage change correctly."""
        reg = Regression(
            model="m",
            benchmark="b",
            baseline_score=0.80,
            new_score=0.60,
            delta=-0.20,
            severity="severe",
        )
        assert abs(reg.pct_change - (-0.25)) < 0.01

    def test_pct_change_zero_baseline(self) -> None:
        """Should handle zero baseline."""
        reg = Regression(
            model="m",
            benchmark="b",
            baseline_score=0.0,
            new_score=0.5,
            delta=0.5,
            severity="minor",
        )
        assert reg.pct_change == 0.0


# =============================================================================
# Trend Dataclass Tests
# =============================================================================


@pytest.mark.unit
class TestTrendDataclass:
    """Tests for Trend dataclass."""

    def test_project_clamps(self) -> None:
        """Should clamp projections to [0, 1]."""
        trend = Trend(
            model="m",
            benchmark="b",
            direction="improving",
            rate_per_run=0.1,
            confidence=0.9,
            data_points=5,
            first_score=0.5,
            latest_score=0.95,
        )
        # 0.95 + 0.1*10 = 1.95, should clamp to 1.0
        assert trend.project(10) == 1.0

    def test_project_declining_clamps_zero(self) -> None:
        """Should clamp negative projections to 0."""
        trend = Trend(
            model="m",
            benchmark="b",
            direction="declining",
            rate_per_run=-0.1,
            confidence=0.9,
            data_points=5,
            first_score=0.5,
            latest_score=0.1,
        )
        # 0.1 + (-0.1)*10 = -0.9, should clamp to 0.0
        assert trend.project(10) == 0.0
