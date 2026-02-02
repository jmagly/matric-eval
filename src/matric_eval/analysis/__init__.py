"""
Analysis module for matric-eval.

Provides tools for analyzing evaluation results, including:
- Thinking model metrics extraction and aggregation
- Performance analysis and reporting
"""

from matric_eval.analysis.thinking_metrics import (
    ThinkingMetrics,
    ThinkingAggregates,
    extract_thinking_metrics,
    aggregate_metrics,
    count_patterns,
    BACKTRACK_PATTERNS,
    CONCLUSION_PATTERNS,
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
