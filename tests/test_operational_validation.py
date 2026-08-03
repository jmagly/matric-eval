"""Tests for the versioned parity and operational validation report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
