"""
Tests for 5-dimensional scoring framework (matric_eval.scorers.multidimensional).

Covers:
- Individual dimension evaluators
- Weighted scoring
- MultidimensionalScore aggregation
- Number extraction utility
- Integration with Inspect AI scoring
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from matric_eval.scorers.multidimensional import (
    ALL_DIMENSIONS,
    DimensionScore,
    MultidimensionalScore,
    RuleBasedClarityEvaluator,
    RuleBasedCompletenessEvaluator,
    RuleBasedConcisenessEvaluator,
    RuleBasedCorrectnessEvaluator,
    RuleBasedHelpfulnessEvaluator,
    correctness_scorer,
    create_evaluators,
    extract_number,
    multidimensional_scorer,
    normalize_text,
    quality_scorer,
)


# =============================================================================
# DimensionScore Tests
# =============================================================================


@pytest.mark.unit
class TestDimensionScore:
    """Tests for DimensionScore dataclass."""

    def test_basic_creation(self) -> None:
        """Should create DimensionScore with required fields."""
        score = DimensionScore(
            name="correctness",
            value=0.8,
        )
        assert score.name == "correctness"
        assert score.value == 0.8
        assert score.weight == 1.0  # Default

    def test_weighted_value(self) -> None:
        """Should calculate weighted value correctly."""
        score = DimensionScore(
            name="clarity",
            value=0.5,
            weight=2.0,
        )
        assert score.weighted_value == 1.0

    def test_with_reasoning(self) -> None:
        """Should store reasoning."""
        score = DimensionScore(
            name="helpfulness",
            value=0.9,
            reasoning="Response was very helpful",
        )
        assert "helpful" in score.reasoning


# =============================================================================
# MultidimensionalScore Tests
# =============================================================================


@pytest.mark.unit
class TestMultidimensionalScore:
    """Tests for MultidimensionalScore dataclass."""

    def test_empty_overall(self) -> None:
        """Should return 0.0 for empty dimensions."""
        score = MultidimensionalScore()
        assert score.overall == 0.0

    def test_single_dimension_overall(self) -> None:
        """Should return single dimension value."""
        score = MultidimensionalScore()
        score.dimensions["correctness"] = DimensionScore("correctness", 0.8)
        assert score.overall == 0.8

    def test_multiple_dimensions_average(self) -> None:
        """Should return weighted average of dimensions."""
        score = MultidimensionalScore()
        score.dimensions["correctness"] = DimensionScore("correctness", 1.0)
        score.dimensions["clarity"] = DimensionScore("clarity", 0.5)
        assert score.overall == 0.75  # (1.0 + 0.5) / 2

    def test_weighted_average(self) -> None:
        """Should respect custom weights."""
        score = MultidimensionalScore()
        score.dimensions["correctness"] = DimensionScore("correctness", 1.0, weight=2.0)
        score.dimensions["clarity"] = DimensionScore("clarity", 0.0, weight=1.0)
        # Weighted: (1.0*2.0 + 0.0*1.0) / (2.0 + 1.0) = 2.0/3.0
        assert abs(score.overall - 2/3) < 0.001

    def test_to_dict(self) -> None:
        """Should convert to dictionary correctly."""
        score = MultidimensionalScore()
        score.dimensions["correctness"] = DimensionScore("correctness", 0.9, reasoning="Good")

        result = score.to_dict()
        assert "overall" in result
        assert "dimensions" in result
        assert "correctness" in result["dimensions"]
        assert result["dimensions"]["correctness"]["value"] == 0.9

    def test_get_dimension(self) -> None:
        """Should retrieve specific dimension."""
        score = MultidimensionalScore()
        dim = DimensionScore("clarity", 0.7)
        score.dimensions["clarity"] = dim

        assert score.get_dimension("clarity") == dim
        assert score.get_dimension("nonexistent") is None


# =============================================================================
# Number Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestExtractNumber:
    """Tests for extract_number() utility."""

    def test_plain_integer(self) -> None:
        """Should extract plain integer."""
        assert extract_number("42") == 42.0

    def test_decimal(self) -> None:
        """Should extract decimal number."""
        assert extract_number("3.14159") == 3.14159

    def test_negative(self) -> None:
        """Should extract negative number."""
        assert extract_number("-5") == -5.0

    def test_with_commas(self) -> None:
        """Should handle number with commas."""
        assert extract_number("1,234,567") == 1234567.0

    def test_in_text(self) -> None:
        """Should extract number from text."""
        assert extract_number("The answer is 42.") == 42.0

    def test_multiple_numbers_returns_last(self) -> None:
        """Should return last number in text."""
        assert extract_number("Step 1: 10, Step 2: 20, Final: 30") == 30.0

    def test_no_number_returns_none(self) -> None:
        """Should return None when no number found."""
        assert extract_number("No numbers here") is None

    def test_empty_string(self) -> None:
        """Should return None for empty string."""
        assert extract_number("") is None


# =============================================================================
# Text Normalization Tests
# =============================================================================


@pytest.mark.unit
class TestNormalizeText:
    """Tests for normalize_text() utility."""

    def test_lowercase(self) -> None:
        """Should convert to lowercase."""
        assert normalize_text("HELLO") == "hello"

    def test_strip_whitespace(self) -> None:
        """Should strip leading/trailing whitespace."""
        assert normalize_text("  hello  ") == "hello"

    def test_collapse_spaces(self) -> None:
        """Should collapse multiple spaces."""
        assert normalize_text("hello    world") == "hello world"


# =============================================================================
# Correctness Evaluator Tests
# =============================================================================


@pytest.mark.unit
class TestCorrectnessEvaluator:
    """Tests for RuleBasedCorrectnessEvaluator."""

    @pytest.fixture
    def evaluator(self) -> RuleBasedCorrectnessEvaluator:
        return RuleBasedCorrectnessEvaluator()

    @pytest.mark.asyncio
    async def test_exact_match(self, evaluator: RuleBasedCorrectnessEvaluator) -> None:
        """Should score 1.0 for exact match."""
        score = await evaluator.evaluate(
            prompt="What is 2+2?",
            response="4",
            target="4",
        )
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self, evaluator: RuleBasedCorrectnessEvaluator) -> None:
        """Should match case-insensitively."""
        score = await evaluator.evaluate(
            prompt="What is the capital?",
            response="Paris",
            target="paris",
        )
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_contains_target(self, evaluator: RuleBasedCorrectnessEvaluator) -> None:
        """Should score high when response contains target."""
        score = await evaluator.evaluate(
            prompt="What is 2+2?",
            response="The answer is 4.",
            target="4",
        )
        assert score.value >= 0.8

    @pytest.mark.asyncio
    async def test_numeric_match(self, evaluator: RuleBasedCorrectnessEvaluator) -> None:
        """Should match numeric values."""
        score = await evaluator.evaluate(
            prompt="Calculate 10*5",
            response="The result is 50",
            target="50",
        )
        # Contains target, so gets 0.9 (high match)
        assert score.value >= 0.8

    @pytest.mark.asyncio
    async def test_no_target(self, evaluator: RuleBasedCorrectnessEvaluator) -> None:
        """Should return 0.5 when no target provided."""
        score = await evaluator.evaluate(
            prompt="What is something?",
            response="Some answer",
            target=None,
        )
        assert score.value == 0.5

    @pytest.mark.asyncio
    async def test_no_match(self, evaluator: RuleBasedCorrectnessEvaluator) -> None:
        """Should score 0.0 for no match."""
        score = await evaluator.evaluate(
            prompt="What is 2+2?",
            response="The answer is five",
            target="4",
        )
        assert score.value == 0.0


# =============================================================================
# Completeness Evaluator Tests
# =============================================================================


@pytest.mark.unit
class TestCompletenessEvaluator:
    """Tests for RuleBasedCompletenessEvaluator."""

    @pytest.fixture
    def evaluator(self) -> RuleBasedCompletenessEvaluator:
        return RuleBasedCompletenessEvaluator()

    @pytest.mark.asyncio
    async def test_empty_response(self, evaluator: RuleBasedCompletenessEvaluator) -> None:
        """Should score 0.0 for empty response."""
        score = await evaluator.evaluate(
            prompt="Explain something",
            response="",
        )
        assert score.value == 0.0

    @pytest.mark.asyncio
    async def test_short_response_to_question(self, evaluator: RuleBasedCompletenessEvaluator) -> None:
        """Should penalize short response to question."""
        score = await evaluator.evaluate(
            prompt="What is the meaning of life?",
            response="42",
        )
        assert score.value < 0.5

    @pytest.mark.asyncio
    async def test_multi_part_addressed(self, evaluator: RuleBasedCompletenessEvaluator) -> None:
        """Should score high when multi-part question addressed."""
        score = await evaluator.evaluate(
            prompt="Explain X and Y",
            response="First, X is about... Second, Y refers to...",
        )
        assert score.value >= 0.8

    @pytest.mark.asyncio
    async def test_substantive_content(self, evaluator: RuleBasedCompletenessEvaluator) -> None:
        """Should score well for substantive content."""
        score = await evaluator.evaluate(
            prompt="Tell me about Python",
            response="Python is a high-level programming language known for its readability and versatility.",
        )
        assert score.value >= 0.6


# =============================================================================
# Clarity Evaluator Tests
# =============================================================================


@pytest.mark.unit
class TestClarityEvaluator:
    """Tests for RuleBasedClarityEvaluator."""

    @pytest.fixture
    def evaluator(self) -> RuleBasedClarityEvaluator:
        return RuleBasedClarityEvaluator()

    @pytest.mark.asyncio
    async def test_empty_response(self, evaluator: RuleBasedClarityEvaluator) -> None:
        """Should score 0.0 for empty response."""
        score = await evaluator.evaluate(
            prompt="Explain",
            response="",
        )
        assert score.value == 0.0

    @pytest.mark.asyncio
    async def test_structured_response(self, evaluator: RuleBasedClarityEvaluator) -> None:
        """Should score well for structured response."""
        score = await evaluator.evaluate(
            prompt="How to bake a cake?",
            response="1. Preheat oven\n2. Mix ingredients\n3. Bake for 30 min",
        )
        assert score.value >= 0.6

    @pytest.mark.asyncio
    async def test_code_block_bonus(self, evaluator: RuleBasedClarityEvaluator) -> None:
        """Should give bonus for code blocks."""
        score = await evaluator.evaluate(
            prompt="Show Python code",
            response="Here's the code:\n```python\nprint('hello')\n```",
        )
        assert score.value >= 0.6


# =============================================================================
# Conciseness Evaluator Tests
# =============================================================================


@pytest.mark.unit
class TestConcisenessEvaluator:
    """Tests for RuleBasedConcisenessEvaluator."""

    @pytest.fixture
    def evaluator(self) -> RuleBasedConcisenessEvaluator:
        return RuleBasedConcisenessEvaluator()

    @pytest.mark.asyncio
    async def test_empty_response(self, evaluator: RuleBasedConcisenessEvaluator) -> None:
        """Should score 0.0 for empty response."""
        score = await evaluator.evaluate(
            prompt="Question",
            response="",
        )
        assert score.value == 0.0

    @pytest.mark.asyncio
    async def test_filler_phrases_penalized(self, evaluator: RuleBasedConcisenessEvaluator) -> None:
        """Should penalize filler phrases."""
        score = await evaluator.evaluate(
            prompt="What is 2+2?",
            response="I think, basically, in my opinion, the answer is essentially 4.",
            target="4",
        )
        # Should be lower due to fillers
        assert score.value < 0.9

    @pytest.mark.asyncio
    async def test_appropriate_length(self, evaluator: RuleBasedConcisenessEvaluator) -> None:
        """Should score well for appropriate length."""
        score = await evaluator.evaluate(
            prompt="What is Python?",
            response="Python is a programming language.",
            target="Python is a high-level programming language.",
        )
        assert score.value >= 0.6


# =============================================================================
# Helpfulness Evaluator Tests
# =============================================================================


@pytest.mark.unit
class TestHelpfulnessEvaluator:
    """Tests for RuleBasedHelpfulnessEvaluator."""

    @pytest.fixture
    def evaluator(self) -> RuleBasedHelpfulnessEvaluator:
        return RuleBasedHelpfulnessEvaluator()

    @pytest.mark.asyncio
    async def test_empty_response(self, evaluator: RuleBasedHelpfulnessEvaluator) -> None:
        """Should score 0.0 for empty response."""
        score = await evaluator.evaluate(
            prompt="Help me",
            response="",
        )
        assert score.value == 0.0

    @pytest.mark.asyncio
    async def test_refusal_penalized(self, evaluator: RuleBasedHelpfulnessEvaluator) -> None:
        """Should penalize refusal responses."""
        score = await evaluator.evaluate(
            prompt="How to do X?",
            response="I cannot help with that as an AI language model.",
        )
        assert score.value <= 0.3

    @pytest.mark.asyncio
    async def test_actionable_content(self, evaluator: RuleBasedHelpfulnessEvaluator) -> None:
        """Should reward actionable content."""
        score = await evaluator.evaluate(
            prompt="How do I fix this error?",
            response="You can try the following to fix the error: first, check your settings, then restart the service.",
        )
        # Contains actionable indicators (try, check), value may vary based on topic overlap
        assert score.value >= 0.4

    @pytest.mark.asyncio
    async def test_explanatory_content(self, evaluator: RuleBasedHelpfulnessEvaluator) -> None:
        """Should reward explanatory content."""
        score = await evaluator.evaluate(
            prompt="Why does this happen?",
            response="This happens because the system needs to refresh. Therefore, you should wait.",
        )
        assert score.value >= 0.6


# =============================================================================
# Create Evaluators Tests
# =============================================================================


@pytest.mark.unit
class TestCreateEvaluators:
    """Tests for create_evaluators() function."""

    def test_all_dimensions(self) -> None:
        """Should create evaluators for all dimensions."""
        evaluators = create_evaluators(ALL_DIMENSIONS)
        assert len(evaluators) == 5

    def test_subset_dimensions(self) -> None:
        """Should create evaluators for subset."""
        evaluators = create_evaluators(["correctness", "clarity"])
        assert len(evaluators) == 2

    def test_custom_weights(self) -> None:
        """Should apply custom weights."""
        evaluators = create_evaluators(
            ["correctness"],
            weights={"correctness": 3.0},
        )
        assert evaluators[0].weight == 3.0


# =============================================================================
# Scorer Integration Tests
# =============================================================================


@pytest.mark.unit
class TestMultidimensionalScorer:
    """Tests for multidimensional_scorer() function."""

    def test_creates_scorer(self) -> None:
        """Should create a scorer."""
        scorer = multidimensional_scorer()
        assert scorer is not None

    def test_custom_dimensions(self) -> None:
        """Should accept custom dimensions."""
        scorer = multidimensional_scorer(dimensions=["correctness", "clarity"])
        assert scorer is not None

    def test_custom_weights(self) -> None:
        """Should accept custom weights."""
        scorer = multidimensional_scorer(
            weights={"correctness": 2.0, "clarity": 1.0},
        )
        assert scorer is not None


@pytest.mark.unit
class TestConvenienceScorers:
    """Tests for convenience scorer functions."""

    def test_correctness_scorer(self) -> None:
        """Should create correctness-only scorer."""
        scorer = correctness_scorer()
        assert scorer is not None

    def test_quality_scorer(self) -> None:
        """Should create quality scorer."""
        scorer = quality_scorer()
        assert scorer is not None


# =============================================================================
# ALL_DIMENSIONS Tests
# =============================================================================


@pytest.mark.unit
class TestAllDimensions:
    """Tests for ALL_DIMENSIONS constant."""

    def test_has_five_dimensions(self) -> None:
        """Should have exactly 5 dimensions."""
        assert len(ALL_DIMENSIONS) == 5

    def test_contains_expected_dimensions(self) -> None:
        """Should contain expected dimension names."""
        expected = ["correctness", "completeness", "clarity", "conciseness", "helpfulness"]
        for dim in expected:
            assert dim in ALL_DIMENSIONS
