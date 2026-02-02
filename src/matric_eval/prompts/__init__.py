"""
Prompt templates for thinking-capable models.

Provides optimized prompts to reduce reasoning cycles and improve response
quality for different benchmark types.
"""

from matric_eval.prompts.templates import PROMPTS, get_prompt

__all__ = ["PROMPTS", "get_prompt"]
