"""
LLM-as-judge scorer for evaluating free-form responses.

Provides comprehensive judge-based evaluation including:
- Single scoring (1-10 scale) for quality assessment
- Pairwise comparison (A/B/tie) for relative ranking
- Template-based customizable judge prompts
- Agentic evaluation support for tool-using models

Ported from matric-memory evaluation infrastructure.

This is particularly useful for benchmarks like MT-Bench where responses
are subjective and don't have a single correct answer.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

from inspect_ai.model import get_model
from inspect_ai.scorer import Score, Scorer, Target, scorer
from inspect_ai.solver import TaskState


class JudgeType(str, Enum):
    """Type of judge evaluation."""

    SINGLE = "single"  # Single response scoring (1-10)
    PAIRWISE = "pairwise"  # Compare two responses (A/B/tie)
    REFERENCE = "reference"  # Score against reference answer


@dataclass
class ScoringConfig:
    """Configuration for score parsing."""

    min_score: int = 1
    max_score: int = 10


@dataclass
class JudgePrompt:
    """
    Template for LLM-as-judge evaluation.

    Ported from matric-memory's JudgePrompt structure.
    Supports variable substitution with {variable} placeholders.
    """

    name: str
    prompt_type: JudgeType
    category: str
    system_prompt: str
    prompt_template: str
    output_format: str
    scoring: ScoringConfig = field(default_factory=ScoringConfig)

    def format(self, **variables: str) -> str:
        """Format the prompt template with variables."""
        result = self.prompt_template
        for key, value in variables.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result


@dataclass
class JudgeResult:
    """Result from an LLM judge evaluation."""

    prompt_name: str
    score: Optional[float] = None  # For single evaluations (normalized 0-1)
    raw_score: Optional[int] = None  # Original score (e.g., 1-10)
    winner: Optional[str] = None  # For pairwise ("A", "B", or "C" for tie)
    reasoning: str = ""
    raw_output: str = ""


# =============================================================================
# Built-in Judge Prompt Templates (ported from matric-memory)
# =============================================================================

JUDGE_PROMPTS: dict[str, JudgePrompt] = {
    "default": JudgePrompt(
        name="default",
        prompt_type=JudgeType.SINGLE,
        category="general",
        system_prompt="You are an expert evaluator assessing the quality of AI responses.",
        prompt_template="""Evaluate the following response based on these criteria:
- Helpfulness: Does it address the user's needs?
- Relevance: Is it on-topic and appropriate?
- Accuracy: Is the information correct?
- Coherence: Is it well-structured and easy to understand?

Question: {question}

Response: {response}

Provide a score from 1-10 where:
- 1-3: Poor quality (unhelpful, off-topic, inaccurate, or incoherent)
- 4-6: Moderate quality (partially helpful, some issues)
- 7-8: Good quality (helpful, relevant, accurate, coherent)
- 9-10: Excellent quality (exceptional in all criteria)

Format your response as: "Score: X/10" followed by a brief explanation.""",
        output_format="Score: X/10",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "mtbench": JudgePrompt(
        name="mtbench",
        prompt_type=JudgeType.SINGLE,
        category="multi_turn",
        system_prompt="You are an expert evaluator for multi-turn conversations.",
        prompt_template="""Please act as an impartial judge and evaluate the quality of the response provided by an AI assistant to the user question displayed below.

[Question]
{question}

[The Start of Assistant's Answer]
{response}
[The End of Assistant's Answer]

Evaluate the response on a scale of 1-10, considering:
1. Helpfulness - Does it address the question effectively?
2. Accuracy - Is the information factually correct?
3. Depth - Does it provide sufficient detail?
4. Clarity - Is it well-organized and easy to understand?

Begin your evaluation by providing a short explanation. Be as objective as possible. After providing your explanation, output your final score using the format: "[[rating]]", for example: "[[8]]".""",
        output_format="[[rating]]",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "pairwise": JudgePrompt(
        name="pairwise",
        prompt_type=JudgeType.PAIRWISE,
        category="comparison",
        system_prompt="You are an expert evaluator comparing AI responses.",
        prompt_template="""Please act as an impartial judge and evaluate the quality of the responses provided by two AI assistants to the user question displayed below.

[Question]
{question}

[The Start of Assistant A's Answer]
{response_a}
[The End of Assistant A's Answer]

[The Start of Assistant B's Answer]
{response_b}
[The End of Assistant B's Answer]

Compare the two responses and determine which is better based on:
1. Helpfulness - Which better addresses the question?
2. Accuracy - Which provides more correct information?
3. Depth - Which provides more useful detail?
4. Clarity - Which is better organized and clearer?

Begin your evaluation by comparing the two responses. Be as objective as possible.
After providing your explanation, output your final verdict by strictly following this format:
- If Assistant A is better: "[[A]]"
- If Assistant B is better: "[[B]]"
- If they are equally good: "[[C]]" (tie)""",
        output_format="[[A/B/C]]",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "reference": JudgePrompt(
        name="reference",
        prompt_type=JudgeType.REFERENCE,
        category="accuracy",
        system_prompt="You are an expert evaluator comparing responses to a reference answer.",
        prompt_template="""Please act as an impartial judge and evaluate the accuracy of the response compared to the reference answer.

[Question]
{question}

[Reference Answer]
{reference}

[Assistant's Answer]
{response}

Evaluate how well the assistant's answer matches the reference answer:
1. Factual Accuracy - Does it contain the same key facts?
2. Completeness - Does it cover the same important points?
3. Correctness - Are there any contradictions with the reference?

Provide a score from 1-10 where:
- 1-3: Major factual errors or missing key information
- 4-6: Some correct information but incomplete or has minor errors
- 7-8: Mostly accurate with good coverage
- 9-10: Excellent match with reference answer

Format your response as: "Score: X/10" followed by a brief explanation.""",
        output_format="Score: X/10",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "title_quality": JudgePrompt(
        name="title_quality",
        prompt_type=JudgeType.SINGLE,
        category="knowledge_management",
        system_prompt="You are an expert evaluator for note title quality.",
        prompt_template="""Evaluate the quality of this title for the given note content.

[Note Content]
{content}

[Generated Title]
{title}

Evaluate the title on these criteria:
1. Relevance - Does it accurately represent the content?
2. Specificity - Is it specific enough to distinguish this note?
3. Conciseness - Is it appropriately brief (not too long)?
4. Format - Is it clean (no markdown, special chars, or "Title:" prefix)?

Provide a score from 1-10 where:
- 1-3: Poor title (irrelevant, too generic, or badly formatted)
- 4-6: Acceptable title (somewhat relevant but could be better)
- 7-8: Good title (relevant, specific, well-formatted)
- 9-10: Excellent title (perfectly captures the content)

Format your response as: "Score: X/10" followed by a brief explanation.""",
        output_format="Score: X/10",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "agentic": JudgePrompt(
        name="agentic",
        prompt_type=JudgeType.SINGLE,
        category="agentic",
        system_prompt="You are an expert evaluator for AI agent behavior and tool usage.",
        prompt_template="""Evaluate the quality of this agent's response and tool usage.

[Task]
{task}

[Available Tools]
{tools}

[Agent Response and Actions]
{response}

[Expected Outcome]
{expected}

Evaluate the agent on these criteria:
1. Tool Selection - Did it choose the appropriate tools?
2. Parameter Accuracy - Were tool parameters correct?
3. Reasoning - Was the thought process sound?
4. Outcome - Did it achieve the expected result?
5. Efficiency - Was the solution appropriately direct?

Provide a score from 1-10 where:
- 1-3: Failed task or major tool usage errors
- 4-6: Partial success or suboptimal tool usage
- 7-8: Good execution with minor improvements possible
- 9-10: Excellent tool usage and task completion

Format your response as: "Score: X/10" followed by a brief explanation.""",
        output_format="Score: X/10",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
}


def build_judge_prompt(question: str, response: str, template: str = "default") -> str:
    """
    Build a prompt for the judge model to evaluate a response.

    Args:
        question: The original question/prompt
        response: The model's response to evaluate
        template: Name of the judge template to use (default: "default")

    Returns:
        Formatted prompt for the judge model
    """
    if template in JUDGE_PROMPTS:
        return JUDGE_PROMPTS[template].format(question=question, response=response)

    # Fallback to simple format
    return f"""You are an expert evaluator assessing the quality of AI responses.

Evaluate the following response based on these criteria:
- Helpfulness: Does it address the user's needs?
- Relevance: Is it on-topic and appropriate?
- Accuracy: Is the information correct?
- Coherence: Is it well-structured and easy to understand?

Question: {question}

Response: {response}

Provide a score from 1-10 where:
- 1-3: Poor quality (unhelpful, off-topic, inaccurate, or incoherent)
- 4-6: Moderate quality (partially helpful, some issues)
- 7-8: Good quality (helpful, relevant, accurate, coherent)
- 9-10: Excellent quality (exceptional in all criteria)

Format your response as: "Score: X/10" followed by a brief explanation.
"""


def parse_judge_score(
    judge_response: str, default: int = 5, config: Optional[ScoringConfig] = None
) -> int:
    """
    Extract numeric score from judge's response.

    Looks for patterns like "Score: 8/10", "Rating: 7", "8/10", "[[8]]", etc.
    Clamps result to configured range (default 1-10).

    Args:
        judge_response: The judge model's response
        default: Default score if parsing fails (default: 5)
        config: Optional scoring configuration with min/max range

    Returns:
        Integer score between min and max (default 1-10)
    """
    if not judge_response:
        return default

    if config is None:
        config = ScoringConfig()

    # Try to find score patterns (look for first valid score)
    patterns = [
        r"\[\[(\d+(?:\.\d+)?)\]\]",  # "[[8]]" MT-Bench format
        r"(?:score|rating)[\s:=]+(-?\d+(?:\.\d+)?)\s*/?\s*(?:10)?",  # "Score: 8/10"
        r"(-?\d+(?:\.\d+)?)\s*/\s*10",  # "8/10"
        r"(?:give it|rate it)(?:\s+a)?\s+(-?\d+(?:\.\d+)?)",  # "I give it a 7"
        r"out of 10[\s:,]+(-?\d+(?:\.\d+)?)",  # "out of 10: 8"
        r"(-?\d+(?:\.\d+)?)\s+out of 10",  # "8 out of 10"
        r"\*\*(\d+(?:\.\d+)?)\*\*/10",  # "**8**/10" markdown bold
        r"\*\*(\d+(?:\.\d+)?)\*\*",  # "**8**" standalone bold
    ]

    for pattern in patterns:
        match = re.search(pattern, judge_response, re.IGNORECASE)
        if match:
            try:
                score = float(match.group(1))
                # Round and clamp to range
                score_int = int(round(score))
                return max(config.min_score, min(config.max_score, score_int))
            except (ValueError, IndexError):
                continue

    # If no pattern matched, return default
    return default


def parse_pairwise_winner(judge_response: str) -> Optional[str]:
    """
    Parse the winner from a pairwise comparison.

    Looks for patterns like [[A]], [[B]], or [[C]] (tie).

    Args:
        judge_response: The judge model's response

    Returns:
        "A", "B", "C" (tie), or None if not found
    """
    if not judge_response:
        return None

    # Look for [[X]] pattern
    if "[[A]]" in judge_response:
        return "A"
    elif "[[B]]" in judge_response:
        return "B"
    elif "[[C]]" in judge_response:
        return "C"

    # Alternative patterns
    patterns = [
        (r"(?:winner|better)[\s:]+(?:assistant\s+)?([ABC])\b", lambda m: m.group(1).upper()),
        (r"(?:assistant\s+)?([AB])\s+(?:is|wins|better)", lambda m: m.group(1).upper()),
        (r"\btie\b|\bdraw\b|\bequal\b", lambda m: "C"),
    ]

    for pattern, extractor in patterns:
        match = re.search(pattern, judge_response, re.IGNORECASE)
        if match:
            try:
                return extractor(match)
            except (ValueError, IndexError):
                continue

    return None


def normalize_score(raw_score: int, config: ScoringConfig) -> float:
    """
    Normalize a raw score to 0.0-1.0 range.

    Args:
        raw_score: The raw score (e.g., 1-10)
        config: Scoring configuration with min/max

    Returns:
        Normalized score between 0.0 and 1.0
    """
    range_size = config.max_score - config.min_score
    if range_size == 0:
        return 0.5
    return (raw_score - config.min_score) / range_size


@scorer(metrics=[])
def llm_judge_scorer(
    judge_model: str = "llama3.2:3b",
    template: str = "default",
    system_prompt: Optional[str] = None,
) -> Scorer:
    """
    Create Inspect AI scorer that uses an LLM to judge responses.

    The judge rates responses on a 1-10 scale for helpfulness, relevance,
    accuracy, and coherence. This is normalized to 0.0-1.0 for Inspect AI.

    Args:
        judge_model: Model to use as judge (default: "llama3.2:3b")
        template: Name of judge template to use (default: "default")
        system_prompt: Optional system prompt override

    Returns:
        Scorer function compatible with Inspect AI

    Example:
        >>> task = Task(
        ...     dataset=samples,
        ...     solver=[generate()],
        ...     scorer=llm_judge_scorer(judge_model="llama3.2:3b")
        ... )
    """
    # Get template config for scoring
    judge_template = JUDGE_PROMPTS.get(template, JUDGE_PROMPTS["default"])
    scoring_config = judge_template.scoring

    async def score(state: TaskState, target: Target) -> Score:
        """
        Score a model response using an LLM judge.

        Args:
            state: Current task state with model output
            target: Target (not used for judge scoring)

        Returns:
            Score with value 0.0-1.0 (normalized from 1-10)
        """
        try:
            # Get the question and response
            question = state.input_text or ""
            response = state.output.completion

            # Build judge prompt
            judge_prompt = build_judge_prompt(question, response, template)

            # Get judge model
            model = get_model(judge_model)

            # Call judge model with optional system prompt
            full_system = system_prompt or judge_template.system_prompt
            judge_result = await model.generate(judge_prompt, system=full_system)

            # Extract score from judge response
            raw_score = parse_judge_score(judge_result.completion, config=scoring_config)

            # Normalize to 0-1 range
            normalized_score = normalize_score(raw_score, scoring_config)

            return Score(
                value=normalized_score,
                explanation=f"Judge score: {raw_score}/{scoring_config.max_score}. {judge_result.completion[:200]}",
                metadata={
                    "raw_score": raw_score,
                    "template": template,
                    "judge_model": judge_model,
                },
            )

        except Exception as e:
            # If judge fails, return middle score with error explanation
            return Score(
                value=0.5,
                explanation=f"Judge scoring error: {str(e)}",
            )

    return score


@scorer(metrics=[])
def pairwise_judge_scorer(
    judge_model: str = "llama3.2:3b",
    reference_key: str = "reference_response",
) -> Scorer:
    """
    Create scorer that compares model response against a reference using pairwise comparison.

    The judge determines which response is better: the model's (A) or reference (B).
    Returns 1.0 if model wins, 0.5 for tie, 0.0 if reference wins.

    Args:
        judge_model: Model to use as judge
        reference_key: Metadata key containing reference response

    Returns:
        Scorer function for pairwise comparison
    """
    judge_template = JUDGE_PROMPTS["pairwise"]

    async def score(state: TaskState, target: Target) -> Score:
        """Compare model response against reference."""
        try:
            question = state.input_text or ""
            response_a = state.output.completion
            response_b = state.metadata.get(reference_key, target.text or "")

            # Format pairwise prompt
            judge_prompt = judge_template.format(
                question=question,
                response_a=response_a,
                response_b=response_b,
            )

            model = get_model(judge_model)
            judge_result = await model.generate(
                judge_prompt, system=judge_template.system_prompt
            )

            winner = parse_pairwise_winner(judge_result.completion)

            # Map winner to score
            if winner == "A":
                score_value = 1.0
                explanation = "Model response preferred"
            elif winner == "B":
                score_value = 0.0
                explanation = "Reference response preferred"
            elif winner == "C":
                score_value = 0.5
                explanation = "Tie - responses equally good"
            else:
                score_value = 0.5
                explanation = "Could not determine winner"

            return Score(
                value=score_value,
                explanation=f"{explanation}. {judge_result.completion[:150]}",
                metadata={
                    "winner": winner,
                    "judge_model": judge_model,
                },
            )

        except Exception as e:
            return Score(
                value=0.5,
                explanation=f"Pairwise judge error: {str(e)}",
            )

    return score


@scorer(metrics=[])
def agentic_judge_scorer(
    judge_model: str = "llama3.2:3b",
    tools_key: str = "available_tools",
    expected_key: str = "expected_outcome",
) -> Scorer:
    """
    Create scorer for evaluating agentic/tool-using responses.

    Evaluates tool selection, parameter accuracy, reasoning, and outcome.

    Args:
        judge_model: Model to use as judge
        tools_key: Metadata key containing available tools description
        expected_key: Metadata key containing expected outcome

    Returns:
        Scorer function for agentic evaluation
    """
    judge_template = JUDGE_PROMPTS["agentic"]
    scoring_config = judge_template.scoring

    async def score(state: TaskState, target: Target) -> Score:
        """Evaluate agentic response quality."""
        try:
            task = state.input_text or ""
            response = state.output.completion
            tools = state.metadata.get(tools_key, "No tools specified")
            expected = state.metadata.get(expected_key, target.text or "Task completion")

            # Format agentic prompt
            judge_prompt = judge_template.format(
                task=task,
                tools=tools,
                response=response,
                expected=expected,
            )

            model = get_model(judge_model)
            judge_result = await model.generate(
                judge_prompt, system=judge_template.system_prompt
            )

            raw_score = parse_judge_score(judge_result.completion, config=scoring_config)
            normalized_score = normalize_score(raw_score, scoring_config)

            return Score(
                value=normalized_score,
                explanation=f"Agentic score: {raw_score}/{scoring_config.max_score}. {judge_result.completion[:200]}",
                metadata={
                    "raw_score": raw_score,
                    "judge_model": judge_model,
                },
            )

        except Exception as e:
            return Score(
                value=0.5,
                explanation=f"Agentic judge error: {str(e)}",
            )

    return score


@scorer(metrics=[])
def reference_judge_scorer(
    judge_model: str = "llama3.2:3b",
) -> Scorer:
    """
    Create scorer that evaluates response against a reference answer.

    Uses the target as the reference answer and scores for factual accuracy.

    Args:
        judge_model: Model to use as judge

    Returns:
        Scorer function for reference-based evaluation
    """
    judge_template = JUDGE_PROMPTS["reference"]
    scoring_config = judge_template.scoring

    async def score(state: TaskState, target: Target) -> Score:
        """Evaluate response against reference."""
        try:
            question = state.input_text or ""
            response = state.output.completion
            reference = target.text or ""

            judge_prompt = judge_template.format(
                question=question,
                response=response,
                reference=reference,
            )

            model = get_model(judge_model)
            judge_result = await model.generate(
                judge_prompt, system=judge_template.system_prompt
            )

            raw_score = parse_judge_score(judge_result.completion, config=scoring_config)
            normalized_score = normalize_score(raw_score, scoring_config)

            return Score(
                value=normalized_score,
                explanation=f"Reference score: {raw_score}/{scoring_config.max_score}. {judge_result.completion[:200]}",
                metadata={
                    "raw_score": raw_score,
                    "judge_model": judge_model,
                },
            )

        except Exception as e:
            return Score(
                value=0.5,
                explanation=f"Reference judge error: {str(e)}",
            )

    return score


def get_judge_template(name: str) -> Optional[JudgePrompt]:
    """
    Get a judge prompt template by name.

    Args:
        name: Template name (e.g., "default", "mtbench", "pairwise")

    Returns:
        JudgePrompt template or None if not found
    """
    return JUDGE_PROMPTS.get(name)


def list_judge_templates() -> list[str]:
    """
    List all available judge prompt template names.

    Returns:
        List of template names
    """
    return list(JUDGE_PROMPTS.keys())


def register_judge_template(template: JudgePrompt) -> None:
    """
    Register a custom judge prompt template.

    Args:
        template: JudgePrompt to register
    """
    JUDGE_PROMPTS[template.name] = template
