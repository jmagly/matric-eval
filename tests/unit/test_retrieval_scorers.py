"""
Tests for retrieval quality scorers (matric_eval.scorers.retrieval).

Covers:
- Recall@K: pure function + Inspect AI scorer
- NDCG@K: pure function + Inspect AI scorer
- MRR: pure function + Inspect AI scorer
- Precision@K: pure function + Inspect AI scorer
- Edge cases: empty results, no relevant items, perfect retrieval
"""

import math

import pytest
from inspect_ai.scorer import Score, Target
from unittest.mock import Mock

from matric_eval.scorers.retrieval import (
    mrr,
    mrr_scorer,
    ndcg_at_k,
    ndcg_at_k_scorer,
    precision_at_k,
    precision_at_k_scorer,
    recall_at_k,
    recall_at_k_scorer,
)


# =============================================================================
# Recall@K Pure Function Tests
# =============================================================================


@pytest.mark.unit
class TestRecallAtK:
    """Tests for recall_at_k() pure function."""

    def test_perfect_recall(self) -> None:
        """Should return 1.0 when all relevant items in top-K."""
        assert recall_at_k(["a", "b", "c"], {"a", "b"}, k=3) == 1.0

    def test_partial_recall(self) -> None:
        """Should return fraction of relevant items found."""
        assert recall_at_k(["a", "b", "c"], {"a", "c", "d"}, k=3) == pytest.approx(2 / 3)

    def test_zero_recall(self) -> None:
        """Should return 0.0 when no relevant items in top-K."""
        assert recall_at_k(["x", "y", "z"], {"a", "b"}, k=3) == 0.0

    def test_k_limits_results(self) -> None:
        """Should only consider top-K results."""
        # "c" is relevant but at position 3, K=2 only looks at first 2
        assert recall_at_k(["a", "b", "c"], {"c"}, k=2) == 0.0
        assert recall_at_k(["a", "b", "c"], {"c"}, k=3) == 1.0

    def test_empty_retrieved(self) -> None:
        """Should return 0.0 for empty retrieved list."""
        assert recall_at_k([], {"a", "b"}, k=5) == 0.0

    def test_empty_relevant(self) -> None:
        """Should return 0.0 for empty relevant set."""
        assert recall_at_k(["a", "b"], set(), k=5) == 0.0

    def test_k_larger_than_retrieved(self) -> None:
        """Should handle K larger than retrieved list."""
        assert recall_at_k(["a"], {"a", "b"}, k=10) == 0.5

    def test_k_equals_1(self) -> None:
        """Should work with K=1."""
        assert recall_at_k(["a", "b"], {"a"}, k=1) == 1.0
        assert recall_at_k(["b", "a"], {"a"}, k=1) == 0.0

    def test_duplicate_retrieved(self) -> None:
        """Should handle duplicates in retrieved list."""
        assert recall_at_k(["a", "a", "a"], {"a", "b"}, k=3) == 0.5

    def test_integer_ids(self) -> None:
        """Should work with integer IDs."""
        assert recall_at_k([1, 2, 3], {2, 4}, k=5) == 0.5

    def test_standard_k5(self) -> None:
        """Standard Recall@5 test case."""
        retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5", "doc6"]
        relevant = {"doc1", "doc3", "doc6", "doc8"}
        # Top 5: doc1, doc2, doc3, doc4, doc5 — hits: doc1, doc3 = 2/4
        assert recall_at_k(retrieved, relevant, k=5) == 0.5


# =============================================================================
# NDCG@K Pure Function Tests
# =============================================================================


@pytest.mark.unit
class TestNDCGAtK:
    """Tests for ndcg_at_k() pure function."""

    def test_perfect_ndcg(self) -> None:
        """Should return 1.0 for ideal ordering."""
        # Retrieved in perfect relevance order
        retrieved = ["a", "b", "c"]
        relevance = {"a": 3, "b": 2, "c": 1}
        assert ndcg_at_k(retrieved, relevance, k=3) == pytest.approx(1.0)

    def test_reversed_ndcg(self) -> None:
        """Should return < 1.0 for reversed ordering."""
        retrieved = ["c", "b", "a"]
        relevance = {"a": 3, "b": 2, "c": 1}
        # DCG: 1/log2(2) + 2/log2(3) + 3/log2(4) = 1.0 + 1.262 + 1.5 = 3.762
        # IDCG: 3/log2(2) + 2/log2(3) + 1/log2(4) = 3.0 + 1.262 + 0.5 = 4.762
        result = ndcg_at_k(retrieved, relevance, k=3)
        assert 0.0 < result < 1.0

    def test_zero_ndcg(self) -> None:
        """Should return 0.0 when no relevant items retrieved."""
        retrieved = ["x", "y", "z"]
        relevance = {"a": 3, "b": 2}
        assert ndcg_at_k(retrieved, relevance, k=3) == 0.0

    def test_empty_relevance(self) -> None:
        """Should return 0.0 for empty relevance dict."""
        assert ndcg_at_k(["a", "b"], {}, k=5) == 0.0

    def test_empty_retrieved(self) -> None:
        """Should return 0.0 for empty retrieved list."""
        assert ndcg_at_k([], {"a": 3}, k=5) == 0.0

    def test_k_limits_results(self) -> None:
        """Should only consider top-K positions."""
        retrieved = ["x", "y", "a"]  # "a" at position 3
        relevance = {"a": 3}
        assert ndcg_at_k(retrieved, relevance, k=2) == 0.0
        assert ndcg_at_k(retrieved, relevance, k=3) > 0.0

    def test_graded_relevance(self) -> None:
        """Should weight higher relevance grades more."""
        # "a" (grade 3) at rank 1 vs "b" (grade 1) at rank 1
        r1 = ndcg_at_k(["a", "b"], {"a": 3, "b": 1}, k=2)
        r2 = ndcg_at_k(["b", "a"], {"a": 3, "b": 1}, k=2)
        assert r1 > r2  # Better to have high-relevance item first

    def test_single_item(self) -> None:
        """Should work with a single retrieved item."""
        assert ndcg_at_k(["a"], {"a": 1}, k=1) == pytest.approx(1.0)

    def test_binary_relevance(self) -> None:
        """Should work with binary (0/1) relevance."""
        retrieved = ["a", "b", "c"]
        relevance = {"a": 1, "c": 1}
        result = ndcg_at_k(retrieved, relevance, k=3)
        assert 0.0 < result <= 1.0


# =============================================================================
# MRR Pure Function Tests
# =============================================================================


@pytest.mark.unit
class TestMRR:
    """Tests for mrr() pure function."""

    def test_first_position(self) -> None:
        """Should return 1.0 when first item is relevant."""
        assert mrr(["a", "b", "c"], {"a"}) == 1.0

    def test_second_position(self) -> None:
        """Should return 0.5 when first relevant at rank 2."""
        assert mrr(["x", "a", "b"], {"a"}) == 0.5

    def test_third_position(self) -> None:
        """Should return 1/3 when first relevant at rank 3."""
        assert mrr(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_no_relevant(self) -> None:
        """Should return 0.0 when no relevant items found."""
        assert mrr(["x", "y", "z"], {"a"}) == 0.0

    def test_empty_retrieved(self) -> None:
        """Should return 0.0 for empty retrieved list."""
        assert mrr([], {"a"}) == 0.0

    def test_empty_relevant(self) -> None:
        """Should return 0.0 for empty relevant set."""
        assert mrr(["a", "b"], set()) == 0.0

    def test_multiple_relevant(self) -> None:
        """Should use rank of the *first* relevant item."""
        # Both "a" and "c" are relevant, but "a" is at rank 2
        assert mrr(["x", "a", "c"], {"a", "c"}) == 0.5


# =============================================================================
# Precision@K Pure Function Tests
# =============================================================================


@pytest.mark.unit
class TestPrecisionAtK:
    """Tests for precision_at_k() pure function."""

    def test_perfect_precision(self) -> None:
        """Should return 1.0 when all top-K are relevant."""
        assert precision_at_k(["a", "b"], {"a", "b", "c"}, k=2) == 1.0

    def test_zero_precision(self) -> None:
        """Should return 0.0 when no top-K are relevant."""
        assert precision_at_k(["x", "y"], {"a", "b"}, k=2) == 0.0

    def test_half_precision(self) -> None:
        """Should return 0.5 when half of top-K are relevant."""
        assert precision_at_k(["a", "x", "b", "y"], {"a", "b"}, k=4) == 0.5

    def test_k_zero(self) -> None:
        """Should return 0.0 for K=0."""
        assert precision_at_k(["a"], {"a"}, k=0) == 0.0

    def test_empty_retrieved(self) -> None:
        """Should return 0.0 for empty retrieved list."""
        assert precision_at_k([], {"a"}, k=5) == 0.0


# =============================================================================
# Recall@K Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestRecallAtKScorer:
    """Tests for recall_at_k_scorer() Inspect AI integration."""

    def test_returns_callable(self) -> None:
        """Should return a callable scorer."""
        scorer = recall_at_k_scorer(k=5)
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_scores_from_metadata(self) -> None:
        """Should read retrieved/gold IDs from metadata."""
        scorer = recall_at_k_scorer(k=5)

        state = Mock()
        state.metadata = {
            "retrieved_ids": ["doc1", "doc2", "doc3", "doc4", "doc5"],
            "gold_ids": ["doc1", "doc3", "doc7"],
        }
        state.output.completion = ""
        target = Target(target="")

        score = await scorer(state, target)
        assert isinstance(score, Score)
        assert score.value == pytest.approx(2 / 3)  # doc1, doc3 found out of 3
        assert score.metadata["k"] == 5
        assert score.metadata["hits"] == 2

    @pytest.mark.asyncio
    async def test_custom_metadata_keys(self) -> None:
        """Should support custom metadata key names."""
        scorer = recall_at_k_scorer(k=3, retrieved_key="results", gold_key="expected")

        state = Mock()
        state.metadata = {
            "results": [1, 2, 3],
            "expected": [2, 4],
        }
        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 0.5  # 1 of 2 found

    @pytest.mark.asyncio
    async def test_missing_metadata_returns_zero(self) -> None:
        """Should return 0.0 when metadata keys missing."""
        scorer = recall_at_k_scorer(k=5)

        state = Mock()
        state.metadata = {}
        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 0.0


# =============================================================================
# NDCG@K Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestNDCGAtKScorer:
    """Tests for ndcg_at_k_scorer() Inspect AI integration."""

    def test_returns_callable(self) -> None:
        """Should return a callable scorer."""
        scorer = ndcg_at_k_scorer(k=10)
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_scores_with_graded_relevance(self) -> None:
        """Should use graded relevance from metadata."""
        scorer = ndcg_at_k_scorer(k=3)

        state = Mock()
        state.metadata = {
            "retrieved_ids": ["a", "b", "c"],
            "relevance": {"a": 3, "b": 2, "c": 1},
        }
        target = Target(target="")

        score = await scorer(state, target)
        assert isinstance(score, Score)
        assert score.value == pytest.approx(1.0)  # Perfect ordering


# =============================================================================
# MRR Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestMRRScorer:
    """Tests for mrr_scorer() Inspect AI integration."""

    def test_returns_callable(self) -> None:
        """Should return a callable scorer."""
        scorer = mrr_scorer()
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_scores_first_hit(self) -> None:
        """Should score based on first relevant item rank."""
        scorer = mrr_scorer()

        state = Mock()
        state.metadata = {
            "retrieved_ids": ["x", "a", "y"],
            "gold_ids": ["a", "b"],
        }
        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 0.5  # First hit at rank 2
        assert score.metadata["first_relevant_rank"] == 2

    @pytest.mark.asyncio
    async def test_no_hits(self) -> None:
        """Should return 0.0 when no relevant items found."""
        scorer = mrr_scorer()

        state = Mock()
        state.metadata = {
            "retrieved_ids": ["x", "y", "z"],
            "gold_ids": ["a"],
        }
        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 0.0
        assert score.metadata["first_relevant_rank"] is None


# =============================================================================
# Precision@K Scorer Tests
# =============================================================================


@pytest.mark.unit
class TestPrecisionAtKScorer:
    """Tests for precision_at_k_scorer() Inspect AI integration."""

    @pytest.mark.asyncio
    async def test_scores_precision(self) -> None:
        """Should compute precision from metadata."""
        scorer = precision_at_k_scorer(k=4)

        state = Mock()
        state.metadata = {
            "retrieved_ids": ["a", "x", "b", "y"],
            "gold_ids": ["a", "b", "c"],
        }
        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 0.5  # 2 relevant in top 4


# =============================================================================
# Cross-Metric Consistency Tests
# =============================================================================


@pytest.mark.unit
class TestCrossMetricConsistency:
    """Tests for consistency between metrics."""

    def test_perfect_retrieval_all_metrics(self) -> None:
        """All metrics should be 1.0 for perfect retrieval."""
        retrieved = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        relevance = {"a": 3, "b": 2, "c": 1}

        assert recall_at_k(retrieved, relevant, k=3) == 1.0
        assert ndcg_at_k(retrieved, relevance, k=3) == pytest.approx(1.0)
        assert mrr(retrieved, relevant) == 1.0
        assert precision_at_k(retrieved, relevant, k=3) == 1.0

    def test_empty_retrieval_all_metrics(self) -> None:
        """All metrics should be 0.0 for empty retrieval."""
        relevant = {"a", "b"}
        relevance = {"a": 3, "b": 2}

        assert recall_at_k([], relevant, k=5) == 0.0
        assert ndcg_at_k([], relevance, k=5) == 0.0
        assert mrr([], relevant) == 0.0
        assert precision_at_k([], relevant, k=5) == 0.0

    def test_no_relevant_all_metrics(self) -> None:
        """All metrics should be 0.0 when no items are relevant."""
        retrieved = ["x", "y", "z"]

        assert recall_at_k(retrieved, set(), k=3) == 0.0
        assert ndcg_at_k(retrieved, {}, k=3) == 0.0
        assert mrr(retrieved, set()) == 0.0
        assert precision_at_k(retrieved, set(), k=3) == 0.0

    def test_recall_geq_precision(self) -> None:
        """Recall should be >= precision when |relevant| <= K."""
        retrieved = ["a", "x", "y", "z", "b"]
        relevant = {"a", "b"}  # 2 relevant, K=5
        r = recall_at_k(retrieved, relevant, k=5)
        p = precision_at_k(retrieved, relevant, k=5)
        # Recall: 2/2 = 1.0, Precision: 2/5 = 0.4
        assert r >= p
