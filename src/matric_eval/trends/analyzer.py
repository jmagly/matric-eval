"""
Trend analysis for evaluation time-series data.

Analyzes performance trajectories, identifies improving/declining trends,
and projects future performance.
"""

from dataclasses import dataclass
from typing import Optional

from matric_eval.trends.store import EvalStore, EvaluationPoint


@dataclass
class Trend:
    """Analysis of a model's performance trend on a benchmark."""

    model: str
    benchmark: str
    direction: str  # "improving", "stable", "declining"
    rate_per_run: float  # Score change per evaluation run
    confidence: float  # 0.0 - 1.0
    data_points: int
    first_score: float
    latest_score: float

    def project(self, runs_ahead: int = 5) -> float:
        """
        Project future score based on trend.

        Args:
            runs_ahead: Number of future runs to project

        Returns:
            Projected score (clamped to 0-1)
        """
        projected = self.latest_score + (self.rate_per_run * runs_ahead)
        return max(0.0, min(1.0, projected))


class TrendAnalyzer:
    """
    Analyzes performance trends from historical evaluation data.

    Args:
        store: EvalStore with historical data
        min_points: Minimum data points needed for trend analysis (default: 3)
    """

    def __init__(self, store: EvalStore, min_points: int = 3):
        self.store = store
        self.min_points = min_points

    def analyze(
        self,
        model: str,
        benchmark: str,
        limit: int = 50,
    ) -> Optional[Trend]:
        """
        Analyze the performance trend for a model/benchmark pair.

        Uses simple linear regression on the score time series.

        Args:
            model: Model name
            benchmark: Benchmark name
            limit: Maximum history points to consider

        Returns:
            Trend analysis or None if insufficient data
        """
        history = self.store.get_history(model, benchmark, limit=limit)

        if len(history) < self.min_points:
            return None

        # Reverse to chronological order (oldest first)
        history = list(reversed(history))

        scores = [h.score for h in history]
        n = len(scores)

        # Simple linear regression: score = a + b * index
        x_mean = (n - 1) / 2.0
        y_mean = sum(scores) / n

        numerator = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(scores))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        # Compute R-squared for confidence
        ss_res = sum(
            (s - (y_mean + slope * (i - x_mean))) ** 2
            for i, s in enumerate(scores)
        )
        ss_tot = sum((s - y_mean) ** 2 for s in scores)

        if ss_tot == 0:
            r_squared = 1.0
        else:
            r_squared = max(0.0, 1.0 - ss_res / ss_tot)

        # Classify direction
        if abs(slope) < 0.005:  # Less than 0.5% per run
            direction = "stable"
        elif slope > 0:
            direction = "improving"
        else:
            direction = "declining"

        return Trend(
            model=model,
            benchmark=benchmark,
            direction=direction,
            rate_per_run=slope,
            confidence=r_squared,
            data_points=n,
            first_score=scores[0],
            latest_score=scores[-1],
        )

    def compare_trajectories(
        self,
        models: list[str],
        benchmark: str,
    ) -> dict[str, Optional[Trend]]:
        """
        Compare performance trajectories across multiple models.

        Args:
            models: List of model names
            benchmark: Benchmark to compare

        Returns:
            Dict mapping model name to Trend (or None if insufficient data)
        """
        return {model: self.analyze(model, benchmark) for model in models}
