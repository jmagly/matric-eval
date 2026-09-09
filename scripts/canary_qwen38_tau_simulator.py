#!/usr/bin/env python3
"""Exercise pinned Tau simulator/interface guards against a loopback API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import threading
from collections import Counter, defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

from qwen38_tau_simulator import (
    load_simulator_patch_contract,
    verify_tau_simulator_checkout,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-simulator-interface-guard.json"
)
STUDY_ID = "qwen38-obliteration-2026-09"
RECEIPT_SCHEMA = "matric-eval.qwen38-tau-simulator-canary-receipt/1"
SOURCE_PATHS = (
    Path("scripts/canary_qwen38_tau_simulator.py"),
    Path("scripts/qwen38_tau_simulator.py"),
    Path("scripts/run_qwen38_tau.py"),
    Path("studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-context-guard.json"),
    Path("studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-context-guard.patch"),
    Path("studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-simulator-interface-guard.json"),
    Path("studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-simulator-interface-guard.patch"),
)


class CanaryAssertionError(RuntimeError):
    """Content-free scenario diagnostics for a fail-closed canary receipt."""

    def __init__(self, evidence: dict[str, Any]):
        self.evidence = evidence
        super().__init__("one or more simulator/interface canary assertions failed")


class _ScriptedServer(ThreadingHTTPServer):
    scripts: dict[str, deque[str]]
    requests: Counter[str]

    def __init__(self, address: tuple[str, int]):
        super().__init__(address, _Handler)
        self.scripts = defaultdict(deque)
        self.requests = Counter()


class _Handler(BaseHTTPRequestHandler):
    server: _ScriptedServer

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(length))
        model = str(request.get("model"))
        self.server.requests[model] += 1
        if not self.server.scripts[model]:
            self.send_error(500)
            return
        response_kind = self.server.scripts[model].popleft()
        if response_kind == "html":
            self._write(502, b"<!doctype html><html></html>", "text/html")
            return
        if response_kind == "truncated_json":
            self._write(200, b'{"id":', "application/json")
            return
        if response_kind == "empty_body":
            self._write(200, b"", "application/json")
            return
        content: str | None = {
            "null": None,
            "empty": "",
            "whitespace": " \n\t ",
            "valid": "synthetic-valid",
        }.get(response_kind)
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if response_kind == "malformed_tool":
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "synthetic-call",
                        "type": "function",
                        "function": {"name": "synthetic_tool", "arguments": '{"bad":'},
                    }
                ],
            }
        payload = {
            "id": "chatcmpl-tau-simulator-canary",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        self._write(200, json.dumps(payload).encode(), "application/json")

    def _write(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


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


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    """Exclusively create and durably flush one content-free JSON receipt."""
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite canary receipt: {path}")
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
        "scenario_assertions": None,
        "counts": None,
        "failure": None,
    }


def _run_canary(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_simulator_patch_contract(args.patch_manifest)
    patch_evidence = verify_tau_simulator_checkout(args.tau_checkout, contract)

    from tau2.data_model.message import AssistantMessage
    from tau2.user.user_simulator import UserSimulator
    from tau2.utils.llm_utils import (
        TauRuntimeInvalid,
        generate,
        mark_environment_call,
        scoped_simulation_runtime_evidence,
    )

    server = _ScriptedServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    scenario_assertions: dict[str, Any] = {}

    def simulator_scenario(
        name: str, script: list[str], *, after_side_effect: bool = False
    ) -> tuple[bool, dict[str, Any], dict[str, Any] | None]:
        server.scripts[name].extend(script)
        user = UserSimulator(
            llm=f"openai/{name}",
            instructions="Synthetic loopback canary.",
            llm_args={
                "api_base": f"http://127.0.0.1:{server.server_port}/v1",
                "api_key": "EMPTY",
                "max_tokens": 32,
                "num_retries": 0,
                "timeout": 5,
            },
        )
        state = user.get_init_state()
        failure: dict[str, Any] | None = None
        with scoped_simulation_runtime_evidence() as evidence:
            if after_side_effect:
                mark_environment_call()
            try:
                user.generate_next_message(
                    AssistantMessage(role="assistant", content="synthetic-input"), state
                )
                succeeded = True
            except TauRuntimeInvalid as exc:
                succeeded = False
                failure = dict(exc.evidence)
        return succeeded, evidence.as_dict(), failure

    try:
        for kind in ("null", "empty", "whitespace"):
            name = f"{kind}_then_valid"
            succeeded, evidence, failure = simulator_scenario(name, [kind, "valid"])
            failures = evidence.get("failures", [])
            first_failure = failures[0] if failures else {}
            scenario_assertions[name] = {
                "passed": succeeded
                and failure is None
                and first_failure.get("reason") == "empty_simulator_output",
                "requests": server.requests[name],
                "recoveries": evidence["simulator_recovery_attempts"],
                "first_failure_reason": first_failure.get("reason"),
            }

        succeeded, evidence, failure = simulator_scenario("always_empty", ["empty", "empty"])
        scenario_assertions["always_empty"] = {
            "passed": not succeeded
            and failure is not None
            and failure.get("reason") == "empty_simulator_output"
            and failure.get("actor") == "user-simulator"
            and failure.get("stage") == "simulator-output-validation",
            "requests": server.requests["always_empty"],
            "reason": failure["reason"] if failure else None,
            "actor": failure["actor"] if failure else None,
            "stage": failure["stage"] if failure else None,
            "recoveries": evidence["simulator_recovery_attempts"],
        }

        malformed_reasons = {
            "html": "html_response_body",
            "truncated_json": "truncated_json_response",
            "empty_body": "empty_response_body",
            "malformed_tool": "malformed_tool_arguments",
        }
        for kind, expected_reason in malformed_reasons.items():
            name = f"always_{kind}"
            succeeded, evidence, failure = simulator_scenario(name, [kind, kind])
            scenario_assertions[name] = {
                "passed": not succeeded
                and failure is not None
                and failure.get("reason") == expected_reason
                and failure.get("actor") == "user-simulator"
                and failure.get("stage") == "simulator-sampling",
                "requests": server.requests[name],
                "reason": failure["reason"] if failure else None,
                "actor": failure["actor"] if failure else None,
                "stage": failure["stage"] if failure else None,
                "recoveries": evidence["simulator_recovery_attempts"],
            }

        succeeded, evidence, failure = simulator_scenario(
            "post_side_effect_empty", ["empty"], after_side_effect=True
        )
        scenario_assertions["post_side_effect_empty"] = {
            "passed": not succeeded
            and failure is not None
            and failure.get("reason") == "empty_simulator_output",
            "requests": server.requests["post_side_effect_empty"],
            "environment_calls": evidence["environment_call_count"],
            "recoveries": evidence["simulator_recovery_attempts"],
            "side_effect_retry_attempted": evidence["side_effect_retry_attempted"],
        }

        for call_name, actor, stage in (
            ("agent_response", "target-model", "target-sampling"),
            ("nl_assertions_eval", "evaluator", "nl-evaluation"),
        ):
            name = stage
            server.scripts[name].append("truncated_json")
            with scoped_simulation_runtime_evidence():
                try:
                    generate(
                        model=f"openai/{name}",
                        messages=[AssistantMessage(role="assistant", content="synthetic-input")],
                        call_name=call_name,
                        api_base=f"http://127.0.0.1:{server.server_port}/v1",
                        api_key="EMPTY",
                        max_tokens=32,
                        num_retries=0,
                        timeout=5,
                    )
                except TauRuntimeInvalid as exc:
                    observed = dict(exc.evidence)
                else:
                    raise RuntimeError(f"{stage} malformed response was not rejected")
            scenario_assertions[stage] = {
                "passed": observed.get("actor") == actor
                and observed.get("stage") == stage
                and observed.get("reason") == "truncated_json_response",
                "requests": server.requests[name],
                "reason": observed.get("reason"),
                "actor": observed.get("actor"),
                "stage": observed.get("stage"),
            }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    expected_requests = {
        "null_then_valid": 2,
        "empty_then_valid": 2,
        "whitespace_then_valid": 2,
        "always_empty": 2,
        "always_html": 2,
        "always_truncated_json": 2,
        "always_empty_body": 2,
        "always_malformed_tool": 2,
        "post_side_effect_empty": 1,
        "target-sampling": 1,
        "nl-evaluation": 1,
    }
    failed_scenarios = sorted(
        name for name, item in scenario_assertions.items() if not item.get("passed")
    )
    request_mismatches = {
        name: {"expected": expected, "observed": server.requests[name]}
        for name, expected in expected_requests.items()
        if server.requests[name] != expected
    }
    post_side_effect_recoveries = scenario_assertions["post_side_effect_empty"]["recoveries"]
    if failed_scenarios or request_mismatches or post_side_effect_recoveries != 0:
        failure_observations = {
            name: {
                key: scenario_assertions[name].get(key)
                for key in (
                    "actor",
                    "stage",
                    "reason",
                    "first_failure_reason",
                    "requests",
                    "recoveries",
                )
                if key in scenario_assertions[name]
            }
            for name in failed_scenarios
        }
        raise CanaryAssertionError(
            {
                "failed_scenarios": failed_scenarios,
                "failure_observations": failure_observations,
                "request_mismatches": request_mismatches,
                "post_side_effect_recoveries": post_side_effect_recoveries,
            }
        )
    return {
        "tau": patch_evidence,
        "scenario_assertions": scenario_assertions,
        "counts": {
            "http_requests": sum(server.requests.values()),
            "bounded_recoveries": 8,
            "side_effect_retries": 0,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tau-checkout", type=Path, required=True)
    parser.add_argument("--patch-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = _base_receipt()
    try:
        receipt.update(_run_canary(args))
        receipt["status"] = "passed"
    except BaseException as exc:
        receipt["failure"] = {"type": type(exc).__name__}
        if isinstance(exc, CanaryAssertionError):
            receipt["failure"]["evidence"] = exc.evidence
    _write_receipt(args.output, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
