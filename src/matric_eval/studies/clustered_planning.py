"""Paired known-variance normal planning approximations, not achieved power."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

import yaml

from matric_eval.studies.clustered_protocol import ClusteredProtocol


def _finite(value: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("finite non-boolean numerical assumption required")


def binary_paired_variance(
    delta: float,
    discordance: float,
    *,
    source_rate: float | None = None,
    intervention_rate: float | None = None,
) -> float:
    _finite(delta)
    _finite(discordance)
    if not abs(delta) <= discordance <= 1:
        raise ValueError("paired probabilities require |delta| <= discordance <= 1")
    if (source_rate is None) != (intervention_rate is None):
        raise ValueError("supply both marginal rates or neither")
    if source_rate is not None and intervention_rate is not None:
        _finite(source_rate)
        _finite(intervention_rate)
        if (
            not 0 <= source_rate <= 1
            or not 0 <= intervention_rate <= 1
            or not math.isclose(intervention_rate - source_rate, delta, abs_tol=1e-12)
        ):
            raise ValueError("marginals contradict the paired difference")
        joint_success = (source_rate + intervention_rate - discordance) / 2
        joint_failure = 1 - discordance - joint_success
        if min(joint_success, joint_failure) < -1e-12:
            raise ValueError("infeasible joint binary probabilities")
    return discordance - delta * delta


def design_effect(tasks_per_cluster: int, correlation: float) -> float:
    if type(tasks_per_cluster) is not int or tasks_per_cluster < 1:
        raise ValueError("positive integer cluster size required")
    _finite(correlation)
    # The first approximation deliberately declines negative-rho power gains;
    # positive-semidefinite exchangeability alone need not ensure binary feasibility.
    if not 0 <= correlation <= 1:
        raise ValueError("this planning profile supports correlation in [0,1] only")
    return 1 + (tasks_per_cluster - 1) * correlation


def planning_sensitivity(protocol: ClusteredProtocol) -> dict[str, Any]:
    protocol = ClusteredProtocol.model_validate(protocol.model_dump())
    family_size = len(protocol.primary_family)
    alpha = protocol.family_alpha / family_size
    normal = NormalDist()
    rows = []
    for hypothesis in protocol.hypotheses:
        if not hypothesis.primary:
            continue
        critical = normal.inv_cdf(
            1 - alpha / (2 if hypothesis.direction == "two_sided_difference" else 1)
        )
        power_critical = normal.inv_cdf(protocol.planning.target_power)
        if hypothesis.direction == "two_sided_difference":
            distance = abs(hypothesis.planning_true_difference)
        else:
            assert hypothesis.noninferiority_margin is not None
            distance = hypothesis.planning_true_difference - hypothesis.noninferiority_margin
        if distance <= 0:
            raise ValueError("assumed effect must exceed the signed noninferiority null margin")
        for variance in protocol.planning.sensitivity_variances:
            for correlation in protocol.planning.sensitivity_correlations:
                effect = design_effect(protocol.planning.tasks_per_cluster, correlation)
                variance_scale = variance * effect
                precision_tasks = (
                    critical**2 * variance_scale / protocol.planning.target_half_width**2
                )
                power_tasks = (critical + power_critical) ** 2 * variance_scale / distance**2
                if not math.isfinite(precision_tasks) or not math.isfinite(power_tasks):
                    raise ValueError("planning calculation overflow")
                rows.append(
                    {
                        "hypothesis_id": hypothesis.hypothesis_id,
                        "units": hypothesis.units,
                        "paired_difference_variance": variance,
                        "paired_difference_correlation": correlation,
                        "equal_tasks_per_cluster": protocol.planning.tasks_per_cluster,
                        "design_effect": effect,
                        "sidedness": hypothesis.direction,
                        "assumed_effect": hypothesis.planning_true_difference,
                        "practical_effect_target": hypothesis.practical_effect,
                        "null_margin": hypothesis.noninferiority_margin,
                        "planning_distance": distance,
                        "precision_clusters_approx": max(
                            1, math.ceil(precision_tasks / protocol.planning.tasks_per_cluster)
                        ),
                        "power_clusters_approx": max(
                            1, math.ceil(power_tasks / protocol.planning.tasks_per_cluster)
                        ),
                    }
                )
    return {
        "planning_schema_version": "1",
        "method": "paired_known_variance_equal_size_normal_approximation/1",
        "protocol_sha256": protocol.sha256,
        "assumptions": [
            *protocol.planning.assumptions,
            "known common paired-difference variance",
            "independent equal-sized clusters with exchangeable paired-difference correlation",
            "no informative nonresponse or finite-population correction",
            "equal-size planning approximation does not estimate unequal-size ratio variance",
        ],
        "family_size": family_size,
        "family_alpha": protocol.family_alpha,
        "planning_alpha": alpha,
        "multiplicity": "Bonferroni planning bound, not realized Holm cutoff",
        "target_power": protocol.planning.target_power,
        "target_half_width": protocol.planning.target_half_width,
        "rows": rows,
        "achieved_power": None,
        "coverage_qualified": False,
    }


def frozen_114_sensitivity(protocol_path: Path) -> dict[str, Any]:
    """Read-only, separate allocation limitation grid; never modifies frozen data."""
    from matric_eval.studies.protocol import StudyProtocol

    raw = protocol_path.read_bytes()
    study = StudyProtocol.from_dict(yaml.safe_load(raw))
    normal = NormalDist()
    z = normal.inv_cdf(0.975)
    power_critical = normal.inv_cdf(0.8)
    rows = [
        {
            "allocation_id": item.id,
            "full_tasks": item.full_samples,
            "assumed_paired_difference_variance": variance,
            "normal_95_half_width": z * math.sqrt(variance / item.full_samples),
            "normal_two_sided_80_detectable_effect": (z + power_critical)
            * math.sqrt(variance / item.full_samples),
        }
        for item in study.benchmarks
        for variance in (1.0, 0.5, 0.1)
    ]
    return {
        "planning_schema_version": "1",
        "source_protocol_sha256": hashlib.sha256(raw).hexdigest(),
        "target": "allocation_limited_sensitivity_only",
        "assumptions": [
            "independent paired tasks",
            "unadjusted known-variance normal approximation",
            "discordance and clustering are unknown",
            "variance 0.1/0.5 scenarios correspond to assumed binary discordance at delta zero",
        ],
        "pilot_total": sum(item.pilot_samples for item in study.benchmarks),
        "full_total": sum(item.full_samples for item in study.benchmarks),
        "rows": rows,
        "frozen_noninferiority_qualified": False,
        "observed_outcomes_used": False,
    }
