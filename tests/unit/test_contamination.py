"""
Tests for contamination detection (matric_eval.contamination).

Covers:
- N-gram extraction and overlap computation
- Single sample contamination detection
- Batch contamination checking
- Contamination report generation
- Score adjustment based on contamination
"""

import pytest

from matric_eval.contamination.detector import (
    ContaminationEvidence,
    ContaminationReport,
    NgramDetector,
    _extract_ngrams,
    check_contamination,
)


# =============================================================================
# N-gram Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestNgramExtraction:
    """Tests for _extract_ngrams() function."""

    def test_extracts_ngrams(self) -> None:
        """Should extract word-level n-grams."""
        ngrams = _extract_ngrams("the quick brown fox jumps", 3)
        assert len(ngrams) == 3
        assert ("the", "quick", "brown") in ngrams
        assert ("quick", "brown", "fox") in ngrams

    def test_returns_empty_for_short_text(self) -> None:
        """Should return empty for text shorter than n."""
        ngrams = _extract_ngrams("short", 5)
        assert ngrams == []

    def test_normalizes_whitespace(self) -> None:
        """Should normalize multiple spaces."""
        ngrams = _extract_ngrams("the   quick   brown", 2)
        assert ("the", "quick") in ngrams

    def test_case_insensitive(self) -> None:
        """Should be case insensitive."""
        ngrams = _extract_ngrams("The Quick Brown", 3)
        assert ("the", "quick", "brown") in ngrams


# =============================================================================
# NgramDetector Tests
# =============================================================================


@pytest.mark.unit
class TestNgramDetector:
    """Tests for NgramDetector class."""

    def test_compute_overlap_identical(self) -> None:
        """Should return high overlap for identical texts."""
        detector = NgramDetector(n=3)
        text = "the quick brown fox jumps over the lazy dog and runs away fast"
        overlap = detector.compute_overlap(text, text)
        assert overlap == 1.0

    def test_compute_overlap_no_match(self) -> None:
        """Should return 0 overlap for completely different texts."""
        detector = NgramDetector(n=5)
        overlap = detector.compute_overlap(
            "alpha beta gamma delta epsilon zeta eta theta iota kappa",
            "one two three four five six seven eight nine ten",
        )
        assert overlap == 0.0

    def test_compute_overlap_partial(self) -> None:
        """Should compute partial overlap correctly."""
        detector = NgramDetector(n=3)
        text_a = "the quick brown fox jumps over the lazy dog"
        text_b = "the quick brown cat sleeps under the lazy dog"
        overlap = detector.compute_overlap(text_a, text_b)
        assert 0.0 < overlap < 1.0

    def test_compute_overlap_empty(self) -> None:
        """Should handle empty text."""
        detector = NgramDetector(n=5)
        assert detector.compute_overlap("", "some text here for testing") == 0.0
        assert detector.compute_overlap("some text here for testing", "") == 0.0

    def test_check_sample_exact_match(self) -> None:
        """Should detect exact match as high-severity contamination."""
        detector = NgramDetector(n=5)
        # Needs >50 chars to trigger exact match detection
        text = "def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2) " * 2
        evidence = detector.check_sample(text, text)
        assert evidence is not None
        assert evidence.type == "exact_match"
        assert evidence.severity == 1.0

    def test_check_sample_no_contamination(self) -> None:
        """Should return None for clean samples."""
        detector = NgramDetector(n=5, threshold=0.3)
        evidence = detector.check_sample(
            "my completely original answer to the problem using dynamic programming",
            "the standard solution using recursion with memoization and base cases",
        )
        assert evidence is None

    def test_check_sample_high_overlap(self) -> None:
        """Should detect high n-gram overlap."""
        detector = NgramDetector(n=3, threshold=0.3)
        base = "the standard implementation uses a dictionary to store cached results and returns the value"
        # Modify slightly
        output = "the standard implementation uses a dictionary to store cached results and returns the output"
        evidence = detector.check_sample(output, base)
        assert evidence is not None
        assert evidence.overlap_ratio > 0.3


# =============================================================================
# Batch Check Tests
# =============================================================================


@pytest.mark.unit
class TestBatchCheck:
    """Tests for batch contamination checking."""

    def test_check_batch_clean(self) -> None:
        """Should produce low contamination for clean outputs."""
        detector = NgramDetector(n=5, threshold=0.5)
        outputs = [
            "my unique approach to solving this particular problem",
            "another original solution with different methodology and structure",
            "a third independent answer using alternative techniques entirely",
        ]
        references = [
            "the canonical solution to problem one involves dynamic programming",
            "standard approach to problem two uses binary search algorithm",
            "expected answer for problem three requires graph traversal method",
        ]
        report = detector.check_batch(
            outputs, references, model="test_model", benchmark="test_bench"
        )
        assert report.contamination_score < 0.3
        assert report.samples_checked == 3

    def test_check_batch_contaminated(self) -> None:
        """Should produce high contamination for memorized outputs."""
        detector = NgramDetector(n=3, threshold=0.3)
        # Outputs that are very similar to references
        base = "the standard solution to this problem uses a hash map to track frequency of each element and then iterates through to find the maximum"
        outputs = [base, base, base]
        references = [base, base, base]
        report = detector.check_batch(
            outputs, references, model="memorizer", benchmark="humaneval"
        )
        assert report.contamination_score > 0.5
        assert report.samples_flagged > 0

    def test_check_batch_mismatched_lengths(self) -> None:
        """Should raise ValueError for mismatched lengths."""
        detector = NgramDetector()
        with pytest.raises(ValueError, match="same length"):
            detector.check_batch(["a"], ["b", "c"])

    def test_check_batch_empty(self) -> None:
        """Should handle empty batch."""
        detector = NgramDetector()
        report = detector.check_batch([], [])
        assert report.contamination_score == 0.0
        assert report.samples_checked == 0


# =============================================================================
# ContaminationReport Tests
# =============================================================================


@pytest.mark.unit
class TestContaminationReport:
    """Tests for ContaminationReport dataclass."""

    def test_recommendation_trustworthy(self) -> None:
        """Should recommend 'trustworthy' for low contamination."""
        report = ContaminationReport(model="m", benchmark="b", contamination_score=0.1)
        assert report.recommendation == "trustworthy"

    def test_recommendation_suspicious(self) -> None:
        """Should recommend 'suspicious' for moderate contamination."""
        report = ContaminationReport(model="m", benchmark="b", contamination_score=0.35)
        assert report.recommendation == "suspicious"

    def test_recommendation_likely_contaminated(self) -> None:
        """Should recommend 'likely_contaminated' for high contamination."""
        report = ContaminationReport(model="m", benchmark="b", contamination_score=0.7)
        assert report.recommendation == "likely_contaminated"

    def test_adjusted_score_clean(self) -> None:
        """Should not adjust score for clean models."""
        report = ContaminationReport(model="m", benchmark="b", contamination_score=0.1)
        assert report.adjusted_score(0.9) == 0.9

    def test_adjusted_score_suspicious(self) -> None:
        """Should reduce score by 10% for suspicious models."""
        report = ContaminationReport(model="m", benchmark="b", contamination_score=0.3)
        assert abs(report.adjusted_score(1.0) - 0.9) < 0.01

    def test_adjusted_score_contaminated(self) -> None:
        """Should reduce score by 30% for likely contaminated models."""
        report = ContaminationReport(model="m", benchmark="b", contamination_score=0.6)
        assert abs(report.adjusted_score(1.0) - 0.7) < 0.01

    def test_adjusted_score_heavily_contaminated(self) -> None:
        """Should reduce score by 50% for heavily contaminated models."""
        report = ContaminationReport(model="m", benchmark="b", contamination_score=0.9)
        assert abs(report.adjusted_score(1.0) - 0.5) < 0.01

    def test_to_dict(self) -> None:
        """Should serialize to dict."""
        report = ContaminationReport(
            model="test_model",
            benchmark="humaneval",
            contamination_score=0.3,
            confidence=0.8,
            samples_checked=50,
            samples_flagged=5,
            evidence=[
                ContaminationEvidence(
                    type="ngram_match",
                    details="High overlap",
                    severity=0.6,
                    sample_id="sample_1",
                    overlap_ratio=0.45,
                )
            ],
        )
        d = report.to_dict()
        assert d["model"] == "test_model"
        assert d["benchmark"] == "humaneval"
        assert d["recommendation"] == "suspicious"
        assert len(d["evidence"]) == 1
        assert d["evidence"][0]["overlap_ratio"] == 0.45


# =============================================================================
# Convenience Function Tests
# =============================================================================


@pytest.mark.unit
class TestCheckContamination:
    """Tests for check_contamination() convenience function."""

    def test_returns_report(self) -> None:
        """Should return a ContaminationReport."""
        report = check_contamination(
            outputs=["original answer"],
            references=["different reference"],
            model="test",
            benchmark="test",
        )
        assert isinstance(report, ContaminationReport)
        assert report.model == "test"
        assert report.benchmark == "test"
        assert report.samples_checked == 1

    def test_custom_ngram_size(self) -> None:
        """Should accept custom n-gram size."""
        report = check_contamination(
            outputs=["answer"],
            references=["answer"],
            n=3,
            threshold=0.5,
        )
        assert isinstance(report, ContaminationReport)
