"""Tests for the broker-attested external-runner model server."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from matric_eval.studies import StudyProtocol, server_cli

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
CHAT_TEMPLATE = ROOT / "studies/qwen38-obliteration-2026-09/chat_template.jinja"


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
    arguments = server_cli._server_arguments(
        study,
        "source",
        tmp_path / "model",
        CHAT_TEMPLATE,
        "127.0.0.1",
        18080,
    )

    assert arguments[0] == str(tmp_path / "model")
    assert arguments[arguments.index("--served-model-name") + 1] == "source"
    assert arguments[arguments.index("--max-num-seqs") + 1] == "1"
    assert arguments[arguments.index("--tool-call-parser") + 1] == "qwen3_coder"
    assert "--disable-log-requests" in arguments
    assert "--disable-access-log" in arguments

    with pytest.raises(ValueError, match="127.0.0.1"):
        server_cli._server_arguments(
            study, "source", tmp_path / "model", CHAT_TEMPLATE, "0.0.0.0", 18080
        )
    with pytest.raises(ValueError, match="between 1024"):
        server_cli._server_arguments(
            study, "source", tmp_path / "model", CHAT_TEMPLATE, "127.0.0.1", 80
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


def test_private_server_receipt_is_non_overwriting(tmp_path: Path) -> None:
    path = tmp_path / "private" / "receipt.json"
    digest = server_cli._write_private_json(path, {"model_id": "source"})

    assert len(digest) == 64
    assert json.loads(path.read_text(encoding="utf-8"))["model_id"] == "source"
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="overwrite"):
        server_cli._write_private_json(path, {})


def test_serve_child_registers_adapter_and_restores_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[tuple[str, str]] = []
    observed_argv: list[str] = []

    class Registry:
        @staticmethod
        def register_model(architecture: str, implementation: str) -> None:
            registered.append((architecture, implementation))

    vllm = ModuleType("vllm")
    vllm.ModelRegistry = Registry  # type: ignore[attr-defined]
    entrypoints = ModuleType("vllm.entrypoints")
    cli = ModuleType("vllm.entrypoints.cli")
    main_module = ModuleType("vllm.entrypoints.cli.main")
    main_module.main = lambda: observed_argv.extend(sys.argv)  # type: ignore[attr-defined]
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
    created_commands: list[list[str]] = []

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
    monkeypatch.setenv("MATRIC_EVAL_CODE_REVISION", "c" * 40)

    assert (
        server_cli.run_attested_server(
            protocol_path=PROTOCOL,
            model_id=model.id,
            model_path=tmp_path / "model",
            qualification_path=tmp_path / "qualification.json",
            chat_template_path=CHAT_TEMPLATE,
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
    assert "completion" not in json.dumps(payload)
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
