"""
Tests for Elo rating aggregation (matric_eval.scorers.elo).

Covers:
- EloAggregator with known match outcomes → expected ratings
- Deterministic ordering (equal ratings sorted by model_id)
- normalize_to_score produces 0.0-1.0 range
- Empty aggregator edge case
- DRAW handling
"""

import pytest

from matric_eval.scorers.elo import EloAggregator, MatchResult


# =============================================================================
# MatchResult Tests
# =============================================================================


@pytest.mark.unit
class TestMatchResult:
    """Tests for MatchResult dataclass."""

    def test_match_result_construction(self) -> None:
        """MatchResult fields should be accessible."""
        match = MatchResult(
            model_a="model_x",
            model_b="model_y",
            winner="model_x",
            sample_id="sample_001",
        )
        assert match.model_a == "model_x"
        assert match.model_b == "model_y"
        assert match.winner == "model_x"
        assert match.sample_id == "sample_001"

    def test_draw_winner(self) -> None:
        """Winner can be 'DRAW'."""
        match = MatchResult(
            model_a="a",
            model_b="b",
            winner="DRAW",
            sample_id="s1",
        )
        assert match.winner == "DRAW"


# =============================================================================
# EloAggregator Basic Tests
# =============================================================================


@pytest.mark.unit
class TestEloAggregatorBasic:
    """Tests for EloAggregator initialization and defaults."""

    def test_default_init(self) -> None:
        """Default base_rating=1200, k_factor=32."""
        agg = EloAggregator()
        assert agg.base_rating == 1200
        assert agg.k_factor == 32

    def test_custom_init(self) -> None:
        """Custom base_rating and k_factor are stored."""
        agg = EloAggregator(base_rating=1000, k_factor=16)
        assert agg.base_rating == 1000
        assert agg.k_factor == 16

    def test_empty_get_ratings(self) -> None:
        """Empty aggregator returns empty ratings list."""
        agg = EloAggregator()
        ratings = agg.get_ratings()
        assert ratings == []

    def test_empty_normalize_to_score(self) -> None:
        """Empty aggregator returns empty dict."""
        agg = EloAggregator()
        scores = agg.normalize_to_score()
        assert scores == {}


# =============================================================================
# EloAggregator Match Recording Tests
# =============================================================================


@pytest.mark.unit
class TestEloAggregatorMatches:
    """Tests for match recording and rating computation."""

    def test_winner_gains_rating(self) -> None:
        """Winning model should gain Elo; loser should lose."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        match = MatchResult(
            model_a="alpha",
            model_b="beta",
            winner="alpha",
            sample_id="s1",
        )
        agg.record_match(match)
        ratings = dict(agg.get_ratings())
        assert ratings["alpha"] > 1200
        assert ratings["beta"] < 1200

    def test_loser_loses_rating(self) -> None:
        """Both models' changes should be equal magnitude (zero-sum)."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        match = MatchResult(
            model_a="alpha",
            model_b="beta",
            winner="alpha",
            sample_id="s1",
        )
        agg.record_match(match)
        ratings = dict(agg.get_ratings())
        total = ratings["alpha"] + ratings["beta"]
        # Zero-sum: total should equal 2 * base_rating
        assert abs(total - 2400) < 1e-6

    def test_draw_minimal_change(self) -> None:
        """DRAW between equal-rated models should change ratings minimally."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        match = MatchResult(
            model_a="alpha",
            model_b="beta",
            winner="DRAW",
            sample_id="s1",
        )
        agg.record_match(match)
        ratings = dict(agg.get_ratings())
        # Equal-rated draw: expected score = 0.5 for both, so no change
        assert abs(ratings["alpha"] - 1200) < 1e-6
        assert abs(ratings["beta"] - 1200) < 1e-6

    def test_multiple_matches_accumulate(self) -> None:
        """Multiple wins for same model should accumulate higher rating."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        for i in range(5):
            agg.record_match(MatchResult(
                model_a="strong",
                model_b="weak",
                winner="strong",
                sample_id=f"s{i}",
            ))
        ratings = dict(agg.get_ratings())
        assert ratings["strong"] > 1200
        assert ratings["weak"] < 1200
        # After 5 wins, strong should be significantly higher
        assert ratings["strong"] > 1220

    def test_three_models(self) -> None:
        """Handles more than two models in the pool."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("a", "b", "a", "s1"))
        agg.record_match(MatchResult("b", "c", "b", "s2"))
        agg.record_match(MatchResult("a", "c", "a", "s3"))
        ratings = dict(agg.get_ratings())
        # 'a' won both matches, should be highest
        assert ratings["a"] > ratings["b"]
        assert ratings["a"] > ratings["c"]


# =============================================================================
# EloAggregator Ordering Tests (BC-003)
# =============================================================================


@pytest.mark.unit
class TestEloAggregatorOrdering:
    """Tests for deterministic ordering in get_ratings()."""

    def test_sorted_by_rating_descending(self) -> None:
        """get_ratings() should return models sorted by rating descending."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("alpha", "beta", "alpha", "s1"))
        ratings = agg.get_ratings()
        values = [r for _, r in ratings]
        assert values == sorted(values, reverse=True)

    def test_deterministic_ordering_equal_ratings(self) -> None:
        """Equal ratings must be sorted alphabetically by model_id (BC-003)."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        # Two models with no matches → both at base_rating
        # Add them by recording a draw so both are tracked
        agg.record_match(MatchResult("zebra", "alpha", "DRAW", "s1"))
        ratings = agg.get_ratings()
        names = [name for name, _ in ratings]
        # Both have same rating after draw → sorted alphabetically
        assert names == sorted(names)

    def test_get_ratings_returns_list_of_tuples(self) -> None:
        """get_ratings() returns list of (model_id, rating) tuples."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("a", "b", "a", "s1"))
        ratings = agg.get_ratings()
        assert isinstance(ratings, list)
        for item in ratings:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], float)

    def test_get_ratings_consistent_calls(self) -> None:
        """Multiple calls to get_ratings() without new matches → same result."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("x", "y", "x", "s1"))
        result1 = agg.get_ratings()
        result2 = agg.get_ratings()
        assert result1 == result2


# =============================================================================
# EloAggregator normalize_to_score Tests
# =============================================================================


@pytest.mark.unit
class TestNormalizeToScore:
    """Tests for normalize_to_score() method."""

    def test_range_is_0_to_1(self) -> None:
        """All normalized scores must be in [0.0, 1.0]."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        for i in range(5):
            agg.record_match(MatchResult("winner", f"loser_{i}", "winner", f"s{i}"))
        scores = agg.normalize_to_score()
        for model, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Out of range for {model}: {score}"

    def test_winner_has_higher_normalized_score(self) -> None:
        """Model with more wins should have higher normalized score."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("strong", "weak", "strong", "s1"))
        agg.record_match(MatchResult("strong", "weak", "strong", "s2"))
        scores = agg.normalize_to_score()
        assert scores["strong"] > scores["weak"]

    def test_single_model_draw(self) -> None:
        """Two equal models → normalized scores should be equal (0.5 each)."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("a", "b", "DRAW", "s1"))
        scores = agg.normalize_to_score()
        assert abs(scores["a"] - scores["b"]) < 1e-6

    def test_returns_dict(self) -> None:
        """normalize_to_score returns dict[str, float]."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("a", "b", "a", "s1"))
        scores = agg.normalize_to_score()
        assert isinstance(scores, dict)
        for k, v in scores.items():
            assert isinstance(k, str)
            assert isinstance(v, float)

    def test_all_models_present(self) -> None:
        """All participating models appear in normalize_to_score result."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("alpha", "beta", "alpha", "s1"))
        agg.record_match(MatchResult("beta", "gamma", "gamma", "s2"))
        scores = agg.normalize_to_score()
        assert "alpha" in scores
        assert "beta" in scores
        assert "gamma" in scores

    def test_single_participant_score(self) -> None:
        """Single participant after self-match → normalized score handled."""
        agg = EloAggregator(base_rating=1200, k_factor=32)
        agg.record_match(MatchResult("only", "only", "DRAW", "s1"))
        scores = agg.normalize_to_score()
        # Single unique model: normalized score should be in [0, 1]
        assert 0.0 <= scores.get("only", 0.5) <= 1.0
