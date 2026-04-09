"""
Ollama-specific judge implementation.

Wraps the OpenAI-compatible judge with Ollama model ID formatting.
"""

from typing import Optional

from matric_eval.judges.base import Judge, JudgeResult
from matric_eval.judges.openai_compat import OpenAICompatibleJudge


class OllamaJudge(Judge):
    """
    Judge using a local Ollama model.

    Formats model IDs as "ollama/{model}" for Inspect AI compatibility.

    Args:
        model: Ollama model name (e.g., "llama3.1:8b", "qwen3:14b")
        base_url: Ollama server URL (default: http://localhost:11434)
        temperature: Sampling temperature (default: 0 for deterministic)
    """

    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
    ):
        self._model = model
        # Ollama uses ollama/ prefix in Inspect AI
        inspect_model = f"ollama/{model}" if not model.startswith("ollama/") else model
        self._inner = OpenAICompatibleJudge(
            model=inspect_model,
            base_url=base_url,
            temperature=temperature,
        )

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    async def evaluate(
        self,
        prompt: str,
        response: str,
        criteria: dict,
        reference: Optional[str] = None,
    ) -> JudgeResult:
        result = await self._inner.evaluate(prompt, response, criteria, reference)
        result.metadata["judge_type"] = "ollama"
        result.metadata["model"] = self._model
        return result

    async def compare(
        self,
        prompt: str,
        response_a: str,
        response_b: str,
        criteria: dict,
    ) -> JudgeResult:
        result = await self._inner.compare(prompt, response_a, response_b, criteria)
        result.metadata["judge_type"] = "ollama"
        result.metadata["model"] = self._model
        return result
