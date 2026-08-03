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

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
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
        category="title",
        system_prompt="You are an expert evaluator of knowledge management systems. Your task is to assess the quality of generated note titles based on their content. Provide objective, consistent ratings.",
        prompt_template="""Evaluate the quality of this generated title for the given note content.

## Note Content:
{content}

## Generated Title:
{title}

## Evaluation Criteria:
1. **Relevance** (3 points): Does the title accurately reflect the main topic/theme?
2. **Conciseness** (2 points): Is it brief yet descriptive (ideally 3-8 words)?
3. **Informativeness** (3 points): Does it convey what the note is about without reading it?
4. **Format Compliance** (2 points): Plain text only, no markdown, no punctuation at end

Provide your rating from 1-10 where:
- 1-3: Poor (misleading, verbose, or non-compliant)
- 4-6: Adequate (somewhat relevant but could be improved)
- 7-8: Good (clear, relevant, well-formatted)
- 9-10: Excellent (perfectly captures content, concise, informative)

Respond with:
Rating: [1-10]
Reasoning: [2-3 sentences explaining your rating based on the criteria]""",
        output_format="Rating: <number>\nReasoning: <text>",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "revision_quality": JudgePrompt(
        name="revision_quality",
        prompt_type=JudgeType.SINGLE,
        category="revision",
        system_prompt="You are an expert evaluator of AI-assisted content revision. Your task is to assess how well a revision improves the original content while maintaining accuracy and preserving key information.",
        prompt_template="""Evaluate the quality of this AI-generated revision.

## Original Content:
{original}

## Revised Content:
{revised}

## Context (Related Notes):
{context}

## Evaluation Criteria:
1. **Structure & Organization** (3 points): Is the revision better organized, with clear sections/flow?
2. **Clarity & Readability** (2 points): Is it easier to understand and more readable?
3. **Information Preservation** (3 points): Are all key facts and ideas from the original retained?
4. **No Hallucination** (2 points): Are there any added facts not present in original or context?

Provide your rating from 1-10 where:
- 1-3: Poor (worse than original, information lost, or hallucinations present)
- 4-6: Adequate (minor improvements but issues remain)
- 7-8: Good (clear improvements in structure/clarity, faithful to original)
- 9-10: Excellent (significantly improved, all info preserved, well-structured)

Respond with:
Rating: [1-10]
Reasoning: [2-3 sentences explaining your rating]
Hallucinations: [None, or list any unsupported claims]""",
        output_format="Rating: <number>\nReasoning: <text>\nHallucinations: <text>",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "title_pairwise": JudgePrompt(
        name="title_pairwise",
        prompt_type=JudgeType.PAIRWISE,
        category="title",
        system_prompt="You are an expert evaluator comparing two generated titles for the same note content. Choose the better title based on relevance, conciseness, and informativeness. Be objective and consistent.",
        prompt_template="""Compare these two generated titles for the given note content.

## Note Content:
{content}

## Title A:
{title_a}

## Title B:
{title_b}

## Comparison Criteria:
- Which title more accurately reflects the main topic?
- Which is more concise while still being descriptive?
- Which better conveys what the note is about?
- Which follows better formatting (plain text, no markdown)?

Choose the better title. If they are equally good, choose tie.

Respond with ONLY one of:
[[A]] - if Title A is better
[[B]] - if Title B is better
[[C]] - if they are equally good (tie)

Then provide a brief explanation (1-2 sentences) of your choice.""",
        output_format="[[A]], [[B]], or [[C]]\n<explanation>",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "revision_pairwise": JudgePrompt(
        name="revision_pairwise",
        prompt_type=JudgeType.PAIRWISE,
        category="revision",
        system_prompt="You are an expert evaluator comparing two AI-generated revisions of the same content. Choose the better revision based on structure, clarity, information preservation, and factual accuracy.",
        prompt_template="""Compare these two revisions of the same original content.

## Original Content:
{original}

## Revision A:
{revision_a}

## Revision B:
{revision_b}

## Context (Related Notes):
{context}

## Comparison Criteria:
- Which has better structure and organization?
- Which is clearer and more readable?
- Which better preserves information from the original?
- Which avoids hallucinations (adding unsupported facts)?

Choose the better revision. If they are equally good, choose tie.

Respond with ONLY one of:
[[A]] - if Revision A is better
[[B]] - if Revision B is better
[[C]] - if they are equally good (tie)

Then provide a brief explanation (1-2 sentences) of your choice.""",
        output_format="[[A]], [[B]], or [[C]]\n<explanation>",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "semantic_relevance": JudgePrompt(
        name="semantic_relevance",
        prompt_type=JudgeType.SINGLE,
        category="semantic",
        system_prompt="You are an expert evaluator of search result relevance. Your task is to assess how well a search result matches the user's query intent and information need.",
        prompt_template="""Evaluate the relevance of this search result to the given query.

## Search Query:
{query}

## Search Result Title:
{result_title}

## Search Result Content:
{result_content}

## Evaluation Criteria:
1. **Topical Match** (5 points): Does the result directly address the query topic?
2. **Information Usefulness** (3 points): Would this result satisfy the user's information need?
3. **Query Intent Alignment** (2 points): Does it match what the user is likely looking for?

Provide your rating from 1-10 where:
- 1-3: Not relevant (off-topic or useless)
- 4-6: Somewhat relevant (related but not ideal)
- 7-8: Relevant (good match, useful information)
- 9-10: Highly relevant (perfect match, exactly what user needs)

Respond with:
Rating: [1-10]
Reasoning: [2-3 sentences explaining relevance to query]""",
        output_format="Rating: <number>\nReasoning: <text>",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "factual_accuracy": JudgePrompt(
        name="factual_accuracy",
        prompt_type=JudgeType.SINGLE,
        category="general",
        system_prompt="You are an expert fact-checker evaluating AI-generated content for hallucinations and unsupported claims. Every statement in the output must be grounded in the provided source material.",
        prompt_template="""Check this AI-generated output for factual accuracy and hallucinations.

## Source Material:
{source}

## AI-Generated Output:
{output}

## Evaluation Criteria:
1. **Grounded Facts** (5 points): Are all factual claims present in the source?
2. **No Fabrication** (3 points): Are there any invented details, names, dates, or statistics?
3. **Accurate Interpretation** (2 points): Are inferences and summaries faithful to the source?

Provide your rating from 1-10 where:
- 1-3: Major hallucinations (multiple unsupported claims or fabricated facts)
- 4-6: Minor hallucinations (some claims not fully supported by source)
- 7-8: Mostly accurate (small interpretation issues only)
- 9-10: Fully accurate (all claims grounded in source)

Respond with:
Rating: [1-10]
Reasoning: [Explanation of accuracy assessment]
Hallucinations: [List specific unsupported claims, or "None detected"]""",
        output_format="Rating: <number>\nReasoning: <text>\nHallucinations: <text>",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "format_compliance": JudgePrompt(
        name="format_compliance",
        prompt_type=JudgeType.SINGLE,
        category="general",
        system_prompt="You are an expert evaluator of constraint adherence. Your task is to assess how well AI-generated output follows specified formatting and content constraints.",
        prompt_template="""Evaluate how well this output follows the given constraints.

## Constraints:
{constraints}

## AI-Generated Output:
{output}

## Evaluation Criteria:
For each constraint listed above:
- Is it fully met? (award points)
- Is it partially met? (award partial points)
- Is it violated? (deduct points)

Provide your rating from 1-10 where:
- 1-3: Major violations (most constraints broken)
- 4-6: Partial compliance (some constraints met, others violated)
- 7-8: Good compliance (most constraints met, minor issues)
- 9-10: Full compliance (all constraints satisfied)

Respond with:
Rating: [1-10]
Compliance Analysis: [For each constraint, state if met/partial/violated]
Reasoning: [Overall assessment]""",
        output_format="Rating: <number>\nCompliance Analysis: <text>\nReasoning: <text>",
        scoring=ScoringConfig(min_score=1, max_score=10),
    ),
    "tag_quality": JudgePrompt(
        name="tag_quality",
        prompt_type=JudgeType.SINGLE,
        category="semantic",
        system_prompt="You are an expert evaluator of knowledge management tag generation. Your task is to assess the quality of automatically generated tags based on their relevance, specificity, and completeness.",
        prompt_template="""Evaluate the quality of these generated tags for the given note content.

## Note Content:
{content}

## Generated Tags:
{tags}

## Evaluation Criteria:
1. **Relevance** (4 points): Do all tags accurately describe the content's topics/themes?
2. **Specificity** (3 points): Are tags specific enough to be useful (not too generic)?
3. **Completeness** (2 points): Are important topics covered? Are there obvious gaps?
4. **Usefulness** (1 point): Would these tags help in finding/organizing this note?

Provide your rating from 1-10 where:
- 1-3: Poor (irrelevant, too generic, or missing key topics)
- 4-6: Adequate (some good tags but issues with relevance or coverage)
- 7-8: Good (relevant, reasonably specific, covers main topics)
- 9-10: Excellent (highly relevant, specific, comprehensive coverage)

Respond with:
Rating: [1-10]
Reasoning: [Assessment of tag quality]
Suggested Additions: [Any important missing tags, or "None"]""",
        output_format="Rating: <number>\nReasoning: <text>\nSuggested Additions: <text>",
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


@scorer(metrics=[mean()])
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
            judge_result = await model.generate(
                judge_prompt, config=GenerateConfig(system_message=full_system)
            )

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


@scorer(metrics=[mean()])
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
                judge_prompt,
                config=GenerateConfig(system_message=judge_template.system_prompt),
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


@scorer(metrics=[mean()])
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
                judge_prompt,
                config=GenerateConfig(system_message=judge_template.system_prompt),
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


@scorer(metrics=[mean()])
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
                judge_prompt,
                config=GenerateConfig(system_message=judge_template.system_prompt),
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


def parse_hallucination_flag(judge_response: str) -> tuple[bool, list[str]]:
    """
    Parse hallucination detection from judge response.

    Looks for "Hallucinations: ..." section in judge output.

    Args:
        judge_response: The judge model's response

    Returns:
        Tuple of (hallucination_detected, list of hallucinated claims)
    """
    if not judge_response:
        return False, []

    # Find the Hallucinations line
    match = re.search(
        r"Hallucinations?:\s*(.+?)(?:\n\n|\n[A-Z]|\Z)",
        judge_response,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return False, []

    content = match.group(1).strip()

    # Check for "none" variants
    if re.match(r"^(?:none|none detected|no hallucinations?|n/a)\.?$", content, re.IGNORECASE):
        return False, []

    # Split into individual claims
    claims = [
        line.strip().lstrip("- ").lstrip("• ")
        for line in content.split("\n")
        if line.strip() and not re.match(r"^(?:none|n/a)$", line.strip(), re.IGNORECASE)
    ]

    return bool(claims), claims


@scorer(metrics=[mean()])
def hallucination_judge_scorer(
    judge_model: str = "llama3.2:3b",
) -> Scorer:
    """
    Create scorer that detects hallucinations in AI-generated content.

    Uses the factual_accuracy template to check for fabricated claims
    against source material. Returns normalized score and hallucination flags.

    Args:
        judge_model: Model to use as judge

    Returns:
        Scorer function for hallucination detection
    """
    judge_template = JUDGE_PROMPTS["factual_accuracy"]
    scoring_config = judge_template.scoring

    async def score(state: TaskState, target: Target) -> Score:
        """Check response for hallucinations against source material."""
        try:
            source = target.text or state.metadata.get("source", "")
            output = state.output.completion

            judge_prompt = judge_template.format(source=source, output=output)

            model = get_model(judge_model)
            judge_result = await model.generate(
                judge_prompt,
                config=GenerateConfig(system_message=judge_template.system_prompt),
            )

            raw_score = parse_judge_score(judge_result.completion, config=scoring_config)
            normalized = normalize_score(raw_score, scoring_config)
            hallucinated, claims = parse_hallucination_flag(judge_result.completion)

            return Score(
                value=normalized,
                explanation=f"Factual accuracy: {raw_score}/{scoring_config.max_score}. {judge_result.completion[:200]}",
                metadata={
                    "raw_score": raw_score,
                    "judge_model": judge_model,
                    "hallucinated": hallucinated,
                    "hallucination_claims": claims,
                },
            )

        except Exception as e:
            return Score(
                value=0.5,
                explanation=f"Hallucination judge error: {str(e)}",
            )

    return score


@scorer(metrics=[mean()])
def revision_quality_scorer(
    judge_model: str = "llama3.2:3b",
) -> Scorer:
    """
    Create scorer for evaluating content revision quality.

    Evaluates structure, clarity, information preservation, and hallucination avoidance.

    Args:
        judge_model: Model to use as judge

    Returns:
        Scorer function for revision quality evaluation
    """
    judge_template = JUDGE_PROMPTS["revision_quality"]
    scoring_config = judge_template.scoring

    async def score(state: TaskState, target: Target) -> Score:
        """Evaluate revision quality."""
        try:
            original = state.metadata.get("original", "")
            revised = state.output.completion
            context = state.metadata.get("context", "No additional context")

            judge_prompt = judge_template.format(
                original=original, revised=revised, context=context
            )

            model = get_model(judge_model)
            judge_result = await model.generate(
                judge_prompt,
                config=GenerateConfig(system_message=judge_template.system_prompt),
            )

            raw_score = parse_judge_score(judge_result.completion, config=scoring_config)
            normalized = normalize_score(raw_score, scoring_config)
            hallucinated, claims = parse_hallucination_flag(judge_result.completion)

            return Score(
                value=normalized,
                explanation=f"Revision quality: {raw_score}/{scoring_config.max_score}. {judge_result.completion[:200]}",
                metadata={
                    "raw_score": raw_score,
                    "judge_model": judge_model,
                    "hallucinated": hallucinated,
                    "hallucination_claims": claims,
                },
            )

        except Exception as e:
            return Score(
                value=0.5,
                explanation=f"Revision quality judge error: {str(e)}",
            )

    return score


@scorer(metrics=[mean()])
def tag_quality_scorer(
    judge_model: str = "llama3.2:3b",
) -> Scorer:
    """
    Create scorer for evaluating auto-generated tag quality.

    Evaluates relevance, specificity, completeness, and usefulness of tags.

    Args:
        judge_model: Model to use as judge

    Returns:
        Scorer function for tag quality evaluation
    """
    judge_template = JUDGE_PROMPTS["tag_quality"]
    scoring_config = judge_template.scoring

    async def score(state: TaskState, target: Target) -> Score:
        """Evaluate tag quality."""
        try:
            content = state.metadata.get("content", state.input_text or "")
            tags = state.output.completion

            judge_prompt = judge_template.format(content=content, tags=tags)

            model = get_model(judge_model)
            judge_result = await model.generate(
                judge_prompt,
                config=GenerateConfig(system_message=judge_template.system_prompt),
            )

            raw_score = parse_judge_score(judge_result.completion, config=scoring_config)
            normalized = normalize_score(raw_score, scoring_config)

            # Extract suggested additions
            suggested = ""
            match = re.search(
                r"Suggested Additions?:\s*(.+?)(?:\n\n|\Z)",
                judge_result.completion,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                suggested = match.group(1).strip()

            return Score(
                value=normalized,
                explanation=f"Tag quality: {raw_score}/{scoring_config.max_score}. {judge_result.completion[:200]}",
                metadata={
                    "raw_score": raw_score,
                    "judge_model": judge_model,
                    "suggested_additions": suggested,
                },
            )

        except Exception as e:
            return Score(
                value=0.5,
                explanation=f"Tag quality judge error: {str(e)}",
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
