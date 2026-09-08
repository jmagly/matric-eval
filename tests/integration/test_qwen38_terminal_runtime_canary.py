"""Opt-in A100 integration for the model-independent Terminal runtime canary."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("MATRIC_EVAL_RUN_QWEN38_TERMINAL_CANARY") != "1",
    reason="requires isolated patched Harbor and Docker environments",
)
def test_scripted_terminal_runtime_controls(tmp_path: Path) -> None:
    required = {
        name: os.environ.get(name)
        for name in (
            "MATRIC_EVAL_HARBOR_PYTHON",
            "MATRIC_EVAL_HARBOR_CHECKOUT",
            "MATRIC_EVAL_HARBOR_DOCKER_HOST",
        )
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        pytest.fail("missing required canary environment: " + ", ".join(missing))
    output = Path(
        os.environ.get(
            "MATRIC_EVAL_QWEN38_TERMINAL_CANARY_OUTPUT",
            str(tmp_path / "terminal-runtime-receipt.json"),
        )
    )
    result = subprocess.run(
        [
            str(required["MATRIC_EVAL_HARBOR_PYTHON"]),
            str(ROOT / "scripts/canary_qwen38_terminal_runtime.py"),
            "--harbor-checkout",
            str(required["MATRIC_EVAL_HARBOR_CHECKOUT"]),
            "--docker-host",
            str(required["MATRIC_EVAL_HARBOR_DOCKER_HOST"]),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    payload = json.loads(result.stdout)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert payload["schema"] == canary_schema()
    assert payload["status"] == "passed"
    assert payload["assertions"]["tiny_sentinel_submit"]["official_reward"] == 1
    assert payload["assertions"]["agent_no_submit"]["analytic_reason"] == "agent_no_submit"
    assert payload["assertions"]["llm_response_timeout"]["analytic_reason"] == (
        "llm_response_timeout"
    )
    assert payload["assertions"]["command_timeout_cleanup"]["child_process_gone"] is True
    assert payload["counts"]["hidden_http_retries"] == 0
    assert payload["counts"]["side_effect_retries"] == 0


def canary_schema() -> str:
    return "matric-eval.qwen38-terminal-runtime-canary-receipt/1"
