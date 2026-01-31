"""
Matric-Memory application-specific evaluation tasks.

Tests title generation capabilities specific to the matric-memory
Rust inference application.
"""

import json
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target, accuracy, scorer
from inspect_ai.solver import generate

from matric_eval.config import get_sample_count

# Path to test data
DATA_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "integration" / "matric_memory" / "data"


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
{case['content']}

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

Text A: {pair['text_a']}

Text B: {pair['text_b']}

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
                rating = float(re.search(r'\d+(?:\.\d+)?', response).group())
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
