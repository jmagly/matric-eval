"""
Tests for universal LLM-as-Judge system (matric_eval.judges).

Covers:
- Judge interface and result types
- OllamaJudge and OpenAICompatibleJudge implementations
- JudgeFactory creation from spec strings and config dicts
- Universal judge scorer integration
- Prompt building and response parsing
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from inspect_ai.scorer import Score, Target

from matric_eval.judges.base import JudgeResult
from matric_eval.judges.factory import JudgeFactory, create_judge
from matric_eval.judges.ollama import OllamaJudge
from matric_eval.judges.openai_compat import (
    OpenAICompatibleJudge,
    _build_compare_prompt,
    _build_eval_prompt,
    _parse_rating,
    _parse_winner,
)
from matric_eval.judges.scorer import universal_judge_scorer

# =============================================================================
# JudgeResult Tests
# =============================================================================


@pytest.mark.unit
class TestJudgeResult:
    """Tests for JudgeResult dataclass."""

    def test_create_basic_result(self) -> None:
        """Should create result with required fields."""
        result = JudgeResult(score=0.8, raw_score=8.0)
        assert result.score == 0.8
        assert result.raw_score == 8.0
        assert result.reasoning == ""
        assert result.confidence == 1.0
        assert result.winner is None

    def test_create_pairwise_result(self) -> None:
        """Should create pairwise result with winner."""
        result = JudgeResult(score=1.0, raw_score=1.0, winner="A", reasoning="A is better")
        assert result.winner == "A"
        assert result.reasoning == "A is better"

    def test_metadata_defaults_to_empty(self) -> None:
        """Should have empty metadata by default."""
        result = JudgeResult(score=0.5, raw_score=5.0)
        assert result.metadata == {}


# =============================================================================
# Prompt Building Tests
# =============================================================================


@pytest.mark.unit
class TestPromptBuilding:
    """Tests for evaluation prompt building."""

    def test_build_eval_prompt_includes_all_parts(self) -> None:
        """Should include prompt, response, and criteria."""
        prompt = _build_eval_prompt(
            "What is 2+2?",
            "The answer is 4.",
            {"accuracy": 0.5, "clarity": 0.5},
        )
        assert "What is 2+2?" in prompt
        assert "The answer is 4." in prompt
        assert "accuracy" in prompt
        assert "clarity" in prompt

    def test_build_eval_prompt_with_reference(self) -> None:
        """Should include reference answer when provided."""
        prompt = _build_eval_prompt(
            "Question",
            "Response",
            {"quality": 1.0},
            reference="Reference answer",
        )
        assert "Reference Answer" in prompt
        assert "Reference answer" in prompt

    def test_build_eval_prompt_without_reference(self) -> None:
        """Should not include reference section when not provided."""
        prompt = _build_eval_prompt(
            "Question",
            "Response",
            {"quality": 1.0},
        )
        assert "Reference Answer" not in prompt

    def test_build_compare_prompt_includes_both_responses(self) -> None:
        """Should include both responses in comparison prompt."""
        prompt = _build_compare_prompt(
            "Question",
            "Response A text",
            "Response B text",
            {"quality": 1.0},
        )
        assert "Response A text" in prompt
        assert "Response B text" in prompt
        assert "[[A]]" in prompt
        assert "[[B]]" in prompt

    def test_build_eval_prompt_with_dict_criteria(self) -> None:
        """Should handle criteria with description dicts."""
        prompt = _build_eval_prompt(
            "Q",
            "R",
            {"accuracy": {"weight": 0.5, "description": "Factually correct"}},
        )
        assert "Factually correct" in prompt


# =============================================================================
# Response Parsing Tests
# =============================================================================


@pytest.mark.unit
class TestResponseParsing:
    """Tests for judge response parsing."""

    def test_parse_rating_standard_format(self) -> None:
        """Should parse 'Rating: N' format."""
        assert _parse_rating("Rating: 8") == 8.0

    def test_parse_rating_fraction_format(self) -> None:
        """Should parse 'N/10' format."""
        assert _parse_rating("7/10") == 7.0

    def test_parse_rating_bracket_format(self) -> None:
        """Should parse '[[N]]' format."""
        assert _parse_rating("[[9]]") == 9.0

    def test_parse_rating_score_format(self) -> None:
        """Should parse 'Score: N' format."""
        assert _parse_rating("Score: 6") == 6.0

    def test_parse_rating_clamps_high(self) -> None:
        """Should clamp scores above 10."""
        assert _parse_rating("Rating: 15") == 10.0

    def test_parse_rating_clamps_low(self) -> None:
        """Should clamp scores below 1."""
        assert _parse_rating("Rating: 0") == 1.0

    def test_parse_rating_default(self) -> None:
        """Should return 5.0 when no rating found."""
        assert _parse_rating("No rating here") == 5.0

    def test_parse_winner_a(self) -> None:
        """Should parse [[A]] winner."""
        assert _parse_winner("The winner is [[A]]") == "A"

    def test_parse_winner_b(self) -> None:
        """Should parse [[B]] winner."""
        assert _parse_winner("I prefer [[B]]") == "B"

    def test_parse_winner_tie(self) -> None:
        """Should parse [[C]] as tie."""
        assert _parse_winner("They are equal [[C]]") == "tie"

    def test_parse_winner_default_tie(self) -> None:
        """Should default to tie when no winner found."""
        assert _parse_winner("I can't decide") == "tie"


# =============================================================================
# JudgeFactory Tests
# =============================================================================


@pytest.mark.unit
class TestJudgeFactory:
    """Tests for JudgeFactory."""

    def test_create_ollama_judge(self) -> None:
        """Should create OllamaJudge from 'ollama:model' spec."""
        judge = JudgeFactory.create("ollama:llama3.1:8b")
        assert isinstance(judge, OllamaJudge)
        assert judge.name == "ollama:llama3.1:8b"

    def test_create_openai_judge(self) -> None:
        """Should create OpenAICompatibleJudge from 'openai:model' spec."""
        judge = JudgeFactory.create("openai:gpt-4o")
        assert isinstance(judge, OpenAICompatibleJudge)

    def test_create_with_default_model(self) -> None:
        """Should use default model when only provider specified."""
        judge = JudgeFactory.create("ollama")
        assert isinstance(judge, OllamaJudge)

    def test_create_unknown_provider_raises(self) -> None:
        """Should raise ValueError for unknown provider."""
        with pytest.raises(ValueError, match="Unknown judge provider"):
            JudgeFactory.create("unknown:model")

    def test_create_bare_model_defaults_to_ollama(self) -> None:
        """Should default to ollama for bare model names."""
        judge = JudgeFactory.create("llama3.1:8b")
        assert isinstance(judge, OllamaJudge)

    def test_from_config_dict(self) -> None:
        """Should create judge from config dict."""
        judge = JudgeFactory.from_config({"type": "ollama", "model": "llama3.1:8b"})
        assert isinstance(judge, OllamaJudge)

    def test_list_providers(self) -> None:
        """Should list available providers."""
        providers = JudgeFactory.list_providers()
        assert "ollama" in providers
        assert "openai" in providers
        assert "openrouter" in providers

    def test_create_judge_convenience_function(self) -> None:
        """Should create judge via convenience function."""
        judge = create_judge("ollama:llama3.1:8b")
        assert isinstance(judge, OllamaJudge)

    def test_parse_spec_with_colon_in_model(self) -> None:
        """Should handle colons in model names (e.g., llama3.1:8b)."""
        provider, model = JudgeFactory._parse_spec("ollama:llama3.1:8b")
        assert provider == "ollama"
        assert model == "llama3.1:8b"

    def test_parse_spec_no_model(self) -> None:
        """Should handle spec with no model."""
        provider, model = JudgeFactory._parse_spec("ollama")
        assert provider == "ollama"
        assert model is None


# =============================================================================
# OllamaJudge Tests
# =============================================================================


@pytest.mark.unit
class TestOllamaJudge:
    """Tests for OllamaJudge."""

    def test_name_format(self) -> None:
        """Should format name as 'ollama:model'."""
        judge = OllamaJudge(model="llama3.1:8b")
        assert judge.name == "ollama:llama3.1:8b"

    def test_prefixes_model_with_ollama(self) -> None:
        """Should add ollama/ prefix for Inspect AI compatibility."""
        judge = OllamaJudge(model="llama3.1:8b")
        # The inner judge should have the ollama/ prefix
        assert judge._inner._model == "ollama/llama3.1:8b"

    def test_does_not_double_prefix(self) -> None:
        """Should not double-prefix ollama/ models."""
        judge = OllamaJudge(model="ollama/llama3.1:8b")
        assert judge._inner._model == "ollama/llama3.1:8b"

    @pytest.mark.asyncio
    async def test_evaluate_delegates_to_inner(self) -> None:
        """Should delegate evaluation to inner OpenAICompatibleJudge."""
        judge = OllamaJudge(model="llama3.1:8b")

        with patch("matric_eval.judges.openai_compat.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Rating: 8\nReasoning: Good response."
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            result = await judge.evaluate("Question", "Response", {"quality": 1.0})

            assert isinstance(result, JudgeResult)
            assert result.metadata["judge_type"] == "ollama"
            assert result.raw_score == 8.0

    @pytest.mark.asyncio
    async def test_compare_delegates_to_inner(self) -> None:
        """Should delegate comparison to inner judge."""
        judge = OllamaJudge(model="llama3.1:8b")

        with patch("matric_eval.judges.openai_compat.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "[[A]] is better"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            result = await judge.compare("Question", "Response A", "Response B", {"quality": 1.0})

            assert result.winner == "A"
            assert result.metadata["judge_type"] == "ollama"


# =============================================================================
# OpenAICompatibleJudge Tests
# =============================================================================


@pytest.mark.unit
class TestOpenAICompatibleJudge:
    """Tests for OpenAICompatibleJudge."""

    def test_name_format(self) -> None:
        """Should include model in name."""
        judge = OpenAICompatibleJudge(model="gpt-4o")
        assert "gpt-4o" in judge.name

    @pytest.mark.asyncio
    async def test_evaluate_returns_normalized_score(self) -> None:
        """Should return score normalized to 0-1."""
        judge = OpenAICompatibleJudge(model="gpt-4o")

        with patch("matric_eval.judges.openai_compat.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Rating: 9\nReasoning: Excellent."
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            result = await judge.evaluate("Question", "Response", {"quality": 1.0})

            assert 0.0 <= result.score <= 1.0
            assert result.raw_score == 9.0
            # (9-1)/(10-1) = 8/9 ≈ 0.889
            assert abs(result.score - 8 / 9) < 0.01

    @pytest.mark.asyncio
    async def test_evaluate_handles_error(self) -> None:
        """Should propagate errors from model."""
        judge = OpenAICompatibleJudge(model="gpt-4o")

        with patch("matric_eval.judges.openai_compat.get_model") as mock_get_model:
            mock_get_model.side_effect = Exception("API error")

            with pytest.raises(Exception, match="API error"):
                await judge.evaluate("Q", "R", {"quality": 1.0})

    @pytest.mark.asyncio
    async def test_compare_returns_winner(self) -> None:
        """Should return comparison result with winner."""
        judge = OpenAICompatibleJudge(model="gpt-4o")

        with patch("matric_eval.judges.openai_compat.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Response B is more accurate. [[B]]"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            result = await judge.compare("Question", "Response A", "Response B", {"quality": 1.0})

            assert result.winner == "B"
            assert result.score == 0.0  # B wins = 0.0 for A


# =============================================================================
# Universal Judge Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestUniversalJudgeScorer:
    """Tests for universal_judge_scorer() Inspect AI integration."""

    def test_returns_callable(self) -> None:
        """Should return a callable scorer."""
        scorer = universal_judge_scorer("ollama:llama3.1:8b")
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_scores_response(self) -> None:
        """Should score a response using the judge."""
        scorer = universal_judge_scorer("ollama:llama3.1:8b")

        state = Mock()
        state.output.completion = "Paris is the capital of France."
        state.input_text = "What is the capital of France?"
        state.metadata = {}

        target = Target(target="Paris")

        with patch("matric_eval.judges.openai_compat.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Rating: 9\nReasoning: Accurate and clear."
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert isinstance(score, Score)
            assert 0.0 <= score.value <= 1.0
            assert "judge" in score.metadata
            assert score.metadata["raw_score"] == 9.0

    @pytest.mark.asyncio
    async def test_handles_judge_error(self) -> None:
        """Should return 0.5 on judge error."""
        scorer = universal_judge_scorer("ollama:llama3.1:8b")

        state = Mock()
        state.output.completion = "Response"
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        with patch("matric_eval.judges.openai_compat.get_model") as mock_get_model:
            mock_get_model.side_effect = Exception("Connection refused")

            score = await scorer(state, target)

            assert score.value == 0.5
            assert "error" in score.explanation.lower()

    @pytest.mark.asyncio
    async def test_includes_judge_name_in_metadata(self) -> None:
        """Should include judge name in score metadata."""
        scorer = universal_judge_scorer("ollama:llama3.1:8b")

        state = Mock()
        state.output.completion = "Response"
        state.input_text = "Question"
        state.metadata = {}

        target = Target(target="")

        with patch("matric_eval.judges.openai_compat.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_result = Mock()
            mock_result.completion = "Rating: 7"
            mock_model.generate.return_value = mock_result
            mock_get_model.return_value = mock_model

            score = await scorer(state, target)

            assert "ollama" in score.metadata.get("judge", "")


# =============================================================================
# Engine Integration Tests
# =============================================================================


@pytest.mark.unit
class TestEngineJudgeIntegration:
    """Tests for judge integration in EvaluationEngine."""

    def test_engine_accepts_judge_spec(self) -> None:
        """Should accept judge_spec parameter."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/llama3.2:3b",
            tier="smoke",
            judge_spec="ollama:llama3.1:8b",
        )
        assert engine.judge_spec == "ollama:llama3.1:8b"

    def test_engine_default_no_judge(self) -> None:
        """Should default to no judge."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(model="ollama/llama3.2:3b", tier="smoke")
        assert engine.judge_spec is None
