"""Opt-in A100 integration for the model-independent Tau context canary."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("MATRIC_EVAL_RUN_QWEN38_TAU_CANARY") != "1",
    reason="requires an isolated patched Tau environment and local tokenizer assets",
)
def test_real_tokenizer_boundary_rejects_before_http(tmp_path: Path) -> None:
    required = {
        name: os.environ.get(name)
        for name in (
            "MATRIC_EVAL_TAU_PYTHON",
            "MATRIC_EVAL_TAU_CHECKOUT",
            "MATRIC_EVAL_QWEN38_MODEL_PATH",
            "MATRIC_EVAL_QWEN38_CHAT_TEMPLATE",
            "MATRIC_EVAL_QWEN38_SERVER_RECEIPT",
        )
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        pytest.fail("missing required canary environment: " + ", ".join(missing))
    output = Path(
        os.environ.get("MATRIC_EVAL_QWEN38_CANARY_OUTPUT", str(tmp_path / "receipt.json"))
    )
    result = subprocess.run(
        [
            str(required["MATRIC_EVAL_TAU_PYTHON"]),
            str(ROOT / "scripts/canary_qwen38_tau_context.py"),
            "--tau-checkout",
            str(required["MATRIC_EVAL_TAU_CHECKOUT"]),
            "--model-path",
            str(required["MATRIC_EVAL_QWEN38_MODEL_PATH"]),
            "--chat-template",
            str(required["MATRIC_EVAL_QWEN38_CHAT_TEMPLATE"]),
            "--server-receipt",
            str(required["MATRIC_EVAL_QWEN38_SERVER_RECEIPT"]),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    payload = json.loads(result.stdout)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert payload["schema"] == "matric-eval.qwen38-tau-context-canary-receipt/1"
    assert payload["status"] == "passed"
    assert payload["boundary_assertions"]["accepted_combined_tokens"] == 32768
    assert payload["boundary_assertions"]["rejected_combined_tokens"] == 32769
    assert payload["boundary_assertions"]["rejected_before_http"] is True
    assert payload["counts"]["http_requests"] == 1
    assert payload["counts"]["side_effect_retries"] == 0
    assert payload["tokenizer"]["transformers_version"] == "5.14.1"
