"""Content-free conversion of pinned Inspect logs to reconciled v2 observations."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, EvalSample

from matric_eval.results.contract import (
    ArtifactReference,
    BenchmarkResult,
    MetricDescriptor,
    ObservationIdentity,
    ResultEnvelope,
)


def unavailable(reason: str) -> dict[str, Any]:
    return {
        "value": None,
        "reason": reason,
        "numerator": None,
        "denominator": None,
        "method": "unavailable",
        "eligibility": {"eligible": False, "reasons": [reason]},
    }


def native_reference(log: EvalLog) -> dict[str, Any]:
    location = str(log.location) if log.location else f"inspect:{log.eval.eval_id}"
    digest = None
    path = Path(location)
    if path.is_file():
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return ArtifactReference(
        uri=location,
        sha256=digest,
        unavailable_reason=None if digest else "native_artifact_not_locally_hashable",
    ).model_dump()


def sample_identity(value: str | int) -> str:
    """Keep integer and string sample IDs distinct, including embedded separators."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    # Inspect's standard correctness labels; other textual/vector scores require
    # an explicitly supplied score adapter rather than a numeric guess.
    return {"C": 1.0, "I": 0.0}.get(value) if isinstance(value, str) else None


def _sample_outcome(
    sample: EvalSample | None, scorer: str
) -> tuple[str, str, float | None, str | None]:
    if sample is None:
        return "unknown", "unavailable", None, "selected_sample_not_logged"
    if sample.error is not None:
        return "failed", "infrastructure_error", None, "inspect_sample_error"
    if sample.limit is not None and sample.limit.type == "operator":
        return "cancelled", "cancelled", None, sample.limit.reason or "operator_cancelled"
    score = (sample.scores or {}).get(scorer)
    if score is None:
        reason = (
            f"inspect_limit:{sample.limit.type}:{sample.limit.reason}"
            if sample.limit
            else "scorer_not_available"
        )
        return "completed", "unavailable", None, reason
    if score.reason in {"grader_failed", "scoring_failed"}:
        return "completed", "grader_failed", None, score.reason
    value = _numeric(score.value)
    if value is None:
        return "completed", "unavailable", None, score.reason or "unsupported_or_nonfinite_score"
    return "completed", "observed", value, None


def adapt_log(
    log: EvalLog,
    *,
    run_id: str,
    model_id: str,
    benchmark_id: str,
    primary_metric_id: str | None = None,
    descriptors: dict[str, MetricDescriptor] | None = None,
) -> BenchmarkResult:
    """Use Inspect's post-selection manifest, never reconstruct it from successes.

    Unsupported dynamic manifests and duplicate terminal records fail explicitly;
    callers retain native references and return an ineligible result.
    """
    selected_ids = log.eval.dataset.sample_ids
    if selected_ids is None:
        raise ValueError("selected_manifest_unavailable")
    epochs = log.eval.config.epochs or 1
    selected = [
        (sample_identity(sid), epoch) for sid in selected_ids for epoch in range(1, epochs + 1)
    ]
    if len(set(selected)) != len(selected):
        raise ValueError("duplicate_selected_identity")
    if log.results is not None and log.results.total_samples != len(selected):
        raise ValueError("selected_manifest_count_mismatch")
    samples: dict[tuple[str, int], EvalSample] = {}
    for logged_sample in log.samples or []:
        key = sample_identity(logged_sample.id), logged_sample.epoch
        if key in samples or key not in selected:
            raise ValueError("duplicate_or_unselected_sample")
        samples[key] = logged_sample
    if (
        log.results is not None
        and log.results.logged_samples is not None
        and log.results.logged_samples != len(samples)
    ):
        raise ValueError("logged_sample_count_mismatch")
    native_metrics: dict[str, tuple[str, str, float | None]] = {
        f"{score.name}/{name}": (score.name, name, metric.value)
        for score in (log.results.scores if log.results else [])
        for name, metric in score.metrics.items()
    }
    if len(native_metrics) != sum(
        len(score.metrics) for score in (log.results.scores if log.results else [])
    ):
        raise ValueError("duplicate_native_metric_identity")
    declared = descriptors or {}
    represented = {item[0] for item in native_metrics.values()} | {
        descriptor.scorer_id for descriptor in declared.values()
    }
    for scorer_id in sorted(
        {name for sample in samples.values() for name in (sample.scores or {})}
    ):
        if scorer_id not in represented:
            # A failed/drained log may have per-sample grades but no summary.
            # Keep those grades without inventing a headline estimate.
            native_metrics[f"{scorer_id}/raw"] = (scorer_id, "raw", None)
    metric_ids = sorted(set(native_metrics) | set(declared))
    if not metric_ids:
        # Retain execution accounting even if Inspect produced no summary metrics.
        metric_ids = ["unavailable/measurement"]
    artifacts = [native_reference(log)]
    observations: list[dict[str, Any]] = []
    metric_results: dict[str, Any] = {}
    execution_counts: Counter[str] = Counter()
    for sid, epoch in selected:
        sample = samples.get((sid, epoch))
        execution_counts[
            "unknown"
            if sample is None
            else "failed"
            if sample.error
            else "cancelled"
            if sample.limit and sample.limit.type == "operator"
            else "completed"
        ] += 1
    terminal = (
        execution_counts["completed"] + execution_counts["failed"] + execution_counts["cancelled"]
    )
    if log.status == "error":
        execution = "failed"
    elif log.status == "cancelled":
        execution = "cancelled"
    elif log.status == "success" and terminal == len(selected):
        execution = "completed"
    else:
        execution = "partial"
    execution_reasons = [] if execution == "completed" else [f"inspect_{log.status}"]
    if terminal != len(selected):
        execution_reasons.append("incomplete_scope")
    if execution_counts["failed"]:
        execution_reasons.append("sample_execution_failed")
    if execution_counts["cancelled"]:
        execution_reasons.append("sample_cancelled")
    if not selected:
        execution_reasons.append("empty_manifest")
    if log.invalidated:
        execution_reasons.append("native_samples_invalidated")

    for metric_id in metric_ids:
        scorer_id, _, native_value = native_metrics.get(
            metric_id, (metric_id.split("/")[0], "", None)
        )
        descriptor = declared.get(metric_id)
        if descriptor is None:
            descriptor = MetricDescriptor(
                metric_id=metric_id,
                version="inspect-native/1",
                scorer_id=scorer_id,
                value_kind="continuous",
                units="undeclared",
                direction="neutral",
                minimum=None,
                maximum=None,
                independent_unit="selected-sample-epoch",
                missingness_policy="exclude-unmeasured/1",
                aggregation_id="inspect-native",
                timeout_value=None,
            )
        scorer_id = descriptor.scorer_id
        counts: Counter[str] = Counter()
        scored = 0
        for sid, epoch in selected:
            sample = samples.get((sid, epoch))
            state, outcome, value, reason = _sample_outcome(sample, scorer_id)
            counts[outcome] += 1
            scored += value is not None
            identity = ObservationIdentity(
                run_id=run_id,
                model_id=model_id,
                benchmark_id=benchmark_id,
                allocation_id=benchmark_id,
                sample_id=sid,
                trial_id=f"epoch-{epoch}",
                metric_id=metric_id,
            )
            retries = list(sample.error_retries or []) if sample else []
            native_score = (sample.scores or {}).get(scorer_id) if sample else None
            metadata = native_score.metadata or {} if native_score else {}
            judge = None
            if isinstance(metadata.get("judge_model"), str):
                summary = next(
                    (
                        item
                        for item in (log.results.scores if log.results else [])
                        if item.name == scorer_id
                    ),
                    None,
                )
                params = summary.params if summary else {}
                recorded = {
                    key: params.get(key, "unknown")
                    for key in ("max_attempts", "check_position_bias")
                }
                recorded["judge_model"] = metadata["judge_model"]
                judge = {
                    "judge_id": metadata["judge_model"],
                    "configuration_sha256": hashlib.sha256(
                        json.dumps(recorded, sort_keys=True, default=str).encode()
                    ).hexdigest(),
                    "reversal_policy": f"recorded:{recorded['check_position_bias']}",
                    "retry_policy": f"recorded:max_attempts:{recorded['max_attempts']}",
                    "calibration": None,
                }
            # Error retries have no native attempt ID. Ordinals are adapter-owned
            # lineage, not independent statistical draws or reconstructed content.
            for attempt in range(len(retries) + 1):
                accepted = attempt == len(retries)
                observations.append(
                    {
                        "observation_id": identity.logical_id(),
                        "identity": identity.model_dump(),
                        "attempt_id": f"inspect-attempt-{attempt}",
                        "previous_attempt_id": f"inspect-attempt-{attempt - 1}"
                        if attempt
                        else None,
                        "accepted": accepted,
                        "execution": state if accepted else "failed",
                        "outcome": outcome if accepted else "infrastructure_error",
                        "value": value if accepted else None,
                        "reason": reason if accepted else "inspect_retry_error",
                        "native_status": str(
                            metadata.get("judge_status")
                            or (native_score.reason if native_score else None)
                            or outcome
                        )
                        if accepted
                        else "error_retry",
                        "judge": judge,
                        "artifacts": artifacts,
                    }
                )
        estimate_value = _numeric(native_value) if scored else None
        reasons = list(execution_reasons)
        if counts["grader_failed"] or counts["unavailable"]:
            reasons.append("unmeasured_samples")
        if metric_id not in declared:
            reasons.append("metric_semantics_undeclared")
        if estimate_value is None:
            reasons.append("estimate_unavailable")
        estimate = (
            unavailable("estimate_unavailable")
            if estimate_value is None
            else {
                "value": estimate_value,
                "reason": None,
                "numerator": None,
                "denominator": float(scored),
                "method": "inspect-native",
                "eligibility": {"eligible": not reasons, "reasons": reasons},
            }
        )
        metric_results[metric_id] = {
            "descriptor": descriptor.model_dump(),
            "estimate": estimate,
            "scored": scored,
            "outcome_counts": dict(counts),
        }
    primary = metric_results.get(primary_metric_id or "")
    primary_estimate = (
        primary["estimate"] if primary else unavailable("primary_metric_undeclared_or_missing")
    )
    eligibility = primary_estimate["eligibility"]
    return BenchmarkResult.model_validate(
        {
            "benchmark_id": benchmark_id,
            "protocol_sha256": None,
            "manifest_sha256": hashlib.sha256(
                json.dumps(selected, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest(),
            "execution": execution,
            "eligibility": eligibility,
            "primary_metric_id": primary_metric_id,
            "primary_estimate": primary_estimate,
            "metrics": metric_results,
            "selection": [
                {
                    "allocation_id": benchmark_id,
                    "sample_id": sid,
                    "trial_id": f"epoch-{epoch}",
                    "data": {
                        "partition_schema_version": "1",
                        "role": "unknown",
                        "row_id": sid,
                        "source_id": log.eval.dataset.name or benchmark_id,
                        "independent_unit_id": sid,
                    },
                }
                for sid, epoch in selected
            ],
            "observations": observations,
            "coverage": {
                "requested": len(selected),
                "attempted": terminal,
                "terminal": terminal,
                "completed": execution_counts["completed"],
                "failed": execution_counts["failed"],
                "cancelled": execution_counts["cancelled"],
                "not_attempted": 0,
                "unknown": execution_counts["unknown"],
            },
            "artifacts": artifacts,
        }
    )


def envelope(benchmark: BenchmarkResult, run_id: str, model_id: str) -> ResultEnvelope:
    return ResultEnvelope.model_validate(
        {
            "result_schema_version": "2",
            "run_id": run_id,
            "model_id": model_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provenance_schema_version": "1",
            "configuration_sha256": None,
            "execution": benchmark.execution,
            "eligibility": benchmark.eligibility.model_dump(),
            "benchmarks": [benchmark.model_dump()],
            "aggregation_id": None,
            "overall_estimate": unavailable("aggregation_undeclared"),
            "artifacts": [],
        }
    )
