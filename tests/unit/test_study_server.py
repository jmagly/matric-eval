"""Tests for the broker-attested external-runner model server."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from matric_eval.studies import StudyProtocol, server_cli

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"


class _Process:
    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: int | None = None) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class _Response:
    status = 200

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return b"{}"[:size]


def test_server_arguments_are_protocol_derived_and_localhost_only(tmp_path: Path) -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    model_id = study.models[0].id
    arguments = server_cli._server_arguments(
        study,
        model_id,
        tmp_path / "model",
        tmp_path / "chat-template.jinja",
        "127.0.0.1",
        18080,
    )

    assert arguments[0] == str(tmp_path / "model")
    served_name_index = arguments.index("--served-model-name")
    assert arguments[served_name_index + 1 : served_name_index + 3] == [
        model_id,
        str(tmp_path / "model"),
    ]
    assert arguments[arguments.index("--max-num-seqs") + 1] == "1"
    assert arguments[arguments.index("--tool-call-parser") + 1] == "qwen3_coder"
    assert "--no-async-scheduling" in arguments
    assert "--enable-log-requests" not in arguments
    assert "--disable-uvicorn-access-log" in arguments

    study.raw["study"]["execution"]["model_server"]["async_scheduling"] = True
    async_arguments = server_cli._server_arguments(
        study,
        model_id,
        tmp_path / "model",
        tmp_path / "chat-template.jinja",
        "127.0.0.1",
        18080,
    )
    assert "--async-scheduling" in async_arguments
    assert "--no-async-scheduling" not in async_arguments

    with pytest.raises(ValueError, match="127.0.0.1"):
        server_cli._server_arguments(
            study,
            model_id,
            tmp_path / "model",
            tmp_path / "chat-template.jinja",
            "0.0.0.0",
            18080,
        )
    with pytest.raises(ValueError, match="between 1024"):
        server_cli._server_arguments(
            study,
            model_id,
            tmp_path / "model",
            tmp_path / "chat-template.jinja",
            "127.0.0.1",
            80,
        )


def test_wait_for_endpoint_handles_readiness_exit_and_timeout() -> None:
    server_cli._wait_for_endpoint(
        _Process(),
        "http://127.0.0.1:18080/v1/models",
        1,
        opener=lambda *args, **kwargs: _Response(),
    )

    with pytest.raises(RuntimeError, match="status 7"):
        server_cli._wait_for_endpoint(
            _Process(7),
            "http://127.0.0.1:18080/v1/models",
            1,
            opener=lambda *args, **kwargs: _Response(),
        )

    ticks = iter([0.0, 1.0])
    with pytest.raises(TimeoutError, match="deadline"):
        server_cli._wait_for_endpoint(
            _Process(),
            "http://127.0.0.1:18080/v1/models",
            0.5,
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("not ready")),
            monotonic=lambda: next(ticks),
            sleep=lambda seconds: None,
        )


def test_private_server_receipt_is_non_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "private" / "receipt.json"
    ownership: list[tuple[Path, int, int]] = []
    monkeypatch.setenv("MATRIC_EVAL_EVIDENCE_UID", "1234")
    monkeypatch.setenv("MATRIC_EVAL_EVIDENCE_GID", "5678")
    monkeypatch.setattr(
        server_cli.os,
        "chown",
        lambda target, uid, gid: ownership.append((Path(target), uid, gid)),
    )
    digest = server_cli._write_private_json(path, {"model_id": "source"})

    assert len(digest) == 64
    assert json.loads(path.read_text(encoding="utf-8"))["model_id"] == "source"
    assert path.stat().st_mode & 0o777 == 0o600
    assert ownership[0][1:] == (1234, 5678)
    assert not list(path.parent.glob(".*.tmp"))
    with pytest.raises(ValueError, match="overwrite"):
        server_cli._write_private_json(path, {})


def test_evidence_owner_requires_paired_decimal_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "receipt.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("MATRIC_EVAL_EVIDENCE_UID", "1234")
    monkeypatch.delenv("MATRIC_EVAL_EVIDENCE_GID", raising=False)

    with pytest.raises(ValueError, match="supplied together"):
        server_cli._set_evidence_owner(path)


def test_serve_child_registers_adapter_and_restores_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[tuple[str, str]] = []
    observed_argv: list[str] = []
    observed_registrations: list[str | None] = []

    class Registry:
        @staticmethod
        def register_model(architecture: str, implementation: str) -> None:
            registered.append((architecture, implementation))

    vllm = ModuleType("vllm")
    vllm.ModelRegistry = Registry  # type: ignore[attr-defined]
    entrypoints = ModuleType("vllm.entrypoints")
    cli = ModuleType("vllm.entrypoints.cli")
    main_module = ModuleType("vllm.entrypoints.cli.main")

    def observe_main() -> None:
        observed_argv.extend(sys.argv)
        observed_registrations.append(
            server_cli.os.environ.get("MATRIC_EVAL_VLLM_ARCHITECTURE_REGISTRATIONS")
        )

    main_module.main = observe_main  # type: ignore[attr-defined]
    for name, module in {
        "vllm": vllm,
        "vllm.entrypoints": entrypoints,
        "vllm.entrypoints.cli": cli,
        "vllm.entrypoints.cli.main": main_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    original_argv = sys.argv

    assert server_cli._serve_child({"Qwen": "adapter:Class"}, ["model", "--port", "1"]) == 0

    assert registered == [("Qwen", "adapter:Class")]
    assert observed_argv == ["vllm", "serve", "model", "--port", "1"]
    assert observed_registrations == ['{"Qwen":"adapter:Class"}']
    assert "MATRIC_EVAL_VLLM_ARCHITECTURE_REGISTRATIONS" not in server_cli.os.environ
    assert sys.argv is original_argv
    with pytest.raises(ValueError, match="map strings"):
        server_cli._serve_child({"Qwen": 1}, [])


def test_run_attested_server_writes_content_free_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    model = study.models[0]
    process = _Process()
    marker = tmp_path / "ready.marker"
    marker.write_text("ready", encoding="utf-8")
    lease = tmp_path / "lease.json"
    receipt = tmp_path / "server.json"
    chat_template = tmp_path / "chat-template.jinja"
    chat_template.write_text("test template", encoding="utf-8")
    created_commands: list[list[str]] = []
    from matric_eval.studies.run_status import RunStatus

    status = RunStatus.create(
        tmp_path / "status",
        run_id=study.id,
        attempt_id="a",
        tasks=[{"model_id": model.id, "suite_id": "terminal-bench", "task_id": "frozen"}],
    )
    monkeypatch.setenv("MATRIC_RUN_STATUS_DIR", str(status.directory))
    observed_phases = []
    original_phase = RunStatus.model_phase

    def observe_phase(self, model_id, phase, **kwargs):
        original_phase(self, model_id, phase, **kwargs)
        observed_phases.append(phase)
        assert self.read()["counts"]["valid"] == 0

    monkeypatch.setattr(RunStatus, "model_phase", observe_phase)

    monkeypatch.setattr(
        server_cli.StudyProtocol, "from_yaml", staticmethod(lambda *args, **kwargs: study)
    )
    monkeypatch.setattr(server_cli.platform, "node", lambda: "basilisk")
    monkeypatch.setattr(server_cli, "verify_runtime_environment", lambda server: {"vllm": "0.26.0"})
    monkeypatch.setattr(server_cli, "_load_json_object", lambda *args: {})
    monkeypatch.setattr(server_cli, "verify_model_artifact", lambda *args, **kwargs: "a" * 64)
    monkeypatch.setattr(server_cli, "_wait_for_endpoint", lambda *args, **kwargs: None)
    monkeypatch.setattr(server_cli, "signal_model_resident", lambda model_id: marker)

    def capture(path: Path) -> str:
        path.write_text("{}\n", encoding="utf-8")
        return "b" * 64

    def start(command: list[str]) -> _Process:
        created_commands.append(command)
        return process

    monkeypatch.setattr(server_cli, "capture_active_gpu_lease", capture)
    expected_template_hash = model.runtime.chat_template_sha256
    real_sha256 = server_cli.hashlib.sha256
    monkeypatch.setattr(
        server_cli.hashlib,
        "sha256",
        lambda content=b"": (
            SimpleNamespace(hexdigest=lambda: expected_template_hash)
            if content == b"test template"
            else real_sha256(content)
        ),
    )
    monkeypatch.setenv("MATRIC_EVAL_CODE_REVISION", "c" * 40)

    assert (
        server_cli.run_attested_server(
            protocol_path=PROTOCOL,
            model_id=model.id,
            model_path=tmp_path / "model",
            qualification_path=tmp_path / "qualification.json",
            chat_template_path=chat_template,
            lease_receipt_path=lease,
            server_receipt_path=receipt,
            host="127.0.0.1",
            port=18080,
            ready_timeout=10,
            process_factory=start,
        )
        == 0
    )

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["model_id"] == model.id
    assert payload["lease_receipt_sha256"] == "b" * 64
    assert payload["runtime"]["endpoint_scope"] == "localhost-only"
    assert payload["runtime"]["language_model_only"] is True
    assert payload["runtime"]["architecture_registrations"] == {
        "Qwen3_5ForCausalLM": "matric_eval.studies.qwen35_vllm:Qwen3_5TextForCausalLM"
    }
    assert payload["runtime"]["architecture_registration_plugin"] == (
        "matric_eval_architecture_registry"
    )
    assert "completion" not in json.dumps(payload)
    assert observed_phases == ["loading", "ready", "stopped"]
    assert created_commands[0][0] == sys.executable
    assert not marker.exists()


def test_terminate_child_escalates_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class Stubborn(_Process):
        def wait(self, timeout: int | None = None) -> int:
            if not self.killed:
                raise subprocess.TimeoutExpired("server", timeout)
            return -9

        def terminate(self) -> None:
            self.terminated = True

    process = Stubborn()
    server_cli._terminate_child(process)
    assert process.terminated is True
    assert process.killed is True


def test_main_rejects_invalid_child_registration_and_timeout() -> None:
    with pytest.raises(ValueError, match="registrations must be an object"):
        server_cli.main(["child", "--registrations-json", "[]", "--"])

    with pytest.raises(ValueError, match="ready timeout"):
        server_cli.main(
            [
                "serve",
                str(PROTOCOL),
                "--model-id",
                "source",
                "--model-path",
                "/model",
                "--qualification",
                "/qualification.json",
                "--chat-template",
                "/chat-template.jinja",
                "--lease-receipt",
                "/lease.json",
                "--server-receipt",
                "/server.json",
                "--ready-timeout",
                "0",
            ]
        )
