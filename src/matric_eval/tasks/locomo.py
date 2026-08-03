"""
LoCoMo (Long-term Conversational Memory) benchmark task.

Evaluates LLM long-term conversational memory with multi-hop QA over
extended multi-session dialogues (~600 turns, ~16K tokens per conversation).

Based on Maharana et al. (ACL 2024): https://github.com/snap-research/locomo
"""

import json
import random
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import match
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed
from matric_eval.tasks.registry import register_benchmark

# Local dataset path
LOCOMO_PATH = "/home/roctinam/data/evals/locomo"

# Valid QA categories
VALID_CATEGORIES = [
    "single-hop",
    "multi-hop",
    "temporal",
    "open-domain",
    "adversarial",
]


def format_conversation(conversation: list[dict[str, Any]], max_tokens: int = 12000) -> str:
    """
    Format conversation sessions into a readable chat transcript.

    Args:
        conversation: List of session objects with turns
        max_tokens: Approximate max character budget (rough proxy for tokens)

    Returns:
        Formatted conversation string
    """
    lines: list[str] = []
    char_budget = max_tokens * 4  # rough chars-per-token estimate

    for session in conversation:
        session_id = session.get("session_id", "?")
        lines.append(f"--- Session {session_id} ---")
        for turn in session.get("turns", []):
            speaker = turn.get("speaker", "unknown")
            text = turn.get("text", "")
            lines.append(f"{speaker}: {text}")
        lines.append("")

    transcript = "\n".join(lines)

    # Truncate from the beginning if too long, keeping most recent context
    if len(transcript) > char_budget:
        transcript = "... [earlier conversation truncated] ...\n\n" + transcript[-char_budget:]

    return transcript


def record_to_sample(
    qa: dict[str, Any],
    conversation: list[dict[str, Any]],
    sample_id: str,
) -> Sample:
    """
    Convert a LoCoMo QA record (with conversation context) to an Inspect AI Sample.

    Args:
        qa: QA dictionary with question, answer, category, evidence
        conversation: List of session objects forming the conversation
        sample_id: Identifier for the parent conversation

    Returns:
        Sample with conversation context + question as input, answer as target
    """
    question = qa.get("question", "")
    answer = qa.get("answer", "")
    category = qa.get("category", "unknown")
    evidence = qa.get("evidence", [])

    transcript = format_conversation(conversation)

    prompt = (
        "You are given a long conversation between two people. "
        "Read the conversation carefully and answer the question based on the "
        "information in the conversation.\n\n"
        f"{transcript}\n\n"
        f"Question: {question}\n\n"
        "Answer concisely with just the factual answer:"
    )

    # Build evidence metadata
    evidence_refs = []
    for ref in evidence:
        evidence_refs.append(
            {
                "session_id": ref.get("session_id"),
                "turn_id": ref.get("turn_id"),
            }
        )

    qa_id = f"{sample_id}_{category}_{hash(question) % 10000:04d}"

    return Sample(
        input=prompt,
        target=answer,
        id=qa_id,
        metadata={
            "conversation_id": sample_id,
            "category": category,
            "evidence": evidence_refs,
            "question": question,
        },
    )


def load_locomo(
    tier: str = "smoke",
    categories: list[str] | None = None,
) -> list[Sample]:
    """
    Load LoCoMo samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")
        categories: Optional list of QA categories to filter by.
            Valid values: single-hop, multi-hop, temporal, open-domain, adversarial

    Returns:
        List of Sample objects

    Raises:
        FileNotFoundError: If LoCoMo dataset not found
        ValueError: If dataset is empty or invalid category specified
    """
    sample_count = get_sample_count("locomo", tier)
    if sample_count == 0:
        return []

    # Validate categories
    if categories is not None:
        for cat in categories:
            if cat not in VALID_CATEGORIES:
                raise ValueError(f"Invalid category '{cat}'. Valid categories: {VALID_CATEGORIES}")

    locomo_dir = Path(LOCOMO_PATH)
    json_path = locomo_dir / "locomo10.json"

    if not json_path.exists():
        raise FileNotFoundError(
            f"LoCoMo dataset not found at {json_path}. "
            f"Download from https://github.com/snap-research/locomo "
            f"and place locomo10.json in {LOCOMO_PATH}/"
        )

    with open(json_path, "r") as f:
        data = json.load(f)

    if not data:
        raise ValueError(f"LoCoMo dataset is empty: {json_path}")

    # Handle both list and dict formats
    if isinstance(data, dict):
        records = [data]
    else:
        records = data

    all_samples: list[Sample] = []
    for record in records:
        sample_id = record.get("sample_id", "unknown")
        conversation = record.get("conversation", [])
        qa_list = record.get("qa", [])

        for qa in qa_list:
            qa_category = qa.get("category", "unknown")
            if categories is not None and qa_category not in categories:
                continue
            all_samples.append(record_to_sample(qa, conversation, sample_id))

    if sample_count >= len(all_samples):
        return all_samples

    seed = get_seed()
    rng = random.Random(seed)
    return rng.sample(all_samples, sample_count)


@task
def locomo(
    tier: str = "smoke",
    categories: list[str] | None = None,
    thinking: bool = False,
) -> Task:
    """
    LoCoMo benchmark task - long-term conversational memory QA.

    Tests ability to answer questions requiring recall and reasoning
    over extended multi-session conversations.

    Args:
        tier: Evaluation tier
        categories: Optional QA category filter
        thinking: Whether model has thinking enabled

    Returns:
        Inspect AI Task for LoCoMo evaluation
    """
    samples = load_locomo(tier, categories)

    system_msg = (
        "You are a helpful assistant with excellent memory. "
        "Read the conversation carefully and answer questions about it. "
        "Think step by step about where in the conversation the answer can be found."
        if thinking
        else "You are a helpful assistant with excellent memory. "
        "Answer questions about the conversation concisely and accurately."
    )

    return Task(
        dataset=samples,
        solver=[
            system_message(system_msg),
            generate(),
        ],
        scorer=match(),
        name="locomo",
    )


register_benchmark(
    name="locomo",
    description=(
        "LoCoMo - Long-term conversational memory with multi-hop QA over ~600-turn dialogues"
    ),
    category="conversation",
    total_samples=0,
)
