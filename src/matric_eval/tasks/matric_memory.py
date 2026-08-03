"""
Matric-Memory application-specific evaluation tasks.

Tests title generation capabilities specific to the matric-memory
Rust inference application.
"""

import json
import math
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target, accuracy, scorer
from inspect_ai.solver import generate

from matric_eval.config import get_sample_count
from matric_eval.tasks.registry import register_benchmark

# Path to test data
DATA_DIR = (
    Path(__file__).parent.parent.parent.parent / "tests" / "integration" / "matric_memory" / "data"
)


def score_legacy_title(
    output: str,
    expected_keywords: list[str],
    max_length: int,
) -> tuple[float, bool, dict[str, Any]]:
    """Apply the matric-memory title scorer from its Rust evaluator."""
    output_lower = output.lower()
    keyword_matches = sum(1 for keyword in expected_keywords if keyword.lower() in output_lower)
    keyword_ratio = keyword_matches / len(expected_keywords) if expected_keywords else 0.0
    length_ok = len(output) <= max_length
    clean_format = (
        "```" not in output
        and not output.startswith("#")
        and "**" not in output
        and "Title:" not in output
    )
    value = (keyword_ratio * 0.6) + (0.2 if length_ok else 0.0) + (0.2 if clean_format else 0.0)
    return (
        value,
        value >= 0.7,
        {
            "keyword_matches": keyword_matches,
            "keyword_total": len(expected_keywords),
            "length_ok": length_ok,
            "clean_format": clean_format,
        },
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Calculate cosine similarity using matric-memory's edge-case behavior."""
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


def score_legacy_semantic(
    query_embedding: list[float],
    positive_embeddings: list[list[float]],
    negative_embeddings: list[list[float]],
) -> tuple[float, bool, dict[str, Any]]:
    """Apply matric-memory's positive-versus-negative embedding scorer."""
    positive_scores = [
        cosine_similarity(query_embedding, embedding) for embedding in positive_embeddings
    ]
    negative_scores = [
        cosine_similarity(query_embedding, embedding) for embedding in negative_embeddings
    ]
    min_positive = min(positive_scores, default=0.0)
    max_negative = max(negative_scores, default=1.0)
    value = max(0.0, min(1.0, min_positive - max_negative + 0.5))
    return (
        value,
        min_positive > max_negative,
        {
            "positive_scores": positive_scores,
            "negative_scores": negative_scores,
            "min_positive": min_positive,
            "max_negative": max_negative,
        },
    )


def load_title_cases() -> list[dict[str, Any]]:
    """Load title generation test cases from JSON."""
    path = DATA_DIR / "title_cases.json"
    if not path.exists():
        raise FileNotFoundError(f"Title cases not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_similarity_pairs() -> list[dict[str, Any]]:
    """Load similarity pairs for embedding evaluation."""
    path = DATA_DIR / "similarity_pairs.json"
    if not path.exists():
        raise FileNotFoundError(f"Similarity pairs not found: {path}")
    with open(path) as f:
        return json.load(f)


def title_case_to_sample(case: dict[str, Any]) -> Sample:
    """Convert a title case dict to an Inspect AI Sample."""
    prompt = f"""Generate a concise, descriptive title for the following note content.
The title should capture the main topic or purpose of the note.
Return only the title, nothing else.

Note content:
{case["content"]}

Title:"""

    return Sample(
        id=f"title-{case['id']}",
        input=prompt,
        target=case["ideal_titles"][0] if case.get("ideal_titles") else "",
        metadata={
            "category": "title_generation",
            "ideal_titles": case.get("ideal_titles", []),
            "bad_titles": case.get("bad_titles", []),
        },
    )


def similarity_to_sample(pair: dict[str, Any], pair_type: str) -> Sample:
    """Convert a similarity pair to an Inspect AI Sample for semantic matching."""
    prompt = f"""Rate the semantic similarity between these two texts on a scale of 0-10.
0 means completely unrelated, 10 means identical meaning.
Return only the number.

Text A: {pair["text1"]}

Text B: {pair["text2"]}

Similarity score:"""

    expected = "high" if pair_type == "similar" else "low"
    return Sample(
        id=pair["id"],
        input=prompt,
        target=expected,
        metadata={
            "category": "embedding_similarity",
            "pair_type": pair_type,
            "expected_similarity": pair.get("expected_similarity", 0.5),
        },
    )


def load_matric_memory(tier: str = "smoke") -> list[Sample]:
    """
    Load matric-memory evaluation samples.

    Args:
        tier: Evaluation tier (smoke, quick, full)

    Returns:
        List of Sample objects for evaluation
    """
    samples = []

    # Load title generation cases
    try:
        title_cases = load_title_cases()
        for case in title_cases:
            samples.append(title_case_to_sample(case))
    except FileNotFoundError:
        pass

    # Load similarity pairs (for semantic understanding)
    try:
        sim_pairs = load_similarity_pairs()
        for pair in sim_pairs[:10]:  # Limit similarity tests
            samples.append(similarity_to_sample(pair, "similar"))
    except FileNotFoundError:
        pass

    # Apply tier-based sampling
    sample_count = get_sample_count("matric_memory", tier)
    if sample_count and len(samples) > sample_count:
        import random

        rng = random.Random(42)
        samples = rng.sample(samples, sample_count)

    return samples


@scorer(metrics=[accuracy()])
def title_quality_scorer():
    """
    Score title generation quality.

    Checks if generated title is similar to ideal titles and
    dissimilar from bad titles.
    """

    async def score(state, target: Target) -> Score:
        response = state.output.completion.strip() if state.output else ""
        metadata = state.metadata or {}
        category = metadata.get("category", "")

        if category == "legacy_title_generation":
            score_value, passed, details = score_legacy_title(
                response,
                list(metadata.get("expected_keywords", [])),
                int(metadata.get("max_length", 80)),
            )
            return Score(
                value=score_value,
                answer=response,
                explanation=(
                    f"Keywords: {details['keyword_matches']}/{details['keyword_total']}, "
                    f"length: {details['length_ok']}, clean: {details['clean_format']}, "
                    f"passed: {passed}"
                ),
            )

        if category == "title_generation":
            ideal_titles = metadata.get("ideal_titles", [])
            bad_titles = metadata.get("bad_titles", [])

            response_lower = response.lower()
            response_words = set(response_lower.split())

            # Check similarity to ideal titles (word overlap)
            best_ideal_score = 0.0
            for ideal in ideal_titles:
                ideal_words = set(ideal.lower().split())
                if ideal_words:
                    overlap = len(response_words & ideal_words) / len(ideal_words)
                    best_ideal_score = max(best_ideal_score, overlap)

            # Penalize if similar to bad titles
            worst_bad_score = 0.0
            for bad in bad_titles:
                bad_words = set(bad.lower().split())
                if bad_words:
                    overlap = len(response_words & bad_words) / len(bad_words)
                    worst_bad_score = max(worst_bad_score, overlap)

            # Final score: reward ideal similarity, penalize bad similarity
            score_value = max(0.0, min(1.0, best_ideal_score - (worst_bad_score * 0.5)))

            # Bonus for appropriate length (4-10 words)
            word_count = len(response.split())
            if 4 <= word_count <= 10:
                score_value = min(1.0, score_value + 0.1)

            return Score(
                value=score_value,
                answer=response,
                explanation=f"Ideal similarity: {best_ideal_score:.2f}, Bad similarity: {worst_bad_score:.2f}",
            )

        elif category == "embedding_similarity":
            # For similarity scoring, check if model gave appropriate rating
            try:
                rating = float(re.search(r"\d+(?:\.\d+)?", response).group())
                expected_high = metadata.get("pair_type") == "similar"

                if expected_high:
                    score_value = 1.0 if rating >= 7 else rating / 10
                else:
                    score_value = 1.0 if rating <= 3 else (10 - rating) / 10

                return Score(value=score_value, answer=str(rating))
            except (AttributeError, ValueError):
                return Score(value=0.0, answer=response[:50])

        return Score(value=0.0, answer=response[:100])

    return score


@register_benchmark(
    name="matric_memory",
    description="Matric-Memory - Title generation & semantics (30 cases)",
    category="application",
    tier_samples={"smoke": 10, "quick": 20, "full": 30},
    total_samples=30,
    protocol_version="project-v1",
    evaluator_source="matric-eval",
    evaluator_revision="0.1.0",
    license="MIT",
    access="local",
    source_kind="local",
    release_policy="local",
)
@task
def matric_memory(tier: str = "smoke") -> Task:
    """
    Matric-Memory evaluation task.

    Evaluates title generation and semantic understanding for the
    matric-memory application.

    Args:
        tier: Evaluation tier (smoke, quick, full)

    Returns:
        Configured Task for evaluation
    """
    samples = load_matric_memory(tier)

    return Task(
        name="matric_memory",
        dataset=samples,
        solver=generate(),
        scorer=title_quality_scorer(),
    )
