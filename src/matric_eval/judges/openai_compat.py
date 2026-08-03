"""
OpenAI-compatible judge implementation.

Works with any OpenAI-compatible API: OpenAI, Ollama, vLLM, llama.cpp,
OpenRouter, Together AI, Groq, etc.
"""

import re
from typing import Optional

from inspect_ai.model import GenerateConfig, get_model

from matric_eval.judges.base import Judge, JudgeResult


def _build_eval_prompt(
    prompt: str, response: str, criteria: dict, reference: Optional[str] = None
) -> str:
    """Build evaluation prompt for the judge."""
    criteria_text = "\n".join(
        f"- {name}: weight {weight}"
        if isinstance(weight, (int, float))
        else f"- {name}: {weight.get('description', '')} (weight {weight.get('weight', 1.0)})"
        for name, weight in criteria.items()
    )

    ref_section = f"\n## Reference Answer\n{reference}\n" if reference else ""

    return f"""You are an expert evaluator. Score the following response.

## Original Prompt
{prompt}

## Response to Evaluate
{response}
{ref_section}
## Evaluation Criteria
{criteria_text}

Score the response from 1-10 considering all criteria and their weights.
Provide your assessment in this exact format:

Rating: [1-10]
Reasoning: [Your explanation]"""


def _build_compare_prompt(prompt: str, response_a: str, response_b: str, criteria: dict) -> str:
    """Build pairwise comparison prompt."""
    criteria_text = "\n".join(
        f"- {name}: weight {weight}"
        if isinstance(weight, (int, float))
        else f"- {name}: {weight.get('description', '')} (weight {weight.get('weight', 1.0)})"
        for name, weight in criteria.items()
    )

    return f"""You are an expert evaluator comparing two responses.

## Original Prompt
{prompt}

## Response A
{response_a}

## Response B
{response_b}

## Evaluation Criteria
{criteria_text}

Compare the two responses. Determine which is better overall.

Respond with ONLY one of:
[[A]] - if Response A is better
[[B]] - if Response B is better
[[C]] - if they are equally good (tie)

Then provide a brief explanation (1-2 sentences)."""


def _parse_rating(text: str) -> float:
    """Parse a numeric rating from judge response."""
    patterns = [
        r"\[\[(\d+(?:\.\d+)?)\]\]",
        r"Rating:\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*/\s*10",
        r"Score:\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return max(1.0, min(10.0, float(match.group(1))))
    return 5.0


def _parse_winner(text: str) -> str:
    """Parse pairwise winner from judge response."""
    if "[[A]]" in text:
        return "A"
    if "[[B]]" in text:
        return "B"
    if "[[C]]" in text:
        return "tie"
    return "tie"


class OpenAICompatibleJudge(Judge):
    """
    Judge using any OpenAI-compatible API.

    Works with OpenAI, vLLM, llama.cpp, OpenRouter, Together AI, Groq, etc.

    Args:
        model: Model name (e.g., "gpt-4o", "meta-llama/Llama-3.2-3B")
        base_url: API base URL (default: OpenAI)
        api_key: API key (default: from OPENAI_API_KEY env var)
        temperature: Sampling temperature (default: 0 for deterministic)
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
    ):
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._temperature = temperature

    @property
    def name(self) -> str:
        return f"openai-compat:{self._model}"

    async def evaluate(
        self,
        prompt: str,
        response: str,
        criteria: dict,
        reference: Optional[str] = None,
    ) -> JudgeResult:
        eval_prompt = _build_eval_prompt(prompt, response, criteria, reference)

        model = get_model(self._model)
        result = await model.generate(
            eval_prompt,
            config=GenerateConfig(
                temperature=self._temperature,
            ),
        )

        raw_score = _parse_rating(result.completion)
        normalized = (raw_score - 1.0) / 9.0

        return JudgeResult(
            score=normalized,
            raw_score=raw_score,
            reasoning=result.completion,
            metadata={"model": self._model, "judge_type": "openai_compatible"},
        )

    async def compare(
        self,
        prompt: str,
        response_a: str,
        response_b: str,
        criteria: dict,
    ) -> JudgeResult:
        compare_prompt = _build_compare_prompt(prompt, response_a, response_b, criteria)

        model = get_model(self._model)
        result = await model.generate(
            compare_prompt,
            config=GenerateConfig(
                temperature=self._temperature,
            ),
        )

        winner = _parse_winner(result.completion)
        score_map = {"A": 1.0, "B": 0.0, "tie": 0.5}

        return JudgeResult(
            score=score_map[winner],
            raw_score=score_map[winner],
            reasoning=result.completion,
            winner=winner,
            metadata={"model": self._model, "judge_type": "openai_compatible"},
        )
