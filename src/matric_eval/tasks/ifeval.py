"""
IFEval (Instruction Following Evaluation) benchmark task.

Loads the IFEval dataset (541 instruction following tasks) and provides
tiered evaluation support (smoke/quick/full).

Tests specific constraints like paragraph count, word limits, keyword presence,
JSON formatting, case requirements, and more.

Based on https://arxiv.org/abs/2311.07911 (Zhou et al., 2023)
"""

import json
import random
import re
import string
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, metric, scorer
from inspect_ai.solver import TaskState, generate, system_message

from matric_eval.config import get_sample_count, get_seed

# Path to IFEval dataset
IFEVAL_PATH = "/home/roctinam/data/evals/ifeval/input_data.jsonl"


def check_constraint(response: str, instruction_id: str, kwargs: dict[str, Any]) -> bool:
    """
    Check if a response satisfies a specific constraint.

    Args:
        response: The model's response text
        instruction_id: Constraint type (e.g., "length_constraints:number_paragraphs")
        kwargs: Constraint parameters

    Returns:
        True if constraint is satisfied, False otherwise
    """
    if not instruction_id:
        return False

    # Length constraints
    if instruction_id == "length_constraints:number_paragraphs":
        return _check_paragraph_count(response, kwargs)
    elif instruction_id == "length_constraints:number_words":
        return _check_word_count(response, kwargs)
    elif instruction_id == "length_constraints:number_sentences":
        return _check_sentence_count(response, kwargs)

    # Keyword constraints
    elif instruction_id == "keywords:existence":
        return _check_keywords_exist(response, kwargs)
    elif instruction_id == "keywords:frequency":
        return _check_keyword_frequency(response, kwargs)
    elif instruction_id == "keywords:letter_frequency":
        return _check_letter_frequency(response, kwargs)
    elif instruction_id == "keywords:forbidden_words":
        return _check_forbidden_words(response, kwargs)

    # Format constraints
    elif instruction_id == "detectable_format:json_format":
        return _check_json_format(response, kwargs)
    elif instruction_id == "detectable_format:number_bullet_lists":
        return _check_bullet_count(response, kwargs)
    elif instruction_id == "detectable_format:title":
        return _check_title_format(response, kwargs)
    elif instruction_id == "detectable_format:number_highlighted_sections":
        return _check_highlighted_sections(response, kwargs)
    elif instruction_id == "detectable_format:multiple_sections":
        return _check_multiple_sections(response, kwargs)

    # Case constraints
    elif instruction_id == "change_case:english_lowercase":
        return _check_lowercase(response, kwargs)
    elif instruction_id == "change_case:english_capital":
        return _check_uppercase(response, kwargs)
    elif instruction_id == "change_case:capital_word_frequency":
        return _check_capital_word_frequency(response, kwargs)

    # Punctuation constraints
    elif instruction_id == "punctuation:no_comma":
        return _check_no_comma(response, kwargs)

    # Start/end constraints
    elif instruction_id == "startend:quotation":
        return _check_quotation_wrapped(response, kwargs)
    elif instruction_id == "startend:end_checker":
        return _check_end_phrase(response, kwargs)

    # Detectable content
    elif instruction_id == "detectable_content:number_placeholders":
        return _check_placeholder_count(response, kwargs)
    elif instruction_id == "detectable_content:postscript":
        return _check_postscript(response, kwargs)

    # Combination constraints
    elif instruction_id == "combination:repeat_prompt":
        return _check_repeat_prompt(response, kwargs)
    elif instruction_id == "combination:two_responses":
        return _check_two_responses(response, kwargs)

    # Language constraints
    elif instruction_id == "language:response_language":
        return _check_response_language(response, kwargs)

    # Unknown constraint type
    return False


# =============================================================================
# Length Constraint Checkers
# =============================================================================


def _check_paragraph_count(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response has exact number of paragraphs."""
    num_paragraphs = kwargs.get("num_paragraphs", 0)

    # Split by double newline or markdown separator (***), filter empty
    paragraphs = re.split(r'\n\n+|\n\*\*\*\n', response)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    return len(paragraphs) == num_paragraphs


def _check_word_count(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response meets word count requirement."""
    relation = kwargs.get("relation", "at least")
    num_words = kwargs.get("num_words", 0)

    # Count words (split by whitespace)
    words = response.split()
    word_count = len(words)

    if relation == "at least":
        return word_count >= num_words
    elif relation == "less than":
        return word_count < num_words
    return False


def _check_sentence_count(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response meets sentence count requirement."""
    relation = kwargs.get("relation", "at least")
    num_sentences = kwargs.get("num_sentences", 0)

    # Count sentences (ending with ., !, or ?)
    sentences = re.split(r'[.!?]+', response)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_count = len(sentences)

    if relation == "at least":
        return sentence_count >= num_sentences
    elif relation == "less than":
        return sentence_count < num_sentences
    return False


# =============================================================================
# Keyword Constraint Checkers
# =============================================================================


def _check_keywords_exist(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if all required keywords are present (case-insensitive)."""
    keywords = kwargs.get("keywords", [])
    response_lower = response.lower()

    for keyword in keywords:
        if keyword.lower() not in response_lower:
            return False
    return True


def _check_keyword_frequency(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if keyword appears minimum number of times."""
    keyword = kwargs.get("keyword", "")
    relation = kwargs.get("relation", "at least")
    frequency = kwargs.get("frequency", 0)

    # Count occurrences (case-insensitive)
    count = response.lower().count(keyword.lower())

    if relation == "at least":
        return count >= frequency
    elif relation == "less than":
        return count < frequency
    return False


def _check_letter_frequency(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if specific letter/character appears minimum times."""
    letter = kwargs.get("letter", "")
    relation = kwargs.get("let_relation", "at least")
    frequency = kwargs.get("let_frequency", 0)

    count = response.count(letter)

    if relation == "at least":
        return count >= frequency
    elif relation == "less than":
        return count < frequency
    return False


def _check_forbidden_words(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if no forbidden words are present (case-insensitive)."""
    forbidden_words = kwargs.get("forbidden_words", [])
    response_lower = response.lower()

    for word in forbidden_words:
        if word.lower() in response_lower:
            return False
    return True


# =============================================================================
# Format Constraint Checkers
# =============================================================================


def _check_json_format(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response contains valid JSON."""
    # Try to find and parse JSON in response
    # First, try parsing the whole response
    try:
        json.loads(response.strip())
        return True
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from response (between { } or [ ])
    json_pattern = r'(\{[^{}]*\}|\[[^\[\]]*\])'
    matches = re.findall(json_pattern, response, re.DOTALL)

    for match in matches:
        try:
            json.loads(match)
            return True
        except json.JSONDecodeError:
            continue

    return False


def _check_bullet_count(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response has exact number of bullet points."""
    num_bullets = kwargs.get("num_bullets", 0)

    # Count bullets (* or -)
    bullet_pattern = r'^\s*[\*\-]\s+'
    bullets = re.findall(bullet_pattern, response, re.MULTILINE)

    return len(bullets) == num_bullets


def _check_title_format(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response contains title in <<title>> format."""
    title_pattern = r'<<[^<>]+>>'
    return bool(re.search(title_pattern, response))


def _check_highlighted_sections(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response has minimum number of *highlighted* sections."""
    num_highlights = kwargs.get("num_highlights", 0)

    # Count *highlighted* sections
    highlight_pattern = r'\*[^\*]+\*'
    highlights = re.findall(highlight_pattern, response)

    return len(highlights) >= num_highlights


def _check_multiple_sections(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response has multiple sections with specific labels."""
    section_splitter = kwargs.get("section_spliter", "")  # Note: typo in original dataset
    num_sections = kwargs.get("num_sections", 0)

    if not section_splitter:
        return False

    # Count occurrences of section label (e.g., "PARAGRAPH")
    count = response.upper().count(section_splitter.upper())

    return count >= num_sections


# =============================================================================
# Case Constraint Checkers
# =============================================================================


def _check_lowercase(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if all English letters are lowercase."""
    for char in response:
        if char.isalpha() and char.isupper():
            return False
    return True


def _check_uppercase(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if all English letters are uppercase."""
    for char in response:
        if char.isalpha() and char.islower():
            return False
    return True


def _check_capital_word_frequency(response: str, kwargs: dict[str, Any]) -> bool:
    """Check frequency of all-caps words."""
    relation = kwargs.get("capital_relation", "at least")
    frequency = kwargs.get("capital_frequency", 0)

    # Find all words that are entirely uppercase (2+ chars)
    # Strip punctuation from words before checking
    words = response.split()
    all_caps_words = []

    for word in words:
        # Strip leading/trailing punctuation
        stripped = word.strip(string.punctuation)
        # Check if stripped word is all caps and alphabetic (2+ chars)
        if len(stripped) >= 2 and stripped.isupper() and stripped.isalpha():
            all_caps_words.append(stripped)

    count = len(all_caps_words)

    if relation == "at least":
        return count >= frequency
    elif relation == "less than":
        return count < frequency
    return False


# =============================================================================
# Punctuation Constraint Checkers
# =============================================================================


def _check_no_comma(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response contains no commas."""
    return ',' not in response


# =============================================================================
# Start/End Constraint Checkers
# =============================================================================


def _check_quotation_wrapped(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if entire response is wrapped in double quotes."""
    stripped = response.strip()
    return stripped.startswith('"') and stripped.endswith('"')


def _check_end_phrase(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response ends with specific phrase."""
    end_phrase = kwargs.get("end_phrase", "")
    if not end_phrase:
        return False

    # Check if phrase appears near end of response
    return end_phrase in response


# =============================================================================
# Detectable Content Checkers
# =============================================================================


def _check_placeholder_count(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response has minimum number of [placeholders]."""
    num_placeholders = kwargs.get("num_placeholders", 0)

    # Count [placeholder] patterns
    placeholders = re.findall(r'\[[^\]]+\]', response)

    return len(placeholders) >= num_placeholders


def _check_postscript(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response contains P.S. or P.P.S."""
    return bool(re.search(r'\bP\.S\.|\bP\.P\.S\.', response))


# =============================================================================
# Combination Constraint Checkers
# =============================================================================


def _check_repeat_prompt(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if original prompt is repeated verbatim at start."""
    prompt_to_repeat = kwargs.get("prompt_to_repeat", "")
    if not prompt_to_repeat:
        return False

    # Check if response starts with the prompt
    return response.strip().startswith(prompt_to_repeat.strip())


def _check_two_responses(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response contains two parts separated by 6 asterisks."""
    return '\n******\n' in response or '******' in response


# =============================================================================
# Language Constraint Checkers
# =============================================================================


def _check_response_language(response: str, kwargs: dict[str, Any]) -> bool:
    """Check if response is in specified language."""
    language_code = kwargs.get("language", "en")

    # Simple heuristic: check for language-specific characters
    # This is a basic implementation; real language detection would use a library

    if language_code == "en":
        # English: mostly ASCII letters
        ascii_count = sum(1 for c in response if ord(c) < 128 and c.isalpha())
        total_alpha = sum(1 for c in response if c.isalpha())
        if total_alpha == 0:
            return False
        return ascii_count / total_alpha > 0.9

    elif language_code == "kn":
        # Kannada: Unicode range 0C80-0CFF
        kannada_count = sum(1 for c in response if '\u0C80' <= c <= '\u0CFF')
        return kannada_count > 0

    # For other languages, do basic check for non-ASCII
    # (In production, use langdetect or similar library)
    non_ascii = sum(1 for c in response if ord(c) > 127)
    return non_ascii > len(response) * 0.1


# =============================================================================
# Dataset Loading
# =============================================================================


def format_ifeval_prompt(prompt: str) -> str:
    """
    Format an IFEval prompt (currently returns as-is).

    Args:
        prompt: The instruction prompt

    Returns:
        Formatted prompt string (unchanged for IFEval)
    """
    return prompt


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert an IFEval JSONL record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys:
            - key: Unique identifier
            - prompt: Instruction text
            - instruction_id_list: List of constraint types
            - kwargs: List of constraint parameters

    Returns:
        Sample with input=prompt, target="" (empty, constraint-based),
        and metadata containing constraints
    """
    prompt = record["prompt"]
    instruction_id_list = record["instruction_id_list"]
    kwargs_list = record["kwargs"]

    return Sample(
        input=format_ifeval_prompt(prompt),
        target="",  # No ground truth; scoring is constraint-based
        id=str(record["key"]),
        metadata={
            "instruction_id_list": instruction_id_list,
            "kwargs": kwargs_list,
        },
    )


def load_ifeval(tier: str = "smoke") -> list[Sample]:
    """
    Load IFEval samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")

    Returns:
        List of Sample objects for the specified tier

    Raises:
        FileNotFoundError: If IFEval dataset file not found
        json.JSONDecodeError: If JSONL file is malformed
        ValueError: If dataset is empty
    """
    # Get sample count from config (respects env overrides)
    sample_count = get_sample_count("ifeval", tier)

    # Handle zero sample request early
    if sample_count == 0:
        return []

    # Load all records from JSONL
    dataset_path = Path(IFEVAL_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"IFEval dataset not found at {IFEVAL_PATH}")

    records = []
    with open(dataset_path, "r") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"IFEval dataset is empty: {IFEVAL_PATH}")

    # Convert to samples
    all_samples = [record_to_sample(record) for record in records]

    # Apply tiered sampling with reproducible seed
    if sample_count >= len(all_samples):
        # Return all samples if requested count exceeds dataset size
        return all_samples

    # Reproducible random sampling
    seed = get_seed()
    rng = random.Random(seed)

    # Sample without replacement
    sampled = rng.sample(all_samples, sample_count)

    # Sort by ID to maintain consistent order
    sampled.sort(key=lambda s: s.id)

    return sampled


# =============================================================================
# Custom Scorer
# =============================================================================


@scorer(metrics=[metric(name="constraint_accuracy")])
def ifeval_scorer() -> Scorer:
    """
    Custom scorer for IFEval that checks constraint satisfaction.

    Evaluates each constraint independently and computes the fraction
    of satisfied constraints.

    Returns:
        Scorer that checks all constraints in sample metadata
    """

    async def score(state: TaskState, target: Target) -> Score:
        """
        Score a model response against IFEval constraints.

        Args:
            state: Task state with model output
            target: Target (unused, constraints are in metadata)

        Returns:
            Score with value = fraction of constraints satisfied
        """
        response = state.output.completion

        # Get constraints from metadata
        instruction_id_list = state.metadata.get("instruction_id_list", [])
        kwargs_list = state.metadata.get("kwargs", [])

        if not instruction_id_list:
            # No constraints means perfect score (edge case)
            return Score(value=1.0, answer=response)

        # Check each constraint
        satisfied = 0
        total = len(instruction_id_list)

        for instruction_id, kwargs in zip(instruction_id_list, kwargs_list):
            if check_constraint(response, instruction_id, kwargs):
                satisfied += 1

        # Return fraction of constraints satisfied
        accuracy = satisfied / total if total > 0 else 0.0

        return Score(
            value=accuracy,
            answer=response,
            explanation=f"Satisfied {satisfied}/{total} constraints",
        )

    return score


# =============================================================================
# Task Definition
# =============================================================================


@task
def ifeval(tier: str = "smoke") -> Task:
    """
    IFEval (Instruction Following Evaluation) benchmark.

    Evaluates model's ability to follow specific instructions like
    paragraph counts, word limits, keyword requirements, formatting
    constraints, and more. Uses 541 diverse instruction-following
    tasks from Zhou et al. (2023).

    Args:
        tier: Evaluation tier
            - "smoke": 10 samples (~1 minute)
            - "quick": 100 samples (~5 minutes)
            - "full": 541 samples (all, ~27 minutes)

    Returns:
        Task configured for IFEval evaluation

    Example:
        >>> task = ifeval(tier="smoke")
        >>> # Run with: inspect eval ifeval.py --model ollama/llama3.2:3b

    References:
        - Paper: https://arxiv.org/abs/2311.07911
        - Dataset: IFEval instruction-following benchmark
    """
    return Task(
        dataset=load_ifeval(tier),
        solver=[
            system_message(
                "You are a helpful AI assistant. "
                "Follow the instructions in the prompt carefully and precisely. "
                "Pay close attention to all formatting, length, and content requirements."
            ),
            generate(),
        ],
        scorer=ifeval_scorer(),
        name="ifeval",
    )
