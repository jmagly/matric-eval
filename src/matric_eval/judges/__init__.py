"""
Universal LLM-as-Judge system.

Supports standard LLM APIs (OpenAI, Ollama, Anthropic) for evaluation
with a unified interface, factory pattern, and Inspect AI scorer integration.
"""

from matric_eval.judges.base import Judge, JudgeResult
from matric_eval.judges.factory import JudgeFactory, create_judge
from matric_eval.judges.ollama import OllamaJudge
from matric_eval.judges.openai_compat import OpenAICompatibleJudge
from matric_eval.judges.scorer import universal_judge_scorer

__all__ = [
    "Judge",
    "JudgeFactory",
    "JudgeResult",
    "OllamaJudge",
    "OpenAICompatibleJudge",
    "create_judge",
    "universal_judge_scorer",
]
