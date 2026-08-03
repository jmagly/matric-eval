"""
Retrieval quality scorers for memory and search evaluation.

Provides standard IR metrics as both pure functions and Inspect AI scorers:
- Recall@K: fraction of relevant items found in top-K results
- NDCG@K: position-aware relevance with graded judgments
- MRR: reciprocal rank of the first relevant result

These are foundational scorers used by LongMemEval, LoCoMo,
MemoryAgentBench, and matric-memory retrieval evaluation.
"""

import math

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

# =============================================================================
# Pure functions (usable outside Inspect AI)
# =============================================================================


def recall_at_k(retrieved: list, relevant: set, k: int = 5) -> float:
    """
    Compute Recall@K — fraction of relevant items in top-K results.

    Args:
        retrieved: Ordered list of retrieved item IDs
        relevant: Set of relevant item IDs
        k: Number of top results to consider

    Returns:
        Recall score between 0.0 and 1.0
    """
    if not relevant:
        return 0.0
    top_k = set(retrieved[:k])
    return len(top_k & relevant) / len(relevant)


def ndcg_at_k(retrieved: list, relevance: dict, k: int = 10) -> float:
    """
    Compute NDCG@K — Normalized Discounted Cumulative Gain.

    Accounts for the position of relevant items: finding a highly relevant
    result at rank 1 is worth more than at rank 10.

    Args:
        retrieved: Ordered list of retrieved item IDs
        relevance: Dict mapping item ID to relevance grade (e.g., {id: 0-3})
        k: Number of top results to consider

    Returns:
        NDCG score between 0.0 and 1.0
    """
    if not relevance:
        return 0.0

    # DCG of the actual retrieved list
    n = min(k, len(retrieved))
    dcg = sum(relevance.get(retrieved[i], 0) / math.log2(i + 2) for i in range(n))

    # Ideal DCG (best possible ordering)
    ideal_gains = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(gain / math.log2(i + 2) for i, gain in enumerate(ideal_gains))

    if idcg == 0:
        return 0.0

    return dcg / idcg


def mrr(retrieved: list, relevant: set) -> float:
    """
    Compute MRR — Mean Reciprocal Rank.

    Returns the reciprocal of the rank of the first relevant result.

    Args:
        retrieved: Ordered list of retrieved item IDs
        relevant: Set of relevant item IDs

    Returns:
        Reciprocal rank (1/rank) or 0.0 if no relevant item found
    """
    for i, item in enumerate(retrieved):
        if item in relevant:
            return 1.0 / (i + 1)
    return 0.0


def precision_at_k(retrieved: list, relevant: set, k: int = 5) -> float:
    """
    Compute Precision@K — fraction of top-K results that are relevant.

    Args:
        retrieved: Ordered list of retrieved item IDs
        relevant: Set of relevant item IDs
        k: Number of top results to consider

    Returns:
        Precision score between 0.0 and 1.0
    """
    if k == 0:
        return 0.0
    top_k = set(retrieved[:k])
    return len(top_k & relevant) / k


# =============================================================================
# Inspect AI Scorers
# =============================================================================


@scorer(metrics=[mean()])
def recall_at_k_scorer(
    k: int = 5,
    retrieved_key: str = "retrieved_ids",
    gold_key: str = "gold_ids",
) -> Scorer:
    """
    Inspect AI scorer for Recall@K.

    Reads retrieved and gold IDs from sample metadata.

    Args:
        k: Number of top results to consider
        retrieved_key: Metadata key for retrieved item IDs
        gold_key: Metadata key for relevant item IDs

    Returns:
        Scorer function
    """

    async def score(state: TaskState, target: Target) -> Score:
        retrieved = state.metadata.get(retrieved_key, [])
        gold = state.metadata.get(gold_key, [])
        gold_set = set(gold)

        value = recall_at_k(retrieved, gold_set, k)

        return Score(
            value=value,
            explanation=f"Recall@{k}: {value:.2%} ({len(set(retrieved[:k]) & gold_set)}/{len(gold_set)} found)",
            metadata={
                "k": k,
                "retrieved_top_k": retrieved[:k],
                "gold": gold,
                "hits": len(set(retrieved[:k]) & gold_set),
            },
        )

    return score


@scorer(metrics=[mean()])
def ndcg_at_k_scorer(
    k: int = 10,
    retrieved_key: str = "retrieved_ids",
    relevance_key: str = "relevance",
) -> Scorer:
    """
    Inspect AI scorer for NDCG@K.

    Reads retrieved IDs from metadata and relevance grades from either
    metadata or target.

    Args:
        k: Number of top results to consider
        retrieved_key: Metadata key for retrieved item IDs
        relevance_key: Metadata key for relevance dict (item_id -> grade)

    Returns:
        Scorer function
    """

    async def score(state: TaskState, target: Target) -> Score:
        retrieved = state.metadata.get(retrieved_key, [])
        relevance = state.metadata.get(relevance_key, {})

        value = ndcg_at_k(retrieved, relevance, k)

        return Score(
            value=value,
            explanation=f"NDCG@{k}: {value:.3f}",
            metadata={
                "k": k,
                "retrieved_top_k": retrieved[:k],
                "relevance": relevance,
            },
        )

    return score


@scorer(metrics=[mean()])
def mrr_scorer(
    retrieved_key: str = "retrieved_ids",
    gold_key: str = "gold_ids",
) -> Scorer:
    """
    Inspect AI scorer for Mean Reciprocal Rank.

    Args:
        retrieved_key: Metadata key for retrieved item IDs
        gold_key: Metadata key for relevant item IDs

    Returns:
        Scorer function
    """

    async def score(state: TaskState, target: Target) -> Score:
        retrieved = state.metadata.get(retrieved_key, [])
        gold = state.metadata.get(gold_key, [])
        gold_set = set(gold)

        value = mrr(retrieved, gold_set)

        # Find the rank of first hit for explanation
        first_rank = None
        for i, item in enumerate(retrieved):
            if item in gold_set:
                first_rank = i + 1
                break

        explanation = (
            f"MRR: {value:.3f} (first relevant at rank {first_rank})"
            if first_rank
            else "MRR: 0.000 (no relevant item found)"
        )

        return Score(
            value=value,
            explanation=explanation,
            metadata={
                "first_relevant_rank": first_rank,
                "retrieved": retrieved[:20],
                "gold": gold,
            },
        )

    return score


@scorer(metrics=[mean()])
def precision_at_k_scorer(
    k: int = 5,
    retrieved_key: str = "retrieved_ids",
    gold_key: str = "gold_ids",
) -> Scorer:
    """
    Inspect AI scorer for Precision@K.

    Args:
        k: Number of top results to consider
        retrieved_key: Metadata key for retrieved item IDs
        gold_key: Metadata key for relevant item IDs

    Returns:
        Scorer function
    """

    async def score(state: TaskState, target: Target) -> Score:
        retrieved = state.metadata.get(retrieved_key, [])
        gold = state.metadata.get(gold_key, [])
        gold_set = set(gold)

        value = precision_at_k(retrieved, gold_set, k)

        return Score(
            value=value,
            explanation=f"Precision@{k}: {value:.2%}",
            metadata={
                "k": k,
                "hits": len(set(retrieved[:k]) & gold_set),
            },
        )

    return score
