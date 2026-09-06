"""Tests for the official Terminal-Bench study bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
SCRIPT = ROOT / "scripts/run_qwen38_terminal.py"
SPEC = importlib.util.spec_from_file_location("qwen38_terminal_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
terminal_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = terminal_runner
SPEC.loader.exec_module(terminal_runner)


def test_protocol_and_generation_seed_match_study_contract() -> None:
    protocol = StudyProtocol.from_yaml(PROTOCOL)
    model = protocol.models[0]
    study_data, model_data, sampler = terminal_runner._load_protocol(PROTOCOL, model.id)

    assert study_data["id"] == protocol.id
    assert model_data["checkpoint_revision"] == model.checkpoint_revision
    assert sampler["temperature"] == 1.0
    assert terminal_runner._generation_seed(
        protocol.seed, "largest-eigenval"
    ) == protocol.generation_seed("terminal-bench-2.1", "largest-eigenval")


def test_manifest_requires_exact_scored_ids(tmp_path: Path) -> None:
    selected = ["largest-eigenval", "extract-elf"]
    manifest = {
        "study_id": "study",
        "cohort": "pilot",
        "allocations": [{"allocation_id": "terminal-bench-2.1", "selected_ids": selected}],
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest["manifest_sha256"] = manifest_hash
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        terminal_runner._verify_manifest(
            path, {"manifest_sha256": manifest_hash}, selected, "study"
        )
        == manifest_hash
    )
    with pytest.raises(ValueError, match="exactly match"):
        terminal_runner._verify_manifest(
            path, {"manifest_sha256": manifest_hash}, list(reversed(selected)), "study"
        )


def test_agent_and_job_config_carry_full_sampler() -> None:
    sampler = {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
        "max_tokens": 8192,
    }
    kwargs = terminal_runner._agent_kwargs("http://127.0.0.1:18080/v1", sampler, 123, 32768)
    calls = kwargs["llm_call_kwargs"]
    assert kwargs["temperature"] == 1.0
    assert kwargs["model_info"]["max_input_tokens"] == 32768
    assert calls == {
        "top_p": 0.95,
        "presence_penalty": 0.0,
        "max_tokens": 8192,
        "seed": 123,
        "extra_body": {"top_k": 20, "min_p": 0.0, "repetition_penalty": 1.0},
    }
    config = terminal_runner._job_config(
        jobs_dir=Path("/private/jobs"),
        job_name="one",
        tasks_dir=Path("/terminal/tasks"),
        task_id="largest-eigenval",
        model_id="model",
        agent_kwargs=kwargs,
    )
    assert config["n_concurrent_trials"] == 1
    assert config["retry"]["max_retries"] == 0
    assert config["agents"][0]["model_name"] == "hosted_vllm/model"
    assert config["datasets"][0]["task_names"] == ["largest-eigenval"]


def test_endpoint_and_job_result_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return json.dumps({"data": [{"id": "model"}, {"id": "/qualified/model"}]}).encode()[
                :size
            ]

    monkeypatch.setattr(
        terminal_runner.urllib.request, "urlopen", lambda *args, **kwargs: Response()
    )
    terminal_runner._validate_endpoint(
        "http://127.0.0.1:18080/v1", "model", Path("/qualified/model")
    )

    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "trial_results": [
                    {
                        "verifier_result": {"rewards": {"reward": 1}},
                        "exception_info": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _, rewards, exception = terminal_runner._parse_job_result(result_path)
    assert rewards == {"reward": 1}
    assert exception is None


def test_result_names_are_content_free_and_stable() -> None:
    one = terminal_runner._result_name("largest-eigenval")
    two = terminal_runner._result_name("extract-elf")
    assert one.startswith("terminal-")
    assert one != two
    assert "eigenval" not in one


def test_isolated_docker_network_contract() -> None:
    terminal_runner._validate_docker_config(
        {
            "data-root": "/srv/obliteratus/matric-eval/docker/data",
            "bridge": "none",
            "iptables": True,
            "ip-forward": True,
            "ip-masq": True,
            "default-address-pools": [{"base": "10.241.0.0/16", "size": 24}],
        }
    )
    with pytest.raises(RuntimeError, match="iptables"):
        terminal_runner._validate_docker_config(
            {
                "data-root": "/srv/obliteratus/matric-eval/docker/data",
                "bridge": "none",
                "iptables": False,
                "ip-forward": True,
                "ip-masq": True,
                "default-address-pools": [{"base": "10.241.0.0/16", "size": 24}],
            }
        )
