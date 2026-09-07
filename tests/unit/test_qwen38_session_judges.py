"""Focused tests for the Qwen3.8 Codex-subagent judge adapter."""

from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
BASE_PLAN = ROOT / "studies/qwen38-obliteration-2026-09/judge-plan.yaml"
SCRIPT = ROOT / "scripts/run_qwen38_session_judges.py"
SPEC = importlib.util.spec_from_file_location("qwen38_session_judges", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _private_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "study"
    monkeypatch.setattr(runner, "PRIVATE_ROOT", root)
    return root


def _session_plan() -> dict[str, Any]:
    return {
        "judges": {
            role: {
                "provider": "codex-collaboration-session",
                "model": model,
                "snapshot": model,
            }
            for role, model in {
                "primary": "gpt-6-astra",
                "secondary": "gpt-5.6-sol",
                "adjudicator": "gpt-5.6-terra",
            }.items()
        },
        "execution_agents": {
            "primary": {"agent_task_id": "/root/judge_primary", "model": "gpt-6-astra"},
            "secondary": {"agent_task_id": "/root/judge_secondary", "model": "gpt-5.6-sol"},
            "adjudicator": {
                "agent_task_id": "/root/judge_adjudicator",
                "model": "gpt-5.6-terra",
            },
        },
    }


def _refusal_row(ordinal: int, blind_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "ordinal": ordinal,
        "blind_id": blind_id,
        "rubric": "refusal_three_way",
        "instruction": "locked instruction",
        "input": "private marker",
        "result_schema": runner.LOCKED._schema("refusal_three_way"),
    }


def test_atomic_private_outputs_and_resolved_containment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _private_root(monkeypatch, tmp_path)
    output = root / "private" / "nested" / "artifact.json"
    runner._write_json(output, {"ok": True})

    assert json.loads(output.read_text()) == {"ok": True}
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.parent.stat().st_mode & 0o777 == 0o700
    assert (root / "private").stat().st_mode & 0o777 == 0o700
    with pytest.raises(ValueError, match="overwrite"):
        runner._write_json(output, {"ok": False})
    with pytest.raises(ValueError, match="must be below"):
        runner._resolved_private(root / "private" / ".." / "public.json", "escape")


def test_byte_bounded_shards_are_deterministic_and_never_split_rows() -> None:
    rows = [_refusal_row(index, f"B{index}") for index in range(1, 7)]
    row_size = len(runner._canonical_line(rows[0]))

    first = runner._shards(rows, row_size * 2)
    second = runner._shards(rows, row_size * 2)

    assert first == second
    assert [row for shard in first for row in shard] == rows
    assert all(
        sum(len(runner._canonical_line(row)) for row in shard) <= row_size * 2 for shard in first
    )
    with pytest.raises(ValueError, match="exceeds"):
        runner._shards(rows, row_size - 1)


@pytest.mark.parametrize(
    "rubric,value",
    [
        ("refusal_three_way", {"behavior": "full_refusal"}),
        (
            "strongreject",
            {"refusal": True, "convincingness": 1, "specificity": 1, "rationale": "x"},
        ),
        (
            "mtbench",
            {
                "turn_1_score": 8,
                "turn_2_score": 8,
                "turn_1_rationale": "x",
                "turn_2_rationale": "y",
                "model_id": "must-not-leak",
            },
        ),
    ],
)
def test_result_schema_is_exact_and_type_strict(rubric: str, value: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        runner._validate_result(rubric, value)


def test_create_plan_separates_truthful_models_from_agent_task_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _private_root(monkeypatch, tmp_path)
    output = root / "private" / "session-plan.json"
    args = Namespace(
        protocol=PROTOCOL,
        base_plan=BASE_PLAN,
        cohort="pilot",
        primary_model="gpt-6-astra",
        secondary_model="gpt-5.6-sol",
        adjudicator_model="gpt-5.6-terra",
        primary_agent_task_id="/root/judge_primary",
        secondary_agent_task_id="/root/judge_secondary",
        adjudicator_agent_task_id="/root/judge_adjudicator",
        output=output,
    )

    runner.create_plan(args)
    plan = json.loads(output.read_text())

    assert plan["judges"]["primary"]["model"] == "gpt-6-astra"
    assert plan["judges"]["primary"]["snapshot"] == "gpt-6-astra"
    assert plan["execution_agents"]["primary"]["agent_task_id"] == "/root/judge_primary"
    assert "session_judge_plan_sha256" not in plan
    assert plan["execution_amendment"]["base_judge_plan_sha256"] == runner._sha256(BASE_PLAN)

    base = yaml.safe_load(BASE_PLAN.read_text())
    plan["rubrics"]["mtbench"]["turn_score_range"] = [0, 10]
    with pytest.raises(ValueError, match="locked field"):
        runner._validate_session_plan(
            plan,
            base_plan=base,
            base_plan_sha256=runner._sha256(BASE_PLAN),
            study=runner.StudyProtocol.from_yaml(PROTOCOL),
            cohort="pilot",
        )


def test_imported_envelope_binds_packet_role_plan_agent_and_strict_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _private_root(monkeypatch, tmp_path)
    private = root / "private" / "judge"
    base_plan = private / "base-plan.json"
    session_plan_path = private / "session-plan.json"
    manifest_path = root / "pilot-manifest.json"
    packet_dir = private / "packets"
    index_path = private / "packet-index.json"
    submission_path = private / "submission.json"
    output = private / "results" / "primary" / "batch-001.json"
    runner._write_json(base_plan, {"base": True})
    runner._write_json(session_plan_path, _session_plan())
    root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}")
    row = _refusal_row(1, "B0001")
    session_sha = runner._sha256(session_plan_path)
    runner._write_packet_set(
        directory=packet_dir,
        index_path=index_path,
        rows=[row],
        max_bytes=100_000,
        header={
            "phase": "first-pass",
            "study_id": "study",
            "protocol_sha256": "p" * 64,
            "manifest_sha256": "m" * 64,
            "cohort": "pilot",
            "base_judge_plan_sha256": runner._sha256(base_plan),
            "session_judge_plan_sha256": session_sha,
        },
        source_artifacts={},
    )
    runner._write_json(
        submission_path,
        {
            "labels": [
                {
                    "blind_id": "B0001",
                    "result": {"behavior": "full_refusal", "rationale": "brief"},
                }
            ]
        },
    )
    monkeypatch.setattr(
        runner,
        "_session_context",
        lambda _args: (
            SimpleNamespace(id="study", canonical_sha256="p" * 64),
            {"manifest_sha256": "m" * 64},
            {},
            _session_plan(),
            [],
            {},
        ),
    )
    monkeypatch.setattr(runner, "_packet_rows", lambda _plan, _items: [row])
    args = Namespace(
        protocol=PROTOCOL,
        base_plan=base_plan,
        session_plan=session_plan_path,
        manifest=manifest_path,
        cohort="pilot",
        result_root=root,
        phase="first-pass",
        role="primary",
        packet_index=index_path,
        packet="batch-001.jsonl",
        input=str(submission_path),
        elapsed_seconds=2.5,
        attempts=1,
        output=output,
    )

    runner.import_results(args)
    envelope = json.loads(output.read_text())

    assert envelope["packet_index_sha256"] == runner._sha256(index_path)
    assert envelope["packet_sha256"] == runner._sha256(packet_dir / "batch-001.jsonl")
    assert envelope["role"] == "primary"
    assert envelope["judge"]["model"] == "gpt-6-astra"
    assert envelope["agent_task_id"] == "/root/judge_primary"
    assert output.stat().st_mode & 0o777 == 0o600


def test_content_free_guard_rejects_private_fields() -> None:
    runner._assert_content_free({"outcomes": [{"components": {"score": 1.0}}]})
    with pytest.raises(ValueError, match="private content"):
        runner._assert_content_free({"outcomes": [{"rationale": "private"}]})
