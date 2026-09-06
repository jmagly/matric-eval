"""Tests for the official tau3-bench study bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
SCRIPT = ROOT / "scripts/run_qwen38_tau.py"
SPEC = importlib.util.spec_from_file_location("qwen38_tau_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
tau_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tau_runner
SPEC.loader.exec_module(tau_runner)


def test_protocol_and_generation_seed_match_study_contract() -> None:
    protocol = StudyProtocol.from_yaml(PROTOCOL)
    model = protocol.models[0]
    study_data, model_data, sampler = tau_runner._load_protocol(PROTOCOL, model.id)

    assert study_data["id"] == protocol.id
    assert model_data["checkpoint_revision"] == model.checkpoint_revision
    assert sampler["temperature"] == 1.0
    assert tau_runner._generation_seed(protocol.seed, "retail:43") == protocol.generation_seed(
        "tau3-bench", "retail:43"
    )

    with pytest.raises(ValueError, match="unknown study model"):
        tau_runner._load_protocol(PROTOCOL, "unknown")


def test_manifest_and_scored_ids_require_exact_order(tmp_path: Path) -> None:
    scored = {"airline": ["3"], "retail": ["43", "47"]}
    flattened = tau_runner._flatten_scored_ids(scored)
    assert flattened == ["airline:3", "retail:43", "retail:47"]

    manifest = {
        "study_id": "study",
        "cohort": "pilot",
        "allocations": [{"allocation_id": "tau3-bench", "selected_ids": flattened}],
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest["manifest_sha256"] = manifest_hash
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        tau_runner._verify_manifest(path, {"manifest_sha256": manifest_hash}, flattened, "study")
        == manifest_hash
    )
    with pytest.raises(ValueError, match="exactly match"):
        tau_runner._verify_manifest(
            path, {"manifest_sha256": manifest_hash}, list(reversed(flattened)), "study"
        )


def test_sampler_and_external_args_are_sealed(tmp_path: Path) -> None:
    sampler = {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
        "max_tokens": 8192,
    }
    assert tau_runner._agent_args("http://127.0.0.1:18080/v1", sampler) == {
        "api_base": "http://127.0.0.1:18080/v1",
        "api_key": "EMPTY",
        "temperature": 1.0,
        "top_p": 0.95,
        "presence_penalty": 0.0,
        "max_tokens": 8192,
        "extra_body": {"top_k": 20, "min_p": 0.0, "repetition_penalty": 1.0},
    }
    assert tau_runner._load_external_args(None) == {"temperature": 0.0}

    secret_args = tmp_path / "secret.json"
    secret_args.write_text('{"api_key": "must-not-be-recorded"}', encoding="utf-8")
    with pytest.raises(ValueError, match="injected through the environment"):
        tau_runner._load_external_args(secret_args)

    nested_secret_args = tmp_path / "nested-secret.json"
    nested_secret_args.write_text(
        '{"extra_headers": {"authorization_token": "must-not-be-recorded"}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="injected through the environment"):
        tau_runner._load_external_args(nested_secret_args)

    seeded_args = tmp_path / "seeded.json"
    seeded_args.write_text('{"seed": 7}', encoding="utf-8")
    with pytest.raises(ValueError, match="derives"):
        tau_runner._load_external_args(seeded_args)


def test_endpoint_and_private_result_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return json.dumps({"data": [{"id": "model"}, {"id": "/qualified/model"}]}).encode()[
                :size
            ]

    monkeypatch.setattr(tau_runner.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    tau_runner._validate_endpoint("http://127.0.0.1:18080/v1", "model", Path("/qualified/model"))
    with pytest.raises(ValueError, match="localhost"):
        tau_runner._validate_endpoint("http://example.com/v1", "model", Path("/qualified/model"))

    first = tau_runner._result_filename("telecom:one")
    second = tau_runner._result_filename("telecom:two")
    assert first.startswith("task-") and first.endswith(".json")
    assert first != second


def test_tau_worktree_allows_only_recorded_lockfile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = iter(
        [
            SimpleNamespace(stdout=" M uv.lock\n"),
            SimpleNamespace(stdout=b"lock diff"),
        ]
    )
    monkeypatch.setattr(tau_runner.subprocess, "run", lambda *args, **kwargs: next(calls))
    evidence = tau_runner._tau_worktree_evidence(Path("/tau"))
    assert evidence["tracked_changes"] == ["uv.lock"]
    assert evidence["tracked_diff_sha256"] == hashlib.sha256(b"lock diff").hexdigest()

    monkeypatch.setattr(
        tau_runner.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=" M src/tau2/run.py\n"),
    )
    with pytest.raises(RuntimeError, match="modified tracked source"):
        tau_runner._tau_worktree_evidence(Path("/tau"))
