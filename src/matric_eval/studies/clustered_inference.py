"""Paired whole-cluster descriptive inference, with no claimed coverage profile."""

from __future__ import annotations

import hashlib
import math
import platform
import random
import re
from pathlib import Path
from typing import Any, Self

from pydantic import model_validator

from matric_eval.results.contract import Count, Number, Record, Text
from matric_eval.studies.clustered_protocol import ClusteredProtocol, canonical, content_hash


class PairedValue(Record):
    source: Number | None
    intervention: Number | None
    source_reason: Text | None
    intervention_reason: Text | None

    @model_validator(mode="after")
    def explicit_missingness(self) -> Self:
        if (self.source is None) != (self.source_reason is not None) or (
            self.intervention is None
        ) != (self.intervention_reason is not None):
            raise ValueError(
                "each missing model outcome needs its own reason; observed values have none"
            )
        return self


class TaskOutcomes(Record):
    task_id: Text
    outcomes: dict[str, PairedValue]
    response_trials: Count
    judge_labels: Count
    infrastructure_exclusions: Count
    unresolved_grades: Count


def _sum(values: list[float]) -> float:
    return math.fsum(sorted(values))


def _signature(values: Any) -> str:
    # Stable numeric content; exclude labels and repeated-row diagnostics.
    return canonical(values)


def _prepare(
    protocol: ClusteredProtocol, rows: list[TaskOutcomes]
) -> tuple[list[dict[str, Any]], list[str]]:
    hypotheses = sorted(protocol.hypotheses, key=lambda hypothesis: hypothesis.hypothesis_id)
    keys = [hypothesis.hypothesis_id for hypothesis in hypotheses]
    by_task = {row.task_id: row for row in rows}
    if len(by_task) != len(rows) or set(by_task) - {item.task_id for item in protocol.manifest}:
        raise ValueError("duplicate or undeclared task outcomes")
    for row in rows:
        if set(row.outcomes) - set(keys):
            raise ValueError("undeclared hypothesis outcome")
    grouped: dict[tuple[str, str], list[Any]] = {}
    for membership in protocol.manifest:
        summaries = []
        task = by_task.get(membership.task_id)
        for hypothesis in hypotheses:
            pair = task.outcomes.get(hypothesis.hypothesis_id) if task else None
            source = pair.source if pair else None
            intervention = pair.intervention if pair else None
            for value in (source, intervention):
                if value is not None and not hypothesis.minimum <= value <= hypothesis.maximum:
                    raise ValueError("outcome outside declared metric bounds")
            paired = source is not None and intervention is not None
            delta = intervention - source if paired else 0.0  # type: ignore[operator]
            lower = (intervention if intervention is not None else hypothesis.minimum) - (
                source if source is not None else hypothesis.maximum
            )
            upper = (intervention if intervention is not None else hypothesis.maximum) - (
                source if source is not None else hypothesis.minimum
            )
            summaries.append([int(paired), delta, lower, upper])
        grouped.setdefault((membership.stratum_id, membership.cluster_id), []).append(
            (membership.task_id, summaries)
        )
    strata: list[dict[str, Any]] = []
    for stratum in protocol.strata:
        clusters = []
        for (stratum_id, cluster_id), tasks in grouped.items():
            if stratum_id != stratum.stratum_id:
                continue
            tasks = sorted(tasks, key=lambda item: _signature(item[1]))
            statistics = []
            for index in range(len(keys)):
                statistics.append(
                    {
                        "requested": len(tasks),
                        "paired": sum(task[1][index][0] for task in tasks),
                        "sum": _sum([task[1][index][1] for task in tasks]),
                        "lower": _sum([task[1][index][2] for task in tasks]),
                        "upper": _sum([task[1][index][3] for task in tasks]),
                    }
                )
            clusters.append(
                {
                    "statistics": statistics,
                    "cluster_id": cluster_id,
                    "task_ids": [task[0] for task in tasks],
                }
            )
        clusters.sort(key=lambda cluster: _signature(cluster["statistics"]))
        strata.append(
            {"weight": stratum.weight, "stratum_id": stratum.stratum_id, "clusters": clusters}
        )
    strata.sort(
        key=lambda stratum: _signature(
            {
                "weight": stratum["weight"],
                "weighting": protocol.weighting,
                "clusters": [cluster["statistics"] for cluster in stratum["clusters"]],
            }
        )
    )
    return strata, keys


def _estimate(
    strata: list[dict[str, Any]], outcome: int, weighting: str, slot: str, conditional: bool = False
) -> float | None:
    weighted = []
    for stratum in strata:
        if stratum["weight"] == 0:
            continue
        statistics = [cluster["statistics"][outcome] for cluster in stratum["clusters"]]
        if conditional:
            statistics = [item for item in statistics if item["paired"] > 0]
        if not statistics:
            return None
        denominator = "paired" if conditional else "requested"
        if (
            slot == "sum"
            and not conditional
            and any(item["paired"] != item["requested"] for item in statistics)
        ):
            return None
        if weighting == "equal_cluster":
            estimate = _sum([item[slot] / item[denominator] for item in statistics]) / len(
                statistics
            )
        else:
            total = sum(item[denominator] for item in statistics)
            if total == 0:
                return None
            estimate = _sum([item[slot] for item in statistics]) / total
        weighted.append(stratum["weight"] * estimate)
    result = _sum(weighted)
    if not math.isfinite(result):
        raise ValueError("estimator overflow")
    return result


def analyze_clustered(
    protocol: ClusteredProtocol,
    rows: list[TaskOutcomes],
    *,
    source_commit: str,
    draw_schedule: list[list[list[int]]] | None = None,
) -> dict[str, Any]:
    """Return descriptive estimates and bounds; confirmatory quantities stay null.

    Explicit draw schedules are a separately labeled enumeration/testing mode,
    never represented as the protocol's seeded Monte Carlo analysis.
    """
    protocol = ClusteredProtocol.model_validate(protocol.model_dump())
    rows = [TaskOutcomes.model_validate(row.model_dump()) for row in rows]
    if not re.fullmatch(r"[a-f0-9]{40}(?:[a-f0-9]{24})?", source_commit):
        raise ValueError("source commit must be an explicit full commit identity")
    strata, keys = _prepare(protocol, rows)
    generator = random.Random(protocol.analysis_seed)
    if draw_schedule is None:
        draw_schedule = [
            [
                [generator.randrange(len(stratum["clusters"])) for _ in stratum["clusters"]]
                for stratum in strata
            ]
            for _ in range(protocol.bootstrap_replicates)
        ]
        draw_mode = "seeded_monte_carlo"
    else:
        draw_mode = "explicit_descriptive_enumeration"
        if not draw_schedule or len(draw_schedule) > 100000:
            raise ValueError("explicit draws must have a bounded nonempty replicate set")
    distributions: list[list[float | None]] = [[] for _ in keys]
    for replicate in draw_schedule:
        if len(replicate) != len(strata):
            raise ValueError("draw must preserve every declared stratum")
        drawn = []
        for stratum, indices in zip(strata, replicate, strict=True):
            if len(indices) != len(stratum["clusters"]) or any(
                type(index) is not int or not 0 <= index < len(stratum["clusters"])
                for index in indices
            ):
                raise ValueError("draw must contain exactly G whole-cluster indices")
            drawn.append({**stratum, "clusters": [stratum["clusters"][index] for index in indices]})
        for index in range(len(keys)):
            distributions[index].append(_estimate(drawn, index, protocol.weighting, "sum"))
    hypotheses = {hypothesis.hypothesis_id: hypothesis for hypothesis in protocol.hypotheses}
    results = {}
    for index, key in enumerate(keys):
        counts = []
        reasons = ["coverage_and_sufficiency_profile_unqualified"]
        missing_reasons: dict[str, int] = {}
        by_task = {row.task_id: row for row in rows}
        for membership in protocol.manifest:
            supplied = by_task.get(membership.task_id)
            pair = supplied.outcomes.get(key) if supplied else None
            pair_reasons = (
                [pair.source_reason, pair.intervention_reason]
                if pair
                else ["requested_pair_unavailable", "requested_pair_unavailable"]
            )
            for reason in pair_reasons:
                if reason is not None:
                    missing_reasons[reason] = missing_reasons.get(reason, 0) + 1
        for stratum in strata:
            statistics = [cluster["statistics"][index] for cluster in stratum["clusters"]]
            usable = sum(item["paired"] > 0 for item in statistics)
            counts.append(
                {
                    "stratum_id": stratum["stratum_id"],
                    "weight": stratum["weight"],
                    "requested_clusters": len(statistics),
                    "paired_clusters": usable,
                    "requested_tasks": sum(item["requested"] for item in statistics),
                    "paired_tasks": sum(item["paired"] for item in statistics),
                }
            )
            if stratum["weight"] > 0 and usable < 2:
                reasons.append(f"insufficient_independent_clusters:{stratum['stratum_id']}")
        point = _estimate(strata, index, protocol.weighting, "sum")
        if point is None:
            reasons.append("requested_target_unresolved_or_empty")
        distribution = distributions[index]
        # Do not cherry-pick replicates that happened to omit unresolved clusters.
        descriptive = distribution if point is not None else None
        results[key] = {
            "hypothesis": hypotheses[key].model_dump(),
            "point_estimate": point,
            "complete_pair_conditional_estimate": _estimate(
                strata, index, protocol.weighting, "sum", conditional=True
            ),
            "conditional_target": "observed_pairs_within_observed_clusters_fixed_stratum_weights",
            "identification_bounds": {
                "lower": _estimate(strata, index, protocol.weighting, "lower"),
                "upper": _estimate(strata, index, protocol.weighting, "upper"),
            },
            "counts_by_stratum": counts,
            "missing_outcome_reason_counts": missing_reasons,
            "confirmatory_interval": None,
            "marginal_p_value": None,
            "adjusted_p_value": None,
            "status": "insufficient_evidence"
            if any(reason.startswith("insufficient_") for reason in reasons)
            else "design_unqualified",
            "reasons": reasons,
            "descriptive_distribution": descriptive,
            "descriptive_distribution_reason": None
            if descriptive is not None
            else "requested_target_unresolved_no_conditional_bootstrap",
            "degenerate_descriptive_distribution": descriptive is not None
            and len(set(descriptive)) == 1,
        }
    numerical_content = [
        {
            "weight": stratum["weight"],
            "clusters": [cluster["statistics"] for cluster in stratum["clusters"]],
        }
        for stratum in strata
    ]
    return {
        "analysis_schema_version": "2",
        "method": f"paired_whole_cluster_{protocol.weighting}/1",
        "accumulation": "sorted_math_fsum/1",
        "canonicalization": "joint_cluster_and_stratum_content/1",
        "protocol_sha256": protocol.sha256,
        "input_manifest_sha256": content_hash([item.model_dump() for item in protocol.manifest]),
        "input_outcomes_sha256": content_hash([row.model_dump() for row in rows]),
        "numerical_content_sha256": content_hash(numerical_content),
        "source_commit": source_commit,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_version": platform.python_version(),
        "independence": "declared_not_proven",
        "primary_family": protocol.primary_family,
        "family_alpha": protocol.family_alpha,
        "multiplicity_status": "all_declared_slots_retained_no_qualified_marginal_tests",
        "results": results,
        "counts": {
            "requested_tasks": len(protocol.manifest),
            "requested_clusters": len({item.cluster_id for item in protocol.manifest}),
            "response_trials": sum(row.response_trials for row in rows),
            "judge_labels": sum(row.judge_labels for row in rows),
            "infrastructure_exclusions": sum(row.infrastructure_exclusions for row in rows),
            "unresolved_grades": sum(row.unresolved_grades for row in rows),
        },
        "draw_receipt": {
            "mode": draw_mode,
            "seed": protocol.analysis_seed if draw_mode == "seeded_monte_carlo" else None,
            "replicates": len(draw_schedule),
            "schedule": draw_schedule,
            "canonical_membership": [
                {
                    "stratum_id": item["stratum_id"],
                    "clusters": [
                        {"cluster_id": cluster["cluster_id"], "task_ids": cluster["task_ids"]}
                        for cluster in item["clusters"]
                    ],
                }
                for item in strata
            ],
        },
    }
