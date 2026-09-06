"""Broker-attested vLLM server for official external study runners."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Sequence

from matric_eval.studies.batch import (
    _load_json_object,
    _model_for_id,
    _sha256_file,
    capture_active_gpu_lease,
    signal_model_resident,
    verify_model_artifact,
    verify_runtime_environment,
)
from matric_eval.studies.protocol import StudyProtocol

JsonObject = dict[str, Any]


def _write_private_json(path: Path, payload: JsonObject) -> str:
    """Create one private, durable JSON receipt without overwriting evidence."""
    if path.exists():
        raise ValueError(f"refusing to overwrite server receipt: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return _sha256_file(path)


def _wait_for_endpoint(
    process: subprocess.Popen[Any],
    url: str,
    timeout: float,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait for the child server while failing closed if it exits or times out."""
    deadline = monotonic() + timeout
    while True:
        returncode = process.poll()
        if returncode is not None:
            raise RuntimeError(f"vLLM server exited before readiness with status {returncode}")
        try:
            with opener(url, timeout=2) as response:
                if response.status == 200:
                    response.read(1024)
                    return
        except (OSError, TimeoutError, urllib.error.URLError):
            pass
        if monotonic() >= deadline:
            raise TimeoutError("vLLM server did not become ready before the deadline")
        sleep(0.5)


def _server_arguments(
    study: StudyProtocol,
    model_id: str,
    model_path: Path,
    chat_template: Path,
    host: str,
    port: int,
) -> list[str]:
    """Build the fixed online exception to the otherwise offline inference contract."""
    model = _model_for_id(study, model_id)
    server = study.raw["study"]["execution"]["model_server"]
    if server.get("online_serving_scope") != "official-agent-runners-only":
        raise ValueError("protocol does not authorize online serving for official agent runners")
    if host != "127.0.0.1":
        raise ValueError("study model server must bind only to 127.0.0.1")
    if isinstance(port, bool) or not 1024 <= port <= 65535:
        raise ValueError("study model server port must be between 1024 and 65535")
    arguments = [
        str(model_path),
        "--host",
        host,
        "--port",
        str(port),
        "--served-model-name",
        model.id,
        str(model_path),
        "--dtype",
        model.runtime.dtype,
        "--max-model-len",
        str(model.runtime.context_limit),
        "--tensor-parallel-size",
        str(server["tensor_parallel_size"]),
        "--gpu-memory-utilization",
        str(server["gpu_memory_utilization"]),
        "--safetensors-load-strategy",
        str(server["safetensors_load_strategy"]),
        "--chat-template",
        str(chat_template),
        "--generation-config",
        "vllm",
        "--max-num-seqs",
        str(study.raw["study"]["execution"]["agentic_request_concurrency"]),
        "--language-model-only",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "qwen3_coder",
        "--reasoning-parser",
        "qwen3",
        "--disable-log-requests",
        "--disable-access-log",
    ]
    if server["async_scheduling"]:
        arguments.append("--async-scheduling")
    if server["v1_multiprocessing"] is False:
        os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"
    return arguments


def _serve_child(registrations: JsonObject, arguments: list[str]) -> int:
    """Register runtime-only architectures before entering the pinned vLLM CLI."""
    try:
        from vllm import ModelRegistry  # type: ignore[import-not-found]
        from vllm.entrypoints.cli.main import main as vllm_main  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - pinned A100 image only
        raise RuntimeError("server child requires the protocol-pinned vLLM image") from exc
    for architecture, implementation in registrations.items():
        if not isinstance(architecture, str) or not isinstance(implementation, str):
            raise ValueError("architecture registrations must map strings to strings")
        ModelRegistry.register_model(architecture, implementation)
    previous_argv = sys.argv
    sys.argv = ["vllm", "serve", *arguments]
    try:
        vllm_main()
    finally:
        sys.argv = previous_argv
    return 0


def _terminate_child(process: subprocess.Popen[Any]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def run_attested_server(
    *,
    protocol_path: Path,
    model_id: str,
    model_path: Path,
    qualification_path: Path,
    chat_template_path: Path,
    lease_receipt_path: Path,
    server_receipt_path: Path,
    host: str,
    port: int,
    ready_timeout: int,
    process_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
) -> int:
    """Validate inputs, start vLLM, attest its lease, and supervise it to exit."""
    study = StudyProtocol.from_yaml(protocol_path, validate_registry=False)
    model = _model_for_id(study, model_id)
    server = study.raw["study"]["execution"]["model_server"]
    expected_hostname = study.raw["study"]["execution"].get("expected_hostname")
    if expected_hostname and platform.node() != expected_hostname:
        raise ValueError(f"study server requires host {expected_hostname}, found {platform.node()}")
    if lease_receipt_path.exists():
        raise ValueError(f"refusing to overwrite GPU lease receipt: {lease_receipt_path}")
    if server_receipt_path.exists():
        raise ValueError(f"refusing to overwrite server receipt: {server_receipt_path}")

    runtime_versions = verify_runtime_environment(server)
    qualification = _load_json_object(qualification_path, "model qualification")
    qualification_sha256 = verify_model_artifact(
        model,
        model_path,
        qualification,
        verify_tensor_hashes=False,
    )
    template = chat_template_path.read_text(encoding="utf-8")
    template_sha256 = hashlib.sha256(template.encode()).hexdigest()
    if template_sha256 != model.runtime.chat_template_sha256:
        raise ValueError("chat template SHA-256 does not match the qualified runtime")
    arguments = _server_arguments(study, model_id, model_path, chat_template_path, host, port)
    registrations = server["architecture_registrations"]
    child_command = [
        sys.executable,
        "-m",
        "matric_eval.studies.server_cli",
        "child",
        "--registrations-json",
        json.dumps(registrations, sort_keys=True),
        "--",
        *arguments,
    ]
    initialization_started = time.time()
    process = process_factory(child_command)

    previous_handlers: dict[signal.Signals, Any] = {}

    def stop_child(_signum: int, _frame: Any) -> None:
        _terminate_child(process)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, stop_child)
    try:
        _wait_for_endpoint(process, f"http://{host}:{port}/v1/models", ready_timeout)
        ready_marker = signal_model_resident(model.id)
        try:
            lease_sha256 = capture_active_gpu_lease(lease_receipt_path)
        finally:
            ready_marker.unlink(missing_ok=True)
        receipt = {
            "schema_version": "1",
            "study_id": study.id,
            "protocol_sha256": study.canonical_sha256,
            "model_id": model.id,
            "model_source": model.source,
            "model_revision": model.checkpoint_revision,
            "qualification_sha256": qualification_sha256,
            "chat_template_sha256": template_sha256,
            "lease_receipt_sha256": lease_sha256,
            "runtime": {
                "engine": "vllm",
                "image": server["image"],
                "versions": runtime_versions,
                "matric_eval_revision": os.environ.get("MATRIC_EVAL_CODE_REVISION"),
                "endpoint_scope": "localhost-only",
                "served_model_names": [model.id, str(model_path)],
                "initialization_seconds": time.time() - initialization_started,
                "arguments": arguments,
            },
        }
        _write_private_json(server_receipt_path, receipt)
        returncode = process.wait()
        if returncode:
            raise RuntimeError(f"vLLM server exited with status {returncode}")
        return 0
    finally:
        _terminate_child(process)
        for signum_value, handler in previous_handlers.items():
            signal.signal(signum_value, handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve")
    serve.add_argument("protocol", type=Path)
    serve.add_argument("--model-id", required=True)
    serve.add_argument("--model-path", type=Path, required=True)
    serve.add_argument("--qualification", type=Path, required=True)
    serve.add_argument("--chat-template", type=Path, required=True)
    serve.add_argument("--lease-receipt", type=Path, required=True)
    serve.add_argument("--server-receipt", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=18080)
    serve.add_argument("--ready-timeout", type=int, default=900)

    child = subparsers.add_parser("child")
    child.add_argument("--registrations-json", required=True)
    child.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "child":
        registrations = json.loads(args.registrations_json)
        if not isinstance(registrations, dict):
            raise ValueError("architecture registrations must be an object")
        arguments = list(args.arguments)
        if arguments and arguments[0] == "--":
            arguments.pop(0)
        return _serve_child(registrations, arguments)
    if not 1 <= args.ready_timeout <= 1800:
        raise ValueError("ready timeout must be between 1 and 1800 seconds")
    return run_attested_server(
        protocol_path=args.protocol,
        model_id=args.model_id,
        model_path=args.model_path.resolve(),
        qualification_path=args.qualification,
        chat_template_path=args.chat_template,
        lease_receipt_path=args.lease_receipt,
        server_receipt_path=args.server_receipt,
        host=args.host,
        port=args.port,
        ready_timeout=args.ready_timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
