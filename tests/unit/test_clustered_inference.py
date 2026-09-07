"""Independent small-design oracles from the separately reviewed #127 design."""

import copy
import hashlib
import multiprocessing
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from matric_eval.studies.clustered_inference import TaskOutcomes, analyze_clustered
from matric_eval.studies.clustered_planning import (
    binary_paired_variance,
    design_effect,
    frozen_114_sensitivity,
    planning_sensitivity,
)
from matric_eval.studies.clustered_protocol import (
    ClusteredProtocol,
    freeze_protocol,
    legacy_compatibility_view,
)
from matric_eval.studies.clustered_stopping import StoppingEvent, StoppingLedger

COMMIT = "a" * 40
ROOT = Path(__file__).resolve().parents[2]


def protocol_data(weighting: str = "equal_cluster") -> dict[str, Any]:
    return {
        "protocol_version": "2",
        "study_id": "synthetic",
        "estimand": "intervention minus source mean difference",
        "target_population": "declared synthetic frame",
        "sampling_frame_sha256": "b" * 64,
        "target": "superpopulation",
        "sampling": "equal_probability_exchangeable_clusters",
        "independence_status": "declared_not_proven",
        "independent_unit": "underlying problem family",
        "task_unit": "problem variant",
        "weighting": weighting,
        "within_cluster_weights": "equal_task",
        "within_task_rule": "fixed task summary/1",
        "repetition_interpretation": "fixed generation/judge budget, repetitions not independent units",
        "pairing_keys": ["task_id"],
        "trial_alignment": "fixed aligned response budget/1",
        "hypotheses": [
            {
                "hypothesis_id": "primary",
                "source_model": "source",
                "intervention_model": "intervention",
                "metric_id": "score",
                "metric_version": "1",
                "units": "fraction",
                "minimum": 0.0,
                "maximum": 1.0,
                "primary": True,
                "direction": "two_sided_difference",
                "practical_effect": 0.1,
                "planning_true_difference": 0.1,
                "noninferiority_margin": None,
            }
        ],
        "primary_family": ["primary"],
        "family_alpha": 0.05,
        "multiplicity": "holm_declared_tests_unavailable",
        "strata": [{"stratum_id": "s", "weight": 1.0, "weight_source": "explicit macro target"}],
        "manifest": [
            {"task_id": str(index), "cluster_id": "A" if index == 0 else "B", "stratum_id": "s"}
            for index in range(4)
        ],
        "missingness": "requested_target_bounds_complete_pair_conditional/1",
        "inference_method": "paired_whole_cluster_percentile/1",
        "confidence_level": 0.95,
        "bootstrap_replicates": 20,
        "analysis_seed": 7,
        "sufficiency_rule": "no coverage-qualified minimum supplied",
        "qualification": "unqualified",
        "planning": {
            "assumptions": ["synthetic sensitivity only"],
            "sensitivity_variances": [0.1, 1.0],
            "sensitivity_correlations": [0.0, 1.0],
            "tasks_per_cluster": 4,
            "target_power": 0.8,
            "target_half_width": 0.1,
        },
        "task_budget": 4,
        "cluster_budget": 2,
        "stopping_rule": "fixed_budget/1",
        "outcome_access": "after_enrollment_closed",
        "deviation_log_location": "stopping.jsonl",
    }


def outcomes(deltas: list[float | None]) -> list[TaskOutcomes]:
    return [
        TaskOutcomes.model_validate(
            {
                "task_id": str(index),
                "outcomes": {
                    "primary": {
                        "source": max(0.0, -delta) if delta is not None else None,
                        "intervention": max(0.0, delta) if delta is not None else None,
                        "source_reason": None if delta is not None else "infrastructure_error",
                        "intervention_reason": None if delta is not None else "grader_failed",
                    }
                },
                "response_trials": 2,
                "judge_labels": 1,
                "infrastructure_exclusions": int(delta is None),
                "unresolved_grades": int(delta is None),
            }
        )
        for index, delta in enumerate(deltas)
    ]


@pytest.mark.parametrize(
    "weighting,point,distribution",
    [("equal_cluster", 0.0, [-1.0, 0.0, 0.0, 1.0]), ("equal_task", -0.5, [-1.0, -0.5, -0.5, 1.0])],
)
def test_hand_enumerated_whole_cluster_oracle(
    weighting: str, point: float, distribution: list[float]
) -> None:
    protocol = ClusteredProtocol.model_validate(protocol_data(weighting))
    report = analyze_clustered(
        protocol,
        outcomes([1, -1, -1, -1]),
        source_commit=COMMIT,
        draw_schedule=[[[0, 0]], [[0, 1]], [[1, 0]], [[1, 1]]],
    )
    result = report["results"]["primary"]
    assert result["point_estimate"] == point
    assert sorted(result["descriptive_distribution"]) == distribution
    assert result["confirmatory_interval"] is None
    assert result["marginal_p_value"] is None
    receipt = report["draw_receipt"]
    assert sorted(
        len(cluster["task_ids"]) for cluster in receipt["canonical_membership"][0]["clusters"]
    ) == [1, 3]
    assert receipt["mode"] == "explicit_descriptive_enumeration"


def test_joint_content_and_stratum_label_invariance_with_diagnostic_repetitions() -> None:
    data = protocol_data()
    data["strata"] = [
        {"stratum_id": "s", "weight": 0.4, "weight_source": "frame"},
        {"stratum_id": "t", "weight": 0.6, "weight_source": "frame"},
    ]
    for index, member in enumerate(data["manifest"]):
        member.update(cluster_id=f"c{index}", stratum_id="s" if index < 2 else "t")
    data["cluster_budget"] = 4
    second = {
        **data["hypotheses"][0],
        "hypothesis_id": "secondary",
        "primary": False,
        "metric_id": "other",
    }
    data["hypotheses"].append(second)
    rows = outcomes([0, 0, 1, -1])
    extra = outcomes([1, -1, 0, 0])
    for row, auxiliary in zip(rows, extra, strict=True):
        row.outcomes["secondary"] = auxiliary.outcomes["primary"]
    original = analyze_clustered(ClusteredProtocol.model_validate(data), rows, source_commit=COMMIT)
    renamed = copy.deepcopy(data)
    for member in renamed["manifest"]:
        member.update(
            task_id="renamed-" + member["task_id"],
            cluster_id="renamed-" + member["cluster_id"],
            stratum_id="renamed-" + member["stratum_id"],
        )
    for stratum in renamed["strata"]:
        stratum["stratum_id"] = "renamed-" + stratum["stratum_id"]
    renamed["strata"].reverse()
    renamed["manifest"].reverse()
    renamed["hypotheses"].reverse()
    for row in rows:
        row.task_id = "renamed-" + row.task_id
        row.outcomes = dict(reversed(list(row.outcomes.items())))
        row.response_trials *= 100
        row.judge_labels *= 100
    changed = analyze_clustered(
        ClusteredProtocol.model_validate(renamed), list(reversed(rows)), source_commit=COMMIT
    )
    assert original["numerical_content_sha256"] == changed["numerical_content_sha256"]
    assert original["draw_receipt"]["schedule"] == changed["draw_receipt"]["schedule"]
    for key in ("primary", "secondary"):
        assert (
            original["results"][key]["descriptive_distribution"]
            == changed["results"][key]["descriptive_distribution"]
        )
    assert original["counts"]["requested_clusters"] == changed["counts"]["requested_clusters"] == 4
    assert changed["counts"]["response_trials"] == 100 * original["counts"]["response_trials"]
    assert original["protocol_sha256"] != changed["protocol_sha256"]


def test_unresolved_requested_target_keeps_denominator_and_bounds() -> None:
    data = protocol_data("equal_task")
    data["manifest"] = data["manifest"][:2]
    data["task_budget"] = 2
    report = analyze_clustered(
        ClusteredProtocol.model_validate(data), outcomes([1, None]), source_commit=COMMIT
    )
    result = report["results"]["primary"]
    assert result["point_estimate"] is None
    assert result["complete_pair_conditional_estimate"] == 1
    assert result["identification_bounds"] == {"lower": 0.0, "upper": 1.0}
    assert result["descriptive_distribution"] is None
    assert result["counts_by_stratum"][0]["requested_tasks"] == 2
    assert result["counts_by_stratum"][0]["paired_tasks"] == 1
    assert report["counts"]["infrastructure_exclusions"] == 1


@pytest.mark.parametrize(
    "source,intervention,bounds",
    [(0.25, None, (-0.25, 0.75)), (None, 0.25, (-0.75, 0.25)), (None, None, (-1.0, 1.0))],
)
def test_one_side_missing_bounds(
    source: float | None, intervention: float | None, bounds: tuple[float, float]
) -> None:
    data = protocol_data()
    data.update(manifest=data["manifest"][:1], task_budget=1, cluster_budget=1)
    rows = outcomes([None])
    pair = rows[0].outcomes["primary"]
    pair.source, pair.intervention = source, intervention
    pair.source_reason = "unknown" if source is None else None
    pair.intervention_reason = "unknown" if intervention is None else None
    result = analyze_clustered(ClusteredProtocol.model_validate(data), rows, source_commit=COMMIT)[
        "results"
    ]["primary"]
    assert result["identification_bounds"] == {"lower": bounds[0], "upper": bounds[1]}
    assert result["confirmatory_interval"] is None


def test_one_cluster_repetition_degeneracy_zero_stratum_and_empty_scope() -> None:
    data = protocol_data()
    for member in data["manifest"]:
        member["cluster_id"] = "single"
    data["cluster_budget"] = 1
    rows = outcomes([1, 1, 1, 1])
    rows[0].judge_labels = 10000
    result = analyze_clustered(ClusteredProtocol.model_validate(data), rows, source_commit=COMMIT)[
        "results"
    ]["primary"]
    assert result["status"] == "insufficient_evidence"
    assert result["confirmatory_interval"] is None
    assert result["degenerate_descriptive_distribution"]
    data = protocol_data()
    data["strata"].append(
        {"stratum_id": "zero", "weight": 0.0, "weight_source": "explicit excluded domain"}
    )
    data["manifest"].append({"task_id": "4", "cluster_id": "zero", "stratum_id": "zero"})
    data.update(task_budget=5, cluster_budget=3)
    result = analyze_clustered(
        ClusteredProtocol.model_validate(data), outcomes([1, -1, -1, -1]), source_commit=COMMIT
    )["results"]["primary"]
    assert result["point_estimate"] == 0
    assert not any(reason.endswith(":zero") for reason in result["reasons"])
    data.update(manifest=[], task_budget=0, cluster_budget=0)
    result = analyze_clustered(ClusteredProtocol.model_validate(data), [], source_commit=COMMIT)[
        "results"
    ]["primary"]
    assert result["point_estimate"] is None and result["confirmatory_interval"] is None


def test_family_missing_slots_and_changed_membership_are_explicit() -> None:
    data = protocol_data()
    data["hypotheses"].append({**data["hypotheses"][0], "hypothesis_id": "missing"})
    data["primary_family"].append("missing")
    result = analyze_clustered(
        ClusteredProtocol.model_validate(data), outcomes([1, -1, -1, -1]), source_commit=COMMIT
    )
    assert result["primary_family"] == ["primary", "missing"]
    assert result["results"]["missing"]["marginal_p_value"] is None
    assert result["results"]["missing"]["point_estimate"] is None
    changed = copy.deepcopy(data)
    for member in changed["manifest"]:
        member["cluster_id"] = "A"
    changed["cluster_budget"] = 1
    altered = analyze_clustered(
        ClusteredProtocol.model_validate(changed), outcomes([1, -1, -1, -1]), source_commit=COMMIT
    )
    assert altered["results"]["primary"]["point_estimate"] == -0.5
    assert result["protocol_sha256"] != altered["protocol_sha256"]


@pytest.mark.parametrize("mutation", ["family", "cluster", "weight", "version", "inference_unit"])
def test_incomplete_or_unsupported_protocol_refused(mutation: str) -> None:
    data = protocol_data()
    if mutation == "family":
        data["primary_family"] = []
    elif mutation == "cluster":
        data["strata"].append({"stratum_id": "other", "weight": 0.0, "weight_source": "frame"})
        data["manifest"][2]["stratum_id"] = "other"
    elif mutation == "weight":
        data["strata"][0]["weight"] = float("nan")
    elif mutation == "version":
        data["protocol_version"] = "1"
    else:
        del data["independent_unit"]
    with pytest.raises(ValidationError):
        ClusteredProtocol.model_validate(data)


def test_paired_planning_oracles_and_signed_noninferiority_distance() -> None:
    assert binary_paired_variance(0.2, 0.5) == pytest.approx(0.46)
    assert design_effect(4, 1) == 4
    assert design_effect(4, 0.2) == pytest.approx(1.6)
    for args in ((0.8, 0.2), (0, 1.1), (True, 0.5)):
        with pytest.raises(ValueError):
            binary_paired_variance(*args)
    with pytest.raises(ValueError):
        binary_paired_variance(0, 0.8, source_rate=0.1, intervention_rate=0.1)
    ordinary = planning_sensitivity(ClusteredProtocol.model_validate(protocol_data()))
    unit_variance = [row for row in ordinary["rows"] if row["paired_difference_variance"] == 1]
    # Independent rounded-normal oracle: z.975=1.959964; z.8=.841621.
    assert [
        (row["precision_clusters_approx"], row["power_clusters_approx"]) for row in unit_variance
    ] == [(97, 197), (385, 785)]
    data = protocol_data()
    data["hypotheses"][0].update(
        direction="noninferiority", noninferiority_margin=-0.03, planning_true_difference=0.0
    )
    report = planning_sensitivity(ClusteredProtocol.model_validate(data))
    assert len(report["rows"]) == 4
    assert all(row["planning_distance"] == 0.03 for row in report["rows"])
    assert report["achieved_power"] is None
    assert "not realized Holm" in report["multiplicity"]


def test_frozen_legacy_compatibility_and_separate_sensitivity(tmp_path: Path) -> None:
    path = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
    before = path.read_bytes()
    view = legacy_compatibility_view(yaml.safe_load(before))
    assert "legacy_sample_independence_assumed" in view["assumptions"]
    grid = frozen_114_sensitivity(path)
    assert (grid["pilot_total"], grid["full_total"]) == (100, 1200)
    assert grid["source_protocol_sha256"] == hashlib.sha256(before).hexdigest()
    examples = [
        row
        for row in grid["rows"]
        if row["full_tasks"] == 100 and row["assumed_paired_difference_variance"] == 1
    ]
    assert examples and examples[0]["normal_95_half_width"] == pytest.approx(0.196, abs=0.00001)
    assert path.read_bytes() == before
    protocol = ClusteredProtocol.model_validate(protocol_data())
    freeze_protocol(tmp_path / "plan.json", protocol)
    with pytest.raises(FileExistsError):
        freeze_protocol(tmp_path / "plan.json", protocol)


def event(event_id: str, event_type: str, **changes: Any) -> StoppingEvent:
    return StoppingEvent.model_validate(
        {
            "version": "1",
            "event_id": event_id,
            "timestamp": "2026-09-07T12:00:00Z",
            "actor": "declared-fixture-reviewer",
            "event_type": event_type,
            "reason": "controlled fixture",
            "information_snapshot": "only recorded information",
            "authorized_action": "fixture action",
            "tasks_accrued": 4,
            "clusters_accrued": 2,
            "outcomes_inspected": False,
            "artifacts": [],
            **changes,
        }
    )


def test_stopping_access_budget_deviation_and_no_retroactive_qualification(tmp_path: Path) -> None:
    protocol = ClusteredProtocol.model_validate(protocol_data())
    ledger = StoppingLedger(
        tmp_path / "events.jsonl", protocol, actor="fixture", outcomes_previously_accessed=False
    )
    with pytest.raises(ValueError, match="closure"):
        ledger.append(event("peek", "analysis_access", outcomes_inspected=True))
    ledger.append(event("close", "enrollment_closed"))
    ledger.append(event("access", "analysis_access", outcomes_inspected=True))
    before = ledger.path.read_bytes()
    with pytest.raises(ValueError, match="expansion"):
        ledger.append(
            event("expand", "operational_pause", tasks_accrued=5, outcomes_inspected=True)
        )
    assert ledger.path.read_bytes() == before
    ledger.append(
        event(
            "proposal",
            "deviation_proposed",
            outcomes_inspected=True,
            proposed_task_budget=5,
            proposed_cluster_budget=3,
        )
    )
    ledger.append(
        event("approval", "deviation_approved", outcomes_inspected=True, proposal_id="proposal")
    )
    ledger.append(
        event(
            "expanded",
            "operational_pause",
            tasks_accrued=5,
            clusters_accrued=3,
            outcomes_inspected=True,
            approved_deviation_id="approval",
        )
    )
    state = ledger.read()
    assert not state["original_confirmatory_interpretation_retained"]
    assert state["actor_authentication"] == "not_established"
    assert ledger.path.read_bytes().startswith(before)
    with pytest.raises(ValueError, match="duplicate"):
        ledger.append(event("expanded", "operational_pause"))
    changed = protocol_data()
    changed["primary_family"] = ["primary"]
    changed["hypotheses"][0]["practical_effect"] = 0.2
    with pytest.raises(ValueError, match="mismatch"):
        StoppingLedger(
            ledger.path,
            ClusteredProtocol.model_validate(changed),
            actor="fixture",
            outcomes_previously_accessed=False,
        )
    with ledger.path.open("ab") as stream:
        stream.write(b'{"truncated":')
    with pytest.raises(ValueError, match="incomplete"):
        ledger.read()


def _append_worker(path: str, event_id: str, release: Any, result: Any) -> None:
    try:
        ledger = StoppingLedger(
            Path(path),
            ClusteredProtocol.model_validate(protocol_data()),
            actor="child",
            outcomes_previously_accessed=False,
        )
        if not release.wait(10):
            raise RuntimeError("parent did not release fixture")
        result.send(("ok", ledger.append(event(event_id, "operational_pause"))))
    except Exception as exc:
        result.send(("error", repr(exc)))


def test_locked_stopping_writers_append_one_chain(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.jsonl"
    ledger = StoppingLedger(
        path,
        ClusteredProtocol.model_validate(protocol_data()),
        actor="fixture",
        outcomes_previously_accessed=False,
    )
    original = path.read_bytes()
    context = multiprocessing.get_context("spawn")
    release = context.Event()
    processes, connections, readers = [], [], []
    try:
        for index in range(2):
            reader, writer = context.Pipe(duplex=False)
            process = context.Process(
                target=_append_worker, args=(str(path), f"event-{index}", release, writer)
            )
            process.start()
            processes.append(process)
            connections.extend((reader, writer))
            readers.append(reader)
        release.set()
        for reader in readers:
            assert reader.poll(20)
            status, evidence = reader.recv()
            assert status == "ok", evidence
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        assert {item["event_id"] for item in ledger.read()["events"]} == {"event-0", "event-1"}
        assert path.read_bytes().startswith(original)
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
            process.join(5)
        for connection in connections:
            connection.close()


def test_positive_weight_singleton_stratum_cannot_borrow_other_clusters() -> None:
    data = protocol_data()
    data["strata"] = [
        {"stratum_id": "s", "weight": 0.5, "weight_source": "frame"},
        {"stratum_id": "other", "weight": 0.5, "weight_source": "frame"},
    ]
    data["manifest"][0]["stratum_id"] = "other"
    result = analyze_clustered(
        ClusteredProtocol.model_validate(data), outcomes([1, -1, -1, -1]), source_commit=COMMIT
    )["results"]["primary"]
    assert result["status"] == "insufficient_evidence"
    assert result["confirmatory_interval"] is None
    assert "insufficient_independent_clusters:other" in result["reasons"]


@pytest.mark.parametrize(
    "changes",
    [
        {"practical_effect": 1.01},
        {"planning_true_difference": 1.01},
        {"planning_true_difference": -1.01},
        {"direction": "noninferiority", "noninferiority_margin": -1.01},
        {"direction": "noninferiority", "noninferiority_margin": 0.01},
    ],
)
def test_impossible_bounded_effect_assumptions_rejected(changes: dict[str, Any]) -> None:
    data = protocol_data()
    data["hypotheses"][0].update(changes)
    with pytest.raises(ValidationError):
        ClusteredProtocol.model_validate(data)


def test_bounded_variance_and_effect_endpoints() -> None:
    data = protocol_data()
    data["hypotheses"][0].update(
        practical_effect=1.0,
        planning_true_difference=-1.0,
        direction="noninferiority",
        noninferiority_margin=-1.0,
    )
    ClusteredProtocol.model_validate(data)
    data["planning"]["sensitivity_variances"] = [1.01]
    with pytest.raises(ValidationError, match="variance"):
        ClusteredProtocol.model_validate(data)


def test_reopening_cannot_hide_declared_prior_outcome_access(tmp_path: Path) -> None:
    path = tmp_path / "access.jsonl"
    protocol = ClusteredProtocol.model_validate(protocol_data())
    ledger = StoppingLedger(path, protocol, actor="fixture", outcomes_previously_accessed=False)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="durable access"):
        StoppingLedger(path, protocol, actor="fixture", outcomes_previously_accessed=True)
    assert path.read_bytes() == before
    ledger.append(event("close", "enrollment_closed"))
    with pytest.raises(ValueError, match="outcomes_inspected"):
        ledger.append(event("hidden-access", "analysis_access", outcomes_inspected=False))
    ledger.append(event("access", "analysis_access", outcomes_inspected=True))
    reopened = StoppingLedger(path, protocol, actor="fixture", outcomes_previously_accessed=True)
    assert reopened.read()["events"][-1]["outcomes_inspected"] is True


def test_durable_deviation_records_unplanned_access_before_reopen(tmp_path: Path) -> None:
    path = tmp_path / "deviation.jsonl"
    protocol = ClusteredProtocol.model_validate(protocol_data())
    ledger = StoppingLedger(path, protocol, actor="fixture", outcomes_previously_accessed=False)
    ledger.append(
        event(
            "unexpected-access",
            "deviation_proposed",
            outcomes_inspected=True,
            proposed_task_budget=4,
            proposed_cluster_budget=2,
        )
    )
    reopened = StoppingLedger(path, protocol, actor="fixture", outcomes_previously_accessed=True)
    assert not reopened.read()["original_confirmatory_interpretation_retained"]
