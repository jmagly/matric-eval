"""
Model utilities for matric-eval.

Provides model capability detection and configuration helpers.
"""

from matric_eval.models.detection import (
    has_thinking_capability,
    get_ollama_model_info,
)

__all__ = [
    "has_thinking_capability",
    "get_ollama_model_info",
]
