"""Versioned execution contract and fail-closed gates for Qwen calibration v2.

This validates plans/evidence only: it never starts a runner or changes rewards.
Changing a locked control requires a new contract version, not a looser v2 file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from matric_eval.studies.protocol import StudyProtocol

STUDY_ID = "qwen38-obliteration-2026-09"
PROTOCOL_SHA256 = "01804a01700335f2b14186c3ead87c71590ff8af1707c70b55a85f42cf26c833"
SEED = 1790783388
MODEL_PINS = {
    "qwen38-27b-source-bf16": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
    "qwen38-27b-e03-bf16": "95583d3ee44c40e840cb0ceb7106d12a1087d52f",
    "qwen38-27b-pliny-v3-bf16": "a58c3b53b3ce71551eafde2ed5ec8df48e0f4ff8",
}
STAGES = [100, 300, 600, 1200]
ALLOCATIONS = {
    "xstest-safe": [10, 25, 50, 100],
    "xstest-unsafe": [5, 25, 50, 100],
    "or-bench-hard-benign": [10, 40, 75, 150],
    "strongreject-harmful": [15, 25, 50, 100],
    "ifeval": [10, 30, 62, 125],
    "mmlu-pro": [15, 50, 100, 200],
    "livecodebench": [10, 30, 63, 125],
    "mtbench": [5, 15, 25, 50],
    "bfcl-v4-agentic": [5, 25, 50, 100],
    "tau3-bench": [10, 25, 50, 100],
    "terminal-bench-2.1": [5, 10, 25, 50],
}
CANARIES = [
    "identity-and-effective-runtime",
    "context-boundary-with-output-reserve",
    "terminal-reference-solution-verifier",
    "terminal-invalid-solution-verifier",
    "terminal-command-and-completion-roundtrip",
    "json-transport-and-malformed-tool",
    "terminal-bounded-recovery-and-timeout-no-submit",
    "tau-valid-user-message",
    "tau-stop-transfer-out-of-scope",
    "tau-post-success-termination",
    "tau-user-tool-ownership-and-persona",
    "bfcl-five-backends-and-dependency-closure",
]
LOCKED_CONTROLS: dict[str, Any] = {
    "selection": {
        "algorithm": "allocation-declared-v1",
        "key_format": "{seed}\\0{allocation_id}\\0{canonical_sample_id}",
        "generation_seed_algorithm": "sha256-uint32-v1",
        "paired_ids_and_seeds": True,
        "nested_prefixes": True,
        "identical_ordered_request_batches": True,
        "bfcl_category_round_robin": True,
        "bfcl_dependencies_scored": False,
    },
    "execution": {
        "generation_host": "a100",
        "direct_mode": "offline-batch",
        "agentic_mode": "serialized-online",
        "agentic_concurrency": 1,
        "model_gpu_assignment": "randomized-three-block-crossover",
        "stage_release": "all-models-paired-gate-and-operator-approval",
        "effective_runtime_receipt_required": True,
        "agentic_amendment_required": True,
        "historical_pilot_is_confirmatory": False,
        "post_side_effect_retry": "require-idempotency-proof",
        "verified_state_success_latch": True,
        "terminal_recovery_max_attempts": 1,
        "terminal_watchdog_budget": "pinned-task-wall-clock-including-recovery",
        "terminal_timeout_submission": "forbidden",
    },
    "gates": {
        "critical_identity_defects_max": 0,
        "critical_context_defects_max": 0,
        "critical_termination_defects_max": 0,
        "direct_generation_valid_min": 0.99,
        "direct_parse_valid_min": 0.99,
        "agentic_trajectory_valid_min": 0.98,
        "denominator": "all-planned-first-attempts-per-model-per-stage",
        "missing_evidence": "no-go",
        "canary_repetitions": 3,
        "canaries_must_all_pass": True,
        "terminal_canaries_model_independent": True,
        "quality_score_is_gate": False,
        "outcome_adaptive_threshold_changes": False,
    },
    "failure_attribution": {
        "required_for_every_attempt": True,
        "owners": [
            "target-model",
            "simulator",
            "evaluator",
            "context-runtime",
            "harness-interface",
            "mixed-uncertain",
        ],
        "actors": ["target-model", "user-simulator", "tool-service", "evaluator", "runner"],
        "stages": [
            "setup",
            "context-budget",
            "transport",
            "generation",
            "parse",
            "tool-execution",
            "simulation",
            "verification",
            "termination",
            "recovery",
        ],
        "actor_stage_separate": True,
        "preserve_official_reward_and_termination": True,
        "infrastructure_quality_policy": "exclude-paired-and-report-bounds",
        "target_error_quality_policy": "failure-and-separate-rate",
        "unknown_origin_policy": "unresolved-and-report-bounds",
        "post_success_timeout_policy": "retain-official-zero-and-secondary-state-evidence",
        "post_success_invalid_trajectory_policy": "analytic-invalid-exclude-paired",
        "retain_partial_trace_and_exception": True,
    },
    "measurement": {
        "required_fields": [
            "invocation_wall_seconds",
            "fresh_attempt_count",
            "recovered_attempt_count",
            "total_attempt_count",
            "unknown_timing_count",
            "fresh_wall_seconds",
            "recovered_wall_seconds",
            "total_wall_seconds",
        ],
        "phase_times": [
            "queue",
            "model-load",
            "context-preparation",
            "generation",
            "tool",
            "simulator",
            "judge",
            "setup",
            "verifier",
            "prerequisite",
            "replay",
            "recovery",
        ],
        "unknown_duration_policy": "null-with-explicit-count",
        "attempt_count_identity": "total-equals-fresh-plus-recovered",
        "invocation_measured_independently": True,
        "recovered_results_are_fresh_latency": False,
        "tokens_and_gpu_lease_hours_required": True,
    },
    "amendment_replay": {
        "seal_before_execution": True,
        "changes_require_new_identity": True,
        "replay_scope": "all-models-for-every-affected-task-or-batch",
        "preserve_old_evidence": True,
        "pool_incompatible_runs": False,
        "reuse_unaffected_requires_hash_identity": True,
        "success_seeking_retries": False,
        "outcome_adaptive_replacement": False,
        "replay_attempts_in_validity_denominator": False,
    },
    "repetitions": {
        "primary_trials_per_task": 1,
        "deterministic_scorer_passes": 2,
        "same_seed_direct_replay": "complete-identical-request-batches",
        "same_seed_agentic_replay_tasks": 5,
        "alternate_seed_tasks": 20,
        "selection": "hash-ranked-before-execution",
        "replicate_seed_domain": "qwen38-calibration-v2-replicate",
        "repeats_count_as_independent_samples": False,
        "replay_scores_enter_primary": False,
    },
}
REQUIRED_ARTIFACTS = [
    "ordered-manifest-and-hash",
    "model-runtime-and-gpu-lease-receipts",
    "execution-schedule",
    "attempt-and-failure-attribution-ledger",
    "canary-evidence",
    "paired-coverage-and-missingness-report",
    "scorer-repeat-and-judge-adjudication-report",
    "timing-and-cost-forecast",
]


def _equal(actual: Any, expected: Any, label: str) -> None:
    """JSON equality with exact scalar types (True must not equal 1)."""
    if type(actual) is not type(expected):
        raise ValueError(f"{label} has an invalid type")
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError(f"{label} has missing or extra fields")
        for key, value in expected.items():
            _equal(actual[key], value, f"{label}.{key}")
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"{label} has an invalid length")
        for index, value in enumerate(expected):
            _equal(actual[index], value, f"{label}[{index}]")
    elif actual != expected:
        raise ValueError(f"{label} must be {expected!r}")


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


# PyYAML is untyped in the existing dependency set.
class _UniqueLoader(yaml.SafeLoader):  # type: ignore[misc]
    """Do not silently replace repeated YAML controls, including merge keys."""


def _unique_mapping(loader: Any, node: Any) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


class CalibrationPlan:
    """Validated, detached plan; all public data returned as independent copies."""

    def __init__(self, serialized: str):
        self._serialized = serialized

    @classmethod
    def from_dict(cls, data: dict[str, Any], study: StudyProtocol) -> CalibrationPlan:
        if study.id != STUDY_ID or study.canonical_sha256 != PROTOCOL_SHA256:
            raise ValueError("calibration-v2 requires the pinned base protocol")
        expected = {
            "schema_version": "1",
            "plan_id": "qwen38-calibration-v2",
            "study_id": STUDY_ID,
            "protocol_sha256": PROTOCOL_SHA256,
            "seed": SEED,
            "model_pins": MODEL_PINS,
            "stages": STAGES,
            **LOCKED_CONTROLS,
            "required_canaries": CANARIES,
            "required_artifacts": REQUIRED_ARTIFACTS,
        }
        if not isinstance(data, dict) or set(data) != {*expected, "allocations"}:
            raise ValueError("plan has missing or extra fields")
        for key, value in expected.items():
            _equal(data[key], value, key)
        allocations = data["allocations"]
        if not isinstance(allocations, dict) or set(allocations) != {
            item.id for item in study.benchmarks
        }:
            raise ValueError("allocations must cover exactly the base protocol")
        for item in study.benchmarks:
            counts = allocations[item.id]
            if not isinstance(counts, list) or len(counts) != len(STAGES):
                raise ValueError(f"allocations.{item.id} requires four stage counts")
            for count in counts:
                _count(count, f"allocations.{item.id}")
            if counts[0] != item.pilot_samples or counts[-1] != item.full_samples:
                raise ValueError(f"allocations.{item.id} changes the fixed 100/1200 allocation")
            if any(a > b for a, b in zip(counts, counts[1:])):
                raise ValueError(f"allocations.{item.id} must be nested")
        for index, stage in enumerate(STAGES):
            if sum(counts[index] for counts in allocations.values()) != stage:
                raise ValueError(f"allocations do not total stage {stage}")
        if any(count % 5 for count in allocations["bfcl-v4-agentic"]):
            raise ValueError("BFCL stages must balance its five categories")
        _equal(allocations, ALLOCATIONS, "allocations")
        return cls(json.dumps(data, sort_keys=True, separators=(",", ":")))

    @classmethod
    def from_yaml(cls, plan_path: Path, protocol_path: Path) -> CalibrationPlan:
        return cls.from_dict(
            yaml.load(plan_path.read_text(encoding="utf-8"), Loader=_UniqueLoader),
            StudyProtocol.from_yaml(protocol_path, validate_registry=False),
        )

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self._serialized.encode()).hexdigest()

    def stage_allocations(self, stage: int) -> dict[str, int]:
        if type(stage) is not int or stage not in STAGES:
            raise ValueError("stage must be 100, 300, 600 or 1200")
        index = STAGES.index(stage)
        data = json.loads(self._serialized)
        return {key: counts[index] for key, counts in data["allocations"].items()}

    def evaluate_gate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        """Return no-go for absent evidence; reject structurally invalid evidence.

        Counts are cumulative first attempts. Replays cannot improve denominators.
        This mechanical gate is necessary, not sufficient: operator approval and
        hash-verifying producers of the referenced artifacts are still required.
        """
        keys = {"plan_sha256", "stage", "models", "critical_defects", "canaries", "artifacts"}
        if not isinstance(evidence, dict) or set(evidence) != keys:
            return {"decision": "no-go", "reasons": ["missing or extra gate evidence"]}
        reasons: list[str] = []
        if evidence["plan_sha256"] != self.canonical_sha256:
            reasons.append("plan identity mismatch")
        allocations = self.stage_allocations(evidence["stage"])
        agentic = sum(
            allocations[key] for key in ("bfcl-v4-agentic", "tau3-bench", "terminal-bench-2.1")
        )
        # MT-Bench has a second direct call; every required call and parse counts.
        direct = evidence["stage"] - agentic + allocations["mtbench"]
        models = evidence["models"]
        if not isinstance(models, dict) or set(models) != set(MODEL_PINS):
            reasons.append("missing or extra model evidence")
        else:
            fields = {
                "direct_attempted",
                "direct_generation_valid",
                "direct_parse_valid",
                "agentic_attempted",
                "agentic_trajectory_valid",
                "attributed_attempts",
            }
            for model, row in models.items():
                if not isinstance(row, dict) or set(row) != fields:
                    reasons.append(f"{model}: incomplete counters")
                    continue
                counts = {key: _count(value, f"{model}.{key}") for key, value in row.items()}
                if counts["direct_attempted"] != direct or counts["agentic_attempted"] != agentic:
                    reasons.append(f"{model}: incomplete first-attempt coverage")
                if counts["attributed_attempts"] != direct + agentic:
                    reasons.append(f"{model}: incomplete failure attribution")
                for field, total, percent in (
                    ("direct_generation_valid", direct, 99),
                    ("direct_parse_valid", direct, 99),
                    ("agentic_trajectory_valid", agentic, 98),
                ):
                    if counts[field] > total:
                        raise ValueError(f"{model}.{field} exceeds planned denominator")
                    if counts[field] * 100 < percent * total:
                        reasons.append(f"{model}: {field} below {percent}%")
                if counts["direct_parse_valid"] > counts["direct_generation_valid"]:
                    raise ValueError(f"{model}: valid parses exceed valid generations")
        defects = evidence["critical_defects"]
        if not isinstance(defects, dict) or set(defects) != {"identity", "context", "termination"}:
            reasons.append("missing critical-defect evidence")
        else:
            for key, value in defects.items():
                if _count(value, key):
                    reasons.append(f"critical {key} defect")
        canaries = evidence["canaries"]
        if not isinstance(canaries, dict) or set(canaries) != set(CANARIES):
            reasons.append("missing or extra canary evidence")
        else:
            for key, results in canaries.items():
                if (
                    not isinstance(results, list)
                    or len(results) != 3
                    or any(result is not True for result in results)
                ):
                    reasons.append(f"{key}: three passing repetitions required")
        artifacts = evidence["artifacts"]
        if not isinstance(artifacts, dict) or set(artifacts) != set(REQUIRED_ARTIFACTS):
            reasons.append("missing or extra artifact evidence")
        else:
            for key, digest in artifacts.items():
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(char not in "0123456789abcdef" for char in digest)
                ):
                    reasons.append(f"{key}: invalid artifact SHA-256")
        return {"decision": "no-go" if reasons else "go", "reasons": reasons}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--gate-evidence", type=Path)
    args = parser.parse_args()
    plan = CalibrationPlan.from_yaml(args.plan, args.protocol)
    result = {"status": "valid", "plan_sha256": plan.canonical_sha256}
    if args.gate_evidence:
        result.update(plan.evaluate_gate(json.loads(args.gate_evidence.read_text())))
    print(json.dumps(result, sort_keys=True))
    if result.get("decision") == "no-go":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
