"""
Historical trend analysis and regression detection for matric-eval.

Tracks evaluation results over time, detects regressions,
and analyzes performance trends.
"""

from matric_eval.trends.store import EvalStore, EvaluationPoint
from matric_eval.trends.regression import RegressionDetector, Regression
from matric_eval.trends.analyzer import TrendAnalyzer, Trend

__all__ = [
    "EvalStore",
    "EvaluationPoint",
    "Regression",
    "RegressionDetector",
    "Trend",
    "TrendAnalyzer",
]
