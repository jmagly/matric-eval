"""
Tests for LLM-as-judge scorer (matric_eval.scorers.llm_judge).

Covers:
- LLM judge scoring with different judge models
- Scoring criteria (helpfulness, relevance, accuracy, coherence)
- Error handling and edge cases
- Integration with Inspect AI
- Pairwise comparison scoring
- Agentic evaluation
- Judge prompt templates
- MT-Bench format parsing
"""

import pytest
from inspect_ai.scorer import Score, Target
from unittest.mock import AsyncMock, Mock, patch

from matric_eval.scorers.llm_judge import (
    JUDGE_PROMPTS,
    JudgePrompt,
    JudgeType,
    ScoringConfig,
    agentic_judge_scorer,
    build_judge_prompt,
    get_judge_template,
    list_judge_templates,
    llm_judge_scorer,
    normalize_score,
    pairwise_judge_scorer,
    parse_judge_score,
    parse_pairwise_winner,
    reference_judge_scorer,
    register_judge_template,
)


# =============================================================================
# Judge Prompt Building Tests
# =============================================================================


@pytest.mark.unit
class TestBuildJudgePrompt:
    """Tests for build_judge_prompt() function."""

    def test_build_judge_prompt_includes_question(self) -> None:
        """Should include the original question in the prompt."""
        prompt = build_judge_prompt(
            question="What is 2+2?",
            response="The answer is 4."
        )
        assert "What is 2+2?" in prompt

    def test_build_judge_prompt_includes_response(self) -> None:
        """Should include the model's response in the prompt."""
        prompt = build_judge_prompt(
            question="Explain gravity.",
            response="Gravity is a force that attracts objects."
        )
        assert "Gravity is a force that attracts objects." in prompt

    def test_build_judge_prompt_includes_scoring_criteria(self) -> None:
        """Should include scoring criteria in the prompt."""
        prompt = build_judge_prompt(
            question="Test question",
            response="Test response"
        )
        assert "helpfulness" in prompt.lower()
        assert "relevance" in prompt.lower()
        assert "accuracy" in prompt.lower()
        assert "coherence" in prompt.lower()

    def test_build_judge_prompt_requests_1_10_scale(self) -> None:
        """Should request scoring on a 1-10 scale."""
        prompt = build_judge_prompt(
            question="Test",
            response="Test"
        )
        assert "1" in prompt
        assert "10" in prompt

    def test_build_judge_prompt_handles_empty_response(self) -> None:
        """Should handle empty response gracefully."""
        prompt = build_judge_prompt(
            question="Test question",
            response=""
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_build_judge_prompt_handles_long_response(self) -> None:
        """Should handle very long responses."""
        long_response = "A " * 1000
        prompt = build_judge_prompt(
            question="Test",
            response=long_response
        )
        assert isinstance(prompt, str)


# =============================================================================
# Score Parsing Tests
# =============================================================================


@pytest.mark.unit
class TestParseJudgeScore:
    """Tests for parse_judge_score() function."""

    def test_parse_judge_score_extracts_integer_score(self) -> None:
        """Should extract integer score from judge response."""
        response = "I would rate this response: 8/10"
        score = parse_judge_score(response)
        assert score == 8

    def test_parse_judge_score_extracts_score_on_first_line(self) -> None:
        """Should find score even with explanation."""
        response = """The response is helpful and accurate.
        Overall score: 9/10

        Explanation: The answer addresses all points clearly."""
        score = parse_judge_score(response)
        assert score == 9

    def test_parse_judge_score_handles_score_format_variations(self) -> None:
        """Should handle different score formats."""
        test_cases = [
            ("Score: 7/10", 7),
            ("Rating: 8 out of 10", 8),
            ("7/10", 7),
            ("Score = 6", 6),
            ("I give it a 9", 9),
        ]
        for response, expected in test_cases:
            score = parse_judge_score(response)
            assert score == expected, f"Failed to parse: {response}"

    def test_parse_judge_score_clamps_to_1_10_range(self) -> None:
        """Should clamp scores outside 1-10 range."""
        assert parse_judge_score("Score: 0/10") == 1
        assert parse_judge_score("Score: 11/10") == 10
        assert parse_judge_score("Score: -5/10") == 1
        assert parse_judge_score("Score: 100/10") == 10

    def test_parse_judge_score_defaults_to_5_on_parse_failure(self) -> None:
        """Should return middle score (5) when parsing fails."""
        response = "This response is good but I cannot provide a numeric score."
        score = parse_judge_score(response)
        assert score == 5

    def test_parse_judge_score_handles_empty_response(self) -> None:
        """Should return default score for empty response."""
        score = parse_judge_score("")
        assert score == 5

    def test_parse_judge_score_consistent_extraction(self) -> None:
        """Should consistently extract scores from standard format."""
        # When score is in standard format, it should be extracted
        response1 = "Score: 8/10. The response is good."
        response2 = "The response is good. Score: 8/10"
        response3 = "Overall rating: 8/10"

        score1 = parse_judge_score(response1)
        score2 = parse_judge_score(response2)
        score3 = parse_judge_score(response3)

        assert score1 == 8
        assert score2 == 8
        assert score3 == 8


# =============================================================================
# Scorer Creation Tests
# =============================================================================


@pytest.mark.unit
class TestLLMJudgeScorer:
    """Tests for llm_judge_scorer() scorer creation."""

    def test_scorer_returns_callable(self) -> None:
        """Should return a callable scorer function."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")
        assert callable(scorer)

    def test_scorer_accepts_custom_judge_model(self) -> None:
        """Should accept custom judge model parameter."""
        scorer = llm_judge_scorer(judge_model="custom-model:7b")
        assert scorer is not None

    def test_scorer_uses_default_judge_model(self) -> None:
        """Should use default judge model if not specified."""
        scorer = llm_judge_scorer()
        assert scorer is not None

    @pytest.mark.asyncio
    async def test_scorer_returns_score_object(self) -> None:
        """Should return Score object with value between 0 and 1."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        # Mock state
        state = Mock()
        state.output.completion = "This is a good answer."
        state.input_text = "What is the capital of France?"
        state.metadata = {}

        target = Target(target="Paris")

        # Mock the model call to return a fixed score
        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 8/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert isinstance(score, Score)
            assert 0.0 <= score.value <= 1.0

    @pytest.mark.asyncio
    async def test_scorer_normalizes_score_to_0_1_range(self) -> None:
        """Should normalize 1-10 score to 0-1 range using proper normalization."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Response"
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        # Mock a judge response with score 8/10
        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 8/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            # Score of 8/10 with min=1, max=10 normalizes to (8-1)/(10-1) = 7/9 ≈ 0.778
            expected = (8 - 1) / (10 - 1)  # 7/9
            assert abs(score.value - expected) < 0.01

    @pytest.mark.asyncio
    async def test_scorer_includes_explanation(self) -> None:
        """Should include judge's reasoning in explanation."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Answer"
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            judge_response = "The response is clear and helpful. Score: 9/10"
            mock_result.completion = judge_response
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert score.explanation is not None
            assert "9" in score.explanation

    @pytest.mark.asyncio
    async def test_scorer_handles_judge_model_error(self) -> None:
        """Should handle gracefully when judge model fails."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Answer"
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_get_model.side_effect = Exception("Model not found")

            score = await scorer(state, target)

            # Should return middle score on error
            assert isinstance(score, Score)
            assert score.value == 0.5
            assert "error" in score.explanation.lower()

    @pytest.mark.asyncio
    async def test_scorer_handles_missing_input_text(self) -> None:
        """Should handle cases where input_text is missing."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Answer"
        state.input_text = None
        state.metadata = {}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 7/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert isinstance(score, Score)
            assert score.value >= 0.0


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
class TestLLMJudgeScorerEdgeCases:
    """Tests for edge cases in LLM judge scorer."""

    @pytest.mark.asyncio
    async def test_scorer_with_empty_response(self) -> None:
        """Should handle empty model response."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = ""
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 1/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            # Empty response should get low score
            assert score.value <= 0.5

    @pytest.mark.asyncio
    async def test_scorer_with_very_long_response(self) -> None:
        """Should handle very long responses."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "A " * 5000
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 7/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert isinstance(score, Score)

    @pytest.mark.asyncio
    async def test_scorer_consistency_with_same_input(self) -> None:
        """Should return similar scores for the same input."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Good answer"
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 8/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score1 = await scorer(state, target)
            score2 = await scorer(state, target)

            # Should be identical with mocked judge
            assert score1.value == score2.value


# =============================================================================
# Pairwise Winner Parsing Tests
# =============================================================================


@pytest.mark.unit
class TestParsePairwiseWinner:
    """Tests for parse_pairwise_winner() function."""

    def test_parse_pairwise_winner_detects_a(self) -> None:
        """Should detect [[A]] winner format."""
        response = "Based on my analysis, [[A]] is better"
        winner = parse_pairwise_winner(response)
        assert winner == "A"

    def test_parse_pairwise_winner_detects_b(self) -> None:
        """Should detect [[B]] winner format."""
        response = "I prefer [[B]] because it's more accurate"
        winner = parse_pairwise_winner(response)
        assert winner == "B"

    def test_parse_pairwise_winner_detects_tie(self) -> None:
        """Should detect [[C]] tie format."""
        response = "Both are equally good, so [[C]]"
        winner = parse_pairwise_winner(response)
        assert winner == "C"

    def test_parse_pairwise_winner_returns_none_for_no_winner(self) -> None:
        """Should return None when no winner found."""
        response = "I cannot determine a clear winner"
        winner = parse_pairwise_winner(response)
        assert winner is None

    def test_parse_pairwise_winner_handles_empty_response(self) -> None:
        """Should return None for empty response."""
        winner = parse_pairwise_winner("")
        assert winner is None

    def test_parse_pairwise_winner_handles_none(self) -> None:
        """Should return None for None response."""
        winner = parse_pairwise_winner(None)
        assert winner is None


# =============================================================================
# MT-Bench Format Tests
# =============================================================================


@pytest.mark.unit
class TestMTBenchFormat:
    """Tests for MT-Bench [[rating]] format parsing."""

    def test_parse_mtbench_double_bracket_format(self) -> None:
        """Should parse [[8]] format."""
        response = "This is a good response. [[8]]"
        score = parse_judge_score(response)
        assert score == 8

    def test_parse_mtbench_decimal_format(self) -> None:
        """Should parse [[7.5]] format and round."""
        response = "Rating: [[7.5]]"
        score = parse_judge_score(response)
        assert score in [7, 8]  # Rounded

    def test_parse_mtbench_with_explanation(self) -> None:
        """Should find score with surrounding explanation."""
        response = """The response is comprehensive and accurate.
        The explanation is clear and well-structured.
        [[9]]"""
        score = parse_judge_score(response)
        assert score == 9


# =============================================================================
# Score Normalization Tests
# =============================================================================


@pytest.mark.unit
class TestNormalizeScore:
    """Tests for normalize_score() function."""

    def test_normalize_score_min_to_zero(self) -> None:
        """Should normalize min score to 0.0."""
        config = ScoringConfig(min_score=1, max_score=10)
        assert normalize_score(1, config) == 0.0

    def test_normalize_score_max_to_one(self) -> None:
        """Should normalize max score to 1.0."""
        config = ScoringConfig(min_score=1, max_score=10)
        assert normalize_score(10, config) == 1.0

    def test_normalize_score_middle(self) -> None:
        """Should normalize middle scores correctly."""
        config = ScoringConfig(min_score=1, max_score=10)
        # Score of 5.5 on 1-10 scale = (5.5-1)/(10-1) = 4.5/9 = 0.5
        assert abs(normalize_score(5, config) - 4 / 9) < 0.01

    def test_normalize_score_custom_range(self) -> None:
        """Should work with custom score ranges."""
        config = ScoringConfig(min_score=0, max_score=100)
        assert normalize_score(50, config) == 0.5
        assert normalize_score(0, config) == 0.0
        assert normalize_score(100, config) == 1.0


# =============================================================================
# Judge Prompt Template Tests
# =============================================================================


@pytest.mark.unit
class TestJudgePromptTemplates:
    """Tests for judge prompt template functionality."""

    def test_default_template_exists(self) -> None:
        """Should have a default template."""
        assert "default" in JUDGE_PROMPTS
        assert JUDGE_PROMPTS["default"].prompt_type == JudgeType.SINGLE

    def test_mtbench_template_exists(self) -> None:
        """Should have MT-Bench template."""
        assert "mtbench" in JUDGE_PROMPTS
        assert JUDGE_PROMPTS["mtbench"].category == "multi_turn"

    def test_pairwise_template_exists(self) -> None:
        """Should have pairwise comparison template."""
        assert "pairwise" in JUDGE_PROMPTS
        assert JUDGE_PROMPTS["pairwise"].prompt_type == JudgeType.PAIRWISE

    def test_reference_template_exists(self) -> None:
        """Should have reference-based template."""
        assert "reference" in JUDGE_PROMPTS
        assert JUDGE_PROMPTS["reference"].prompt_type == JudgeType.REFERENCE

    def test_agentic_template_exists(self) -> None:
        """Should have agentic evaluation template."""
        assert "agentic" in JUDGE_PROMPTS
        assert JUDGE_PROMPTS["agentic"].category == "agentic"

    def test_title_quality_template_exists(self) -> None:
        """Should have title quality template from matric-memory."""
        assert "title_quality" in JUDGE_PROMPTS

    def test_get_judge_template_returns_template(self) -> None:
        """Should return template by name."""
        template = get_judge_template("default")
        assert template is not None
        assert isinstance(template, JudgePrompt)

    def test_get_judge_template_returns_none_for_unknown(self) -> None:
        """Should return None for unknown template."""
        template = get_judge_template("nonexistent")
        assert template is None

    def test_list_judge_templates_returns_all(self) -> None:
        """Should list all available templates."""
        templates = list_judge_templates()
        assert "default" in templates
        assert "mtbench" in templates
        assert "pairwise" in templates

    def test_register_judge_template(self) -> None:
        """Should register custom template."""
        custom = JudgePrompt(
            name="custom_test",
            prompt_type=JudgeType.SINGLE,
            category="test",
            system_prompt="Test system",
            prompt_template="Test: {question}",
            output_format="Score: X/10",
        )
        register_judge_template(custom)
        assert "custom_test" in JUDGE_PROMPTS
        # Cleanup
        del JUDGE_PROMPTS["custom_test"]


@pytest.mark.unit
class TestJudgePromptFormatting:
    """Tests for JudgePrompt.format() method."""

    def test_format_replaces_variables(self) -> None:
        """Should replace {variable} placeholders."""
        template = JudgePrompt(
            name="test",
            prompt_type=JudgeType.SINGLE,
            category="test",
            system_prompt="",
            prompt_template="Question: {question}\nResponse: {response}",
            output_format="",
        )
        result = template.format(question="What is 2+2?", response="4")
        assert "What is 2+2?" in result
        assert "4" in result

    def test_format_handles_missing_variables(self) -> None:
        """Should leave unreplaced variables as-is."""
        template = JudgePrompt(
            name="test",
            prompt_type=JudgeType.SINGLE,
            category="test",
            system_prompt="",
            prompt_template="Question: {question}\nContext: {context}",
            output_format="",
        )
        result = template.format(question="Test")
        assert "Test" in result
        assert "{context}" in result  # Unreplaced


# =============================================================================
# Build Judge Prompt with Templates Tests
# =============================================================================


@pytest.mark.unit
class TestBuildJudgePromptWithTemplates:
    """Tests for build_judge_prompt() with template parameter."""

    def test_build_with_default_template(self) -> None:
        """Should use default template by default."""
        prompt = build_judge_prompt("Question", "Response", template="default")
        assert "Question" in prompt
        assert "Response" in prompt

    def test_build_with_mtbench_template(self) -> None:
        """Should use MT-Bench template when specified."""
        prompt = build_judge_prompt("Question", "Response", template="mtbench")
        assert "Question" in prompt
        assert "[[rating]]" in prompt

    def test_build_with_unknown_template_uses_fallback(self) -> None:
        """Should use fallback for unknown template."""
        prompt = build_judge_prompt("Question", "Response", template="nonexistent")
        assert "Question" in prompt
        assert "Response" in prompt


# =============================================================================
# Pairwise Judge Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestPairwiseJudgeScorer:
    """Tests for pairwise_judge_scorer()."""

    def test_pairwise_scorer_returns_callable(self) -> None:
        """Should return a callable scorer function."""
        scorer = pairwise_judge_scorer(judge_model="llama3.2:3b")
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_pairwise_scorer_returns_1_for_model_win(self) -> None:
        """Should return 1.0 when model response wins."""
        scorer = pairwise_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Model response"
        state.input_text = "Question"
        state.metadata = {"reference_response": "Reference response"}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "[[A]] is better"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert score.value == 1.0
            assert score.metadata["winner"] == "A"

    @pytest.mark.asyncio
    async def test_pairwise_scorer_returns_0_for_reference_win(self) -> None:
        """Should return 0.0 when reference response wins."""
        scorer = pairwise_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Model response"
        state.input_text = "Question"
        state.metadata = {"reference_response": "Reference response"}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "[[B]] is better"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert score.value == 0.0
            assert score.metadata["winner"] == "B"

    @pytest.mark.asyncio
    async def test_pairwise_scorer_returns_05_for_tie(self) -> None:
        """Should return 0.5 for tie."""
        scorer = pairwise_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Model response"
        state.input_text = "Question"
        state.metadata = {"reference_response": "Reference response"}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "[[C]] - tie"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert score.value == 0.5
            assert score.metadata["winner"] == "C"


# =============================================================================
# Agentic Judge Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestAgenticJudgeScorer:
    """Tests for agentic_judge_scorer()."""

    def test_agentic_scorer_returns_callable(self) -> None:
        """Should return a callable scorer function."""
        scorer = agentic_judge_scorer(judge_model="llama3.2:3b")
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_agentic_scorer_evaluates_tool_usage(self) -> None:
        """Should evaluate agentic response with tool usage."""
        scorer = agentic_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Using search_tool to find information..."
        state.input_text = "Find the weather in Paris"
        state.metadata = {
            "available_tools": "search_tool, calculator",
            "expected_outcome": "Weather information retrieved",
        }

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 8/10. Good tool selection."
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert isinstance(score, Score)
            assert 0.0 <= score.value <= 1.0
            assert score.metadata["raw_score"] == 8


# =============================================================================
# Reference Judge Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestReferenceJudgeScorer:
    """Tests for reference_judge_scorer()."""

    def test_reference_scorer_returns_callable(self) -> None:
        """Should return a callable scorer function."""
        scorer = reference_judge_scorer(judge_model="llama3.2:3b")
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_reference_scorer_compares_to_target(self) -> None:
        """Should compare response to target reference."""
        scorer = reference_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Paris is the capital of France."
        state.input_text = "What is the capital of France?"
        state.metadata = {}

        target = Target(target="The capital of France is Paris.")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 9/10. Factually accurate."
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert isinstance(score, Score)
            assert score.metadata["raw_score"] == 9


# =============================================================================
# Template with Custom Scorer Tests
# =============================================================================


# =============================================================================
# Regression Tests for API Compatibility
# =============================================================================


@pytest.mark.unit
class TestLLMJudgeScorerAPICompatibility:
    """Regression tests for Inspect AI API compatibility.

    These tests ensure we use the correct Inspect AI Model.generate() API.
    Bug: Model.generate() does NOT accept `system` kwarg - must use
    GenerateConfig(system_message=...) or ChatMessageSystem in message list.
    """

    @pytest.mark.asyncio
    async def test_model_generate_uses_config_not_system_kwarg(self) -> None:
        """REGRESSION: Model.generate() should NOT use system= kwarg.

        The Inspect AI Model.generate() API accepts:
        - input: str | list[ChatMessage]
        - config: GenerateConfig (which has system_message field)

        NOT: system=... as a direct kwarg.

        This test verifies the correct API is used.
        """
        scorer = llm_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Test response"
        state.input_text = "Test question"
        state.metadata = {}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 8/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            # Verify generate was called
            mock_model.generate.assert_called_once()

            # Get the call kwargs
            call_kwargs = mock_model.generate.call_args.kwargs

            # REGRESSION CHECK: 'system' should NOT be in kwargs
            assert 'system' not in call_kwargs, \
                "Model.generate() was called with 'system' kwarg which is not supported. " \
                "Use GenerateConfig(system_message=...) instead."

            # Should use 'config' with system_message
            assert 'config' in call_kwargs, \
                "Model.generate() should be called with config=GenerateConfig(...)"

    @pytest.mark.asyncio
    async def test_pairwise_scorer_uses_config_not_system_kwarg(self) -> None:
        """REGRESSION: pairwise_judge_scorer should use correct API."""
        scorer = pairwise_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Model response"
        state.input_text = "Question"
        state.metadata = {"reference_response": "Reference"}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "[[A]]"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            await scorer(state, target)

            call_kwargs = mock_model.generate.call_args.kwargs
            assert 'system' not in call_kwargs, \
                "pairwise scorer: 'system' kwarg not supported"

    @pytest.mark.asyncio
    async def test_agentic_scorer_uses_config_not_system_kwarg(self) -> None:
        """REGRESSION: agentic_judge_scorer should use correct API."""
        scorer = agentic_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Using tool..."
        state.input_text = "Question"
        state.metadata = {"available_tools": "tool1", "expected_outcome": "result"}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 8/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            await scorer(state, target)

            call_kwargs = mock_model.generate.call_args.kwargs
            assert 'system' not in call_kwargs, \
                "agentic scorer: 'system' kwarg not supported"

    @pytest.mark.asyncio
    async def test_reference_scorer_uses_config_not_system_kwarg(self) -> None:
        """REGRESSION: reference_judge_scorer should use correct API."""
        scorer = reference_judge_scorer(judge_model="llama3.2:3b")

        state = Mock()
        state.output.completion = "Response"
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="Reference answer")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Score: 8/10"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            await scorer(state, target)

            call_kwargs = mock_model.generate.call_args.kwargs
            assert 'system' not in call_kwargs, \
                "reference scorer: 'system' kwarg not supported"


@pytest.mark.unit
class TestLLMJudgeScorerWithTemplates:
    """Tests for llm_judge_scorer() with template parameter."""

    def test_scorer_accepts_template_parameter(self) -> None:
        """Should accept template parameter."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b", template="mtbench")
        assert scorer is not None

    @pytest.mark.asyncio
    async def test_scorer_uses_specified_template(self) -> None:
        """Should use the specified template for judging."""
        scorer = llm_judge_scorer(judge_model="llama3.2:3b", template="mtbench")

        state = Mock()
        state.output.completion = "Answer"
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        with patch('matric_eval.scorers.llm_judge.get_model') as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "[[8]]"  # MT-Bench format
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert score.metadata["template"] == "mtbench"
            assert score.metadata["raw_score"] == 8
