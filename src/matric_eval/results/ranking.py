"""Declared full-scope recommendations with retained exclusions and native sources."""

from __future__ import annotations

from typing import Any, Literal

from matric_eval.results.comparison import require_comparable
from matric_eval.results.consumer import (
    ConsumerResult,
    LegacyImport,
    ResultCollection,
    canonical_json,
    read_consumer_result,
)
from matric_eval.results.contract import Digest, Number, Record, ResultEnvelope
from matric_eval.results.policies import SuiteAggregation
from matric_eval.results.reducers import aggregate_benchmarks


class RecommendationPolicy(Record):
    version: Literal["1"]
    comparison_sha256: Digest
    capabilities: dict[str, SuiteAggregation]
    minimum_score: Number | None = None
    require_qualified_judges: bool = False


def recommend_consumers(
    sources: list[ConsumerResult], policy: RecommendationPolicy | None
) -> dict[str, Any]:
    if policy is not None:
        policy = RecommendationPolicy.model_validate(policy.model_dump())
        if not policy.capabilities or any(
            item.missingness_policy != "require-complete" for item in policy.capabilities.values()
        ):
            raise ValueError("recommendation_requires_complete_declared_capabilities")
        if policy.minimum_score is not None and (
            len({item.target_units for item in policy.capabilities.values()}) != 1
            or any(item.target_direction != "higher" for item in policy.capabilities.values())
        ):
            raise ValueError("global_threshold_requires_shared_higher_target_scale")
    records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    candidates: list[ResultEnvelope] = []
    retained_envelopes: list[ResultEnvelope] = []
    seen: dict[tuple[str, str], str] = {}
    for supplied in sources:
        source = read_consumer_result(canonical_json(supplied.model_dump()))
        records.append(source.model_dump())
        items = source.results if isinstance(source, ResultCollection) else [source]
        if isinstance(source, ResultCollection):
            exclusions.extend(
                {
                    "run_id": failure.run_id,
                    "model_id": failure.model_id,
                    "reasons": [failure.reason],
                }
                for failure in source.failures
            )
        for item in items:
            if not isinstance(item, ResultEnvelope):
                exclusions.append(
                    {
                        "source_index": len(records) - 1,
                        "reasons": [
                            "legacy_unverified"
                            if isinstance(item, LegacyImport)
                            else "trial_metric_policy_undeclared"
                        ],
                    }
                )
                continue
            key = (item.run_id, item.model_id)
            document = canonical_json(item.model_dump())
            if key in seen:
                if seen[key] != document:
                    raise ValueError("conflicting_source_identity")
                continue
            seen[key] = document
            retained_envelopes.append(item)
            reasons = []
            if policy is None:
                reasons.append("recommendation_policy_undeclared")
            if item.execution != "completed" or not item.eligibility.eligible:
                reasons.append("result_ineligible")
            if item.comparability is None or not item.comparability.eligibility.eligible:
                reasons.append("comparison_identity_ineligible")
            elif policy is not None and item.comparability.sha256 != policy.comparison_sha256:
                reasons.append("comparison_scope_mismatch")
            if (
                policy is not None
                and policy.require_qualified_judges
                and any(
                    row.judge is not None
                    for benchmark in item.benchmarks
                    for row in benchmark.observations
                )
            ):
                reasons.append("judge_qualification_unavailable")
            if reasons:
                exclusions.append(
                    {"run_id": item.run_id, "model_id": item.model_id, "reasons": reasons}
                )
            else:
                require_comparable(item, item)
                candidates.append(item)
    # A model's multiple runs are not silently collapsed into a best/latest score.
    duplicate_models = {
        item.model_id
        for item in candidates
        if sum(other.model_id == item.model_id for other in candidates) > 1
    }
    for item in candidates:
        if item.model_id in duplicate_models:
            exclusions.append(
                {
                    "run_id": item.run_id,
                    "model_id": item.model_id,
                    "reasons": ["multiple_runs_require_explicit_selection"],
                }
            )
    candidates = [item for item in candidates if item.model_id not in duplicate_models]
    recommendations: dict[str, Any] = {}
    model_scores: dict[str, Any] = {}
    for item in candidates:
        if candidates:
            require_comparable(candidates[0], item)
        model_scores[item.model_id] = {
            "model": item.model_id,
            "run_id": item.run_id,
            "benchmark_scores": {
                bench.benchmark_id: bench.primary_estimate.value for bench in item.benchmarks
            },
            "capability_scores": {},
            "overall_score": item.overall_estimate.value,
            "size_gb": None,
        }
    for name, aggregation in policy.capabilities.items() if policy else []:
        ranking = []
        expected = {term.benchmark_id for term in aggregation.terms}
        for item in candidates:
            if {bench.benchmark_id for bench in item.benchmarks} != expected:
                exclusions.append(
                    {
                        "model_id": item.model_id,
                        "capability": name,
                        "reasons": ["capability_scope_mismatch"],
                    }
                )
                model_scores[item.model_id]["capability_scores"][name] = None
                continue
            result = aggregate_benchmarks(item.benchmarks, sorted(expected), aggregation)
            model_scores[item.model_id]["capability_scores"][name] = result.estimate.value
            if result.estimate.value is None or not result.estimate.eligibility.eligible:
                exclusions.append(
                    {
                        "model_id": item.model_id,
                        "capability": name,
                        "reasons": result.estimate.eligibility.reasons,
                    }
                )
            elif (
                policy is not None
                and policy.minimum_score is not None
                and (
                    aggregation.target_direction != "higher"
                    or result.estimate.value < policy.minimum_score
                )
            ):
                exclusions.append(
                    {
                        "model_id": item.model_id,
                        "capability": name,
                        "reasons": ["score_threshold_not_satisfied"],
                    }
                )
            else:
                ranking.append((item.model_id, result.estimate.value))
        ranking.sort(
            key=lambda entry: (
                (-entry[1] if aggregation.target_direction == "higher" else entry[1]),
                entry[0],
            )
        )
        recommendations[name] = {
            "status": "recommended" if ranking else "no_recommendation",
            "recommended": ranking[0][0] if ranking else None,
            "score": ranking[0][1] if ranking else None,
            "alternatives": [{"model": model, "score": score} for model, score in ranking[1:]],
            "units": aggregation.target_units,
            "direction": aggregation.target_direction,
            "reasons": [] if ranking else ["no_eligible_candidate"],
        }
    return {
        "recommendation_schema_version": "2",
        "status": "recommended"
        if any(item["status"] == "recommended" for item in recommendations.values())
        else "no_recommendation",
        "recommendations": recommendations,
        "model_scores": model_scores,
        "best_overall": None,
        "best_balanced": None,
        "exclusions": exclusions,
        "sources": records,
        "policy": policy.model_dump() if policy else None,
        "judge_controls": [
            {
                "run_id": item.run_id,
                "model_id": item.model_id,
                "judge": row.judge.model_dump(),
                "qualification": "unverified",
                "reason": "qualification_policy_evidence_unavailable",
            }
            for item in retained_envelopes
            for benchmark in item.benchmarks
            for row in benchmark.observations
            if row.judge is not None
        ],
        "limitations": [
            "comparison_scope_is_declared_not_model_snapshot_attestation",
            "no_implicit_overall_or_balanced_ranking",
            "judge_qualification_not_inferred",
        ],
    }
