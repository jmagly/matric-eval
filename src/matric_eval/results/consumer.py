"""Strict migration ingress; historical evidence never becomes an invented result."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal, Self, cast

from pydantic import Field, model_validator

from matric_eval.contamination.diagnostics import strict_json as parse_unique_json
from matric_eval.results.contract import (
    ArtifactReference,
    Eligibility,
    Record,
    ResultEnvelope,
    Text,
)
from matric_eval.results.trials import TrialEvaluation

DISCRIMINATORS = {
    "result_schema_version",
    "trial_schema_version",
    "result_collection_schema_version",
    "consumer_import_schema_version",
}


class ConsumerError(ValueError):
    """Stable, content-free ingress/projection failure."""


def strict_json(source: str) -> Any:
    try:
        source.encode("utf-8")
        value = parse_unique_json(source)
        # Reject overflowing finite-spelled tokens and unpaired Unicode escapes.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        code = (
            "duplicate_object_key"
            if str(exc) == "duplicate JSON key"
            else "nonfinite_or_invalid_json"
        )
        raise ConsumerError(code) from None


def canonical_json(value: Any) -> str:
    try:
        result = json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        strict_json(result)
        return result
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ConsumerError("nonfinite_or_invalid_json") from None


def _legacy_format(value: Any) -> str:
    if (
        isinstance(value, dict)
        and "schema_version" in value
        and value["schema_version"] in ("1", "2")
    ):
        if (
            not any(
                key == "version" or (key.endswith("_schema_version") and key != "schema_version")
                for key in value
            )
            and not DISCRIMINATORS.intersection(value)
            and isinstance(value.get("results"), list)
            and type(value.get("matrix_runs")) is int
            and value["matrix_runs"] == len(value["results"])
            and isinstance(value.get("timestamp"), str)
            and isinstance(value.get("tier"), str)
            and all(_legacy_format(item) == "legacy_model/1" for item in value["results"])
        ):
            return "legacy_matrix/1"
        raise ConsumerError("unrecognized_legacy_shape")
    if isinstance(value, dict) and any(
        key in {"version", "schema_version"} or key.endswith("_schema_version") for key in value
    ):
        raise ConsumerError("unsupported_schema")
    if not isinstance(value, dict) or DISCRIMINATORS.intersection(value):
        raise ConsumerError("unrecognized_legacy_shape")
    if (
        isinstance(value.get("model"), str)
        and value["model"].strip()
        and (
            isinstance(value.get("benchmarks"), dict)
            or (value.get("status") in ("error", "failed") and isinstance(value.get("error"), str))
        )
    ):
        if "results" in value:
            raise ConsumerError("ambiguous_schema")
        return "legacy_model/1"
    if isinstance(value.get("results"), list) and all(
        _legacy_format(item) == "legacy_model/1" for item in value["results"]
    ):
        return "legacy_summary/1"
    raise ConsumerError("unrecognized_legacy_shape")


class LegacyImport(Record):
    consumer_import_schema_version: Literal["1"] = "1"
    conversion_profile: Literal["legacy-preservation/1"] = "legacy-preservation/1"
    source_format: Literal["legacy_model/1", "legacy_summary/1", "legacy_matrix/1"]
    source_sha256: Text
    conversion_sha256: Text
    source_text: str
    payload: dict[str, Any]
    status: Literal["legacy_unverified"] = "legacy_unverified"
    eligibility: Eligibility = Field(
        default_factory=lambda: Eligibility(eligible=False, reasons=["legacy_unverified"])
    )

    @model_validator(mode="after")
    def verify_source(self) -> Self:
        raw = self.source_text.encode("utf-8")
        parsed = strict_json(self.source_text)
        if (
            hashlib.sha256(raw).hexdigest() != self.source_sha256
            or hashlib.sha256(b"legacy-preservation/1\0" + raw).hexdigest()
            != self.conversion_sha256
            or canonical_json(parsed) != canonical_json(self.payload)
            or _legacy_format(parsed) != self.source_format
            or self.eligibility != Eligibility(eligible=False, reasons=["legacy_unverified"])
        ):
            raise ValueError("legacy_source_binding_invalid")
        return self


class ConsumerFailure(Record):
    run_id: Text
    model_id: Text
    execution: Literal["failed", "cancelled", "unknown"]
    reason: Literal["result_projection_unavailable"]
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    eligibility: Eligibility = Field(
        default_factory=lambda: Eligibility(
            eligible=False, reasons=["result_projection_unavailable"]
        )
    )

    @model_validator(mode="after")
    def ineligible(self) -> Self:
        if self.eligibility != Eligibility(
            eligible=False, reasons=["result_projection_unavailable"]
        ):
            raise ValueError("failure_is_ineligible")
        return self


class ResultCollection(Record):
    result_collection_schema_version: Literal["1"] = "1"
    results: list[ResultEnvelope]
    failures: list[ConsumerFailure]

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        keys = [(item.run_id, item.model_id) for item in self.results] + [
            (failure.run_id, failure.model_id) for failure in self.failures
        ]
        if len(set(keys)) != len(keys) or not (self.results or self.failures):
            raise ValueError("collection_source_identity_invalid")
        return self


ConsumerResult = ResultEnvelope | TrialEvaluation | LegacyImport | ResultCollection


def read_consumer_result(source: str) -> ConsumerResult:
    value = strict_json(source)
    if not isinstance(value, dict):
        raise ConsumerError("unrecognized_legacy_shape")
    markers = DISCRIMINATORS.intersection(value)
    if len(markers) > 1:
        raise ConsumerError("ambiguous_schema")
    types: dict[str, tuple[str, Any]] = {
        "result_schema_version": ("2", ResultEnvelope),
        "trial_schema_version": ("1", TrialEvaluation),
        "result_collection_schema_version": ("1", ResultCollection),
        "consumer_import_schema_version": ("1", LegacyImport),
    }
    if markers:
        marker = next(iter(markers))
        version, model = types[marker]
        if value[marker] != version:
            raise ConsumerError("unsupported_schema")
        try:
            if marker == "consumer_import_schema_version" and set(value) != set(
                LegacyImport.model_fields
            ):
                raise ValueError("incomplete_import")
            if marker == "result_collection_schema_version" and any(
                set(item) != set(ConsumerFailure.model_fields) for item in value.get("failures", [])
            ):
                raise ValueError("incomplete_failure")
            envelopes = (
                value.get("results", [])
                if marker == "result_collection_schema_version"
                else [value]
            )
            for envelope in envelopes:
                comparison = envelope.get("comparability") if isinstance(envelope, dict) else None
                if isinstance(comparison, dict) and isinstance(comparison.get("payload"), str):
                    strict_json(comparison["payload"])
            return cast(ConsumerResult, model.model_validate(value))
        except (ValueError, TypeError, KeyError):
            raise ConsumerError("invalid_versioned_result") from None
    source_format = _legacy_format(value)
    raw = source.encode("utf-8")
    return LegacyImport.model_validate(
        {
            "source_format": source_format,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "conversion_sha256": hashlib.sha256(b"legacy-preservation/1\0" + raw).hexdigest(),
            "source_text": source,
            "payload": value,
        }
    )


def write_consumer_result(result: ConsumerResult) -> str:
    payload = canonical_json(result.model_dump(exclude_unset=False))
    read_consumer_result(payload)
    return payload


def read_consumer_collection(source: str) -> list[ResultEnvelope | TrialEvaluation | LegacyImport]:
    result = read_consumer_result(source)
    if isinstance(result, ResultCollection):
        if result.failures:
            raise ConsumerError("collection_contains_execution_failures")
        return list(result.results)
    return [result]


def convert_legacy_artifact(source: Path, output: Path) -> LegacyImport:
    try:
        raw = source.read_bytes()
        result = read_consumer_result(raw.decode("utf-8"))
    except (OSError, UnicodeError):
        raise ConsumerError("source_unreadable") from None
    if not isinstance(result, LegacyImport):
        raise ConsumerError("conversion_requires_legacy")
    payload = write_consumer_result(result).encode("utf-8") + b"\n"
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        raise ConsumerError("output_requires_new_path") from None
    with os.fdopen(descriptor, "wb") as target:
        target.write(payload)
        target.flush()
        os.fsync(target.fileno())
    directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return result


def project_legacy(result: ConsumerResult) -> dict[str, Any]:
    """Explicit historical numeric projection only; never a comparable ranking."""
    result = read_consumer_result(canonical_json(result.model_dump()))
    if not isinstance(result, LegacyImport):
        raise ConsumerError("legacy_projection_unrepresentable:versioned_measurements")
    payload = result.payload
    rows = payload["results"] if result.source_format != "legacy_model/1" else [payload]
    expected_counts = {
        "total_models": len(rows),
        "models_evaluated": len(rows),
        "successful": sum(row.get("status") == "success" for row in rows),
        "failed": sum(row.get("status") in ("error", "failed") for row in rows),
        "skipped": sum(row.get("status") == "skipped" for row in rows),
    }
    for key, expected in expected_counts.items():
        if key in payload and (
            type(payload[key]) is not int
            or not 0 <= payload[key] <= 9007199254740991
            or payload[key] != expected
        ):
            raise ConsumerError("legacy_projection_unrepresentable:counts")
    for row in [payload, *rows]:
        for key in ("size_gb", "duration_seconds"):
            if (
                key in row
                and row[key] is not None
                and (type(row[key]) not in (int, float) or row[key] < 0)
            ):
                raise ConsumerError("legacy_projection_unrepresentable:metadata")
        for key in ("timestamp", "output_dir", "error"):
            if key in row and row[key] is not None and not isinstance(row[key], str):
                raise ConsumerError("legacy_projection_unrepresentable:metadata")
    for row in rows:
        if (
            not isinstance(row.get("tier"), str)
            or not isinstance(row.get("status"), str)
            or row["tier"] not in {"smoke", "quick", "full"}
            or row["status"] not in {"success", "error", "failed", "skipped"}
        ):
            raise ConsumerError("legacy_projection_unrepresentable:status_or_tier")
        if (
            type(row.get("overall_score")) not in (int, float)
            or row.get("eligible") is False
            or "eligibility" in row
            or not isinstance(row.get("benchmarks"), dict)
            or any(key in row for key in ("observation_result", "comparability", "trials"))
        ):
            raise ConsumerError("legacy_projection_unrepresentable:overall_score_or_eligibility")
        for benchmark in row["benchmarks"].values():
            if (
                not isinstance(benchmark, dict)
                or type(benchmark.get("score")) not in (int, float)
                or benchmark.get("eligible") is False
                or "eligibility" in benchmark
                or any(key in benchmark for key in ("observation_result", "metrics", "trials"))
            ):
                raise ConsumerError("legacy_projection_unrepresentable:benchmark_measurements")
    return payload
