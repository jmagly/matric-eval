"""Preregistered paired statistics for complete matched-comparison studies."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from matric_eval.models import LineageRole
from matric_eval.studies.protocol import StudyProtocol

JsonObject = dict[str, Any]
OBSERVATION_STATUSES = frozenset(
    {"observed", "model-timeout", "infrastructure-error", "judge-parse-failure"}
)


@dataclass(frozen=True)
class StudyObservation:
    """One content-free primary outcome for a model/allocation/sample tuple."""

    study_id: str
    protocol_sha256: str
    manifest_sha256: str
    model_id: str
    allocation_id: str
    sample_id: str
    metric_id: str
    status: str
    value: float | None

    @classmethod
    def from_dict(cls, data: JsonObject, line_number: int) -> StudyObservation:
        context = f"observation line {line_number}"
        strings: dict[str, str] = {}
        for key in (
            "study_id",
            "protocol_sha256",
            "manifest_sha256",
            "model_id",
            "allocation_id",
            "sample_id",
            "metric_id",
            "status",
        ):
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{context}.{key} must be a non-empty string")
            strings[key] = value.strip()
        status = strings["status"]
        if status not in OBSERVATION_STATUSES:
            raise ValueError(f"{context}.status is not a declared missingness state")
        raw_value = data.get("value")
        if isinstance(raw_value, bool) or (
            raw_value is not None and not isinstance(raw_value, (int, float))
        ):
            raise ValueError(f"{context}.value must be numeric or null")
        value = float(raw_value) if raw_value is not None else None
        if status == "model-timeout":
            if value != 0.0:
                raise ValueError(f"{context} model-timeout must have value 0")
        elif status == "observed":
            if value is None or not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{context} observed value must be finite and within [0, 1]")
        elif value is not None:
            raise ValueError(f"{context} excluded or unresolved status must have null value")
        return cls(**strings, value=value)


def load_observations(rows: Iterable[JsonObject]) -> list[StudyObservation]:
    """Parse rows and reject duplicate primary-outcome identities."""
    observations = [StudyObservation.from_dict(row, line) for line, row in enumerate(rows, 1)]
    if not observations:
        raise ValueError("observations must contain at least one row")
    keys = [
        (item.model_id, item.allocation_id, item.sample_id, item.metric_id) for item in observations
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("observations contain duplicate model/allocation/sample/metric rows")
    return observations


def _canonical_manifest_sha256(manifest: JsonObject) -> str:
    canonical = dict(manifest)
    declared = canonical.pop("manifest_sha256", None)
    actual = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared != actual:
        raise ValueError("manifest_sha256 does not match canonical manifest content")
    return actual


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot calculate a quantile of an empty sample")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _seed(root_seed: int, label: str) -> int:
    payload = f"{root_seed}\0analysis\0{label}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def bootstrap_mean_ci(
    values: Sequence[float],
    *,
    seed: int,
    replicates: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Return a deterministic percentile bootstrap interval for a mean."""
    if not values:
        raise ValueError("bootstrap values cannot be empty")
    if replicates < 1:
        raise ValueError("bootstrap replicates must be positive")
    rng = random.Random(seed)
    count = len(values)
    draws = [
        sum(values[rng.randrange(count)] for _ in range(count)) / count for _ in range(replicates)
    ]
    alpha = (1.0 - confidence) / 2.0
    return _quantile(draws, alpha), _quantile(draws, 1.0 - alpha)


def paired_bootstrap_delta_ci(
    pairs: Sequence[tuple[float, float]],
    *,
    seed: int,
    replicates: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Return a deterministic paired percentile interval for intervention-source."""
    deltas = [intervention - source for source, intervention in pairs]
    return bootstrap_mean_ci(
        deltas,
        seed=seed,
        replicates=replicates,
        confidence=confidence,
    )


def stratified_paired_bootstrap_ci(
    strata: Sequence[Sequence[tuple[float, float]]],
    *,
    seed: int,
    replicates: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Bootstrap within allocations and macro-average allocation deltas."""
    if not strata or any(not stratum for stratum in strata):
        raise ValueError("each bootstrap stratum must contain at least one pair")
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(replicates):
        stratum_means = []
        for stratum in strata:
            count = len(stratum)
            sampled = [stratum[rng.randrange(count)] for _ in range(count)]
            stratum_means.append(
                sum(intervention - source for source, intervention in sampled) / count
            )
        draws.append(sum(stratum_means) / len(stratum_means))
    alpha = (1.0 - confidence) / 2.0
    return _quantile(draws, alpha), _quantile(draws, 1.0 - alpha)


def wilson_interval(
    successes: int,
    total: int,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    """Calculate a two-sided Wilson score interval for a binomial proportion."""
    if total < 1 or successes < 0 or successes > total:
        raise ValueError("Wilson counts must satisfy 0 <= successes <= total and total > 0")
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return max(0.0, center - half), min(1.0, center + half)


def exact_mcnemar_pvalue(pairs: Sequence[tuple[float, float]]) -> float:
    """Calculate the two-sided exact McNemar binomial p-value."""
    if any(
        source not in {0.0, 1.0} or intervention not in {0.0, 1.0} for source, intervention in pairs
    ):
        raise ValueError("exact McNemar requires binary paired outcomes")
    source_only = sum(source == 1.0 and intervention == 0.0 for source, intervention in pairs)
    intervention_only = sum(source == 0.0 and intervention == 1.0 for source, intervention in pairs)
    discordant = source_only + intervention_only
    if discordant == 0:
        return 1.0
    tail = min(source_only, intervention_only)
    probability = sum(math.comb(discordant, index) for index in range(tail + 1)) / 2**discordant
    return min(1.0, 2.0 * probability)


def holm_adjust(pvalues: dict[str, float]) -> dict[str, float]:
    """Adjust one declared hypothesis family with Holm's step-down method."""
    ordered = sorted(pvalues.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, (name, pvalue) in enumerate(ordered):
        if not 0.0 <= pvalue <= 1.0:
            raise ValueError("p-values must be within [0, 1]")
        running = max(running, min(1.0, (count - rank) * pvalue))
        adjusted[name] = running
    return adjusted


def _effective_value(observation: StudyObservation) -> float | None:
    if observation.status in {"observed", "model-timeout"}:
        return observation.value
    return None


def _model_summary(
    observations: Sequence[StudyObservation],
    *,
    root_seed: int,
    label: str,
    replicates: int,
) -> JsonObject:
    values = [value for item in observations if (value := _effective_value(item)) is not None]
    infrastructure = sum(item.status == "infrastructure-error" for item in observations)
    unresolved = sum(item.status == "judge-parse-failure" for item in observations)
    timeouts = sum(item.status == "model-timeout" for item in observations)
    denominator = len(observations) - infrastructure
    if not values or denominator < 1:
        raise ValueError(f"{label} contains no analyzable observations")
    mean = sum(values) / len(values)
    binary = all(value in {0.0, 1.0} for value in values)
    if binary:
        low, high = wilson_interval(sum(value == 1.0 for value in values), len(values))
        interval_method = "wilson-95"
    else:
        low, high = bootstrap_mean_ci(
            values,
            seed=_seed(root_seed, label),
            replicates=replicates,
        )
        interval_method = "percentile-bootstrap-95"
    known_sum = sum(values)
    return {
        "selected": len(observations),
        "analyzed": len(values),
        "infrastructure_excluded": infrastructure,
        "judge_unresolved": unresolved,
        "model_timeouts": timeouts,
        "mean": mean,
        "mean_percent": 100.0 * mean,
        "interval_95": [low, high],
        "interval_method": interval_method,
        "missingness_bounds": [known_sum / denominator, (known_sum + unresolved) / denominator],
        "binary": binary,
    }


def _paired_summary(
    source: Sequence[StudyObservation],
    intervention: Sequence[StudyObservation],
    *,
    root_seed: int,
    label: str,
    replicates: int,
) -> tuple[JsonObject, list[tuple[float, float]]]:
    if [item.sample_id for item in source] != [item.sample_id for item in intervention]:
        raise ValueError(f"{label} paired sample order does not match")
    pairs: list[tuple[float, float]] = []
    lower_sum = 0.0
    upper_sum = 0.0
    infrastructure = 0
    unresolved = 0
    for source_item, intervention_item in zip(source, intervention, strict=True):
        if "infrastructure-error" in {source_item.status, intervention_item.status}:
            infrastructure += 1
            continue
        source_value = _effective_value(source_item)
        intervention_value = _effective_value(intervention_item)
        if source_value is not None and intervention_value is not None:
            delta = intervention_value - source_value
            pairs.append((source_value, intervention_value))
            lower_sum += delta
            upper_sum += delta
            continue
        unresolved += 1
        if source_value is not None:
            lower_sum += -source_value
            upper_sum += 1.0 - source_value
        elif intervention_value is not None:
            lower_sum += intervention_value - 1.0
            upper_sum += intervention_value
        else:
            lower_sum -= 1.0
            upper_sum += 1.0
    denominator = len(source) - infrastructure
    if not pairs or denominator < 1:
        raise ValueError(f"{label} contains no analyzable pairs")
    delta = sum(
        intervention_value - source_value for source_value, intervention_value in pairs
    ) / len(pairs)
    low, high = paired_bootstrap_delta_ci(
        pairs,
        seed=_seed(root_seed, label),
        replicates=replicates,
    )
    binary = all(value in {0.0, 1.0} for pair in pairs for value in pair)
    result: JsonObject = {
        "paired_analyzed": len(pairs),
        "infrastructure_excluded_pairs": infrastructure,
        "judge_unresolved_pairs": unresolved,
        "delta": delta,
        "delta_percentage_points": 100.0 * delta,
        "paired_bootstrap_interval_95": [low, high],
        "missingness_delta_bounds": [lower_sum / denominator, upper_sum / denominator],
        "binary": binary,
    }
    if binary:
        result["mcnemar_exact_p"] = exact_mcnemar_pvalue(pairs)
    return result, pairs


def _expected_ids(manifest: JsonObject) -> dict[str, list[str]]:
    allocations = manifest.get("allocations")
    if not isinstance(allocations, list):
        raise ValueError("manifest.allocations must be a list")
    expected: dict[str, list[str]] = {}
    for allocation in allocations:
        if not isinstance(allocation, dict):
            raise ValueError("manifest allocation must be an object")
        allocation_id = allocation.get("allocation_id")
        selected_ids = allocation.get("selected_ids")
        if (
            not isinstance(allocation_id, str)
            or not isinstance(selected_ids, list)
            or not all(isinstance(sample_id, str) for sample_id in selected_ids)
        ):
            raise ValueError("manifest allocation identity is malformed")
        expected[allocation_id] = selected_ids
    return expected


def analyze_observations(
    study: StudyProtocol,
    manifest: JsonObject,
    observations: Sequence[StudyObservation],
) -> JsonObject:
    """Validate a complete full matrix and produce content-free preregistered statistics."""
    if (
        manifest.get("study_id") != study.id
        or manifest.get("protocol_sha256") != study.canonical_sha256
    ):
        raise ValueError("manifest identity does not match the protocol")
    if manifest.get("cohort") != "full":
        raise ValueError("confirmatory statistical analysis requires the full cohort")
    manifest_sha256 = _canonical_manifest_sha256(manifest)
    expected_ids = _expected_ids(manifest)
    allocations = {allocation.id: allocation for allocation in study.benchmarks}
    if list(expected_ids) != [allocation.id for allocation in study.benchmarks]:
        raise ValueError("manifest allocation order does not match the protocol")
    models = {model.id: model for model in study.models}
    source_models = [
        model for model in study.models if model.lineage_role is LineageRole.UNTOUCHED_CONTROL
    ]
    if len(source_models) != 1:
        raise ValueError("analysis requires exactly one untouched control")
    source_model = source_models[0]

    grouped: dict[str, dict[str, list[StudyObservation]]] = defaultdict(lambda: defaultdict(list))
    for observation in observations:
        if (
            observation.study_id != study.id
            or observation.protocol_sha256 != study.canonical_sha256
            or observation.manifest_sha256 != manifest_sha256
        ):
            raise ValueError("observation study/protocol/manifest identity mismatch")
        if observation.model_id not in models or observation.allocation_id not in allocations:
            raise ValueError("observation references an unknown model or allocation")
        grouped[observation.allocation_id][observation.model_id].append(observation)

    replicates = int(study.raw["study"]["analysis"]["bootstrap_replicates"])
    allocation_results: dict[str, JsonObject] = {}
    paired_by_axis: dict[str, dict[str, list[list[tuple[float, float]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    holm_families: dict[str, dict[str, float]] = defaultdict(dict)
    for allocation in study.benchmarks:
        model_rows = grouped.get(allocation.id, {})
        metric_ids = {item.metric_id for rows in model_rows.values() for item in rows}
        if len(metric_ids) != 1:
            raise ValueError(f"allocation {allocation.id} must contain exactly one primary metric")
        metric_id = next(iter(metric_ids))
        ordered_by_model: dict[str, list[StudyObservation]] = {}
        model_summaries: dict[str, JsonObject] = {}
        for model in study.models:
            rows = model_rows.get(model.id, [])
            indexed = {item.sample_id: item for item in rows}
            selected_ids = expected_ids[allocation.id]
            if len(rows) != len(indexed) or set(indexed) != set(selected_ids):
                raise ValueError(
                    f"allocation {allocation.id} model {model.id} does not exactly match full IDs"
                )
            ordered = [indexed[sample_id] for sample_id in selected_ids]
            if any(item.metric_id != metric_id for item in ordered):
                raise ValueError(
                    f"allocation {allocation.id} metric identity differs across models"
                )
            ordered_by_model[model.id] = ordered
            model_summaries[model.id] = _model_summary(
                ordered,
                root_seed=study.seed,
                label=f"{allocation.id}:{metric_id}:{model.id}:absolute",
                replicates=replicates,
            )

        comparisons: dict[str, JsonObject] = {}
        for model in study.models:
            if model.id == source_model.id:
                continue
            comparison, pairs = _paired_summary(
                ordered_by_model[source_model.id],
                ordered_by_model[model.id],
                root_seed=study.seed,
                label=f"{allocation.id}:{metric_id}:{model.id}:delta",
                replicates=replicates,
            )
            comparisons[model.id] = comparison
            paired_by_axis[allocation.axis][model.id].append(pairs)
            if allocation.axis in {"capability", "agentic"}:
                paired_by_axis["capability_and_agentic"][model.id].append(pairs)
            if "mcnemar_exact_p" in comparison:
                holm_families[allocation.axis][f"{allocation.id}:{model.id}"] = float(
                    comparison["mcnemar_exact_p"]
                )
        allocation_results[allocation.id] = {
            "axis": allocation.axis,
            "metric_id": metric_id,
            "models": model_summaries,
            "comparisons_to_source": comparisons,
        }

    for axis, pvalues in holm_families.items():
        for key, adjusted in holm_adjust(pvalues).items():
            allocation_id, model_id = key.split(":", 1)
            allocation_results[allocation_id]["comparisons_to_source"][model_id][
                "mcnemar_holm_adjusted_p"
            ] = adjusted
            allocation_results[allocation_id]["comparisons_to_source"][model_id][
                "mcnemar_holm_family"
            ] = axis

    axis_results: dict[str, JsonObject] = {}
    margin = float(study.raw["study"]["analysis"]["capability_noninferiority_margin_pp"])
    for axis, by_model in paired_by_axis.items():
        comparisons: dict[str, JsonObject] = {}
        allocation_ids = [
            allocation.id
            for allocation in study.benchmarks
            if allocation.axis == axis
            or (axis == "capability_and_agentic" and allocation.axis in {"capability", "agentic"})
        ]
        model_macro_means = {
            model.id: sum(
                float(allocation_results[allocation_id]["models"][model.id]["mean"])
                for allocation_id in allocation_ids
            )
            / len(allocation_ids)
            for model in study.models
        }
        for model_id, strata in by_model.items():
            deltas = [
                sum(intervention - source for source, intervention in stratum) / len(stratum)
                for stratum in strata
            ]
            low, high = stratified_paired_bootstrap_ci(
                strata,
                seed=_seed(study.seed, f"{axis}:{model_id}:stratified-delta"),
                replicates=replicates,
            )
            comparison: JsonObject = {
                "allocation_macro_delta": sum(deltas) / len(deltas),
                "allocation_macro_delta_percentage_points": 100.0 * sum(deltas) / len(deltas),
                "paired_stratified_bootstrap_interval_95": [low, high],
            }
            missingness_bounds = [
                allocation_results[allocation_id]["comparisons_to_source"][model_id][
                    "missingness_delta_bounds"
                ]
                for allocation_id in allocation_ids
            ]
            macro_missingness_bounds = [
                sum(float(bounds[0]) for bounds in missingness_bounds) / len(missingness_bounds),
                sum(float(bounds[1]) for bounds in missingness_bounds) / len(missingness_bounds),
            ]
            comparison["missingness_delta_bounds"] = macro_missingness_bounds
            if axis == "capability":
                comparison["noninferiority_margin_percentage_points"] = margin
                comparison["noninferiority_basis"] = (
                    "minimum-of-bootstrap-lower-and-missingness-lower"
                )
                comparison["noninferior"] = 100.0 * min(low, macro_missingness_bounds[0]) > margin
            comparisons[model_id] = comparison
        axis_results[axis] = {
            "allocations": allocation_ids,
            "weighting": "equal-allocation-macro-average",
            "model_macro_means": model_macro_means,
            "comparisons_to_source": comparisons,
        }

    return {
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest_sha256,
        "cohort": "full",
        "study_seed": study.seed,
        "source_model_id": source_model.id,
        "models": [model.id for model in study.models],
        "bootstrap_replicates": replicates,
        "confidence_level": 0.95,
        "missingness_policy": {
            "infrastructure-error": "exclude-and-report",
            "model-timeout": "zero-score-and-separate-rate",
            "judge-parse-failure": "report-lower-upper-bounds",
        },
        "allocations": allocation_results,
        "axes": axis_results,
    }
