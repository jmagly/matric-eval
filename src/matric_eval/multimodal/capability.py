"""
Vision capability detection for inference providers.

supports_vision() provides a conservative best-effort determination of
whether a given model is vision-capable, based on known naming patterns.
Returns False for unknown models — false negatives are safer than
accidentally passing image content to a text-only model.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Known vision-capable model name patterns (case-insensitive)
# ---------------------------------------------------------------------------
# Patterns that indicate a model has vision/multimodal capability.
_VISION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bvision\b", re.IGNORECASE),
    re.compile(r"\bvl\b", re.IGNORECASE),          # e.g. qwen2-vl, internvl
    re.compile(r"[-_]vl[-_]?", re.IGNORECASE),     # qwen2-vl-7b
    re.compile(r"\bllava\b", re.IGNORECASE),        # LLaVA models
    re.compile(r"\b4o\b", re.IGNORECASE),           # gpt-4o, gpt-4o-mini
    re.compile(r"\bpixtral\b", re.IGNORECASE),      # Pixtral
    re.compile(r"\bgemini\b", re.IGNORECASE),       # All Gemini models are multimodal
    re.compile(r"\bclaude-3\b", re.IGNORECASE),     # Claude 3 series supports vision
    re.compile(r"\bclaude-opus\b", re.IGNORECASE),
    re.compile(r"\bclaude-sonnet\b", re.IGNORECASE),
    re.compile(r"\bclaude-haiku\b", re.IGNORECASE),
    re.compile(r"\binternvl\b", re.IGNORECASE),     # InternVL
    re.compile(r"\bmoondream\b", re.IGNORECASE),    # Moondream
    re.compile(r"\bminicpm[-_]v\b", re.IGNORECASE),# MiniCPM-V
    re.compile(r"\bqwen.*vl\b", re.IGNORECASE),     # Qwen VL family
    re.compile(r"\bphi-?3.*vision\b", re.IGNORECASE),  # Phi-3-Vision
]


def supports_vision(provider_name: str, model: str) -> bool:
    """
    Return True if the model is known to support vision/image inputs.

    This is a conservative heuristic based on model name patterns.
    Unknown models return False.

    Args:
        provider_name: Provider identifier (e.g. 'ollama', 'openrouter').
                       Currently not used for matching but reserved for
                       future provider-specific overrides.
        model:         Model identifier string.

    Returns:
        True if the model is known to be vision-capable, False otherwise.
    """
    if not model:
        return False

    for pattern in _VISION_PATTERNS:
        if pattern.search(model):
            return True

    return False
