import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import qwen38_tau_local as local


def test_identity_mismatch_fails_before_embedder_import(monkeypatch):
    payload = {"models": [{"name": local.MODEL.removeprefix("ollama_chat/"), "digest": "wrong"}]}
    monkeypatch.setattr(
        local.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(payload).encode())
    )
    with pytest.raises(RuntimeError, match="identity mismatch"):
        local.configure_local()


def test_local_arguments_use_public_broker_without_hidden_retries():
    args = local.external_arguments()
    assert args["api_base"] == "http://127.0.0.1:11434"
    assert args["num_retries"] == 0
    assert args["timeout"] == 180
    assert "api_key" not in args
    assert args["reasoning_effort"] == "none"
