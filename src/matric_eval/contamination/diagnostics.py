"""Versioned local text overlap evidence; training exposure remains unknown."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Method(Record):
    method_id: Literal["normalized-exact-and-word-ngram/1"] = "normalized-exact-and-word-ngram/1"
    normalization: Literal["unicode-lower-whitespace-collapse/1"] = (
        "unicode-lower-whitespace-collapse/1"
    )
    tokenization: Literal["python-str-split-whitespace/1"] = "python-str-split-whitespace/1"
    n: int = Field(default=10, gt=0, le=10000)
    threshold: float = Field(default=0.3, ge=0, le=1)
    denominator: Literal["output-word-ngram-occurrences"] = "output-word-ngram-occurrences"


class TextIdentity(Record):
    source_id: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    words: int = Field(ge=0)


class SampleDiagnostic(Record):
    sample_id: str = Field(min_length=1)
    output: TextIdentity
    reference: TextIdentity
    status: Literal["tested_with_method", "insufficient_text"]
    normalized_exact_match: bool | None
    output_ngrams: int = Field(ge=0)
    reference_ngrams: int = Field(ge=0)
    matching_output_ngrams: int = Field(ge=0)
    overlap_ratio: float | None = Field(ge=0, le=1)
    exceeds_similarity_threshold: bool | None
    limits: list[str]


class OverlapReport(Record):
    diagnostic_schema_version: Literal["1"] = "1"
    model: str = Field(min_length=1)
    benchmark: str = Field(min_length=1)
    scope: Literal["provided_output_reference_pairs", "provided_train_eval_datasets"]
    method: Method
    status: Literal["tested_with_method", "partial", "insufficient_text", "empty_batch"]
    training_exposure: Literal["unknown"] = "unknown"
    likelihood_test_status: Literal["unsupported"] = "unsupported"
    likelihood_test_reason: Literal["likelihood_method_not_implemented"] = (
        "likelihood_method_not_implemented"
    )
    raw_score: float | None = None
    samples: list[SampleDiagnostic]
    limits: list[str]

    @model_validator(mode="after")
    def consistent_evidence(self) -> Self:
        ids = [sample.sample_id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("sample identities must be unique")
        tested = 0
        for sample in self.samples:
            output_count = max(0, sample.output.words - self.method.n + 1)
            reference_count = max(0, sample.reference.words - self.method.n + 1)
            if (sample.output_ngrams, sample.reference_ngrams) != (output_count, reference_count):
                raise ValueError("ngram counts differ from method and text lengths")
            empty = not sample.output.words or not sample.reference.words
            expected_exact = (
                None
                if empty
                else sample.output.normalized_sha256 == sample.reference.normalized_sha256
            )
            if sample.normalized_exact_match != expected_exact:
                raise ValueError("exact-match evidence differs from normalized identities")
            if sample.status != ("insufficient_text" if empty else "tested_with_method"):
                raise ValueError("sample status differs from available text")
            expected_limits = ["local_overlap_does_not_establish_training_exposure"]
            if empty:
                expected_limits.append("empty_normalized_text")
            if not output_count or not reference_count:
                expected_limits.append("insufficient_words_for_ngram_method")
            if sample.limits != expected_limits:
                raise ValueError("sample method limits differ from available evidence")
            tested += not empty
            if sample.matching_output_ngrams > output_count:
                raise ValueError("matching count exceeds denominator")
            available = bool(output_count and reference_count)
            ratio = sample.matching_output_ngrams / output_count if available else None
            if not available and sample.matching_output_ngrams:
                raise ValueError("short text cannot have matching ngrams")
            if sample.overlap_ratio != ratio:
                raise ValueError("overlap ratio differs from counts")
            threshold = ratio >= self.method.threshold if ratio is not None else None
            if sample.exceeds_similarity_threshold != threshold:
                raise ValueError("similarity flag differs from declared threshold")
        status = (
            "empty_batch"
            if not self.samples
            else "tested_with_method"
            if tested == len(self.samples)
            else "partial"
            if tested
            else "insufficient_text"
        )
        if self.limits != [
            "paired_local_text_only",
            "foundation_model_training_history_unknown",
            "similarity_threshold_is_not_a_contamination_test",
            "no_score_adjustment",
        ]:
            raise ValueError("report must retain diagnostic scope limitations")
        if self.status != status:
            raise ValueError("report status differs from sample coverage")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def adjusted_score(self, raw_score: float) -> float:
        """Deprecated compatibility call: retain the raw measurement without discount."""
        import math
        import warnings

        warnings.warn(
            "adjusted_score is deprecated; overlap does not adjust benchmark scores",
            DeprecationWarning,
            stacklevel=2,
        )
        if (
            isinstance(raw_score, bool)
            or not isinstance(raw_score, (int, float))
            or not math.isfinite(raw_score)
        ):
            raise ValueError("raw score must be finite")
        return raw_score


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def text_identity(text: str, source_id: str) -> TextIdentity:
    normalized = normalize(text)
    return TextIdentity(
        source_id=source_id,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
        words=len(normalized.split()),
    )


def strict_json(payload: str) -> Any:
    def reject(value: str) -> None:
        raise ValueError(f"nonfinite JSON constant: {value}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(payload, parse_constant=reject, object_pairs_hook=unique)


class LegacyDiagnostic(Record):
    diagnostic_schema_version: Literal["legacy-adapter/1"] = "legacy-adapter/1"
    status: Literal["legacy_heuristic_unverified"] = "legacy_heuristic_unverified"
    training_exposure: Literal["unknown"] = "unknown"
    comparison_eligible: Literal[False] = False
    flags: list[str]
    raw_score: float | None
    historical_adjusted_score: float | None
    original_artifact: dict[str, Any]


def legacy_flags(value: Any) -> list[str]:
    """Detect legacy labels/discounts recursively before any score-series ingestion."""
    flags: set[str] = set()
    if isinstance(value, dict):
        if "adjusted_score" in value or "historical_adjusted_score" in value:
            flags.add("legacy_adjusted_score_excluded")
        if "contamination_score" in value or value.get("recommendation") in (
            "trustworthy",
            "suspicious",
            "likely_contaminated",
        ):
            flags.add("legacy_heuristic_label_unverified")
        if value.get("diagnostic_schema_version") == "legacy-adapter/1":
            flags.add("legacy_diagnostic_excluded")
        for item in value.values():
            flags.update(legacy_flags(item))
    elif isinstance(value, list):
        for item in value:
            flags.update(legacy_flags(item))
    return sorted(flags)


def read_diagnostic(payload: str) -> OverlapReport | LegacyDiagnostic:
    value = strict_json(payload)
    json.dumps(
        value, allow_nan=False
    )  # Reject overflowed numeric literals in legacy nested fields.
    if not isinstance(value, dict):
        raise ValueError("diagnostic must be an object")
    version = value.get("diagnostic_schema_version")
    if version == "1":
        return OverlapReport.model_validate(value)
    if version == "legacy-adapter/1":
        return LegacyDiagnostic.model_validate(value)
    if version is not None:
        raise ValueError("unsupported diagnostic schema version")
    flags = legacy_flags(value)
    if not flags:
        raise ValueError("unrecognized legacy diagnostic")
    return LegacyDiagnostic(
        flags=flags,
        raw_score=value.get("raw_score"),
        historical_adjusted_score=value.get("adjusted_score"),
        original_artifact=value,
    )


def write_diagnostic(report: OverlapReport | LegacyDiagnostic) -> str:
    # Revalidate to catch mutation of mutable Pydantic records.
    value = read_diagnostic(json.dumps(report.model_dump(), allow_nan=False))
    return json.dumps(value.model_dump(), allow_nan=False, sort_keys=True)


def score_series_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    """Separate legacy series and expose current diagnostic methods without rescoring."""
    flags = legacy_flags(result)
    summaries = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            if "diagnostic_schema_version" in value:
                report = read_diagnostic(json.dumps(value, allow_nan=False))
                if isinstance(report, OverlapReport):
                    summaries.append(
                        {
                            "method": report.method.model_dump(),
                            "status": report.status,
                            "scope": report.scope,
                            "training_exposure": report.training_exposure,
                        }
                    )
                return
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(result)
    return {
        "legacy_series_excluded": bool(flags),
        "exclusion_reasons": flags,
        "overlap_diagnostics": summaries,
    }
