"""
Inspect AI scorer integration for the universal judge system.

Bridges the Judge interface with Inspect AI's scorer protocol.
"""

from typing import Optional

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from matric_eval.judges.factory import create_judge


@scorer(metrics=[mean()])
def universal_judge_scorer(
    judge_spec: str = "ollama:llama3.1:8b",
    criteria: Optional[dict] = None,
    template: Optional[str] = None,
) -> Scorer:
    """
    Create an Inspect AI scorer using any judge provider.

    This bridges the universal Judge interface with Inspect AI's scorer protocol.
    It can use any configured judge (Ollama, OpenAI, Anthropic, etc.) to evaluate
    model responses.

    Args:
        judge_spec: Judge specification string (e.g., "ollama:llama3.1:8b", "openai:gpt-4o")
        criteria: Evaluation criteria with weights. If None, uses default quality criteria.
        template: Optional judge template name from JUDGE_PROMPTS (overrides criteria-based eval)

    Returns:
        Scorer function compatible with Inspect AI

    Example:
        >>> task = Task(
        ...     dataset=samples,
        ...     solver=[generate()],
        ...     scorer=universal_judge_scorer("ollama:llama3.1:8b")
        ... )
    """
    judge = create_judge(judge_spec)
    eval_criteria = criteria or {
        "helpfulness": 0.3,
        "accuracy": 0.3,
        "relevance": 0.2,
        "clarity": 0.2,
    }

    if template:
        # Use template-based evaluation via existing llm_judge infrastructure
        from matric_eval.scorers.llm_judge import (
            JUDGE_PROMPTS,
        )

        judge_template = JUDGE_PROMPTS.get(template)
        if not judge_template:
            raise ValueError(f"Unknown judge template: {template}")

    async def score(state: TaskState, target: Target) -> Score:
        """Score using the universal judge."""
        try:
            prompt = state.input_text or ""
            response = state.output.completion
            reference = target.text if target and target.text else None

            result = await judge.evaluate(
                prompt=prompt,
                response=response,
                criteria=eval_criteria,
                reference=reference,
            )

            return Score(
                value=result.score,
                explanation=f"Judge ({judge.name}): {result.raw_score}/10. {result.reasoning[:200]}",
                metadata={
                    "raw_score": result.raw_score,
                    "judge": judge.name,
                    "confidence": result.confidence,
                    **result.metadata,
                },
            )

        except Exception as e:
            return Score(
                value=0.5,
                explanation=f"Judge error ({judge.name}): {str(e)}",
            )

    return score
