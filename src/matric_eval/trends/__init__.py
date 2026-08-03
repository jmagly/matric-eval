"""
Historical trend analysis and regression detection for matric-eval.

Tracks evaluation results over time, detects regressions,
and analyzes performance trends.
"""

from matric_eval.trends.analyzer import Trend, TrendAnalyzer
from matric_eval.trends.regression import Regression, RegressionDetector
from matric_eval.trends.store import EvalStore, EvaluationPoint

__all__ = [
    "EvalStore",
    "EvaluationPoint",
    "Regression",
    "RegressionDetector",
    "Trend",
    "TrendAnalyzer",
]
