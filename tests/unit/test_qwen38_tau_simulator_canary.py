"""Unit tests for the Tau simulator loopback receipt writer."""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "canary_qwen38_tau_simulator.py"
SPEC = importlib.util.spec_from_file_location("qwen38_tau_simulator_canary_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
canary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = canary
SPEC.loader.exec_module(canary)


def test_receipt_is_exclusive_private_and_durable(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "receipt.json"
    receipt = {"schema": canary.RECEIPT_SCHEMA, "status": "passed"}
    canary._write_receipt(output, receipt)
    assert json.loads(output.read_text(encoding="utf-8")) == receipt
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError, match="overwrite"):
        canary._write_receipt(output, receipt)
    assert json.loads(output.read_text(encoding="utf-8")) == receipt


def test_receipt_refuses_dangling_symlink(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    output.symlink_to(tmp_path / "missing.json")
    with pytest.raises(FileExistsError, match="overwrite"):
        canary._write_receipt(output, {"status": "passed"})


def test_canary_assertion_error_retains_only_structured_evidence() -> None:
    evidence = {
        "failed_scenarios": ["always_empty_body"],
        "failure_observations": {
            "always_empty_body": {
                "actor": "user-simulator",
                "stage": "simulator-sampling",
                "reason": "sampling_failure",
                "requests": 2,
                "recoveries": 1,
            }
        },
        "request_mismatches": {},
        "post_side_effect_recoveries": 0,
    }
    error = canary.CanaryAssertionError(evidence)
    assert error.evidence == evidence
    assert str(error) == "one or more simulator/interface canary assertions failed"
