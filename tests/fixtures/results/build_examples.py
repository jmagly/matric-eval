"""Author sanitized contract examples using fixed expected values, never reducers.

Only logical IDs are calculated. Coverage/estimates below are independent fixture
expectations. Run on A100 and commit the generated JSON for both language readers.
"""

import hashlib
import json
from pathlib import Path


def missing(reason):
    return {
        "value": None,
        "reason": reason,
        "numerator": None,
        "denominator": None,
        "method": "none",
        "eligibility": {"eligible": False, "reasons": [reason]},
    }


def example():
    outcomes = [
        ("completed", "observed", 0.0, None),
        ("completed", "observed", 1.0, None),
        ("completed", "model_timeout", 0.0, "deadline"),
        ("failed", "infrastructure_error", None, "backend_unavailable"),
        ("completed", "grader_failed", None, "position_inconsistent"),
        ("cancelled", "cancelled", None, "operator_cancelled"),
        ("not_attempted", "not_attempted", None, "not_dispatched"),
        ("unknown", "legacy_unknown", None, "legacy_unverified"),
        ("completed", "unavailable", None, "metric_unavailable"),
    ]
    selection = [
        {
            "allocation_id": "allocation",
            "sample_id": f"sample-{i}",
            "trial_id": "trial-0",
            "data": {
                "partition_schema_version": "1",
                "role": "unknown",
                "row_id": f"row-{i}",
                "source_id": "synthetic/1",
                "independent_unit_id": f"unit-{i}",
            },
        }
        for i in range(9)
    ]
    metrics = {}
    observations = []
    for metric_id, units, maximum, correct in [
        ("exact/accuracy", "fraction", 1.0, 1.0),
        ("rubric/points", "points", 5.0, 5.0),
    ]:
        estimate = {
            "value": correct / 3,
            "reason": None,
            "numerator": correct,
            "denominator": 3.0,
            "method": "measured-mean/1",
            "eligibility": {"eligible": False, "reasons": ["incomplete_scope"]},
        }
        metrics[metric_id] = {
            "descriptor": {
                "metric_id": metric_id,
                "version": "1",
                "scorer_id": metric_id.split("/")[0],
                "value_kind": "continuous",
                "units": units,
                "direction": "higher",
                "minimum": 0.0,
                "maximum": maximum,
                "independent_unit": "task",
                "missingness_policy": "fixture-timeout-zero-exclude-unmeasured/1",
                "aggregation_id": "measured-mean/1",
                "timeout_value": 0.0,
            },
            "estimate": estimate,
            "scored": 3,
            "outcome_counts": {
                "observed": 2,
                "model_timeout": 1,
                "infrastructure_error": 1,
                "grader_failed": 1,
                "cancelled": 1,
                "not_attempted": 1,
                "legacy_unknown": 1,
                "unavailable": 1,
            },
        }
        for i, (execution, outcome, value, reason) in enumerate(outcomes):
            parts = [
                "run-example",
                "model-example",
                "benchmark-example",
                "allocation",
                f"sample-{i}",
                "trial-0",
                metric_id,
            ]
            identity = dict(
                zip(
                    [
                        "run_id",
                        "model_id",
                        "benchmark_id",
                        "allocation_id",
                        "sample_id",
                        "trial_id",
                        "metric_id",
                    ],
                    parts,
                    strict=True,
                )
            )
            observations.append(
                {
                    "observation_id": hashlib.sha256(
                        json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()
                    ).hexdigest(),
                    "identity": identity,
                    "attempt_id": "attempt-1",
                    "previous_attempt_id": None,
                    "accepted": True,
                    "execution": execution,
                    "outcome": outcome,
                    "value": correct if value == 1.0 else value,
                    "reason": reason,
                    "native_status": outcome,
                    "judge": {
                        "judge_id": "fixture-judge",
                        "configuration_sha256": "b" * 64,
                        "reversal_policy": "required/1",
                        "retry_policy": "max-attempts-2/1",
                        "calibration": None,
                    }
                    if metric_id == "rubric/points"
                    else None,
                    "artifacts": [
                        {
                            "uri": "fixture://native/log",
                            "sha256": "a" * 64,
                            "unavailable_reason": None,
                        }
                    ],
                }
            )
    return {
        "result_schema_version": "2",
        "run_id": "run-example",
        "model_id": "model-example",
        "created_at": "2026-09-06T00:00:00Z",
        "provenance_schema_version": "1",
        "configuration_sha256": "c" * 64,
        "execution": "partial",
        "eligibility": {"eligible": False, "reasons": ["incomplete_scope"]},
        "benchmarks": [
            {
                "benchmark_id": "benchmark-example",
                "protocol_sha256": "d" * 64,
                "manifest_sha256": "e" * 64,
                "execution": "partial",
                "eligibility": {"eligible": False, "reasons": ["incomplete_scope"]},
                "primary_metric_id": "exact/accuracy",
                "primary_estimate": metrics["exact/accuracy"]["estimate"],
                "metrics": metrics,
                "selection": selection,
                "observations": observations,
                "coverage": {
                    "requested": 9,
                    "attempted": 7,
                    "terminal": 7,
                    "completed": 5,
                    "failed": 1,
                    "cancelled": 1,
                    "not_attempted": 1,
                    "unknown": 1,
                },
                "artifacts": [],
            }
        ],
        "aggregation_id": None,
        "overall_estimate": missing("aggregation_undeclared"),
        "artifacts": [],
    }


if __name__ == "__main__":
    path = Path(__file__).parent / "v2"
    path.mkdir(exist_ok=True)
    (path / "mixed.json").write_text(json.dumps(example(), indent=2, allow_nan=False) + "\n")
    # Both consumers use exactly the same shared role identifiers and version.
    roles = [
        {
            "partition_schema_version": "1",
            "role": role,
            "row_id": "synthetic-row",
            "source_id": "synthetic/1",
            "independent_unit_id": "synthetic-unit",
        }
        for role in [
            "development",
            "validation",
            "calibration",
            "final_test",
            "training",
            "unknown",
        ]
    ]
    (path.parent / "partition-roles.json").write_text(
        json.dumps({"calibration_input": roles, "export_input": roles}, indent=2) + "\n"
    )
