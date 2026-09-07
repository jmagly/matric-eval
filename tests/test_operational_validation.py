"""Tests for the versioned parity and operational validation report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from matric_eval.tasks.matric_memory import score_legacy_semantic, score_legacy_title
from scripts import run_operational_validation as validation

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "validation/operational-parity-matrix-v1.json"
REPORT = ROOT / "docs/validation/operational-validation-v1.json"


def test_legacy_title_scorer_matches_source_formula() -> None:
    score, passed, details = score_legacy_title(
        "Redis Session Caching Improvements",
        ["Redis", "caching", "session"],
        80,
    )

    assert score == pytest.approx(1.0)
    assert passed is True
    assert details == {
        "keyword_matches": 3,
        "keyword_total": 3,
        "length_ok": True,
        "clean_format": True,
    }


def test_legacy_semantic_scorer_matches_source_formula() -> None:
    score, passed, details = score_legacy_semantic(
        [1.0, 0.0],
        [[1.0, 0.0], [0.9, 0.1]],
        [[0.0, 1.0]],
    )

    assert score == pytest.approx(1.0)
    assert passed is True
    assert details["min_positive"] > details["max_negative"]


def test_validation_runner_passes_all_contracts(tmp_path: Path) -> None:
    # This test exercises report plumbing. Real scorer parity requires configured
    # isolated execution and is verified separately on the validation host.
    matrix = json.loads(MATRIX.read_text())
    outcomes = [
        {
            "status": "passed" if case["expected_pass"] else "incorrect",
            "stdout": "",
            "stderr": "",
            "error": None if case["expected_pass"] else "incorrect",
            "provenance": {"profile": "unit-fixture", "cleanup": "verified_absent"},
        }
        for case in matrix["code_cases"]
    ]
    with (
        patch("matric_eval.scorers.code_execution.execute_python", side_effect=outcomes),
        patch(
            "scripts.run_operational_validation.execute_python",
            side_effect=outcomes,
        ),
    ):
        report = validation.run(MATRIX, tmp_path)

    assert report["status"] == "passed"
    assert report["public_scorer_parity"]["passed"] is True
    assert report["matric_memory_parity"]["agreement_rate"] == 1.0
    assert {case["scorer"] for case in report["matric_memory_parity"]["cases"]} == {
        "title",
        "semantic",
    }
    assert report["checkpoint_resume"]["duplicate_count"] == 0
    assert report["parallel_equivalence"]["result_set_difference"] == 0
    assert (tmp_path / "operational-validation-v1.json").exists()
    assert (tmp_path / "operational-validation-v1.md").exists()


def test_committed_report_matches_versioned_matrix() -> None:
    report = json.loads(REPORT.read_text())
    matrix_hash = hashlib.sha256(MATRIX.read_bytes()).hexdigest()

    assert report["status"] == "passed"
    assert report["matrix"] == {
        "id": "operational-parity-v1",
        "sha256": matrix_hash,
    }


def test_no_configured_image_keeps_parity_unavailable_and_gate_failed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("MATRIC_EVAL_SANDBOX_IMAGE", raising=False)
    monkeypatch.setenv("MATRIC_EVAL_SANDBOX_COMMAND", '["docker"]')
    # The actual runner's configuration check must reject before launching even
    # a container CLI; this test does not replace execution results with mocks.
    with patch("subprocess.Popen") as launch:
        report = validation.run(MATRIX, tmp_path)
    launch.assert_not_called()
    assert report["status"] == "failed"
    code = report["public_scorer_parity"]
    assert code["passed"] is False
    for case in code["cases"]:
        assert case["matric_eval_pass"] is None
        assert case["reference_pass"] is None
        assert case["agreement"] is False
        for key in ("matric_eval_execution", "reference_execution"):
            assert case[key]["status"] in {"unavailable", "policy_denied"}
            assert case[key]["error"] == "pinned_image_required"
            assert case[key]["provenance"]["cleanup"] == "not_created"
    for benchmark in code["benchmarks"].values():
        assert benchmark["passed"] is False
        assert benchmark["availability"] == "unavailable"
        assert benchmark["matric_eval_observed"] == benchmark["reference_observed"] == 0
        assert benchmark["matric_eval_pass_rate"] is None
        assert benchmark["reference_pass_rate"] is None
        assert benchmark["variance_percentage_points"] is None
    markdown = (tmp_path / "operational-validation-v1.md").read_text()
    assert "| HumanEval scorer parity | FAIL | Unavailable execution" in markdown
    assert "| MBPP scorer parity | FAIL | Unavailable execution" in markdown


def test_reference_harness_remains_independently_constructed():
    case = {
        "benchmark": "humaneval",
        "entry_point": "double",
        "prompt": "def double(value):",
        "response": "return value * 2",
        "test": "def check(candidate):\n    assert candidate(3) == 6",
    }
    with patch(
        "scripts.run_operational_validation.execute_python", return_value={"status": "passed"}
    ) as execute:
        assert validation.legacy_code_pass(case) == {"status": "passed"}
    execute.assert_called_once_with(
        "def double(value):\n    return value * 2\ndef check(candidate):\n    assert candidate(3) == 6\n\ncheck(double)",
        timeout=5,
    )
