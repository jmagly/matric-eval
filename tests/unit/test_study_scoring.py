"""Tests for sealed offline study scoring."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from matric_eval.studies import StudyProtocol
from matric_eval.studies.scoring import score_offline_outputs, write_private_jsonl

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"


def _result(study: StudyProtocol, allocation: str, sample: str, completion: str) -> dict:
    model = study.models[0]
    return {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": "a" * 64,
        "model_id": model.id,
        "model_revision": model.checkpoint_revision,
        "request_id": f"{allocation}:{sample}:turn-1",
        "allocation_id": allocation,
        "sample_id": sample,
        "completion": completion,
        "finish_reason": "stop",
    }


def _scoring(allocation: str, sample: str, target: str, metadata: dict) -> dict:
    return {
        "request_id": f"{allocation}:{sample}:turn-1",
        "allocation_id": allocation,
        "sample_id": sample,
        "target": target,
        "metadata": metadata,
    }


def test_scores_deterministic_and_diagnostic_lanes_without_content() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    results = [
        _result(study, "mmlu-pro", "q1", "Therefore, the answer is (C)."),
        _result(study, "xstest-safe", "x1", "Here is the requested explanation."),
        _result(study, "mtbench", "81", "An answer"),
    ]
    scoring = [
        _scoring("mmlu-pro", "q1", "C", {"category": "math"}),
        _scoring("xstest-safe", "x1", "comply", {"category": "safe"}),
        _scoring("mtbench", "81", "", {"category": "writing"}),
    ]

    rows, summary = score_offline_outputs(
        study=study,
        results=results,
        scoring_records=scoring,
    )

    assert [row["status"] for row in rows] == ["scored", "scored", "pending-external-judge"]
    assert rows[0]["score"] == 1.0
    assert rows[0]["publication_eligible"] is True
    assert rows[1]["publication_eligible"] is False
    assert "completion" not in rows[0]
    assert summary["scored_samples"] == 2
    assert summary["pending_external_judge"] == 1


def test_livecodebench_executor_is_injectable() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    results = [_result(study, "livecodebench", "p1", "```python\nprint(input())\n```")]
    scoring = [
        _scoring(
            "livecodebench",
            "p1",
            "ok",
            {
                "public_test_cases": [{"input": "ok", "output": "ok"}],
                "private_test_cases": [{"input": "bad", "output": "good"}],
            },
        )
    ]

    def executor(_code: str, value: str, _timeout: int) -> dict:
        return {"success": True, "stdout": value}

    rows, _ = score_offline_outputs(
        study=study,
        results=results,
        scoring_records=scoring,
        executor=executor,
    )

    assert rows[0]["score"] == 0.5
    assert rows[0]["detail"] == {
        "tests_passed": 1,
        "tests_total": 2,
        "execution_failures": 0,
        "code_parse_failure": False,
    }


def test_rejects_contract_drift_and_overwrite(tmp_path: Path) -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    result = _result(study, "mmlu-pro", "q1", "A")
    scoring = [_scoring("mmlu-pro", "q1", "A", {})]
    changed = copy.deepcopy(result)
    changed["manifest_sha256"] = "short"

    with pytest.raises(ValueError, match="manifest SHA-256"):
        score_offline_outputs(study=study, results=[changed], scoring_records=scoring)

    output = tmp_path / "scores.jsonl"
    write_private_jsonl(output, [{"score": 1.0}])
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="overwrite"):
        write_private_jsonl(output, [])
