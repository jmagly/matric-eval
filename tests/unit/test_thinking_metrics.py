"""
Tests for thinking model metrics analysis (matric_eval.analysis.thinking_metrics).

Covers:
- ThinkingMetrics dataclass structure
- Pattern counting (backtracks, conclusions, questions)
- Metrics extraction from eval samples
- Aggregate metrics calculation
- Edge cases (empty reasoning, missing data)
"""

import pytest
from dataclasses import asdict

from matric_eval.analysis.thinking_metrics import (
    ThinkingMetrics,
    ThinkingAggregates,
    extract_thinking_metrics,
    aggregate_metrics,
    count_patterns,
    BACKTRACK_PATTERNS,
    CONCLUSION_PATTERNS,
)


@pytest.mark.unit
class TestThinkingMetrics:
    """Tests for ThinkingMetrics dataclass."""

    def test_metrics_initialization(self) -> None:
        """Should initialize ThinkingMetrics with all required fields."""
        metrics = ThinkingMetrics(
            reasoning_chars=34275,
            reasoning_tokens=8568,  # ~chars / 4
            text_chars=4052,
            text_tokens=1013,
            reasoning_cycles=3,
            backtrack_count=18,
            conclusion_count=42,
            question_count=5,
        )

        assert metrics.reasoning_chars == 34275
        assert metrics.reasoning_tokens == 8568
        assert metrics.text_chars == 4052
        assert metrics.text_tokens == 1013
        assert metrics.reasoning_cycles == 3
        assert metrics.backtrack_count == 18
        assert metrics.conclusion_count == 42
        assert metrics.question_count == 5
        assert metrics.total_time is None
        assert metrics.working_time is None

    def test_metrics_with_timing(self) -> None:
        """Should support optional timing metrics."""
        metrics = ThinkingMetrics(
            reasoning_chars=1000,
            reasoning_tokens=250,
            text_chars=500,
            text_tokens=125,
            reasoning_cycles=1,
            backtrack_count=2,
            conclusion_count=3,
            question_count=1,
            total_time=15.5,
            working_time=12.3,
        )

        assert metrics.total_time == 15.5
        assert metrics.working_time == 12.3

    def test_metrics_serializable(self) -> None:
        """Should be serializable to dict for JSON export."""
        metrics = ThinkingMetrics(
            reasoning_chars=1000,
            reasoning_tokens=250,
            text_chars=500,
            text_tokens=125,
            reasoning_cycles=1,
            backtrack_count=2,
            conclusion_count=3,
            question_count=1,
        )

        data = asdict(metrics)
        assert isinstance(data, dict)
        assert data["reasoning_chars"] == 1000
        assert data["backtrack_count"] == 2


@pytest.mark.unit
class TestPatternCounting:
    """Tests for count_patterns() function."""

    def test_count_single_pattern(self) -> None:
        """Should count single occurrence of pattern."""
        text = "Wait, let me reconsider this approach."
        count = count_patterns(text, ["Wait,"])
        assert count == 1

    def test_count_multiple_occurrences(self) -> None:
        """Should count multiple occurrences of same pattern."""
        text = "Wait, this doesn't work. Wait, let me try again. Wait, now I see it."
        count = count_patterns(text, ["Wait,"])
        assert count == 3

    def test_count_multiple_patterns(self) -> None:
        """Should count occurrences across multiple patterns."""
        text = "Wait, this is wrong. Actually, let me reconsider. Hmm, interesting."
        count = count_patterns(text, ["Wait,", "Actually,", "Hmm,"])
        assert count == 3

    def test_backtrack_patterns(self) -> None:
        """Should count all backtrack patterns from constants."""
        text = "Wait, this is wrong. Actually, let me reconsider. Hmm, interesting. But wait, there's more."
        count = count_patterns(text, BACKTRACK_PATTERNS)
        assert count == 4

    def test_conclusion_patterns(self) -> None:
        """Should count all conclusion patterns from constants."""
        text = "So the answer is 42. Therefore, we can conclude. Thus, the result is correct."
        count = count_patterns(text, CONCLUSION_PATTERNS)
        assert count == 3

    def test_case_sensitive(self) -> None:
        """Should be case-sensitive in pattern matching."""
        text = "wait, this is lowercase. Wait, this is uppercase."
        count = count_patterns(text, ["Wait,"])
        assert count == 1

    def test_empty_text(self) -> None:
        """Should return 0 for empty text."""
        count = count_patterns("", ["Wait,", "Actually,"])
        assert count == 0

    def test_empty_patterns(self) -> None:
        """Should return 0 for empty pattern list."""
        count = count_patterns("Some text here", [])
        assert count == 0


@pytest.mark.unit
class TestExtractThinkingMetrics:
    """Tests for extract_thinking_metrics() function."""

    def test_extract_from_sample_with_reasoning(self) -> None:
        """Should extract metrics from sample with thinking tags."""
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "Wait, let me think about this. So the answer is clear. Actually, wait. Therefore, we conclude.",
                        },
                        {
                            "type": "text",
                            "text": "The answer is 42.",
                        },
                    ],
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)

        assert metrics.reasoning_chars > 0
        assert metrics.text_chars > 0
        assert metrics.backtrack_count >= 2  # "Wait," and "Actually,"
        assert metrics.conclusion_count >= 2  # "So the" and "Therefore,"

    def test_extract_question_count(self) -> None:
        """Should count questions in reasoning text."""
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "What if we try this? Is this correct? Maybe another approach?",
                        },
                        {
                            "type": "text",
                            "text": "Yes, it works.",
                        },
                    ],
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)
        assert metrics.question_count == 3

    def test_extract_token_estimation(self) -> None:
        """Should estimate tokens as chars / 4."""
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "x" * 1000,  # 1000 chars
                        },
                        {
                            "type": "text",
                            "text": "y" * 400,  # 400 chars
                        },
                    ],
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)
        assert metrics.reasoning_chars == 1000
        assert metrics.reasoning_tokens == 250  # 1000 / 4
        assert metrics.text_chars == 400
        assert metrics.text_tokens == 100  # 400 / 4

    def test_extract_from_realistic_sample(self) -> None:
        """Should handle realistic sample from investigation."""
        # Based on actual data: 34,275 chars with "Wait," ×18, "So the" ×42
        reasoning_text = "Wait, " * 18 + "So the " * 42 + "x" * 34000
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": reasoning_text,
                        },
                        {
                            "type": "text",
                            "text": "The final answer is correct.",
                        },
                    ],
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)
        assert metrics.backtrack_count >= 18
        assert metrics.conclusion_count >= 42
        assert metrics.reasoning_chars > 34000

    def test_extract_no_thinking_content(self) -> None:
        """Should handle samples without thinking content."""
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Regular response without thinking.",
                        },
                    ],
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)
        assert metrics.reasoning_chars == 0
        assert metrics.reasoning_tokens == 0
        assert metrics.text_chars > 0
        assert metrics.backtrack_count == 0
        assert metrics.conclusion_count == 0

    def test_extract_multiple_thinking_blocks(self) -> None:
        """Should aggregate metrics from multiple thinking blocks."""
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "Wait, let me think. " * 5,
                        },
                        {
                            "type": "text",
                            "text": "Intermediate answer.",
                        },
                        {
                            "type": "thinking",
                            "thinking": "Actually, reconsider. " * 3,
                        },
                        {
                            "type": "text",
                            "text": "Final answer.",
                        },
                    ],
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)
        assert metrics.backtrack_count >= 8  # 5 "Wait," + 3 "Actually,"
        assert metrics.reasoning_chars > 0

    def test_extract_empty_sample(self) -> None:
        """Should handle empty sample gracefully."""
        sample = {"messages": []}

        metrics = extract_thinking_metrics(sample)
        assert metrics.reasoning_chars == 0
        assert metrics.text_chars == 0
        assert metrics.backtrack_count == 0

    def test_extract_malformed_sample(self) -> None:
        """Should handle malformed sample structure."""
        sample = {"messages": [{"role": "user", "content": "Just a question"}]}

        metrics = extract_thinking_metrics(sample)
        assert metrics.reasoning_chars == 0
        assert metrics.text_chars == 0


@pytest.mark.unit
class TestAggregateMetrics:
    """Tests for aggregate_metrics() function."""

    def test_aggregate_single_sample(self) -> None:
        """Should aggregate metrics from single sample."""
        metrics_list = [
            ThinkingMetrics(
                reasoning_chars=1000,
                reasoning_tokens=250,
                text_chars=500,
                text_tokens=125,
                reasoning_cycles=2,
                backtrack_count=5,
                conclusion_count=10,
                question_count=3,
                total_time=10.0,
                working_time=8.0,
            )
        ]

        agg = aggregate_metrics(metrics_list)

        assert agg.sample_count == 1
        assert agg.avg_reasoning_chars == 1000.0
        assert agg.avg_cycles_per_sample == 2.0
        assert agg.total_reasoning_time == 8.0
        assert agg.reasoning_to_text_ratio == 2.0  # 1000 / 500

    def test_aggregate_multiple_samples(self) -> None:
        """Should calculate averages across multiple samples."""
        metrics_list = [
            ThinkingMetrics(
                reasoning_chars=1000,
                reasoning_tokens=250,
                text_chars=500,
                text_tokens=125,
                reasoning_cycles=2,
                backtrack_count=5,
                conclusion_count=10,
                question_count=3,
                total_time=10.0,
                working_time=8.0,
            ),
            ThinkingMetrics(
                reasoning_chars=2000,
                reasoning_tokens=500,
                text_chars=1000,
                text_tokens=250,
                reasoning_cycles=4,
                backtrack_count=10,
                conclusion_count=20,
                question_count=6,
                total_time=20.0,
                working_time=16.0,
            ),
        ]

        agg = aggregate_metrics(metrics_list)

        assert agg.sample_count == 2
        assert agg.avg_reasoning_chars == 1500.0  # (1000 + 2000) / 2
        assert agg.avg_cycles_per_sample == 3.0  # (2 + 4) / 2
        assert agg.total_reasoning_time == 24.0  # 8.0 + 16.0
        assert agg.reasoning_to_text_ratio == pytest.approx(2.0)  # (1000/500 + 2000/1000) / 2 = (2 + 2) / 2

    def test_aggregate_with_zero_text(self) -> None:
        """Should handle samples with zero text chars."""
        metrics_list = [
            ThinkingMetrics(
                reasoning_chars=1000,
                reasoning_tokens=250,
                text_chars=0,
                text_tokens=0,
                reasoning_cycles=1,
                backtrack_count=2,
                conclusion_count=3,
                question_count=1,
            )
        ]

        agg = aggregate_metrics(metrics_list)

        assert agg.sample_count == 1
        assert agg.reasoning_to_text_ratio == 0.0  # Handle division by zero

    def test_aggregate_without_timing(self) -> None:
        """Should handle samples without timing data."""
        metrics_list = [
            ThinkingMetrics(
                reasoning_chars=1000,
                reasoning_tokens=250,
                text_chars=500,
                text_tokens=125,
                reasoning_cycles=1,
                backtrack_count=2,
                conclusion_count=3,
                question_count=1,
            )
        ]

        agg = aggregate_metrics(metrics_list)

        assert agg.total_reasoning_time == 0.0

    def test_aggregate_empty_list(self) -> None:
        """Should handle empty metrics list."""
        agg = aggregate_metrics([])

        assert agg.sample_count == 0
        assert agg.avg_reasoning_chars == 0.0
        assert agg.avg_cycles_per_sample == 0.0
        assert agg.total_reasoning_time == 0.0
        assert agg.reasoning_to_text_ratio == 0.0


@pytest.mark.unit
class TestThinkingAggregates:
    """Tests for ThinkingAggregates dataclass."""

    def test_aggregates_initialization(self) -> None:
        """Should initialize ThinkingAggregates with all fields."""
        agg = ThinkingAggregates(
            sample_count=10,
            avg_reasoning_chars=5000.0,
            avg_cycles_per_sample=2.5,
            total_reasoning_time=120.0,
            reasoning_to_text_ratio=3.2,
        )

        assert agg.sample_count == 10
        assert agg.avg_reasoning_chars == 5000.0
        assert agg.avg_cycles_per_sample == 2.5
        assert agg.total_reasoning_time == 120.0
        assert agg.reasoning_to_text_ratio == 3.2

    def test_aggregates_serializable(self) -> None:
        """Should be serializable to dict for JSON export."""
        agg = ThinkingAggregates(
            sample_count=5,
            avg_reasoning_chars=1000.0,
            avg_cycles_per_sample=1.5,
            total_reasoning_time=50.0,
            reasoning_to_text_ratio=2.0,
        )

        data = asdict(agg)
        assert isinstance(data, dict)
        assert data["sample_count"] == 5
        assert data["total_reasoning_time"] == 50.0


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_unicode_patterns(self) -> None:
        """Should handle Unicode characters in text."""
        text = "Wait, let me think 🤔. So the answer is correct ✓."
        count = count_patterns(text, ["Wait,", "So the"])
        assert count == 2

    def test_patterns_at_boundaries(self) -> None:
        """Should count patterns at text boundaries."""
        text = "Wait, this is at start"
        count = count_patterns(text, ["Wait,"])
        assert count == 1

        text = "This ends with So the"
        count = count_patterns(text, ["So the"])
        assert count == 1

    def test_overlapping_patterns(self) -> None:
        """Should not double-count overlapping patterns."""
        text = "Wait, wait, this is tricky."
        # Only "Wait," (capital) should match, not "wait,"
        count = count_patterns(text, ["Wait,"])
        assert count == 1

    def test_very_large_reasoning_text(self) -> None:
        """Should handle very large reasoning blocks efficiently."""
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "x" * 100000,  # 100K chars
                        },
                        {
                            "type": "text",
                            "text": "Answer.",
                        },
                    ],
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)
        assert metrics.reasoning_chars == 100000
        assert metrics.reasoning_tokens == 25000  # 100000 / 4

    def test_extract_from_string_content(self) -> None:
        """Should handle string content format (non-structured)."""
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": "Simple string response without thinking blocks.",
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)
        assert metrics.reasoning_chars == 0
        assert metrics.text_chars > 0
        assert metrics.backtrack_count == 0

    def test_extract_from_non_dict_blocks(self) -> None:
        """Should skip non-dict blocks in content list."""
        sample = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        "string item",  # Non-dict block
                        {"type": "text", "text": "Actual text."},
                    ],
                }
            ]
        }

        metrics = extract_thinking_metrics(sample)
        assert metrics.text_chars > 0
