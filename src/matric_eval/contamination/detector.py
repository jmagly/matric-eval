"""Word n-gram and normalized exact overlap diagnostics, not training detection."""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from matric_eval.contamination.diagnostics import (
    Method,
    OverlapReport,
    SampleDiagnostic,
    normalize,
    read_diagnostic,
    text_identity,
)


@dataclass
class ContaminationEvidence:
    """Legacy evidence container; severity is historical and has no validity meaning."""

    type: str
    details: str
    severity: float
    sample_id: str | None = None
    overlap_ratio: float = 0.0


@dataclass
class ContaminationReport:
    """Deprecated constructor for historical heuristic artifacts, never ranking input."""

    model: str
    benchmark: str
    contamination_score: float = 0.0
    confidence: float = 0.0
    evidence: list[ContaminationEvidence] = field(default_factory=list)
    samples_checked: int = 0
    samples_flagged: int = 0

    def __post_init__(self) -> None:
        warnings.warn(
            "ContaminationReport is legacy; use OverlapReport diagnostics",
            DeprecationWarning,
            stacklevel=2,
        )

    @property
    def recommendation(self) -> str:
        warnings.warn(
            "Overlap cannot establish trustworthiness or training exposure",
            DeprecationWarning,
            stacklevel=2,
        )
        return "unknown_training_exposure"

    def adjusted_score(self, raw_score: float) -> float:
        return OverlapReport.adjusted_score(self, raw_score)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, Any]:
        import json

        return read_diagnostic(json.dumps(asdict(self), allow_nan=False)).model_dump()


def _extract_ngrams(text: str, n: int) -> list[tuple[str, ...]]:
    """Extract overlapping word n-gram occurrences after lower/whitespace normalization."""
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive integer")
    words = normalize(text).split()
    return [tuple(words[index : index + n]) for index in range(len(words) - n + 1)]


class NgramDetector:
    """Measure overlap only within supplied text pairs; threshold selects similarity.

    Exact independently solved answers can overlap. Low-overlap paraphrases do
    not exclude training exposure. Neither event changes a benchmark score.
    """

    def __init__(self, n: int = 10, threshold: float = 0.3):
        self.method = Method(n=n, threshold=threshold)
        self.n = self.method.n
        self.threshold = self.method.threshold

    def compute_overlap(self, output: str, reference: str) -> float | None:
        """Output-occurrence overlap ratio, or None when either text has no n-grams."""
        output_ngrams = _extract_ngrams(output, self.n)
        reference_ngrams = set(_extract_ngrams(reference, self.n))
        if not output_ngrams or not reference_ngrams:
            return None
        return sum(item in reference_ngrams for item in output_ngrams) / len(output_ngrams)

    def check_sample(
        self,
        output: str,
        reference: str,
        sample_id: str | None = None,
        *,
        output_source_id: str = "provided-output",
        reference_source_id: str = "provided-reference",
    ) -> SampleDiagnostic:
        """Return evidence for every pair, including low overlap and insufficient text."""
        output_id = text_identity(output, output_source_id)
        reference_id = text_identity(reference, reference_source_id)
        output_ngrams = _extract_ngrams(output, self.n)
        reference_ngrams = _extract_ngrams(reference, self.n)
        ratio = self.compute_overlap(output, reference)
        empty = not output_id.words or not reference_id.words
        limits = ["local_overlap_does_not_establish_training_exposure"]
        if empty:
            limits.append("empty_normalized_text")
        if ratio is None:
            limits.append("insufficient_words_for_ngram_method")
        return SampleDiagnostic(
            sample_id=sample_id if sample_id is not None else "0",
            output=output_id,
            reference=reference_id,
            status="insufficient_text" if empty else "tested_with_method",
            normalized_exact_match=None if empty else normalize(output) == normalize(reference),
            output_ngrams=len(output_ngrams),
            reference_ngrams=len(reference_ngrams),
            matching_output_ngrams=sum(item in set(reference_ngrams) for item in output_ngrams),
            overlap_ratio=ratio,
            exceeds_similarity_threshold=ratio >= self.threshold if ratio is not None else None,
            limits=limits,
        )

    def check_batch(
        self,
        outputs: list[str],
        references: list[str],
        sample_ids: list[str] | None = None,
        model: str = "unknown",
        benchmark: str = "unknown",
        *,
        raw_score: float | None = None,
        output_source_id: str = "provided-output",
        reference_source_id: str = "provided-reference",
        scope: Literal[
            "provided_output_reference_pairs", "provided_train_eval_datasets"
        ] = "provided_output_reference_pairs",
    ) -> OverlapReport:
        if (
            not isinstance(outputs, list)
            or not isinstance(references, list)
            or any(not isinstance(item, str) for item in [*outputs, *references])
        ):
            raise ValueError("outputs and references must be arrays of strings")
        if len(outputs) != len(references):
            raise ValueError("outputs and references must have the same length")
        if sample_ids is None:
            sample_ids = [str(index) for index in range(len(outputs))]
        if not isinstance(sample_ids, list) or any(not isinstance(sid, str) for sid in sample_ids):
            raise ValueError("sample identities must be an array of strings")
        if len(sample_ids) != len(outputs) or len(set(sample_ids)) != len(sample_ids):
            raise ValueError("sample identities must be unique and cover every pair")
        if scope == "provided_train_eval_datasets" and (
            output_source_id == "provided-output" or reference_source_id == "provided-reference"
        ):
            raise ValueError(
                "dataset overlap requires explicit train and evaluation source identities"
            )
        samples = [
            self.check_sample(
                output,
                reference,
                sid,
                output_source_id=output_source_id,
                reference_source_id=reference_source_id,
            )
            for output, reference, sid in zip(outputs, references, sample_ids, strict=True)
        ]
        tested = sum(sample.status == "tested_with_method" for sample in samples)
        status: Literal["empty_batch", "tested_with_method", "partial", "insufficient_text"] = (
            "empty_batch"
            if not samples
            else "tested_with_method"
            if tested == len(samples)
            else "partial"
            if tested
            else "insufficient_text"
        )
        return OverlapReport(
            model=model,
            benchmark=benchmark,
            scope=scope,
            method=self.method,
            status=status,
            raw_score=raw_score,
            samples=samples,
            limits=[
                "paired_local_text_only",
                "foundation_model_training_history_unknown",
                "similarity_threshold_is_not_a_contamination_test",
                "no_score_adjustment",
            ],
        )


def check_overlap(
    outputs: list[str], references: list[str], *, n: int = 10, threshold: float = 0.3, **kwargs: Any
) -> OverlapReport:
    """Measure supplied text pairs without training-exposure or trustworthiness claims."""
    return NgramDetector(n=n, threshold=threshold).check_batch(outputs, references, **kwargs)


def check_contamination(
    outputs: list[str],
    references: list[str],
    model: str = "unknown",
    benchmark: str = "unknown",
    n: int = 10,
    threshold: float = 0.3,
) -> OverlapReport:
    """Deprecated name: returns versioned overlap diagnostics, never a trust verdict."""
    warnings.warn(
        "check_contamination is deprecated; use check_overlap", DeprecationWarning, stacklevel=2
    )
    return check_overlap(
        outputs, references, model=model, benchmark=benchmark, n=n, threshold=threshold
    )
