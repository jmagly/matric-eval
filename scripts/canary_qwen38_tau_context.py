#!/usr/bin/env python3
"""Exercise the patched Tau context guard against a scripted local API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

from qwen38_tau_context import (
    TargetContextGuard,
    TargetContextRuntimeInvalid,
    TokenCounter,
    load_attested_tokenizer,
    load_patch_contract,
)
from qwen38_tau_simulator import (
    load_simulator_patch_contract,
    verify_tau_simulator_checkout,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-context-guard.json"
)
DEFAULT_SIMULATOR_MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-simulator-interface-guard.json"
)
STUDY_ID = "qwen38-obliteration-2026-09"
RECEIPT_SCHEMA = "matric-eval.qwen38-tau-context-canary-receipt/1"
SOURCE_PATHS = (
    Path("scripts/canary_qwen38_tau_context.py"),
    Path("scripts/qwen38_tau_context.py"),
    Path("scripts/qwen38_tau_simulator.py"),
    Path("studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-context-guard.json"),
    Path("studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-context-guard.patch"),
    Path("studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-simulator-interface-guard.json"),
    Path("studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-simulator-interface-guard.patch"),
)


class _CanaryServer(ThreadingHTTPServer):
    requests_seen: int = 0


class _Handler(BaseHTTPRequestHandler):
    server: _CanaryServer

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(length))
        if self.path != "/v1/chat/completions" or request.get("max_tokens") != 8192:
            self.send_error(400)
            return
        self.server.requests_seen += 1
        payload = {
            "id": "chatcmpl-context-canary",
            "object": "chat.completion",
            "created": 0,
            "model": "canary",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "canary-ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def _messages(content: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "Tau context boundary canary."},
        {"role": "user", "content": content},
    ]


def _fit_content(
    count_tokens: TokenCounter,
    tools_schema: list[dict[str, Any]],
    target_tokens: int,
) -> str:
    """Find a deterministic repeated-token payload at an exact rendered size."""

    def size(repetitions: int) -> int:
        return count_tokens(_messages(" x" * repetitions), tools_schema)

    low, high = 0, target_tokens
    while size(high) < target_tokens:
        high *= 2
    while low < high:
        middle = (low + high) // 2
        if size(middle) < target_tokens:
            low = middle + 1
        else:
            high = middle
    for repetitions in range(max(0, low - 16), low + 17):
        if size(repetitions) == target_tokens:
            return " x" * repetitions
    raise RuntimeError(f"real tokenizer could not construct exact {target_tokens}-token fixture")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tau-checkout", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--chat-template", type=Path, required=True)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--patch-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--simulator-patch-manifest", type=Path, default=DEFAULT_SIMULATOR_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _source_evidence() -> dict[str, str]:
    return {path.as_posix(): _sha256_file(ROOT / path) for path in SOURCE_PATHS}


def _code_revision() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _ensure_output_available(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite canary receipt: {path}")


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    """Exclusively create and durably flush one content-free JSON receipt."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _base_receipt() -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "schema_version": "1",
        "study_id": STUDY_ID,
        "status": "failed",
        "host": socket.gethostname(),
        "matric_eval_revision": _code_revision(),
        "source_sha256": _source_evidence(),
        "tau": None,
        "tokenizer": None,
        "boundary_assertions": None,
        "counts": None,
        "failure": None,
    }


def _run_canary(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_patch_contract(args.patch_manifest)
    simulator_contract = load_simulator_patch_contract(args.simulator_patch_manifest)
    if simulator_contract.context_contract != contract:
        raise RuntimeError("context canary manifests do not describe one patch chain")
    patch_evidence = verify_tau_simulator_checkout(args.tau_checkout, simulator_contract)
    server_receipt = json.loads(args.server_receipt.read_text(encoding="utf-8"))
    runtime = server_receipt.get("runtime", {})
    versions = runtime.get("versions", {}) if isinstance(runtime, dict) else {}
    if versions.get("transformers") != contract.transformers_version:
        raise RuntimeError("server and patched Tau Transformers versions differ")
    expected_template = server_receipt.get("chat_template_sha256")
    if not isinstance(expected_template, str):
        raise RuntimeError("server receipt lacks its chat-template attestation")
    count_tokens, tokenizer_evidence = load_attested_tokenizer(
        model_path=args.model_path,
        chat_template_path=args.chat_template,
        expected_template_sha256=expected_template,
        expected_transformers_version=contract.transformers_version,
    )

    from tau2.data_model.message import SystemMessage, UserMessage
    from tau2.environment.tool import as_tool
    from tau2.utils.llm_utils import generate, scoped_llm_request_guard

    def canary_echo(value: str) -> str:
        """Return the supplied canary value."""
        return value

    tool = as_tool(canary_echo)
    tools_schema = [tool.openai_schema]
    accepted_content = _fit_content(count_tokens, tools_schema, 24544)
    rejected_content = _fit_content(count_tokens, tools_schema, 24545)
    server = _CanaryServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target_model = "hosted_vllm/qwen38-context-canary"
    budget = {
        "max_context_tokens": 32768,
        "max_input_tokens": 24544,
        "max_output_tokens": 8192,
        "safety_margin_tokens": 32,
    }
    try:
        guard = TargetContextGuard(target_model, budget, count_tokens)
        with scoped_llm_request_guard(guard):
            generate(
                model=target_model,
                messages=[
                    SystemMessage(role="system", content="Tau context boundary canary."),
                    UserMessage(role="user", content=accepted_content),
                ],
                tools=[tool],
                call_name="agent_response",
                api_base=f"http://127.0.0.1:{server.server_port}/v1",
                api_key="EMPTY",
                max_tokens=8192,
                num_retries=0,
            )
        accepted_observation = guard.observations[-1]
        if (
            server.requests_seen != 1
            or accepted_observation["input_tokens"] != 24544
            or accepted_observation["combined_tokens"] != 32768
        ):
            raise RuntimeError("32768-token accepted canary did not make exactly one HTTP call")

        trajectory_attempts = 0
        side_effects = 0
        rejected_guard = TargetContextGuard(target_model, budget, count_tokens)

        def rejected_attempt() -> None:
            nonlocal trajectory_attempts, side_effects
            trajectory_attempts += 1
            side_effects += 1
            with scoped_llm_request_guard(rejected_guard):
                generate(
                    model=target_model,
                    messages=[
                        SystemMessage(role="system", content="Tau context boundary canary."),
                        UserMessage(role="user", content=rejected_content),
                    ],
                    tools=[tool],
                    call_name="agent_response",
                    api_base=f"http://127.0.0.1:{server.server_port}/v1",
                    api_key="EMPTY",
                    max_tokens=8192,
                    num_retries=0,
                )

        try:
            rejected_attempt()
        except TargetContextRuntimeInvalid as exc:
            rejected_observation = exc.observation
            if (
                rejected_observation["input_tokens"] != 24545
                or rejected_observation["combined_tokens"] != 32769
            ):
                raise RuntimeError(
                    "rejected canary reported the wrong combined-token count"
                ) from exc
        else:
            raise RuntimeError("32769-token request was not rejected")
        if server.requests_seen != 1 or trajectory_attempts != 1 or side_effects != 1:
            raise RuntimeError("rejected request retried HTTP or a prior side effect")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return {
        "tau": {
            "upstream_revision": patch_evidence["upstream_revision"],
            "patch_sha256": patch_evidence["patch_file_sha256"],
            "applied_diff_sha256": patch_evidence["tracked_diff_sha256"],
            "changed_paths": patch_evidence["tracked_changes"],
        },
        "tokenizer": tokenizer_evidence,
        "boundary_assertions": {
            "accepted_input_tokens": accepted_observation["input_tokens"],
            "accepted_output_tokens": accepted_observation["output_tokens"],
            "accepted_safety_margin_tokens": accepted_observation["safety_margin_tokens"],
            "accepted_combined_tokens": accepted_observation["combined_tokens"],
            "context_limit_tokens": accepted_observation["context_limit"],
            "rejected_input_tokens": rejected_observation["input_tokens"],
            "rejected_output_tokens": rejected_observation["output_tokens"],
            "rejected_safety_margin_tokens": rejected_observation["safety_margin_tokens"],
            "rejected_combined_tokens": rejected_observation["combined_tokens"],
            "rejected_before_http": True,
        },
        "counts": {
            "http_requests": server.requests_seen,
            "trajectory_attempts": trajectory_attempts,
            "side_effect_retries": 0,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _ensure_output_available(args.output)
    receipt = _base_receipt()
    try:
        receipt.update(_run_canary(args))
    except Exception as exc:
        receipt["failure"] = {"type": type(exc).__name__}
        _write_receipt(args.output, receipt)
        raise
    receipt["status"] = "passed"
    _write_receipt(args.output, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
