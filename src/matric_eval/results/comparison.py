"""Content-free comparison keys; identity does not itself qualify a measurement."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from matric_eval.results.contract import ResultEnvelope


def comparison_inputs(result: ResultEnvelope) -> dict[str, Any]:
    """Exclude the varied model/run and measured values; preserve requested scope."""
    return {
        "version": "comparison/1",
        "configuration_sha256": result.configuration_sha256,
        "aggregation": result.aggregation.model_dump() if result.aggregation else None,
        "benchmarks": [
            {
                "benchmark_id": benchmark.benchmark_id,
                "protocol_sha256": benchmark.protocol_sha256,
                "manifest_sha256": benchmark.manifest_sha256,
                "primary_metric_id": benchmark.primary_metric_id,
                "metrics": {
                    mid: {
                        "descriptor": metric.descriptor.model_dump(),
                        "observation_metric_id": metric.observation_metric_id,
                    }
                    for mid, metric in sorted(benchmark.metrics.items())
                },
                "selection": [item.model_dump() for item in benchmark.selection],
                "judges": [
                    json.loads(item)
                    for item in sorted(
                        {
                            json.dumps(
                                row.judge.model_dump(), sort_keys=True, separators=(",", ":")
                            )
                            for row in benchmark.observations
                            if row.judge is not None
                        }
                    )
                ],
            }
            for benchmark in result.benchmarks
        ],
    }


def comparison_reasons(result: ResultEnvelope) -> list[str]:
    reasons = []
    if result.configuration_sha256 is None:
        reasons.append("comparison_configuration_unverified")
    if not result.eligibility.eligible:
        reasons.append("measurement_scope_ineligible")
    if result.aggregation is not None and not result.overall_estimate.eligibility.eligible:
        reasons.append("aggregate_ineligible")
    for benchmark in result.benchmarks:
        if benchmark.protocol_sha256 is None or benchmark.manifest_sha256 is None:
            reasons.append(f"protocol_or_manifest_unverified:{benchmark.benchmark_id}")
        if any(item.data.role == "unknown" for item in benchmark.selection):
            reasons.append(f"partition_role_unknown:{benchmark.benchmark_id}")
    return reasons


def attach_comparison(result: ResultEnvelope) -> ResultEnvelope:
    from matric_eval.results.contract import ComparisonIdentity, Eligibility, ResultEnvelope

    payload = json.dumps(
        comparison_inputs(result),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    reasons = comparison_reasons(result)
    result.comparability = ComparisonIdentity(
        version="1",
        sha256=hashlib.sha256(payload.encode()).hexdigest(),
        payload=payload,
        eligibility=Eligibility(eligible=not reasons, reasons=reasons),
    )
    return ResultEnvelope.model_validate(result.model_dump())


def validate_comparison(result: ResultEnvelope) -> None:
    identity = result.comparability
    if identity is None:
        return
    if hashlib.sha256(identity.payload.encode()).hexdigest() != identity.sha256:
        raise ValueError("comparison digest differs from payload")
    if not _same_json(json.loads(identity.payload), comparison_inputs(result)):
        raise ValueError("comparison payload differs from result scope")
    reasons = comparison_reasons(result)
    if identity.eligibility.reasons != reasons:
        raise ValueError("comparison eligibility differs from verified scope")


def _same_json(left: Any, right: Any) -> bool:
    # JSON numeric spelling may differ across readers; booleans are not numbers.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return bool(left == right)
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_json(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_json(a, b) for a, b in zip(left, right))
    return bool(left == right)


def require_comparable(left: ResultEnvelope, right: ResultEnvelope) -> None:
    """Readers must validate both scope and identity before treating runs as peers."""
    from matric_eval.results.contract import ResultEnvelope

    for result in (left, right):
        ResultEnvelope.model_validate(result.model_dump())
        if result.comparability is None or not result.comparability.eligibility.eligible:
            raise ValueError("comparison scope is unverified or ineligible")
    assert left.comparability is not None and right.comparability is not None
    if left.comparability.sha256 != right.comparability.sha256:
        raise ValueError("comparison identities differ")
