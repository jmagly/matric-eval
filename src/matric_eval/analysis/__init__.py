"""
Analysis module for matric-eval.

Provides tools for analyzing evaluation results, including:
- Thinking model metrics extraction and aggregation
- Performance analysis and reporting
"""

from matric_eval.analysis.thinking_metrics import (
    BACKTRACK_PATTERNS,
    CONCLUSION_PATTERNS,
    ThinkingAggregates,
    ThinkingMetrics,
    aggregate_metrics,
    count_patterns,
    extract_thinking_metrics,
)

__all__ = [
    "ThinkingMetrics",
    "ThinkingAggregates",
    "extract_thinking_metrics",
    "aggregate_metrics",
    "count_patterns",
    "BACKTRACK_PATTERNS",
    "CONCLUSION_PATTERNS",
]
