"""Unit tests for the pinned Harbor runtime and parent watchdog."""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import qwen38_terminal_runtime as runtime  # noqa: E402

MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/harbor-0.22.0-terminal-runtime-guard.json"
)


def test_patch_manifest_is_content_addressed() -> None:
    contract = runtime.load_patch_contract(MANIFEST)
    assert contract.upstream_revision == "4407eb5227a2ff4f0d3f16b2eb48849382fdf276"
    assert contract.package_version == "0.22.0"
    assert contract.patch_sha256 == hashlib.sha256(contract.patch_path.read_bytes()).hexdigest()
    assert contract.patch_sha256 == contract.patched_diff_sha256
    assert contract.changed_paths == (
        "src/harbor/agents/terminus_2/terminus_2.py",
        "src/harbor/llms/base.py",
        "src/harbor/llms/lite_llm.py",
    )


@pytest.mark.parametrize(
    ("exception_type", "reason"),
    [
        ("ContextPreflightError", "context_preflight"),
        ("ContextRecoveryExhaustedError", "context_recovery_exhausted"),
        ("OutputRecoveryExhaustedError", "output_recovery_exhausted"),
        ("LLMResponseTimeoutError", "llm_response_timeout"),
        ("CommandTimeoutError", "command_timeout"),
        ("AgentNoSubmitError", "agent_no_submit"),
        ("AgentTimeoutError", "agent_no_submit"),
    ],
)
def test_trial_exceptions_are_analytic_invalid(exception_type: str, reason: str) -> None:
    result = runtime.classify_trial(
        exception_type=exception_type,
        rewards={"reward": 0},
        harbor_exit_code=0,
        watchdog_timed_out=False,
    )
    assert result["status"] == "invalid"
    assert result["reason"] == reason
    assert result["exception_chain"] == [{"type": exception_type}]


def test_official_zero_is_valid_but_missing_reward_is_not() -> None:
    valid = runtime.classify_trial(
        exception_type=None,
        rewards={"reward": 0},
        harbor_exit_code=0,
        watchdog_timed_out=False,
    )
    missing = runtime.classify_trial(
        exception_type=None,
        rewards={},
        harbor_exit_code=0,
        watchdog_timed_out=False,
    )
    assert valid["status"] == "valid"
    assert missing["status"] == "invalid"
    assert missing["reason"] == "missing_reward"


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True])
def test_nonfinite_or_boolean_reward_is_invalid(invalid: Any) -> None:
    result = runtime.classify_trial(
        exception_type=None,
        rewards={"reward": invalid},
        harbor_exit_code=0,
        watchdog_timed_out=False,
    )
    assert result["status"] == "invalid"
    assert result["reason"] == "missing_reward"


def test_watchdog_terminates_then_kills_one_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[float] = []

    class Process:
        pid = 4242

        def wait(self, timeout: float) -> int:
            waits.append(timeout)
            if len(waits) == 1:
                raise runtime.subprocess.TimeoutExpired(["fixture"], timeout)
            return -9

        def poll(self) -> int | None:
            return None

    process = Process()
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *args, **kwargs: process)
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(runtime.os, "killpg", lambda pid, signum: signals.append((pid, signum)))
    group_waits: list[float] = []

    def wait_for_group(_: object, deadline: float) -> bool:
        group_waits.append(deadline)
        return len(group_waits) == 2

    monkeypatch.setattr(runtime, "_wait_for_process_group_exit", wait_for_group)
    ticks = iter([10.0, 11.0, 12.0, 14.5])
    monkeypatch.setattr(runtime.time, "monotonic", lambda: next(ticks))
    stdout = (tmp_path / "stdout").open("w", encoding="utf-8")
    stderr = (tmp_path / "stderr").open("w", encoding="utf-8")
    try:
        result = runtime.run_with_watchdog(
            ["fixture"],
            cwd=tmp_path,
            env={},
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=3.0,
            teardown_grace_seconds=1.0,
        )
    finally:
        stdout.close()
        stderr.close()
    assert waits == [3.0, 1.0]
    assert group_waits == [12.0, 13.0]
    assert signals == [
        (4242, runtime.signal.SIGTERM),
        (4242, runtime.signal.SIGKILL),
    ]
    assert result == runtime.WatchdogResult(-9, True, True, True, 4.5)


def test_watchdog_kills_child_when_leader_exits_on_sigterm(tmp_path: Path) -> None:
    if sys.platform != "linux":
        pytest.skip("Linux process-group fixture")
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0  # PR_GET_CHILD_SUBREAPER
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        pytest.skip("Linux child-subreaper support is unavailable")
    child_pid_path = tmp_path / "child.pid"
    code = (
        "import subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c',"
        "'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)']);"
        f"open({str(child_pid_path)!r},'w').write(str(child.pid));"
        "time.sleep(60)"
    )
    child_pid: int | None = None
    stop_reaper = threading.Event()

    def reap_adopted_child() -> None:
        deadline = time.monotonic() + 5
        while not stop_reaper.is_set() and time.monotonic() < deadline:
            if child_pid_path.is_file():
                try:
                    pid = int(child_pid_path.read_text(encoding="utf-8"))
                except ValueError:
                    time.sleep(0.01)
                    continue
                try:
                    reaped, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    reaped = 0
                if reaped == pid:
                    return
            time.sleep(0.01)

    reaper = threading.Thread(target=reap_adopted_child, daemon=True)
    reaper.start()
    with (
        (tmp_path / "stdout").open("x", encoding="utf-8") as stdout,
        (tmp_path / "stderr").open("x", encoding="utf-8") as stderr,
    ):
        try:
            result = runtime.run_with_watchdog(
                [sys.executable, "-c", code],
                cwd=tmp_path,
                env={},
                stdout=stdout,
                stderr=stderr,
                timeout_seconds=0.5,
                teardown_grace_seconds=0.5,
            )
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            assert result.timed_out is True
            assert result.sent_sigterm is True
            assert result.sent_sigkill is True
            assert not Path(f"/proc/{child_pid}").exists()
        finally:
            if child_pid is None and child_pid_path.is_file():
                child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            if child_pid is not None and Path(f"/proc/{child_pid}").exists():
                try:
                    runtime.os.kill(child_pid, runtime.signal.SIGKILL)
                except ProcessLookupError:
                    pass
            reaper.join(timeout=5)
            stop_reaper.set()
            assert libc.prctl(36, previous.value, 0, 0, 0) == 0


def test_timing_summary_splits_fresh_recovered_and_unknown() -> None:
    records: list[dict[str, Any]] = [
        {"recovered_existing_trial": False, "task_wall_seconds": 2.0},
        {"recovered_existing_trial": True, "task_wall_seconds": 5.0},
    ]
    summary = runtime.timing_summary(records, 1.0)
    assert summary == {
        "invocation_wall_seconds": 1.0,
        "fresh_attempt_count": 1,
        "recovered_attempt_count": 1,
        "total_attempt_count": 2,
        "unknown_timing_count": 0,
        "fresh_wall_seconds": 2.0,
        "recovered_wall_seconds": 5.0,
        "total_wall_seconds": 7.0,
    }

    records[1]["task_wall_seconds"] = None
    summary = runtime.timing_summary(records, 1.0)
    assert summary["unknown_timing_count"] == 1
    assert summary["recovered_wall_seconds"] is None
    assert summary["total_wall_seconds"] is None


def test_apply_patch_requires_clean_exact_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = SimpleNamespace(upstream_revision="a" * 40)
    outputs = iter(["a" * 40 + "\n", " M source.py\n"])
    monkeypatch.setattr(runtime, "_git", lambda *args, **kwargs: next(outputs))
    with pytest.raises(RuntimeError, match="exact clean upstream"):
        runtime.apply_harbor_patch(tmp_path, contract)
