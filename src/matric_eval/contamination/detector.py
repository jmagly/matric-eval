"""
Contamination detection via n-gram overlap analysis.

Compares model outputs against known benchmark solutions to detect
potential memorization of evaluation data.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContaminationEvidence:
    """Evidence of contamination for a single sample."""

    type: str  # "ngram_match", "exact_match", "high_overlap"
    details: str
    severity: float  # 0.0 - 1.0
    sample_id: Optional[str] = None
    overlap_ratio: float = 0.0


@dataclass
class ContaminationReport:
    """Contamination analysis report for a model/benchmark pair."""

    model: str
    benchmark: str
    contamination_score: float = 0.0  # 0.0 (clean) to 1.0 (contaminated)
    confidence: float = 0.0
    evidence: list[ContaminationEvidence] = field(default_factory=list)
    samples_checked: int = 0
    samples_flagged: int = 0

    @property
    def recommendation(self) -> str:
        """Get recommendation based on contamination score."""
        if self.contamination_score < 0.2:
            return "trustworthy"
        elif self.contamination_score < 0.5:
            return "suspicious"
        else:
            return "likely_contaminated"

    def adjusted_score(self, raw_score: float) -> float:
        """
        Adjust a benchmark score based on contamination likelihood.

        Args:
            raw_score: The raw benchmark score

        Returns:
            Adjusted score accounting for potential contamination
        """
        if self.contamination_score < 0.2:
            return raw_score
        elif self.contamination_score < 0.5:
            return raw_score * 0.9
        elif self.contamination_score < 0.8:
            return raw_score * 0.7
        else:
            return raw_score * 0.5

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "model": self.model,
            "benchmark": self.benchmark,
            "contamination_score": self.contamination_score,
            "confidence": self.confidence,
            "recommendation": self.recommendation,
            "samples_checked": self.samples_checked,
            "samples_flagged": self.samples_flagged,
            "evidence": [
                {
                    "type": e.type,
                    "details": e.details,
                    "severity": e.severity,
                    "sample_id": e.sample_id,
                    "overlap_ratio": e.overlap_ratio,
                }
                for e in self.evidence
            ],
        }


def _extract_ngrams(text: str, n: int) -> list[tuple[str, ...]]:
    """
    Extract character-level n-grams from text.

    Args:
        text: Input text
        n: N-gram size

    Returns:
        List of n-gram tuples
    """
    # Normalize: lowercase, collapse whitespace
    normalized = " ".join(text.lower().split())
    words = normalized.split()
    if len(words) < n:
        return []
    return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]


class NgramDetector:
    """
    Detects contamination via n-gram overlap between model outputs
    and known benchmark solutions.

    A high n-gram overlap suggests the model may have memorized the
    benchmark data rather than genuinely solving the problem.

    Args:
        n: N-gram size (default: 10). Larger values reduce false positives.
        threshold: Overlap threshold to flag as contaminated (default: 0.3).
            Fraction of output n-grams found in reference solutions.
    """

    def __init__(self, n: int = 10, threshold: float = 0.3):
        self.n = n
        self.threshold = threshold

    def compute_overlap(self, output: str, reference: str) -> float:
        """
        Compute n-gram overlap ratio between output and reference.

        Args:
            output: Model output text
            reference: Known reference/solution text

        Returns:
            Overlap ratio (0.0 - 1.0). Fraction of output n-grams
            found in the reference.
        """
        output_ngrams = _extract_ngrams(output, self.n)
        if not output_ngrams:
            return 0.0

        reference_ngrams = set(_extract_ngrams(reference, self.n))
        if not reference_ngrams:
            return 0.0

        matches = sum(1 for ng in output_ngrams if ng in reference_ngrams)
        return matches / len(output_ngrams)

    def check_sample(
        self,
        output: str,
        reference: str,
        sample_id: Optional[str] = None,
    ) -> Optional[ContaminationEvidence]:
        """
        Check a single sample for contamination.

        Args:
            output: Model's output for this sample
            reference: Known correct solution/answer
            sample_id: Optional identifier for the sample

        Returns:
            ContaminationEvidence if contamination detected, None otherwise
        """
        # Check for exact match first
        norm_output = " ".join(output.lower().split())
        norm_ref = " ".join(reference.lower().split())

        if norm_output == norm_ref and len(norm_output) > 50:
            return ContaminationEvidence(
                type="exact_match",
                details="Output exactly matches reference solution",
                severity=1.0,
                sample_id=sample_id,
                overlap_ratio=1.0,
            )

        # Check n-gram overlap
        overlap = self.compute_overlap(output, reference)

        if overlap >= self.threshold:
            severity = min(1.0, overlap / 0.8)  # Scale: threshold->0.8 maps to mild->severe
            return ContaminationEvidence(
                type="ngram_match" if overlap < 0.7 else "high_overlap",
                details=f"{self.n}-gram overlap: {overlap:.1%} (threshold: {self.threshold:.1%})",
                severity=severity,
                sample_id=sample_id,
                overlap_ratio=overlap,
            )

        return None

    def check_batch(
        self,
        outputs: list[str],
        references: list[str],
        sample_ids: Optional[list[str]] = None,
        model: str = "unknown",
        benchmark: str = "unknown",
    ) -> ContaminationReport:
        """
        Check a batch of samples for contamination.

        Args:
            outputs: List of model outputs
            references: List of reference solutions (same order)
            sample_ids: Optional list of sample identifiers
            model: Model name for the report
            benchmark: Benchmark name for the report

        Returns:
            ContaminationReport with aggregate contamination assessment
        """
        if len(outputs) != len(references):
            raise ValueError(
                f"Outputs ({len(outputs)}) and references ({len(references)}) must have same length"
            )

        if sample_ids is None:
            sample_ids = [str(i) for i in range(len(outputs))]

        evidence = []
        for output, reference, sid in zip(outputs, references, sample_ids):
            result = self.check_sample(output, reference, sid)
            if result is not None:
                evidence.append(result)

        # Compute aggregate contamination score
        samples_checked = len(outputs)
        samples_flagged = len(evidence)

        if samples_checked == 0:
            contamination_score = 0.0
        else:
            # Weight by severity
            total_severity = sum(e.severity for e in evidence)
            contamination_score = min(1.0, total_severity / max(1, samples_checked))

        # Confidence based on sample size
        confidence = min(1.0, samples_checked / 50)  # Full confidence at 50+ samples

        return ContaminationReport(
            model=model,
            benchmark=benchmark,
            contamination_score=contamination_score,
            confidence=confidence,
            evidence=evidence,
            samples_checked=samples_checked,
            samples_flagged=samples_flagged,
        )


def check_contamination(
    outputs: list[str],
    references: list[str],
    model: str = "unknown",
    benchmark: str = "unknown",
    n: int = 10,
    threshold: float = 0.3,
) -> ContaminationReport:
    """
    Convenience function to check for contamination.

    Args:
        outputs: List of model outputs
        references: List of reference solutions
        model: Model name
        benchmark: Benchmark name
        n: N-gram size
        threshold: Overlap threshold

    Returns:
        ContaminationReport
    """
    detector = NgramDetector(n=n, threshold=threshold)
    return detector.check_batch(outputs, references, model=model, benchmark=benchmark)
