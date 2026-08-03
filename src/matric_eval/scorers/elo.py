"""
Elo rating aggregation for pairwise model comparison.

Provides an Elo rating system (Arpad Elo, 1960) adapted for LLM evaluation.
Models are rated based on pairwise comparison outcomes across benchmark samples.

The Elo update formula:
    R'(A) = R(A) + K * (S(A) - E(A))

Where:
    E(A) = 1 / (1 + 10^((R(B) - R(A)) / 400))  -- expected score
    S(A) = 1.0 win, 0.5 draw, 0.0 loss           -- actual score
    K    = k_factor (update magnitude)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MatchResult:
    """Result of a pairwise comparison between two models on a sample.

    Attributes:
        model_a: Identifier for model A
        model_b: Identifier for model B
        winner: One of model_a's id, model_b's id, or "DRAW"
        sample_id: Identifier for the evaluation sample
    """

    model_a: str
    model_b: str
    winner: str  # model_a, model_b, or "DRAW"
    sample_id: str


class EloAggregator:
    """Elo rating system for LLM model comparison.

    Records pairwise match outcomes and maintains running Elo ratings
    for each participating model. Ratings start at base_rating and are
    updated after each match using the standard Elo formula.

    Args:
        base_rating: Starting Elo rating for all models (default: 1200)
        k_factor: Update magnitude per match (default: 32)

    Example:
        >>> agg = EloAggregator()
        >>> agg.record_match(MatchResult("gpt4", "llama3", "gpt4", "q001"))
        >>> ratings = agg.get_ratings()
        >>> print(ratings[0])  # ("gpt4", 1216.0)
    """

    def __init__(self, base_rating: float = 1200, k_factor: float = 32) -> None:
        self.base_rating = base_rating
        self.k_factor = k_factor
        self._ratings: dict[str, float] = {}

    def _ensure_model(self, model_id: str) -> None:
        """Initialize model rating at base_rating if not already tracked."""
        if model_id not in self._ratings:
            self._ratings[model_id] = float(self.base_rating)

    def _expected_score(self, rating_a: float, rating_b: float) -> float:
        """Compute expected score for model A against model B.

        E(A) = 1 / (1 + 10^((R(B) - R(A)) / 400))

        Args:
            rating_a: Current Elo rating of model A
            rating_b: Current Elo rating of model B

        Returns:
            Expected score for model A in [0.0, 1.0]
        """
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def record_match(self, result: MatchResult) -> None:
        """Record a pairwise match outcome and update Elo ratings.

        Args:
            result: MatchResult describing the match and winner
        """
        self._ensure_model(result.model_a)
        self._ensure_model(result.model_b)

        ra = self._ratings[result.model_a]
        rb = self._ratings[result.model_b]

        ea = self._expected_score(ra, rb)
        eb = self._expected_score(rb, ra)

        # Determine actual scores
        if result.winner == result.model_a:
            sa, sb = 1.0, 0.0
        elif result.winner == result.model_b:
            sa, sb = 0.0, 1.0
        else:
            # DRAW or unrecognized winner → treat as draw
            sa, sb = 0.5, 0.5

        # Update ratings
        self._ratings[result.model_a] = ra + self.k_factor * (sa - ea)
        self._ratings[result.model_b] = rb + self.k_factor * (sb - eb)

    def get_ratings(self) -> list[tuple[str, float]]:
        """Return sorted Elo ratings for all participating models.

        Sorted by (-rating, model_id) for deterministic ordering when
        ratings are equal (BC-003 requirement).

        Returns:
            List of (model_id, rating) tuples, sorted by rating descending.
            Ties broken alphabetically by model_id.
        """
        return sorted(
            [(model, rating) for model, rating in self._ratings.items()],
            key=lambda item: (-item[1], item[0]),
        )

    def normalize_to_score(self) -> dict[str, float]:
        """Normalize Elo ratings to [0.0, 1.0] range relative to participants.

        Uses min-max normalization across all participating models.
        When only one unique rating value exists (all tied or single model),
        all models receive 0.5.

        Returns:
            dict mapping model_id to normalized score in [0.0, 1.0]
        """
        if not self._ratings:
            return {}

        ratings = list(self._ratings.values())
        min_rating = min(ratings)
        max_rating = max(ratings)
        rating_range = max_rating - min_rating

        if rating_range == 0.0:
            # All models have equal rating → 0.5 for all
            return {model: 0.5 for model in self._ratings}

        return {
            model: (rating - min_rating) / rating_range for model, rating in self._ratings.items()
        }
