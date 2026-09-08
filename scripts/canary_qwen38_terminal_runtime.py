#!/usr/bin/env python3
"""Exercise the patched Harbor runtime with scripted, model-independent trials."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

from qwen38_terminal_runtime import (
    classify_trial,
    load_patch_contract,
    run_with_watchdog,
    verify_harbor_checkout,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/harbor-0.22.0-terminal-runtime-guard.json"
)
STUDY_ID = "qwen38-obliteration-2026-09"
RECEIPT_SCHEMA = "matric-eval.qwen38-terminal-runtime-canary-receipt/1"
SOURCE_PATHS = (
    Path("scripts/canary_qwen38_terminal_runtime.py"),
    Path("scripts/qwen38_terminal_runtime.py"),
    Path("scripts/run_qwen38_terminal.py"),
    Path("studies/qwen38-obliteration-2026-09/patches/harbor-0.22.0-terminal-runtime-guard.json"),
    Path("studies/qwen38-obliteration-2026-09/patches/harbor-0.22.0-terminal-runtime-guard.patch"),
)


def _response(content: str, model: str) -> dict[str, Any]:
    return {
        "id": "terminal-runtime-canary",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _action(command: str = "", *, complete: bool = False) -> str:
    commands = [] if not command else [{"keystrokes": command, "duration": 0.1}]
    return json.dumps(
        {
            "analysis": "scripted canary action",
            "plan": "execute the deterministic fixture",
            "commands": commands,
            "task_complete": complete,
        }
    )


class _ScriptedServer(ThreadingHTTPServer):
    scripts: dict[str, list[tuple[str, float] | str]]
    counts: dict[str, int]

    def __init__(self, scripts: dict[str, list[tuple[str, float] | str]]) -> None:
        super().__init__(("127.0.0.1", 0), _ScriptedHandler)
        self.scripts = scripts
        self.counts = {name: 0 for name in scripts}


class _ScriptedHandler(BaseHTTPRequestHandler):
    server: _ScriptedServer

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(length))
        model_value = request.get("model")
        model = str(model_value).rsplit("/", 1)[-1]
        if self.path != "/v1/chat/completions" or model not in self.server.scripts:
            self.send_error(400)
            return
        index = self.server.counts[model]
        self.server.counts[model] = index + 1
        script = self.server.scripts[model]
        item = script[index] if index < len(script) else script[-1]
        if isinstance(item, tuple):
            kind, delay = item
            time.sleep(delay)
            if kind == "slow":
                item = _action()
            else:
                item = kind
        if item == "context_error":
            payload: dict[str, Any] = {
                "error": {
                    "message": "scripted context limit",
                    "type": "invalid_request_error",
                    "param": "messages",
                    "code": "context_length_exceeded",
                }
            }
            status = 400
        else:
            payload = _response(str(item), model)
            status = 200
        encoded = json.dumps(payload).encode()
        try:
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, format: str, *args: object) -> None:
        return


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _code_revision() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _source_evidence() -> dict[str, str]:
    return {path.as_posix(): _sha256_file(ROOT / path) for path in SOURCE_PATHS}


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


def _make_task(root: Path) -> Path:
    task = root / "terminal-runtime-canary"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "instruction.md").write_text(
        "Create the requested sentinel and explicitly submit completion.\n",
        encoding="utf-8",
    )
    (task / "environment/Dockerfile").write_text(
        "FROM ubuntu:24.04\n\nWORKDIR /app\n", encoding="utf-8"
    )
    test_script = task / "tests/test.sh"
    test_script.write_text(
        "#!/bin/sh\n"
        'if [ -f /app/sentinel ] && [ "$(wc -l < /app/sentinel)" -eq 1 ]; then\n'
        "  echo 1 > /logs/verifier/reward.txt\n"
        "else\n"
        "  echo 0 > /logs/verifier/reward.txt\n"
        "fi\n",
        encoding="utf-8",
    )
    test_script.chmod(0o755)
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n\n'
        "[task]\n"
        'name = "matric-eval/terminal-runtime-canary"\n'
        'version = "1.0.0"\n'
        "authors = []\n"
        "keywords = []\n\n"
        "[metadata]\n"
        'author_name = "matric-eval"\n'
        'author_email = "noreply@example.invalid"\n'
        'difficulty = "easy"\n'
        'category = "canary"\n'
        'tags = ["canary"]\n\n'
        "[verifier]\n"
        "timeout_sec = 30.0\n\n"
        "[agent]\n"
        "timeout_sec = 30.0\n\n"
        "[environment]\n"
        "build_timeout_sec = 120.0\n"
        "cpus = 1\n"
        "memory_mb = 512\n"
        "storage_mb = 1024\n"
        "gpus = 0\n"
        "mcp_servers = []\n\n"
        "[verifier.env]\n\n"
        "[solution.env]\n",
        encoding="utf-8",
    )
    return task


def _agent_kwargs(port: int, model: str, *, max_turns: int, timeout: float) -> dict[str, Any]:
    return {
        "parser_name": "json",
        "api_base": f"http://127.0.0.1:{port}/v1",
        "temperature": 0.0,
        "max_turns": max_turns,
        "enable_summarize": True,
        "proactive_summarization_threshold": 0,
        "max_recovery_attempts": 1,
        "suppress_max_turns_warning": True,
        "model_info": {
            "max_input_tokens": 24544,
            "max_output_tokens": 8192,
            "input_cost_per_token": 0.0,
            "output_cost_per_token": 0.0,
            "cache_creation_input_token_cost": 0.0,
            "cache_read_input_token_cost": 0.0,
        },
        "llm_kwargs": {"api_key": "EMPTY", "timeout": timeout, "num_retries": 0},
        "llm_call_kwargs": {
            "max_tokens": 8192,
            "seed": 0,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
        "session_id": f"terminal-runtime-{model}",
    }


async def _run_trial(
    *,
    task: Path,
    trials_dir: Path,
    port: int,
    model: str,
    max_turns: int,
    timeout: float,
) -> dict[str, Any]:
    from harbor.models.agent.name import AgentName
    from harbor.models.environment_type import EnvironmentType
    from harbor.models.trial.config import (
        AgentConfig,
        EnvironmentConfig,
        TaskConfig,
        TrialConfig,
    )
    from harbor.trial.trial import Trial

    config = TrialConfig(
        task=TaskConfig(path=task),
        agent=AgentConfig(
            name=AgentName.TERMINUS_2.value,
            model_name=f"hosted_vllm/{model}",
            kwargs=_agent_kwargs(port, model, max_turns=max_turns, timeout=timeout),
        ),
        environment=EnvironmentConfig(
            type=EnvironmentType.DOCKER,
            force_build=False,
            delete=True,
        ),
        trials_dir=trials_dir,
    )
    trial = await Trial.create(config=config)
    return trial_result_to_dict(await trial.run())


def _run_trial_subprocess(
    *,
    task: Path,
    trials_dir: Path,
    port: int,
    model: str,
    max_turns: int,
    timeout: float,
    output: Path,
) -> tuple[dict[str, Any], int]:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--_single-trial",
            "--task",
            str(task),
            "--trials-dir",
            str(trials_dir),
            "--port",
            str(port),
            "--model",
            model,
            "--max-turns",
            str(max_turns),
            "--timeout",
            str(timeout),
            "--result-output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0 or not output.is_file():
        raise RuntimeError("failed-trial subprocess did not retain a Harbor result")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("failed-trial subprocess result must be an object")
    return payload, completed.returncode


def trial_result_to_dict(result: Any) -> dict[str, Any]:
    payload = result.model_dump(mode="json", exclude_none=True)
    if not isinstance(payload, dict):
        raise RuntimeError("Harbor trial result did not serialize to an object")
    return payload


def _exception_type(result: dict[str, Any]) -> str | None:
    exception = result.get("exception_info")
    value = exception.get("exception_type") if isinstance(exception, dict) else None
    return value if isinstance(value, str) else None


def _official_reward(result: dict[str, Any]) -> float | int | None:
    verifier = result.get("verifier_result")
    rewards = verifier.get("rewards") if isinstance(verifier, dict) else None
    reward = rewards.get("reward") if isinstance(rewards, dict) else None
    return reward if isinstance(reward, (int, float)) and not isinstance(reward, bool) else None


def _runtime_control(result: dict[str, Any]) -> dict[str, Any]:
    agent = result.get("agent_result")
    metadata = agent.get("metadata") if isinstance(agent, dict) else None
    control = metadata.get("runtime_control") if isinstance(metadata, dict) else None
    if not isinstance(control, dict):
        raise RuntimeError("patched Harbor result lacks runtime-control metadata")
    return control


def _assert_trial(
    result: dict[str, Any],
    *,
    exception_type: str | None,
    reward: float | int | None,
) -> dict[str, Any]:
    actual_exception = _exception_type(result)
    actual_reward = _official_reward(result)
    if actual_exception != exception_type or actual_reward != reward:
        raise RuntimeError("scripted Harbor trial produced an unexpected typed outcome")
    rewards = {"reward": actual_reward} if actual_reward is not None else None
    analytic = classify_trial(
        exception_type=actual_exception,
        rewards=rewards,
        harbor_exit_code=0,
        watchdog_timed_out=False,
    )
    return {
        "exception_type": actual_exception,
        "official_reward": actual_reward,
        "analytic_status": analytic["status"],
        "analytic_reason": analytic["reason"],
        "runtime_control": _runtime_control(result),
    }


def _watchdog_case(root: Path, name: str, *, leader_ignores_term: bool) -> dict[str, Any]:
    child_pid_path = root / f"watchdog-{name}-child.pid"
    leader_signal = "signal.signal(signal.SIGTERM,signal.SIG_IGN);" if leader_ignores_term else ""
    code = (
        "import os,signal,subprocess,sys,time;"
        f"{leader_signal}"
        "child=subprocess.Popen([sys.executable,'-c',"
        "'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)']);"
        f"open({str(child_pid_path)!r},'w').write(str(child.pid));"
        "time.sleep(60)"
    )
    stdout_path = root / f"watchdog-{name}.stdout"
    stderr_path = root / f"watchdog-{name}.stderr"
    with (
        stdout_path.open("x", encoding="utf-8") as stdout,
        stderr_path.open("x", encoding="utf-8") as stderr,
    ):
        result = run_with_watchdog(
            [sys.executable, "-c", code],
            cwd=root,
            env=os.environ,
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=0.5,
            teardown_grace_seconds=1.0,
        )
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    child_gone = not Path(f"/proc/{child_pid}").exists()
    if not (result.timed_out and result.sent_sigterm and result.sent_sigkill and child_gone):
        raise RuntimeError("parent watchdog did not bound and reap its process group")
    return {
        "timed_out": result.timed_out,
        "sent_sigterm": result.sent_sigterm,
        "sent_sigkill": result.sent_sigkill,
        "child_process_gone": child_gone,
    }


def _watchdog_cleanup(root: Path) -> dict[str, Any]:
    leader_ignores = _watchdog_case(root, "leader-ignores", leader_ignores_term=True)
    leader_exits = _watchdog_case(root, "leader-exits", leader_ignores_term=False)
    if not leader_exits["sent_sigkill"]:
        raise RuntimeError("watchdog did not kill descendants after the leader exited")
    return {
        **leader_ignores,
        "leader_exits_child_cleaned": leader_exits["child_process_gone"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harbor-checkout", type=Path, required=True)
    parser.add_argument("--patch-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--docker-host", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _single_trial_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--trials-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-turns", type=int, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    return parser


def _single_trial_main(argv: Sequence[str]) -> int:
    args = _single_trial_parser().parse_args(argv)
    result = asyncio.run(
        _run_trial(
            task=args.task,
            trials_dir=args.trials_dir,
            port=args.port,
            model=args.model,
            max_turns=args.max_turns,
            timeout=args.timeout,
        )
    )
    with args.result_output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True)
    return 0


def _base_receipt() -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "schema_version": "1",
        "study_id": STUDY_ID,
        "status": "failed",
        "host": socket.gethostname(),
        "matric_eval_revision": _code_revision(),
        "source_sha256": _source_evidence(),
        "harbor": None,
        "assertions": None,
        "counts": None,
        "failure": None,
    }


def _run_canary(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_patch_contract(args.patch_manifest)
    patch_evidence = verify_harbor_checkout(args.harbor_checkout, contract)
    if importlib.metadata.version("harbor") != contract.package_version:
        raise RuntimeError("imported Harbor package version differs from patch contract")
    import harbor

    harbor_source = Path(str(harbor.__file__)).resolve()
    if not harbor_source.is_relative_to(args.harbor_checkout.resolve()):
        raise RuntimeError("canary did not import Harbor from the patched checkout")

    os.environ["OPENAI_API_KEY"] = "EMPTY"
    os.environ["DOCKER_HOST"] = args.docker_host
    scripts: dict[str, list[tuple[str, float] | str]] = {
        "canary-success": [
            _action("printf 'canary\\n' >> /app/sentinel\n"),
            _action(complete=True),
            _action(complete=True),
        ],
        "canary-recovery": [
            "not-json",
            _action("printf 'canary\\n' >> /app/sentinel\n"),
            _action(complete=True),
            _action(complete=True),
        ],
        "canary-output-exhausted": ["not-json", "still-not-json"],
        "canary-no-submit": [_action(), _action()],
        "canary-timeout": [("slow", 2.0)],
        "canary-context-preflight": ["context_error"],
        "canary-context-recovery": [
            _action(),
            "context_error",
            "context_error",
        ],
    }
    server = _ScriptedServer(scripts)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="qwen38-terminal-canary-") as temporary:
            root = Path(temporary)
            task = _make_task(root)

            async def run_trials() -> dict[str, dict[str, Any]]:
                outcomes: dict[str, dict[str, Any]] = {}
                failed_trial_exit_code: int | None = None
                specifications = (
                    ("success", "canary-success", 4, 2.0, None, 1),
                    ("recovery", "canary-recovery", 5, 2.0, None, 1),
                    (
                        "output_recovery_exhausted",
                        "canary-output-exhausted",
                        3,
                        2.0,
                        "OutputRecoveryExhaustedError",
                        None,
                    ),
                    (
                        "agent_no_submit",
                        "canary-no-submit",
                        2,
                        2.0,
                        "AgentNoSubmitError",
                        None,
                    ),
                    (
                        "llm_response_timeout",
                        "canary-timeout",
                        2,
                        0.25,
                        "LLMResponseTimeoutError",
                        None,
                    ),
                    (
                        "context_preflight",
                        "canary-context-preflight",
                        2,
                        2.0,
                        "ContextPreflightError",
                        None,
                    ),
                    (
                        "context_recovery_exhausted",
                        "canary-context-recovery",
                        4,
                        2.0,
                        "ContextRecoveryExhaustedError",
                        None,
                    ),
                )
                for name, model, max_turns, timeout, exception, reward in specifications:
                    if name == "agent_no_submit":
                        result, failed_trial_exit_code = _run_trial_subprocess(
                            task=task,
                            trials_dir=root / "trials" / name,
                            port=server.server_port,
                            model=model,
                            max_turns=max_turns,
                            timeout=timeout,
                            output=root / "failed-trial-result.json",
                        )
                    else:
                        result = await _run_trial(
                            task=task,
                            trials_dir=root / "trials" / name,
                            port=server.server_port,
                            model=model,
                            max_turns=max_turns,
                            timeout=timeout,
                        )
                    outcomes[name] = _assert_trial(result, exception_type=exception, reward=reward)
                if failed_trial_exit_code != 0:
                    raise RuntimeError("typed failed Harbor trial did not exit zero")
                outcomes["agent_no_submit"]["subprocess_exit_code"] = failed_trial_exit_code
                return outcomes

            outcomes = asyncio.run(run_trials())
            watchdog = _watchdog_cleanup(root)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    if server.counts != {
        "canary-success": 3,
        "canary-recovery": 4,
        "canary-output-exhausted": 2,
        "canary-no-submit": 2,
        "canary-timeout": 1,
        "canary-context-preflight": 1,
        "canary-context-recovery": 3,
    }:
        raise RuntimeError("scripted server request counts reveal hidden retries")
    if outcomes["recovery"]["runtime_control"]["recovery_attempts"] != 1:
        raise RuntimeError("bounded recovery canary did not consume exactly one recovery")
    if outcomes["success"]["runtime_control"]["submitted"] is not True:
        raise RuntimeError("success canary did not latch verified submission")

    return {
        "harbor": patch_evidence,
        "assertions": {
            "tiny_sentinel_submit": outcomes["success"],
            "bounded_recovery": outcomes["recovery"],
            "output_recovery_exhausted": outcomes["output_recovery_exhausted"],
            "agent_no_submit": outcomes["agent_no_submit"],
            "llm_response_timeout": outcomes["llm_response_timeout"],
            "context_preflight": outcomes["context_preflight"],
            "context_recovery_exhausted": outcomes["context_recovery_exhausted"],
            "command_timeout_cleanup": watchdog,
            "failed_trial_exit_zero": outcomes["agent_no_submit"]["subprocess_exit_code"] == 0,
            "official_verifier_preserved": True,
        },
        "counts": {
            "http_requests": sum(server.counts.values()),
            "http_requests_by_scenario": server.counts,
            "hidden_http_retries": 0,
            "recovery_attempts": outcomes["recovery"]["runtime_control"]["recovery_attempts"],
            "side_effect_retries": 0,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _ensure_output_available(args.output)
    receipt = _base_receipt()
    try:
        receipt.update(_run_canary(args))
    except Exception as error:
        receipt["failure"] = {"type": type(error).__name__}
        _write_receipt(args.output, receipt)
        raise
    receipt["status"] = "passed"
    _write_receipt(args.output, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--_single-trial":
        raise SystemExit(_single_trial_main(sys.argv[2:]))
    raise SystemExit(main())
