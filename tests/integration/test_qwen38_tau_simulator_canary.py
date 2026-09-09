"""Opt-in A100 integration for the model-independent Tau simulator canary."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _receipt_from_stdout(stdout: str) -> dict[str, object]:
    """Load the final receipt line after any dependency startup notices."""
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("schema") == (
            "matric-eval.qwen38-tau-simulator-canary-receipt/1"
        ):
            return payload
    raise ValueError("canary stdout did not contain a receipt object")


def test_receipt_parser_ignores_dependency_notices() -> None:
    receipt = {
        "schema": "matric-eval.qwen38-tau-simulator-canary-receipt/1",
        "status": "passed",
    }
    stdout = "dependency notice\n" + json.dumps(receipt) + "\n"
    assert _receipt_from_stdout(stdout) == receipt


@pytest.mark.skipif(
    os.environ.get("MATRIC_EVAL_RUN_QWEN38_TAU_SIMULATOR_CANARY") != "1",
    reason="requires an isolated patched Tau environment",
)
def test_loopback_simulator_boundaries(tmp_path: Path) -> None:
    required = {
        name: os.environ.get(name)
        for name in (
            "MATRIC_EVAL_TAU_PYTHON",
            "MATRIC_EVAL_TAU_CHECKOUT",
        )
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        pytest.fail("missing required canary environment: " + ", ".join(missing))
    output = Path(
        os.environ.get(
            "MATRIC_EVAL_QWEN38_TAU_SIMULATOR_CANARY_OUTPUT",
            str(tmp_path / "receipt.json"),
        )
    )
    result = subprocess.run(
        [
            str(required["MATRIC_EVAL_TAU_PYTHON"]),
            str(ROOT / "scripts/canary_qwen38_tau_simulator.py"),
            "--tau-checkout",
            str(required["MATRIC_EVAL_TAU_CHECKOUT"]),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    payload = _receipt_from_stdout(result.stdout)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert payload["schema"] == "matric-eval.qwen38-tau-simulator-canary-receipt/1"
    assert payload["status"] == "passed"
    assert payload["counts"]["side_effect_retries"] == 0
    assert payload["scenario_assertions"]["post_side_effect_empty"]["requests"] == 1
    assert payload["scenario_assertions"]["target-sampling"]["actor"] == "target-model"
    assert payload["scenario_assertions"]["nl-evaluation"]["actor"] == "evaluator"
