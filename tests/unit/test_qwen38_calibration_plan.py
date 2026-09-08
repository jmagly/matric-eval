"""Independent regression tests for the fail-closed calibration-v2 contract."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from matric_eval.studies import StudyProtocol
from matric_eval.studies import calibration_plan as plan_module
from matric_eval.studies.calibration_plan import CalibrationPlan

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
PLAN = ROOT / "studies/qwen38-obliteration-2026-09/calibration-v2-plan.yaml"


@pytest.fixture
def study() -> StudyProtocol:
    return StudyProtocol.from_yaml(PROTOCOL, validate_registry=False)


@pytest.fixture
def plan_data() -> dict[str, Any]:
    data = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture
def plan(plan_data: dict[str, Any], study: StudyProtocol) -> CalibrationPlan:
    return CalibrationPlan.from_dict(plan_data, study=study)


def test_committed_plan_loads_from_yaml_and_dict(
    plan: CalibrationPlan,
) -> None:
    assert CalibrationPlan.from_yaml(PLAN, PROTOCOL).canonical_sha256 == plan.canonical_sha256
    assert len(plan.canonical_sha256) == 64
    assert int(plan.canonical_sha256, 16) >= 0


def test_canonical_hash_is_independent_of_mapping_order(
    plan_data: dict[str, Any], study: StudyProtocol, plan: CalibrationPlan
) -> None:
    reordered = json.loads(json.dumps(plan_data, sort_keys=True))
    assert (
        CalibrationPlan.from_dict(reordered, study=study).canonical_sha256 == plan.canonical_sha256
    )


def test_plan_validation_does_not_mutate_input(
    plan_data: dict[str, Any], study: StudyProtocol
) -> None:
    original = copy.deepcopy(plan_data)
    CalibrationPlan.from_dict(plan_data, study=study)
    assert plan_data == original


@pytest.mark.parametrize("stage", [100, 300, 600, 1200])
def test_stage_allocations_are_complete_exact_and_nonnegative(
    plan: CalibrationPlan, study: StudyProtocol, stage: int
) -> None:
    allocations = plan.stage_allocations(stage)
    assert set(allocations) == {allocation.id for allocation in study.benchmarks}
    assert sum(allocations.values()) == stage
    assert all(type(count) is int and count > 0 for count in allocations.values())


def test_stage_allocations_are_nested_and_preserve_original_endpoints(
    plan: CalibrationPlan, study: StudyProtocol
) -> None:
    stages = [plan.stage_allocations(stage) for stage in (100, 300, 600, 1200)]
    for earlier, later in zip(stages, stages[1:]):
        assert all(earlier[key] <= later[key] for key in earlier)
    assert stages[0] == {allocation.id: allocation.pilot_samples for allocation in study.benchmarks}
    assert stages[-1] == {allocation.id: allocation.full_samples for allocation in study.benchmarks}


@pytest.mark.parametrize("stage", [0, -1, 1, 99, 101, 1000, 1500, True, 100.0, "100", None])
def test_unknown_or_mistyped_stage_is_rejected(plan: CalibrationPlan, stage: Any) -> None:
    with pytest.raises(ValueError):
        plan.stage_allocations(stage)


def _replace(data: dict[str, Any], path: tuple[str | int, ...], value: Any) -> None:
    current: Any = data
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), 1),
        (("plan_id",), "qwen38-calibration-v3"),
        (("study_id",), "different-study"),
        (("protocol_sha256",), "a" * 64),
        (("seed",), 42),
        (("seed",), True),
        (("model_pins", "qwen38-27b-source-bf16"), "a" * 40),
        (("model_pins", "qwen38-27b-e03-bf16"), "a" * 40),
        (("model_pins", "qwen38-27b-pliny-v3-bf16"), "a" * 40),
        (("stages",), [100, 300, 600, 1500]),
        (("stages",), [100, 600, 300, 1200]),
        (("stages",), [100, 300, 300, 1200]),
        (("stages", 0), 100.0),
        (("selection", "paired_ids_and_seeds"), False),
        (("selection", "nested_prefixes"), False),
        (("selection", "bfcl_dependencies_scored"), True),
        (("execution", "generation_host"), "other-host"),
        (("execution", "agentic_concurrency"), True),
        (("execution", "historical_pilot_is_confirmatory"), True),
        (("execution", "post_side_effect_retry"), "allow-without-proof"),
        (("execution", "verified_state_success_latch"), False),
        (("execution", "verified_state_success_latch"), 1),
        (("execution", "terminal_recovery_max_attempts"), 2),
        (("execution", "terminal_recovery_max_attempts"), True),
        (("execution", "terminal_watchdog_budget"), "restart-after-recovery"),
        (("execution", "terminal_timeout_submission"), "allowed"),
        (("gates", "direct_generation_valid_min"), 0.98),
        (("gates", "direct_parse_valid_min"), 0.98),
        (("gates", "agentic_trajectory_valid_min"), 0.95),
        (("gates", "direct_parse_valid_min"), float("nan")),
        (("gates", "critical_context_defects_max"), False),
        (("gates", "canary_repetitions"), 2),
        (("gates", "missing_evidence"), "go"),
        (("gates", "quality_score_is_gate"), True),
        (("failure_attribution", "owners"), ["target", "harness"]),
        (("failure_attribution", "preserve_official_reward_and_termination"), False),
        (("failure_attribution", "unknown_origin_policy"), "target-failure"),
        (("failure_attribution", "actors"), ["target-model", "simulator", "runner"]),
        (("failure_attribution", "stages"), ["generation", "termination"]),
        (("failure_attribution", "actor_stage_separate"), False),
        (("failure_attribution", "post_success_invalid_trajectory_policy"), "score-as-success"),
        (("measurement", "unknown_duration_policy"), "zero"),
        (("measurement", "attempt_count_identity"), "total-equals-fresh"),
        (("measurement", "invocation_measured_independently"), False),
        (("measurement", "recovered_results_are_fresh_latency"), True),
        (("measurement", "tokens_and_gpu_lease_hours_required"), False),
        (("amendment_replay", "pool_incompatible_runs"), True),
        (("amendment_replay", "success_seeking_retries"), True),
        (("amendment_replay", "replay_scope"), "failed-model-only"),
        (("amendment_replay", "replay_attempts_in_validity_denominator"), True),
        (("repetitions", "repeats_count_as_independent_samples"), True),
        (("repetitions", "replay_scores_enter_primary"), True),
        (("required_canaries",), []),
        (("required_artifacts",), []),
        (("allocations", "xstest-safe", 0), 11),
        (("allocations", "xstest-safe", 3), 101),
        (("allocations", "xstest-safe", 1), -1),
        (("allocations", "xstest-safe", 1), True),
        (("allocations", "xstest-safe", 1), 25.0),
        (("allocations", "xstest-safe"), [10, 25, 100]),
    ],
)
def test_contract_mutations_are_rejected(
    plan_data: dict[str, Any], study: StudyProtocol, path: tuple[str | int, ...], value: Any
) -> None:
    _replace(plan_data, path, value)
    with pytest.raises(ValueError):
        CalibrationPlan.from_dict(plan_data, study=study)


@pytest.mark.parametrize(
    "section",
    [
        None,
        "model_pins",
        "selection",
        "gates",
        "allocations",
        "execution",
        "failure_attribution",
        "measurement",
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_missing_or_extra_contract_fields_are_rejected(
    plan_data: dict[str, Any], study: StudyProtocol, section: str | None, mutation: str
) -> None:
    target = plan_data if section is None else plan_data[section]
    if mutation == "missing":
        target.pop(next(iter(target)))
    else:
        target["unexpected"] = True
    with pytest.raises(ValueError):
        CalibrationPlan.from_dict(plan_data, study=study)


def test_attribution_vocabularies_keep_owner_actor_and_stage_distinct(
    plan_data: dict[str, Any],
) -> None:
    attribution = plan_data["failure_attribution"]
    assert attribution["owners"] == [
        "target-model",
        "simulator",
        "evaluator",
        "context-runtime",
        "harness-interface",
        "mixed-uncertain",
    ]
    assert attribution["actors"] == [
        "target-model",
        "user-simulator",
        "tool-service",
        "evaluator",
        "runner",
    ]
    assert attribution["stages"] == [
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
    ]


@pytest.mark.parametrize(
    ("field", "required"),
    [
        ("required_fields", name)
        for name in (
            "invocation_wall_seconds",
            "fresh_attempt_count",
            "recovered_attempt_count",
            "total_attempt_count",
            "unknown_timing_count",
            "fresh_wall_seconds",
            "recovered_wall_seconds",
            "total_wall_seconds",
        )
    ]
    + [
        ("phase_times", name)
        for name in (
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
        )
    ],
)
def test_each_split_measurement_is_required_by_contract(
    plan_data: dict[str, Any], study: StudyProtocol, field: str, required: str
) -> None:
    plan_data["measurement"][field].remove(required)
    with pytest.raises(ValueError):
        CalibrationPlan.from_dict(plan_data, study=study)


@pytest.mark.parametrize(
    "canary",
    ["json-transport-and-malformed-tool", "terminal-bounded-recovery-and-timeout-no-submit"],
)
def test_transport_and_recovery_canaries_are_required_in_contract(
    plan_data: dict[str, Any], study: StudyProtocol, canary: str
) -> None:
    plan_data["required_canaries"].remove(canary)
    with pytest.raises(ValueError):
        CalibrationPlan.from_dict(plan_data, study=study)


def test_reallocation_with_unchanged_stage_total_is_rejected(
    plan_data: dict[str, Any], study: StudyProtocol
) -> None:
    plan_data["allocations"]["xstest-safe"][1] += 1
    plan_data["allocations"]["xstest-unsafe"][1] -= 1
    with pytest.raises(ValueError):
        CalibrationPlan.from_dict(plan_data, study=study)


def test_changed_base_protocol_is_rejected(plan_data: dict[str, Any]) -> None:
    protocol_data = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    protocol_data["study"]["title"] += " changed"
    changed = StudyProtocol.from_dict(protocol_data, validate_registry=False)
    with pytest.raises(ValueError, match="pinned base protocol"):
        CalibrationPlan.from_dict(plan_data, study=changed)


def test_plan_detaches_from_input_and_returned_allocations(
    plan_data: dict[str, Any], study: StudyProtocol
) -> None:
    plan = CalibrationPlan.from_dict(plan_data, study=study)
    digest = plan.canonical_sha256
    plan_data["seed"] = 0
    returned = plan.stage_allocations(100)
    returned["xstest-safe"] = 0
    assert plan.canonical_sha256 == digest
    assert plan.stage_allocations(100)["xstest-safe"] == 10


def _evidence(
    plan: CalibrationPlan, plan_data: dict[str, Any], study: StudyProtocol, stage: int = 1200
) -> dict[str, Any]:
    # Independent expected call counts include the required MT-Bench second turn.
    direct, agentic = {100: (85, 20), 300: (255, 60), 600: (500, 125), 1200: (1000, 250)}[stage]
    return {
        "plan_sha256": plan.canonical_sha256,
        "stage": stage,
        "models": {
            model.id: {
                "direct_attempted": direct,
                "direct_generation_valid": direct,
                "direct_parse_valid": direct,
                "agentic_attempted": agentic,
                "agentic_trajectory_valid": agentic,
                "attributed_attempts": direct + agentic,
            }
            for model in study.models
        },
        "critical_defects": {"identity": 0, "context": 0, "termination": 0},
        "canaries": {name: [True, True, True] for name in plan_data["required_canaries"]},
        "artifacts": {name: "a" * 64 for name in plan_data["required_artifacts"]},
    }


@pytest.fixture
def evidence(
    plan: CalibrationPlan, plan_data: dict[str, Any], study: StudyProtocol
) -> dict[str, Any]:
    return _evidence(plan, plan_data, study)


@pytest.mark.parametrize("stage", [100, 300, 600, 1200])
def test_gate_accepts_complete_evidence_at_each_stage(
    plan: CalibrationPlan, plan_data: dict[str, Any], study: StudyProtocol, stage: int
) -> None:
    evidence = _evidence(plan, plan_data, study, stage)
    before = copy.deepcopy(evidence)
    assert plan.evaluate_gate(evidence) == {"decision": "go", "reasons": []}
    assert evidence == before


def test_gate_accepts_exact_threshold_boundaries(
    plan: CalibrationPlan, evidence: dict[str, Any]
) -> None:
    for row in evidence["models"].values():
        row.update(
            direct_generation_valid=990, direct_parse_valid=990, agentic_trajectory_valid=245
        )
    assert plan.evaluate_gate(evidence) == {"decision": "go", "reasons": []}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("direct_generation_valid", 989),
        ("direct_parse_valid", 989),
        ("agentic_trajectory_valid", 244),
    ],
)
@pytest.mark.parametrize("model_index", [0, 1, 2])
def test_gate_rejects_one_model_below_each_threshold(
    plan: CalibrationPlan, evidence: dict[str, Any], field: str, value: int, model_index: int
) -> None:
    model = list(evidence["models"])[model_index]
    row = evidence["models"][model]
    row[field] = value
    if field == "direct_generation_valid":
        row["direct_parse_valid"] = value
    result = plan.evaluate_gate(evidence)
    assert result["decision"] == "no-go"
    assert any(model in reason and field in reason for reason in result["reasons"])


@pytest.mark.parametrize("defect", ["identity", "context", "termination"])
def test_any_critical_defect_blocks_gate(
    plan: CalibrationPlan, evidence: dict[str, Any], defect: str
) -> None:
    evidence["critical_defects"][defect] = 1
    result = plan.evaluate_gate(evidence)
    assert result["decision"] == "no-go"
    assert any(defect in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    "section", [None, "models", "critical_defects", "canaries", "artifacts", "model-counter"]
)
@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_incomplete_or_extra_gate_evidence_blocks_gate(
    plan: CalibrationPlan, evidence: dict[str, Any], section: str | None, mutation: str
) -> None:
    if section == "model-counter":
        target = next(iter(evidence["models"].values()))
    else:
        target = evidence if section is None else evidence[section]
    if mutation == "missing":
        target.pop(next(iter(target)))
    else:
        target["unexpected"] = True
    result = plan.evaluate_gate(evidence)
    assert result["decision"] == "no-go"
    assert result["reasons"]


@pytest.mark.parametrize("value", [-1, True, 1.0, "1", None, float("nan"), float("inf")])
@pytest.mark.parametrize("field", ["direct_attempted", "direct_parse_valid", "attributed_attempts"])
def test_malformed_counters_raise_value_error(
    plan: CalibrationPlan, evidence: dict[str, Any], field: str, value: Any
) -> None:
    next(iter(evidence["models"].values()))[field] = value
    with pytest.raises(ValueError):
        plan.evaluate_gate(evidence)


@pytest.mark.parametrize(
    "field", ["direct_generation_valid", "direct_parse_valid", "agentic_trajectory_valid"]
)
def test_valid_count_cannot_exceed_planned_denominator(
    plan: CalibrationPlan, evidence: dict[str, Any], field: str
) -> None:
    row = next(iter(evidence["models"].values()))
    row[field] += 1
    with pytest.raises(ValueError):
        plan.evaluate_gate(evidence)


def test_parse_count_cannot_exceed_generation_count(
    plan: CalibrationPlan, evidence: dict[str, Any]
) -> None:
    next(iter(evidence["models"].values()))["direct_generation_valid"] = 999
    with pytest.raises(ValueError, match="parses exceed"):
        plan.evaluate_gate(evidence)


@pytest.mark.parametrize("field", ["direct_attempted", "agentic_attempted", "attributed_attempts"])
@pytest.mark.parametrize("delta", [-1, 1])
def test_incomplete_or_replayed_attempt_counts_cannot_pass(
    plan: CalibrationPlan, evidence: dict[str, Any], field: str, delta: int
) -> None:
    next(iter(evidence["models"].values()))[field] += delta
    assert plan.evaluate_gate(evidence)["decision"] == "no-go"


@pytest.mark.parametrize(
    "results", [[], [True], [True, True], [True] * 4, [True, False, True], [1, 1, 1], "true", None]
)
def test_canary_requires_exactly_three_boolean_passes(
    plan: CalibrationPlan, evidence: dict[str, Any], results: Any
) -> None:
    evidence["canaries"][next(iter(evidence["canaries"]))] = results
    assert plan.evaluate_gate(evidence)["decision"] == "no-go"


@pytest.mark.parametrize(
    "canary",
    ["json-transport-and-malformed-tool", "terminal-bounded-recovery-and-timeout-no-submit"],
)
@pytest.mark.parametrize("failure", ["missing", "failed", "incomplete"])
def test_transport_and_recovery_canaries_block_release_without_three_passes(
    plan: CalibrationPlan, evidence: dict[str, Any], canary: str, failure: str
) -> None:
    if failure == "missing":
        evidence["canaries"].pop(canary)
    elif failure == "failed":
        evidence["canaries"][canary] = [True, False, True]
    else:
        evidence["canaries"][canary] = [True, True]
    assert plan.evaluate_gate(evidence)["decision"] == "no-go"


@pytest.mark.parametrize("digest", ["", "a" * 63, "a" * 65, "g" * 64, "A" * 64, 0, None])
def test_artifact_requires_canonical_sha256(
    plan: CalibrationPlan, evidence: dict[str, Any], digest: Any
) -> None:
    evidence["artifacts"][next(iter(evidence["artifacts"]))] = digest
    assert plan.evaluate_gate(evidence)["decision"] == "no-go"


def test_other_plan_identity_cannot_pass(plan: CalibrationPlan, evidence: dict[str, Any]) -> None:
    evidence["plan_sha256"] = "b" * 64
    result = plan.evaluate_gate(evidence)
    assert result["decision"] == "no-go"
    assert any("identity" in reason for reason in result["reasons"])


@pytest.mark.parametrize("stage", [True, 100.0, "100", 1500, None])
def test_invalid_gate_stage_is_rejected(
    plan: CalibrationPlan, evidence: dict[str, Any], stage: Any
) -> None:
    evidence["stage"] = stage
    with pytest.raises(ValueError):
        plan.evaluate_gate(evidence)


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_yaml_controls_are_rejected(tmp_path: Path, nested: bool) -> None:
    text = PLAN.read_text(encoding="utf-8")
    if nested:
        text = text.replace(
            "  agentic_concurrency: 1", "  agentic_concurrency: 1\n  agentic_concurrency: 1"
        )
    else:
        text += "\nseed: 1790783388\n"
    changed = tmp_path / "duplicate.yaml"
    changed.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate YAML key"):
        CalibrationPlan.from_yaml(changed, PROTOCOL)


@pytest.mark.parametrize("text", ["null", "[]", "42", "a string"])
def test_yaml_root_must_be_mapping(tmp_path: Path, text: str) -> None:
    changed = tmp_path / "invalid.yaml"
    changed.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        CalibrationPlan.from_yaml(changed, PROTOCOL)


@pytest.mark.parametrize("invalid", [None, [], "not evidence", 0])
def test_nonmapping_gate_evidence_cannot_pass(plan: CalibrationPlan, invalid: Any) -> None:
    assert plan.evaluate_gate(invalid)["decision"] == "no-go"


@pytest.mark.parametrize("value", [-1, True, 0.0, "0", None])
def test_malformed_critical_defect_count_is_rejected(
    plan: CalibrationPlan, evidence: dict[str, Any], value: Any
) -> None:
    evidence["critical_defects"]["identity"] = value
    with pytest.raises(ValueError):
        plan.evaluate_gate(evidence)


def test_non_nested_allocations_are_rejected(
    plan_data: dict[str, Any], study: StudyProtocol
) -> None:
    plan_data["allocations"]["xstest-safe"][1] = 60
    with pytest.raises(ValueError, match="nested"):
        CalibrationPlan.from_dict(plan_data, study=study)


def test_stage_total_drift_is_rejected(plan_data: dict[str, Any], study: StudyProtocol) -> None:
    plan_data["allocations"]["xstest-safe"][1] += 1
    with pytest.raises(ValueError, match="total stage"):
        CalibrationPlan.from_dict(plan_data, study=study)


def test_bfcl_category_imbalance_is_rejected(
    plan_data: dict[str, Any], study: StudyProtocol
) -> None:
    plan_data["allocations"]["bfcl-v4-agentic"][1] += 1
    plan_data["allocations"]["xstest-safe"][1] -= 1
    with pytest.raises(ValueError, match="five categories"):
        CalibrationPlan.from_dict(plan_data, study=study)


def test_cli_validates_without_running_evaluations(
    plan: CalibrationPlan, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["calibration-plan", str(PLAN), "--protocol", str(PROTOCOL)])
    plan_module.main()
    assert json.loads(capsys.readouterr().out) == {
        "status": "valid",
        "plan_sha256": plan.canonical_sha256,
    }


@pytest.mark.parametrize("go", [False, True])
def test_cli_gate_exit_status_matches_decision(
    evidence: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    go: bool,
) -> None:
    if not go:
        evidence["critical_defects"]["termination"] = 1
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["calibration-plan", str(PLAN), "--protocol", str(PROTOCOL), "--gate-evidence", str(path)],
    )
    if go:
        plan_module.main()
    else:
        with pytest.raises(SystemExit) as error:
            plan_module.main()
        assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["decision"] == ("go" if go else "no-go")
