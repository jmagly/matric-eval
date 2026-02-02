"""
Thinking model metrics extraction and analysis.

Captures and analyzes metrics from thinking model evaluations, including:
- Reasoning vs text content sizes
- Self-correction patterns (backtracks, conclusions)
- Reasoning cycles and question counts
- Timing metrics (when available)

Example:
    >>> sample = {"messages": [...]}  # From eval log
    >>> metrics = extract_thinking_metrics(sample)
    >>> print(f"Reasoning: {metrics.reasoning_chars} chars")
    >>> print(f"Backtracks: {metrics.backtrack_count}")
"""

from dataclasses import dataclass
from typing import Any, Optional


# Pattern lists for detecting reasoning behaviors
BACKTRACK_PATTERNS = [
    "Wait,",
    "Actually,",
    "Hmm,",
    "But wait",
    "Let me think",
    "Let me reconsider",
]

CONCLUSION_PATTERNS = [
    "So the",
    "Therefore,",
    "Thus,",
    "Hence,",
    "In conclusion",
    "So,",
]


@dataclass
class ThinkingMetrics:
    """Metrics captured from thinking model output."""

    # Size metrics
    reasoning_chars: int
    reasoning_tokens: int  # Estimated: chars / 4
    text_chars: int
    text_tokens: int

    # Pattern metrics
    reasoning_cycles: int  # Count of self-correction patterns
    backtrack_count: int  # "Wait,", "Actually,", "Hmm," etc.
    conclusion_count: int  # "So the", "Therefore,", "Thus," etc.
    question_count: int  # "?" in reasoning

    # Timing metrics (optional, from eval log)
    total_time: Optional[float] = None
    working_time: Optional[float] = None


@dataclass
class ThinkingAggregates:
    """Aggregated metrics across multiple samples."""

    sample_count: int
    avg_reasoning_chars: float
    avg_cycles_per_sample: float
    total_reasoning_time: float
    reasoning_to_text_ratio: float


def count_patterns(text: str, patterns: list[str]) -> int:
    """
    Count occurrences of patterns in text.

    Args:
        text: Text to search in
        patterns: List of pattern strings to count

    Returns:
        Total count of all pattern occurrences

    Example:
        >>> count_patterns("Wait, let me think. Actually, no.", ["Wait,", "Actually,"])
        2
    """
    if not text or not patterns:
        return 0

    total_count = 0
    for pattern in patterns:
        total_count += text.count(pattern)

    return total_count


def extract_thinking_metrics(sample: dict[str, Any]) -> ThinkingMetrics:
    """
    Extract thinking metrics from an eval sample.

    Parses the sample's message structure to identify thinking and text blocks,
    then calculates size metrics and pattern counts.

    Args:
        sample: Eval sample dict with 'messages' key containing message list

    Returns:
        ThinkingMetrics with extracted data

    Example:
        >>> sample = {
        ...     "messages": [{
        ...         "role": "assistant",
        ...         "content": [
        ...             {"type": "thinking", "thinking": "Wait, let me think..."},
        ...             {"type": "text", "text": "The answer is 42."}
        ...         ]
        ...     }]
        ... }
        >>> metrics = extract_thinking_metrics(sample)
        >>> metrics.backtrack_count
        1
    """
    reasoning_text = ""
    text_output = ""

    # Parse messages to extract thinking and text blocks
    messages = sample.get("messages", [])

    for message in messages:
        if message.get("role") != "assistant":
            continue

        content = message.get("content", [])

        # Handle both list and string content
        if isinstance(content, str):
            # Simple text response without thinking
            text_output += content
            continue

        # Process content blocks
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "thinking":
                    reasoning_text += block.get("thinking", "")
                elif block.get("type") == "text":
                    text_output += block.get("text", "")

    # Calculate size metrics
    reasoning_chars = len(reasoning_text)
    reasoning_tokens = reasoning_chars // 4  # Rough estimate
    text_chars = len(text_output)
    text_tokens = text_chars // 4

    # Count patterns
    backtrack_count = count_patterns(reasoning_text, BACKTRACK_PATTERNS)
    conclusion_count = count_patterns(reasoning_text, CONCLUSION_PATTERNS)
    question_count = reasoning_text.count("?")

    # Calculate reasoning cycles (sum of major self-correction indicators)
    reasoning_cycles = backtrack_count

    return ThinkingMetrics(
        reasoning_chars=reasoning_chars,
        reasoning_tokens=reasoning_tokens,
        text_chars=text_chars,
        text_tokens=text_tokens,
        reasoning_cycles=reasoning_cycles,
        backtrack_count=backtrack_count,
        conclusion_count=conclusion_count,
        question_count=question_count,
    )


def aggregate_metrics(metrics: list[ThinkingMetrics]) -> ThinkingAggregates:
    """
    Aggregate metrics from multiple samples.

    Args:
        metrics: List of ThinkingMetrics from individual samples

    Returns:
        ThinkingAggregates with averaged/summed values

    Example:
        >>> metrics_list = [
        ...     ThinkingMetrics(reasoning_chars=1000, reasoning_tokens=250, ...),
        ...     ThinkingMetrics(reasoning_chars=2000, reasoning_tokens=500, ...),
        ... ]
        >>> agg = aggregate_metrics(metrics_list)
        >>> agg.avg_reasoning_chars
        1500.0
    """
    if not metrics:
        return ThinkingAggregates(
            sample_count=0,
            avg_reasoning_chars=0.0,
            avg_cycles_per_sample=0.0,
            total_reasoning_time=0.0,
            reasoning_to_text_ratio=0.0,
        )

    sample_count = len(metrics)

    # Calculate averages
    total_reasoning_chars = sum(m.reasoning_chars for m in metrics)
    avg_reasoning_chars = total_reasoning_chars / sample_count

    total_cycles = sum(m.reasoning_cycles for m in metrics)
    avg_cycles_per_sample = total_cycles / sample_count

    # Sum timing data (only for samples with timing)
    total_reasoning_time = sum(
        m.working_time for m in metrics if m.working_time is not None
    )

    # Calculate reasoning to text ratio (average of individual ratios)
    ratios = []
    for m in metrics:
        if m.text_chars > 0:
            ratios.append(m.reasoning_chars / m.text_chars)
        else:
            ratios.append(0.0)

    reasoning_to_text_ratio = sum(ratios) / sample_count if ratios else 0.0

    return ThinkingAggregates(
        sample_count=sample_count,
        avg_reasoning_chars=avg_reasoning_chars,
        avg_cycles_per_sample=avg_cycles_per_sample,
        total_reasoning_time=total_reasoning_time,
        reasoning_to_text_ratio=reasoning_to_text_ratio,
    )
