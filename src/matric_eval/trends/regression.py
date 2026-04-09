"""
Regression detection for evaluation scores.

Compares new evaluation results against historical baselines
to detect significant performance drops.
"""

from dataclasses import dataclass
from typing import Optional

from matric_eval.trends.store import EvalStore, EvaluationPoint


@dataclass
class Regression:
    """A detected regression in model performance."""

    model: str
    benchmark: str
    baseline_score: float
    new_score: float
    delta: float  # Negative = regression
    severity: str  # "minor", "moderate", "severe"
    probable_cause: str = ""

    @property
    def pct_change(self) -> float:
        """Percentage change from baseline."""
        if self.baseline_score == 0:
            return 0.0
        return self.delta / self.baseline_score


class RegressionDetector:
    """
    Detects performance regressions by comparing new scores against
    historical baselines.

    Args:
        store: EvalStore with historical data
        threshold: Minimum score drop to flag (default: 0.05 = 5%)
        window_size: Number of recent runs to use as baseline (default: 5)
    """

    def __init__(
        self,
        store: EvalStore,
        threshold: float = 0.05,
        window_size: int = 5,
    ):
        self.store = store
        self.threshold = threshold
        self.window_size = window_size

    def check(
        self,
        model: str,
        new_results: dict[str, float],
    ) -> list[Regression]:
        """
        Check for regressions in new results against historical baseline.

        Args:
            model: Model name
            new_results: Dict mapping benchmark name to new score

        Returns:
            List of detected regressions
        """
        regressions = []

        for benchmark, new_score in new_results.items():
            history = self.store.get_history(model, benchmark, limit=self.window_size)

            if not history:
                continue  # No baseline to compare against

            # Compute baseline as mean of recent scores
            baseline_scores = [h.score for h in history]
            baseline = sum(baseline_scores) / len(baseline_scores)

            delta = new_score - baseline

            # Check if regression exceeds threshold
            if delta < -self.threshold:
                severity = self._classify_severity(delta, baseline)
                regressions.append(
                    Regression(
                        model=model,
                        benchmark=benchmark,
                        baseline_score=baseline,
                        new_score=new_score,
                        delta=delta,
                        severity=severity,
                    )
                )

        return regressions

    def check_point(
        self,
        point: EvaluationPoint,
    ) -> Optional[Regression]:
        """
        Check a single evaluation point for regression.

        Args:
            point: New evaluation point

        Returns:
            Regression if detected, None otherwise
        """
        results = self.check(point.model, {point.benchmark: point.score})
        return results[0] if results else None

    def _classify_severity(self, delta: float, baseline: float) -> str:
        """Classify regression severity based on score drop."""
        if baseline == 0:
            return "minor"

        pct_drop = abs(delta / baseline)

        if pct_drop >= 0.20:
            return "severe"
        elif pct_drop >= 0.10:
            return "moderate"
        else:
            return "minor"
