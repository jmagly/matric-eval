"""
5-dimensional scoring framework for comprehensive response evaluation.

Evaluates responses across multiple quality dimensions:
1. Correctness - Is the answer factually/logically correct?
2. Completeness - Does it address all parts of the question?
3. Clarity - Is the response clear and well-organized?
4. Conciseness - Is it appropriately brief without excess?
5. Helpfulness - Does it actually help the user?
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from inspect_ai.scorer import Score, Scorer, Target, scorer

DimensionName = Literal[
    "correctness",
    "completeness",
    "clarity",
    "conciseness",
    "helpfulness",
]

ALL_DIMENSIONS: list[DimensionName] = [
    "correctness",
    "completeness",
    "clarity",
    "conciseness",
    "helpfulness",
]


@dataclass
class DimensionScore:
    """Score for a single dimension."""

    name: DimensionName
    value: float  # 0.0 to 1.0
    weight: float = 1.0
    reasoning: str = ""

    @property
    def weighted_value(self) -> float:
        """Get weighted score value."""
        return self.value * self.weight


@dataclass
class MultidimensionalScore:
    """Aggregate score across all dimensions."""

    dimensions: dict[DimensionName, DimensionScore] = field(default_factory=dict)

    @property
    def overall(self) -> float:
        """Weighted average of all dimensions."""
        if not self.dimensions:
            return 0.0
        total_weight = sum(d.weight for d in self.dimensions.values())
        weighted_sum = sum(d.weighted_value for d in self.dimensions.values())
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "overall": self.overall,
            "dimensions": {
                name: {
                    "value": d.value,
                    "weight": d.weight,
                    "reasoning": d.reasoning,
                }
                for name, d in self.dimensions.items()
            },
        }

    def get_dimension(self, name: DimensionName) -> DimensionScore | None:
        """Get a specific dimension score."""
        return self.dimensions.get(name)


class DimensionEvaluator:
    """Base class for dimension evaluators."""

    def __init__(self, dimension: DimensionName, weight: float = 1.0):
        self.dimension = dimension
        self.weight = weight

    async def evaluate(
        self,
        prompt: str,
        response: str,
        target: str | None = None,
        metadata: dict | None = None,
    ) -> DimensionScore:
        """
        Evaluate a response for this dimension.

        Args:
            prompt: Original prompt/question
            response: Model's response
            target: Expected/reference answer (optional)
            metadata: Additional context

        Returns:
            DimensionScore with value and reasoning
        """
        raise NotImplementedError


def extract_number(text: str) -> float | None:
    """
    Extract numeric value from text.

    Handles:
    - Plain numbers: "42"
    - Numbers with commas: "1,234"
    - Decimals: "3.14"
    - Negative numbers: "-5"
    - Numbers in text: "The answer is 42."

    Args:
        text: Text containing a number

    Returns:
        Extracted float or None if not found
    """
    # Remove commas from numbers
    text = text.replace(",", "")

    # Find all numbers (including negatives and decimals)
    matches = re.findall(r"-?\d+\.?\d*", text)

    if matches:
        # Return the last number (usually the final answer)
        return float(matches[-1])

    return None


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    # Lowercase, strip whitespace, remove extra spaces
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


class RuleBasedCorrectnessEvaluator(DimensionEvaluator):
    """Rule-based correctness evaluation."""

    def __init__(self, weight: float = 1.0):
        super().__init__("correctness", weight)

    async def evaluate(
        self,
        prompt: str,
        response: str,
        target: str | None = None,
        metadata: dict | None = None,
    ) -> DimensionScore:
        if not target:
            return DimensionScore(
                self.dimension,
                0.5,
                self.weight,
                "No target answer to compare against",
            )

        response_norm = normalize_text(response)
        target_norm = normalize_text(target)

        # Exact match
        if response_norm == target_norm:
            return DimensionScore(
                self.dimension,
                1.0,
                self.weight,
                "Exact match with target answer",
            )

        # Contains target (for short answers)
        if len(target_norm) < 50 and target_norm in response_norm:
            return DimensionScore(
                self.dimension,
                0.9,
                self.weight,
                "Response contains the target answer",
            )

        # Numeric comparison for math problems
        response_num = extract_number(response)
        target_num = extract_number(target)

        if response_num is not None and target_num is not None:
            if abs(response_num - target_num) < 0.001:
                return DimensionScore(
                    self.dimension,
                    1.0,
                    self.weight,
                    f"Numeric match: {response_num} == {target_num}",
                )
            # Close but not exact
            if target_num != 0:
                relative_error = abs(response_num - target_num) / abs(target_num)
                if relative_error < 0.01:
                    return DimensionScore(
                        self.dimension,
                        0.9,
                        self.weight,
                        f"Close numeric match (error: {relative_error:.2%})",
                    )
                if relative_error < 0.1:
                    return DimensionScore(
                        self.dimension,
                        0.5,
                        self.weight,
                        f"Approximate numeric match (error: {relative_error:.2%})",
                    )

        # Word overlap for longer answers
        response_words = set(response_norm.split())
        target_words = set(target_norm.split())

        if target_words:
            overlap = len(response_words & target_words) / len(target_words)
            if overlap > 0.8:
                return DimensionScore(
                    self.dimension,
                    0.7,
                    self.weight,
                    f"High word overlap: {overlap:.0%}",
                )
            if overlap > 0.5:
                return DimensionScore(
                    self.dimension,
                    0.5,
                    self.weight,
                    f"Moderate word overlap: {overlap:.0%}",
                )

        return DimensionScore(
            self.dimension,
            0.0,
            self.weight,
            "No match found with target answer",
        )


class RuleBasedCompletenessEvaluator(DimensionEvaluator):
    """Rule-based completeness evaluation."""

    def __init__(self, weight: float = 1.0):
        super().__init__("completeness", weight)

    async def evaluate(
        self,
        prompt: str,
        response: str,
        target: str | None = None,
        metadata: dict | None = None,
    ) -> DimensionScore:
        if not response.strip():
            return DimensionScore(
                self.dimension,
                0.0,
                self.weight,
                "Empty response",
            )

        # Check for question words that need addressing
        prompt_lower = prompt.lower()
        question_indicators = ["?", "what", "how", "why", "when", "where", "who", "which"]
        has_question = any(q in prompt_lower for q in question_indicators)

        if has_question and len(response.split()) < 3:
            return DimensionScore(
                self.dimension,
                0.3,
                self.weight,
                "Response too short for question",
            )

        # Check for multi-part questions
        parts_indicators = [" and ", "1.", "2.", "a)", "b)", "first", "second"]
        multi_part = any(p in prompt_lower for p in parts_indicators)

        if multi_part:
            # Check if response addresses multiple parts
            response_parts = len(re.split(r"[.!?\n]", response))
            if response_parts >= 2:
                return DimensionScore(
                    self.dimension,
                    0.9,
                    self.weight,
                    "Response appears to address multiple parts",
                )
            return DimensionScore(
                self.dimension,
                0.5,
                self.weight,
                "Multi-part question but response seems incomplete",
            )

        # Basic completeness - has reasonable length
        words = len(response.split())
        if words >= 10:
            return DimensionScore(
                self.dimension,
                0.8,
                self.weight,
                "Response has substantive content",
            )
        if words >= 5:
            return DimensionScore(
                self.dimension,
                0.6,
                self.weight,
                "Response is brief but present",
            )

        return DimensionScore(
            self.dimension,
            0.4,
            self.weight,
            "Response may be incomplete",
        )


class RuleBasedClarityEvaluator(DimensionEvaluator):
    """Rule-based clarity evaluation."""

    def __init__(self, weight: float = 1.0):
        super().__init__("clarity", weight)

    async def evaluate(
        self,
        prompt: str,
        response: str,
        target: str | None = None,
        metadata: dict | None = None,
    ) -> DimensionScore:
        if not response.strip():
            return DimensionScore(
                self.dimension,
                0.0,
                self.weight,
                "Empty response",
            )

        # Check for structure indicators
        has_structure = any([
            "\n\n" in response,  # Paragraphs
            re.search(r"\d\.", response),  # Numbered lists
            "- " in response or "* " in response,  # Bullet points
            ":" in response,  # Definitions/explanations
        ])

        # Check for clear sentence structure
        sentences = re.split(r"[.!?]", response)
        avg_sentence_length = (
            sum(len(s.split()) for s in sentences) / len(sentences)
            if sentences
            else 0
        )

        # Very long sentences are harder to read
        if avg_sentence_length > 40:
            clarity_penalty = 0.2
        elif avg_sentence_length > 30:
            clarity_penalty = 0.1
        else:
            clarity_penalty = 0.0

        base_score = 0.7 if has_structure else 0.5
        final_score = max(0.0, base_score - clarity_penalty)

        # Boost for code blocks (technical clarity)
        if "```" in response or "`" in response:
            final_score = min(1.0, final_score + 0.2)

        return DimensionScore(
            self.dimension,
            final_score,
            self.weight,
            f"Structure: {'yes' if has_structure else 'no'}, avg sentence: {avg_sentence_length:.0f} words",
        )


class RuleBasedConcisenessEvaluator(DimensionEvaluator):
    """Rule-based conciseness evaluation."""

    def __init__(self, weight: float = 1.0, target_ratio: float = 1.5):
        super().__init__("conciseness", weight)
        self.target_ratio = target_ratio  # Response:target length ratio

    async def evaluate(
        self,
        prompt: str,
        response: str,
        target: str | None = None,
        metadata: dict | None = None,
    ) -> DimensionScore:
        if not response.strip():
            return DimensionScore(
                self.dimension,
                0.0,
                self.weight,
                "Empty response",
            )

        response_words = len(response.split())
        prompt_words = len(prompt.split())

        # Check for obvious verbosity
        filler_phrases = [
            "i think",
            "in my opinion",
            "to be honest",
            "as you know",
            "it's important to note",
            "it should be noted",
            "basically",
            "essentially",
            "actually",
        ]
        filler_count = sum(
            1 for phrase in filler_phrases if phrase in response.lower()
        )

        # Repetition detection (simple)
        sentences = [s.strip() for s in re.split(r"[.!?]", response) if s.strip()]
        unique_sentences = len(set(normalize_text(s) for s in sentences))
        repetition_ratio = unique_sentences / len(sentences) if sentences else 1.0

        # Length-based scoring
        if target:
            target_words = len(target.split())
            ratio = response_words / target_words if target_words > 0 else 1.0

            if 0.5 <= ratio <= self.target_ratio:
                length_score = 1.0
            elif ratio < 0.5:
                length_score = 0.6  # Too short
            else:
                # Penalty for being too long
                length_score = max(0.3, 1.0 - (ratio - self.target_ratio) * 0.2)
        else:
            # Without target, use prompt-relative heuristic
            if response_words < prompt_words * 0.5:
                length_score = 0.7  # Maybe too brief
            elif response_words > prompt_words * 5:
                length_score = 0.5  # Probably too verbose
            else:
                length_score = 0.8

        # Combine factors
        filler_penalty = min(0.3, filler_count * 0.1)
        repetition_penalty = (1.0 - repetition_ratio) * 0.2

        final_score = max(0.0, length_score - filler_penalty - repetition_penalty)

        return DimensionScore(
            self.dimension,
            final_score,
            self.weight,
            f"Words: {response_words}, fillers: {filler_count}, repetition: {1-repetition_ratio:.0%}",
        )


class RuleBasedHelpfulnessEvaluator(DimensionEvaluator):
    """Rule-based helpfulness evaluation."""

    def __init__(self, weight: float = 1.0):
        super().__init__("helpfulness", weight)

    async def evaluate(
        self,
        prompt: str,
        response: str,
        target: str | None = None,
        metadata: dict | None = None,
    ) -> DimensionScore:
        if not response.strip():
            return DimensionScore(
                self.dimension,
                0.0,
                self.weight,
                "Empty response",
            )

        response_lower = response.lower()

        # Check for refusal indicators
        refusal_phrases = [
            "i cannot",
            "i can't",
            "i'm not able",
            "i am not able",
            "i don't have",
            "i do not have",
            "as an ai",
            "as a language model",
        ]
        is_refusal = any(phrase in response_lower for phrase in refusal_phrases)

        if is_refusal:
            return DimensionScore(
                self.dimension,
                0.2,
                self.weight,
                "Response appears to refuse the request",
            )

        # Check for actionable content
        action_indicators = [
            "you can",
            "you should",
            "try",
            "use",
            "here's",
            "here is",
            "follow",
            "step",
            "example",
            "```",  # Code block
        ]
        has_actionable = any(ind in response_lower for ind in action_indicators)

        # Check for explanatory content
        explanation_indicators = [
            "because",
            "since",
            "therefore",
            "this means",
            "in other words",
            "for example",
            "such as",
        ]
        has_explanation = any(ind in response_lower for ind in explanation_indicators)

        score = 0.5  # Base score
        if has_actionable:
            score += 0.25
        if has_explanation:
            score += 0.25

        # Check if response addresses the prompt topic
        prompt_keywords = set(
            word.lower()
            for word in prompt.split()
            if len(word) > 3 and word.isalpha()
        )
        response_keywords = set(
            word.lower()
            for word in response.split()
            if len(word) > 3 and word.isalpha()
        )
        topic_overlap = len(prompt_keywords & response_keywords) / len(prompt_keywords) if prompt_keywords else 0

        if topic_overlap < 0.1:
            score = max(0.2, score - 0.3)  # Response may be off-topic

        return DimensionScore(
            self.dimension,
            min(1.0, score),
            self.weight,
            f"Actionable: {has_actionable}, explanatory: {has_explanation}, topic overlap: {topic_overlap:.0%}",
        )


def create_evaluators(
    dimensions: list[DimensionName],
    weights: dict[DimensionName, float] | None = None,
) -> list[DimensionEvaluator]:
    """
    Create evaluators for the specified dimensions.

    Args:
        dimensions: List of dimensions to evaluate
        weights: Optional custom weights per dimension

    Returns:
        List of DimensionEvaluator instances
    """
    weights = weights or {}
    evaluators = []

    evaluator_classes = {
        "correctness": RuleBasedCorrectnessEvaluator,
        "completeness": RuleBasedCompletenessEvaluator,
        "clarity": RuleBasedClarityEvaluator,
        "conciseness": RuleBasedConcisenessEvaluator,
        "helpfulness": RuleBasedHelpfulnessEvaluator,
    }

    for dim in dimensions:
        weight = weights.get(dim, 1.0)
        evaluator_class = evaluator_classes.get(dim)
        if evaluator_class:
            evaluators.append(evaluator_class(weight))

    return evaluators


@scorer(metrics=["accuracy"])
def multidimensional_scorer(
    dimensions: list[DimensionName] | None = None,
    weights: dict[DimensionName, float] | None = None,
) -> Scorer:
    """
    Create a multi-dimensional scorer.

    Args:
        dimensions: Which dimensions to evaluate (default: all 5)
        weights: Custom weights per dimension (default: equal weights)

    Returns:
        Scorer that evaluates across multiple dimensions

    Example:
        >>> scorer = multidimensional_scorer(
        ...     dimensions=["correctness", "clarity"],
        ...     weights={"correctness": 2.0, "clarity": 1.0}
        ... )
    """
    dims = dimensions or ALL_DIMENSIONS
    evaluators = create_evaluators(dims, weights)

    async def score(state, target: Target) -> Score:
        # Extract prompt from state
        prompt = ""
        if hasattr(state, "messages") and state.messages:
            for msg in state.messages:
                if hasattr(msg, "role") and msg.role == "user":
                    prompt = msg.content if hasattr(msg, "content") else str(msg)
                    break

        response = state.output.completion if state.output else ""

        # Evaluate each dimension
        result = MultidimensionalScore()
        for evaluator in evaluators:
            dim_score = await evaluator.evaluate(
                prompt,
                response,
                target.text if target else None,
                state.metadata if hasattr(state, "metadata") else None,
            )
            result.dimensions[evaluator.dimension] = dim_score

        return Score(
            value=result.overall,
            explanation=f"5D Score: {result.overall:.2%}",
            metadata=result.to_dict(),
        )

    return score


# Convenience aliases
def correctness_scorer(weight: float = 1.0) -> Scorer:
    """Single-dimension correctness scorer."""
    return multidimensional_scorer(dimensions=["correctness"], weights={"correctness": weight})


def quality_scorer() -> Scorer:
    """Quality-focused scorer (clarity, conciseness, helpfulness)."""
    return multidimensional_scorer(
        dimensions=["clarity", "conciseness", "helpfulness"],
    )
