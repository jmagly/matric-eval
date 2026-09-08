"""Correlated external-worker status; a projection, never an observation journal."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import signal
import socket
import subprocess
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from matric_eval.results.contract import Observation

SCHEMA = "matric-eval.external-run-status/1"
PHASES = {
    "planned",
    "preflight-blocked",
    "queued",
    "loading",
    "ready",
    "executing",
    "completed",
    "failed",
    "cancelled",
    "unknown",
    "cleanup-pending",
}
TERMINAL = {"completed", "failed", "cancelled", "unknown", "preflight-blocked"}
TASK_STATES = {
    "not-started",
    "executing",
    "scored-valid",
    "invalid",
    "failed",
    "cancelled",
    "unknown",
}
LIMIT = 8192


def sanitize(text: str, secrets: Sequence[str] = ()) -> str:
    """Redact known secret values and common credential forms before persistence."""
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    text = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1<redacted>", text)
    text = re.sub(
        r"(?i)((?:api[_-]?key|token|password|secret|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s,\"'}]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1<redacted>@", text)
    return text


def diagnostic(
    error: BaseException, *, actor: str, stage: str, reason: str, secrets: Sequence[str] = ()
) -> dict[str, Any]:
    chain: list[dict[str, str]] = []
    seen: set[int] = set()
    message_truncated = False
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        message_truncated |= len(str(current)) > LIMIT
        chain.append(
            {"type": type(current).__name__, "message": sanitize(str(current), secrets)[:LIMIT]}
        )
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    stdout = getattr(error, "stdout", "") or ""
    stderr = getattr(error, "stderr", "") or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    code = getattr(error, "returncode", None)
    return {
        "actor": actor,
        "stage": stage,
        "reason": reason,
        "exit_code": code if isinstance(code, int) and code >= 0 else None,
        "signal": -code if isinstance(code, int) and code < 0 else None,
        "stdout": sanitize(stdout, secrets)[:LIMIT],
        "stderr": sanitize(stderr, secrets)[:LIMIT],
        "truncated": len(stdout) > LIMIT
        or len(stderr) > LIMIT
        or current is not None
        or message_truncated,
        "exception_chain": chain,
        "evidence": [],
        "cleanup_disposition": "unverified",
    }


def process_identity(pid: int) -> dict[str, Any] | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if stat[0] == "Z":
            return None
        return {
            "pid": pid,
            "start_ticks": stat[19],
            "host": socket.gethostname(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        }
    except (OSError, IndexError):
        return None


def alive(identity: dict[str, Any] | None) -> bool | None:
    if identity is None or identity.get("host") != socket.gethostname():
        return None
    return process_identity(identity["pid"]) == identity


def group_alive(group: int) -> bool:
    """Count live members even when the process-group leader already exited."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] != "Z" and int(fields[2]) == group:
                return True
        except (FileNotFoundError, ProcessLookupError):
            continue
    return False


class RunStatus:
    """Single atomic status document, locked across adapter and supervisor writers."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "status.json"

    @classmethod
    def create(
        cls, directory: Path, *, run_id: str, attempt_id: str, tasks: list[dict[str, str]]
    ) -> RunStatus:
        keys = [(t["model_id"], t["suite_id"], t["task_id"]) for t in tasks]
        if (
            not run_id
            or not attempt_id
            or len(keys) != len(set(keys))
            or any(not all(k) for k in keys)
        ):
            raise ValueError("status plan requires unique nonempty task identities")
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        status = cls(directory)
        now = time.time()
        status._write(
            {
                "schema": SCHEMA,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "phase": "planned",
                "phase_timestamps": {"planned": now},
                "heartbeat_at": None,
                "last_progress_at": None,
                "supervisor": process_identity(os.getpid()),
                "worker": None,
                "models": {},
                "cleanup": "not-required",
                "diagnostics": [],
                "terminal_event": None,
                "tasks": [
                    {
                        **t,
                        "state": "not-started",
                        "attempted": False,
                        "reason": None,
                        "reward": None,
                        "observation": None,
                        "updated_at": now,
                    }
                    for t in tasks
                ],
            }
        )
        return status

    def _write(self, data: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=".status-", dir=self.directory)
        try:
            if self.path.exists():
                owner = self.path.stat()
                os.fchown(fd, owner.st_uid, owner.st_gid)
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, allow_nan=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            Path(name).unlink(missing_ok=True)

    @contextmanager
    def update(self) -> Iterator[dict[str, Any]]:
        fd = os.open(self.directory / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        owner = self.path.stat()
        os.fchown(fd, owner.st_uid, owner.st_gid)
        with os.fdopen(fd, "r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data: dict[str, Any] = json.loads(self.path.read_text())
            if data["schema"] != SCHEMA:
                raise ValueError("unsupported external status schema")
            yield data
            self._write(data)

    def phase(self, phase: str) -> None:
        if phase not in PHASES:
            raise ValueError("unknown supervisor phase")
        with self.update() as data:
            if data["terminal_event"] is not None:
                raise ValueError("run is already terminal")
            data["phase"] = phase
            data["phase_timestamps"][phase] = time.time()

    def model_phase(self, model: str, phase: str, *, evidence: str | None = None) -> None:
        if phase not in {"loading", "ready", "stopped"}:
            raise ValueError("unknown model phase")
        with self.update() as data:
            if model not in {t["model_id"] for t in data["tasks"]}:
                raise ValueError("model is outside this run's plan")
            data.setdefault("models", {})[model] = {
                "phase": phase,
                "at": time.time(),
                "process": process_identity(os.getpid()),
                "evidence": evidence,
            }
            if phase in {"loading", "ready"} and data["terminal_event"] is None:
                data["phase"] = phase
                data["phase_timestamps"][phase] = time.time()

    def task(
        self,
        model: str,
        suite: str,
        task: str,
        *,
        state: str,
        reason: str | None = None,
        observation: Observation | None = None,
    ) -> None:
        if state not in TASK_STATES:
            raise ValueError("unknown task state")
        with self.update() as data:
            if data["terminal_event"] is not None:
                raise ValueError("terminal status cannot accept task updates")
            row = next(
                (
                    t
                    for t in data["tasks"]
                    if (t["model_id"], t["suite_id"], t["task_id"]) == (model, suite, task)
                ),
                None,
            )
            if row is None:
                raise ValueError("task is outside this run's plan")
            if row["state"] not in {"not-started", "executing"}:
                raise ValueError("task already has a terminal disposition")
            if state == "scored-valid":
                if (
                    observation is None
                    or not observation.accepted
                    or observation.outcome != "observed"
                ):
                    raise ValueError("valid progress requires an accepted measured observation")
            if observation is not None:
                identity = observation.identity
                if (
                    identity.run_id,
                    identity.model_id,
                    identity.benchmark_id,
                    identity.sample_id,
                    observation.attempt_id,
                ) != (data["run_id"], model, suite, task, data["attempt_id"]):
                    raise ValueError("observation is not correlated to the planned attempt")
                if state != "scored-valid" and observation.outcome == "observed":
                    raise ValueError("observed measurement requires scored-valid disposition")
            now = time.time()
            row.update(
                state=state,
                reason=sanitize(reason) if reason else None,
                attempted=row["attempted"] or state == "executing" or observation is not None,
                observation=observation.model_dump() if observation else None,
                reward=observation.value if observation else None,
                updated_at=now,
            )
            data["last_progress_at"] = now

    def finish(
        self, phase: str, *, failure: dict[str, Any] | None = None, cleanup: str = "unverified"
    ) -> None:
        if phase not in TERMINAL:
            raise ValueError("finish requires a terminal phase")
        with self.update() as data:
            if data["terminal_event"] is not None:
                return
            unfinished = [t for t in data["tasks"] if t["state"] in {"not-started", "executing"}]
            if phase == "completed" and unfinished:
                phase = "failed"
                if failure is not None:
                    data["diagnostics"].append(failure)
                failure = diagnostic(
                    RuntimeError("worker exited without all planned task receipts"),
                    actor="supervisor",
                    stage="receipt",
                    reason="missing_task_receipts",
                )
            now = time.time()
            reason = failure["reason"] if failure else phase
            for task in unfinished:
                if task["state"] == "executing":
                    task["state"] = "cancelled" if phase == "cancelled" else "unknown"
                task.update(reason=reason, updated_at=now)
            if failure is not None:
                failure["cleanup_disposition"] = cleanup
                data["diagnostics"].append(failure)
                data["diagnostics"] = data["diagnostics"][-16:]
            data["cleanup"] = cleanup
            data["phase"] = "cleanup-pending" if cleanup == "pending" else phase
            data["phase_timestamps"][data["phase"]] = now
            data["terminal_event"] = {
                "run_id": data["run_id"],
                "attempt_id": data["attempt_id"],
                "phase": phase,
                "at": now,
                "reason": reason,
            }

    def read(self, *, stale_seconds: float = 15.0, reconcile: bool = True) -> dict[str, Any]:
        if not math.isfinite(stale_seconds) or stale_seconds <= 0:
            raise ValueError("stale_seconds must be finite and positive")
        data: dict[str, Any] = json.loads(self.path.read_text())
        if data["schema"] != SCHEMA:
            raise ValueError("unsupported external status schema")
        supervisor_alive = alive(data["supervisor"])
        if reconcile and data["terminal_event"] is None and supervisor_alive is False:
            self.finish(
                "unknown",
                failure=diagnostic(
                    RuntimeError("supervisor exited without a terminal receipt"),
                    actor="supervisor",
                    stage=data["phase"],
                    reason="supervisor_lost",
                ),
                cleanup="pending",
            )
            data = json.loads(self.path.read_text())
        for model in data.get("models", {}).values():
            model["alive"] = alive(model["process"])
            model["current_phase"] = (
                model["phase"]
                if model["alive"] is True or model["phase"] == "stopped"
                else "unknown"
            )
        heartbeat = data["heartbeat_at"]
        data["liveness"] = {
            "supervisor_alive": supervisor_alive,
            "worker_alive": alive(data["worker"]),
            "heartbeat_age_seconds": max(0, time.time() - heartbeat) if heartbeat else None,
            "heartbeat_fresh": heartbeat is not None
            and 0 <= time.time() - heartbeat <= stale_seconds,
        }
        states = Counter(t["state"] for t in data["tasks"])
        data["counts"] = {
            "planned": len(data["tasks"]),
            "attempted": sum(t["attempted"] for t in data["tasks"]),
            "completed": states["scored-valid"] + states["invalid"],
            "valid": states["scored-valid"],
            "invalid": states["invalid"],
            "not_started": states["not-started"],
            "states": dict(states),
        }
        return data


def supervise(
    status: RunStatus,
    command: Sequence[str],
    *,
    timeout: float,
    grace: float = 2.0,
    secrets: Sequence[str] = (),
) -> int:
    """Run one adapter with bounded output and correlated process identity.

    No task is marked attempted just because this process was launched. Adapters
    report tasks through RunStatus, using the inherited MATRIC_RUN_STATUS_DIR.
    """
    if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(grace) or grace <= 0:
        raise ValueError("timeout and grace must be finite positive durations")
    process: subprocess.Popen[bytes] | None = None
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    totals = {"stdout": 0, "stderr": 0}
    threads: list[threading.Thread] = []
    cancelled: list[int] = []
    old_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in old_handlers:
        signal.signal(sig, lambda number, frame: cancelled.append(number))
    failure = None
    phase = "failed"
    code = 1
    cleanup = "not-required"
    try:
        status.phase("queued")
        env = {**os.environ, "MATRIC_RUN_STATUS_DIR": str(status.directory.resolve())}
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, start_new_session=True
        )
        cleanup = "pending"
        with status.update() as data:
            data["worker"] = process_identity(process.pid)

        def drain(name: str, stream: Any) -> None:
            while chunk := stream.read(4096):
                totals[name] += len(chunk)
                buffers[name].extend(chunk[: max(0, LIMIT * 2 - len(buffers[name]))])
            stream.close()

        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            thread = threading.Thread(target=drain, args=(name, stream), daemon=True)
            thread.start()
            threads.append(thread)
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if cancelled:
                raise InterruptedError("supervised worker cancelled")
            if time.monotonic() >= deadline:
                raise TimeoutError("supervised worker exceeded its wall-clock budget")
            with status.update() as data:
                data["heartbeat_at"] = time.time()
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        code = process.returncode
        if code:
            raise subprocess.CalledProcessError(code, "adapter")
        phase = "completed"
    except BaseException as error:
        phase = (
            "cancelled" if isinstance(error, (InterruptedError, KeyboardInterrupt)) else "failed"
        )
        reason = (
            "cancelled"
            if phase == "cancelled"
            else "worker_timeout"
            if isinstance(error, TimeoutError)
            else "worker_exit"
            if isinstance(error, subprocess.CalledProcessError)
            else "supervisor_error"
        )
        current = status.read(reconcile=False)
        if current["phase"] == "queued" and not current["counts"]["attempted"]:
            status.phase("preflight-blocked")
        if status.read(reconcile=False)["phase"] == "preflight-blocked" and phase != "cancelled":
            phase = "preflight-blocked"
        failure = diagnostic(
            error,
            actor="adapter",
            stage=status.read(reconcile=False)["phase"],
            reason=reason,
            secrets=secrets,
        )
        code = (
            128 + cancelled[0]
            if cancelled
            else 124
            if isinstance(error, TimeoutError)
            else code or 1
        )
    finally:
        if process is not None:
            # Stop the entire owned group even when its original leader already exited.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if not group_alive(process.pid):
                    break
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    break
                deadline = time.monotonic() + grace
                while group_alive(process.pid) and time.monotonic() < deadline:
                    process.poll()
                    time.sleep(0.01)
            process.poll()
            for thread in threads:
                thread.join(timeout=grace)
            cleanup = (
                "pending"
                if group_alive(process.pid) or any(t.is_alive() for t in threads)
                else "process-group-stopped-gpu-unverified"
            )
            if failure is None:
                failure = {
                    "actor": "adapter",
                    "stage": status.read(reconcile=False)["phase"],
                    "reason": "worker_completed",
                    "exit_code": 0,
                    "signal": None,
                    "stdout": "",
                    "stderr": "",
                    "truncated": False,
                    "exception_chain": [],
                    "evidence": [],
                    "cleanup_disposition": cleanup,
                }
            if failure is not None:
                for name in buffers:
                    failure[name] = sanitize(
                        buffers[name].decode("utf-8", errors="replace"), secrets
                    )[:LIMIT]
                failure["truncated"] |= any(totals[n] > LIMIT for n in buffers)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        status.finish(phase, failure=failure, cleanup=cleanup)
    return code if status.read()["terminal_event"]["phase"] == "completed" else code or 1


class AdapterStatus:
    """Optional adapter-side projection into a supervisor-owned task plan."""

    def __init__(self, model: str, suite: str):
        directory = os.environ.get("MATRIC_RUN_STATUS_DIR")
        self.status = RunStatus(Path(directory)) if directory else None
        self.model = model
        self.suite = suite

    def start(self, task: str) -> None:
        if self.status:
            self.status.phase("executing")
            self.status.task(self.model, self.suite, task, state="executing")

    def result(
        self,
        task: str,
        *,
        reward: float | None,
        valid: bool,
        reason: str | None,
        evidence_uri: str,
        evidence_sha256: str | None,
        native_failure: dict[str, Any] | None = None,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        exit_code: int | None = None,
    ) -> None:
        if self.status is None:
            return
        from matric_eval.results.contract import ArtifactReference, ObservationIdentity

        data = self.status.read(reconcile=False)
        identity = ObservationIdentity(
            run_id=data["run_id"],
            model_id=self.model,
            benchmark_id=self.suite,
            allocation_id=self.suite,
            sample_id=task,
            trial_id="1",
            metric_id="official_reward",
        )
        measured = valid and reward is not None
        grader_failed = not measured and (native_failure or {}).get("owner") == "evaluator"
        observation = Observation(
            observation_id=identity.logical_id(),
            identity=identity,
            attempt_id=data["attempt_id"],
            previous_attempt_id=None,
            accepted=True,
            execution="completed" if measured or grader_failed else "failed",
            outcome="observed"
            if measured
            else "grader_failed"
            if grader_failed
            else "infrastructure_error",
            value=reward if measured else None,
            reason=None if measured else reason or "missing_reward",
            native_status="valid" if valid else "invalid",
            judge=None,
            artifacts=[
                ArtifactReference(
                    uri=evidence_uri,
                    sha256=evidence_sha256,
                    unavailable_reason=None if evidence_sha256 else "native_evidence_missing",
                )
            ],
        )
        self.status.task(
            self.model,
            self.suite,
            task,
            state="scored-valid" if measured else "invalid",
            reason=observation.reason,
            observation=observation,
        )

        if not measured:
            native_failure = native_failure or {}
            failure = diagnostic(
                RuntimeError(str(native_failure.get("detail") or reason or "missing_reward")),
                actor=str(native_failure.get("actor") or "adapter"),
                stage=str(native_failure.get("stage") or "result-ingest"),
                reason=reason or "missing_reward",
            )
            failure["exit_code"] = exit_code if exit_code is not None and exit_code >= 0 else None
            failure["signal"] = -exit_code if exit_code is not None and exit_code < 0 else None
            failure["model_id"], failure["suite_id"], failure["task_id"] = (
                self.model,
                self.suite,
                task,
            )
            # Keep the native attribution, bounded before it reaches the status document.
            native_text = sanitize(json.dumps(native_failure, allow_nan=False))
            failure["native_attribution"] = native_text[:LIMIT]
            failure["truncated"] |= len(native_text) > LIMIT
            failure["evidence"] = [evidence_uri]
            for name, path in (("stdout", stdout_path), ("stderr", stderr_path)):
                if path is not None and path.is_file():
                    with path.open("rb") as stream:
                        content = stream.read(LIMIT + 1)
                    failure[name] = sanitize(content.decode("utf-8", errors="replace"))[:LIMIT]
                    failure["truncated"] |= len(content) > LIMIT
                    failure["evidence"].append(str(path))
            with self.status.update() as data:
                data["diagnostics"] = (data["diagnostics"] + [failure])[-16:]


def adapter_main(action: Callable[[], int]) -> int:
    """Retain structured adapter exceptions before the supervisor observes exit."""
    try:
        return action()
    except BaseException as error:
        if isinstance(error, SystemExit) and error.code in (None, 0):
            raise
        directory = os.environ.get("MATRIC_RUN_STATUS_DIR")
        if directory is None:
            raise
        status = RunStatus(Path(directory))
        current = status.read(reconcile=False)
        if current["phase"] == "queued" and not current["counts"]["attempted"]:
            status.phase("preflight-blocked")
        failure = diagnostic(
            error,
            actor="adapter",
            stage=status.read(reconcile=False)["phase"],
            reason="adapter_exception",
        )
        with status.update() as data:
            data["diagnostics"] = (data["diagnostics"] + [failure])[-16:]
        return 1
