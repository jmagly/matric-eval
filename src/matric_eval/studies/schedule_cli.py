"""Plan or execute explicitly authorized suites through preflight and lifecycle contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import Field

from matric_eval.results.contract import Record
from matric_eval.state.journal import AttemptIntent, ObservationJournal, TerminalAttempt
from matric_eval.state.observation_identity import canonical_json
from matric_eval.studies.suite_schedule import (
    GlobalFailure,
    Schedule,
    SuiteFailure,
    Work,
    execute,
    plan,
)


class ResidentService(Record):
    command: list[str] = Field(min_length=1)
    gpu: str
    broker_socket: str = "/run/ollama-unify/gpu-negotiator.sock"
    docker_host: str = "unix:///run/matric-eval-docker.sock"
    memory_mib: int = Field(default=75000, gt=0)
    ready_timeout_seconds: float = Field(default=900.0, gt=0, le=86400)


class Binding(Record):
    preflight: dict[str, Any]
    service: ResidentService
    command: list[str] = Field(min_length=1)
    timeout_seconds: float = Field(gt=0, le=86400)
    admission_max_age_seconds: float = Field(default=3600.0, gt=0, le=86400)
    # Nonzero exits are global unless the native adapter explicitly declares
    # these codes as a confirmed suite-local failure (never unknown execution).
    suite_failure_exit_codes: list[int] = Field(default_factory=list)


class CommandPlan(Record):
    schedule: Schedule
    bindings: dict[str, Binding]


def capture_binding(binding: Binding) -> str:
    """Capture argv, executable/code bytes and declared inputs before freezing work."""
    from matric_eval.studies.preflight import file_digest

    paths = {
        Path(__file__).resolve(),
        Path(__file__).with_name("suite_schedule.py").resolve(),
        Path(__file__).with_name("resource_lifecycle.py").resolve(),
        Path(__file__).with_name("preflight.py").resolve(),
    }
    commands = [binding.command, binding.service.command]
    for check in binding.preflight["checks"]:
        paths.update(Path(path).resolve(strict=True) for path in check["inputs"])
        commands.append(check["command"])
    for command in commands:
        executable = shutil.which(command[0])
        if executable is None:
            raise ValueError("command executable unavailable")
        paths.add(Path(executable).resolve(strict=True))
        paths.update(Path(arg).resolve() for arg in command[1:] if Path(arg).is_file())
    files = [{"path": str(path), "sha256": file_digest(path)} for path in sorted(paths)]
    return hashlib.sha256(
        canonical_json({"binding": binding.model_dump(), "files": files}).encode()
    ).hexdigest()


def _read(path: Path, limit: int = 4 * 1024 * 1024) -> dict[str, Any]:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("receipt exceeds bounded contract")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("receipt must be an object")
    return value


def _run_task(
    command: list[str], timeout: float, env: dict[str, str], owner_path: Path
) -> dict[str, Any]:
    """Register the gated task group durably before releasing its first instruction."""
    from matric_eval.studies.resource_lifecycle import atomic, process_identity
    from matric_eval.studies.run_status import LIMIT, group_alive, sanitize

    read_fd, write_fd = os.pipe()
    process = None
    tails = [bytearray(), bytearray()]
    threads: list[threading.Thread] = []
    owner: dict[str, Any] = {}
    timed_out = False
    try:
        gate = 'import os,sys; fd=int(sys.argv[1]); ok=os.read(fd,1); os.close(fd); os.execvpe(sys.argv[2],sys.argv[2:],os.environ) if ok == b"1" else sys.exit(125)'
        process = subprocess.Popen(
            [sys.executable, "-c", gate, str(read_fd), *command],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(read_fd,),
            start_new_session=True,
        )
        owner = {"identity": process_identity(process.pid), "cleanup": "pending"}
        if owner["identity"] is None:
            raise GlobalFailure("task_process_identity_unavailable")
        atomic(owner_path, owner)

        def drain(stream: Any, tail: bytearray) -> None:
            try:
                while chunk := stream.read(4096):
                    tail.extend(chunk)
                    del tail[:-LIMIT]
            finally:
                stream.close()

        for index, stream in enumerate((process.stdout, process.stderr)):
            thread = threading.Thread(target=drain, args=(stream, tails[index]), daemon=True)
            thread.start()
            threads.append(thread)
        os.write(write_fd, b"1")
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
    finally:
        os.close(read_fd)
        os.close(write_fd)
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            for thread in threads:
                thread.join(5)
            deadline = time.monotonic() + 5
            while group_alive(process.pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            if owner.get("identity") is not None:
                owner["cleanup"] = "pending" if group_alive(process.pid) else "complete"
                atomic(owner_path, owner)
            if group_alive(process.pid):
                raise GlobalFailure("task_group_cleanup_pending")
    assert process is not None
    stdout, stderr = [tail.decode("utf-8", errors="replace") for tail in tails]
    if timed_out or process.returncode:
        raise subprocess.CalledProcessError(
            process.returncode, command, output=stdout, stderr=stderr
        )
    secrets = [
        value
        for key, value in env.items()
        if any(word in key.lower() for word in ("key", "token", "secret", "password"))
    ]
    return {
        "exit_code": process.returncode,
        "stdout": sanitize(stdout, secrets),
        "stderr": sanitize(stderr, secrets),
    }


class CommandAdapter:
    """Run declared argv adapters; never interpret a shell command or retry a body."""

    def __init__(self, config: CommandPlan, directory: Path):
        from matric_eval.studies.preflight import write_receipt

        self.config, self.directory = config, directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.stat().st_mode & 0o077:
            raise ValueError("schedule execution directory must be private")
        self.write = write_receipt
        self.admissions: dict[str, dict[str, Any]] = {}
        self.binding_blockers: dict[str, list[str]] = {}
        self.process: subprocess.Popen[bytes] | None = None
        self.resource: Path | None = None
        for work in config.schedule.work:
            if (
                work.deferred
                or work.reuse_only
                or work.suite not in config.schedule.authorized_suites
            ):
                continue
            binding = config.bindings[work.key]
            digest = capture_binding(binding)
            if work.fingerprint.environment.document.get("scheduler_binding_sha256") != digest:
                self.binding_blockers[work.key] = ["fingerprint_command_inputs_changed"]
            if work.residency != binding.service.model_dump():
                self.binding_blockers.setdefault(work.key, []).append(
                    "fingerprint_residency_changed"
                )

    def preflight(self, work: Work) -> list[str]:
        from matric_eval.studies.preflight import execute_plan, validate_admission

        if work.reuse_only:
            return []
        if work.key in self.binding_blockers:
            return self.binding_blockers[work.key]
        binding = self.config.bindings[work.key]
        if work.fingerprint.environment.document.get("scheduler_binding_sha256") != capture_binding(
            binding
        ):
            return ["fingerprint_command_inputs_changed"]
        receipt_path = (
            self.directory / "preflight" / f"{hashlib.sha256(work.key.encode()).hexdigest()}.json"
        )
        if work.key not in self.admissions:
            self.admissions[work.key] = execute_plan(binding.preflight, receipt_path, launch=False)
        try:
            validate_admission(
                self.admissions[work.key], binding.preflight, binding.admission_max_age_seconds
            )
        except (ValueError, OSError, KeyError):
            return ["preflight_admission_unavailable"]
        return []

    def _controller_command(self, action: str, resource: Path, binding: Binding) -> list[str]:
        return [
            sys.executable,
            "-m",
            "matric_eval.studies.resource_lifecycle",
            action,
            "--directory",
            str(resource),
            "--broker-socket",
            binding.service.broker_socket,
            "--docker-host",
            binding.service.docker_host,
        ]

    def reconcile(self) -> None:
        """Recover only this scheduler's persisted, exact controller identities."""
        from matric_eval.studies.resource_lifecycle import alive, atomic
        from matric_eval.studies.run_status import group_alive

        for task_owner in sorted((self.directory / "tasks").glob("*/controller.json")):
            owner = _read(task_owner)
            if owner.get("cleanup") == "complete":
                continue
            identity = owner["identity"]
            if identity.get("host") != socket.gethostname():
                raise GlobalFailure("owned_process_host_mismatch")
            if alive(identity):
                os.killpg(identity["pid"], signal.SIGKILL)
                deadline = time.monotonic() + 10
                while group_alive(identity["pid"]) and time.monotonic() < deadline:
                    time.sleep(0.1)
            if group_alive(identity["pid"]):
                raise GlobalFailure("prior_task_group_cleanup_unverified")
            owner["cleanup"] = "complete"
            atomic(task_owner, owner)

        for owner_file in sorted((self.directory / "resources").glob("*/controller.json")):
            owner = _read(owner_file)
            identity = owner["identity"]
            if identity.get("host") != socket.gethostname():
                raise GlobalFailure("owned_process_host_mismatch")
            if alive(identity):
                os.killpg(identity["pid"], signal.SIGTERM)
                deadline = time.monotonic() + 30
                while alive(identity) and time.monotonic() < deadline:
                    time.sleep(0.1)
                if alive(identity):
                    os.killpg(identity["pid"], signal.SIGKILL)
            binding = Binding.model_validate(owner["binding"])
            result = subprocess.run(
                self._controller_command("reconcile", owner_file.parent, binding),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
            if result.returncode != 0:
                raise GlobalFailure("previous_resource_cleanup_pending")

    def start(self, work: Work) -> None:
        from matric_eval.studies.resource_lifecycle import process_identity

        binding = self.config.bindings[work.key]
        resource = self.directory / "resources" / uuid.uuid4().hex
        resource.mkdir(parents=True, mode=0o700)
        self.resource = resource
        self.write(resource / "preflight-plan.json", binding.preflight)
        command = self._controller_command("run", resource, binding)
        command += [
            "--preflight-plan",
            str(resource / "preflight-plan.json"),
            "--run-id",
            work.identities[0].run_id,
            "--attempt-id",
            resource.name,
            "--gpu",
            binding.service.gpu,
            "--owner",
            "matric-suite-schedule",
            "--ready-timeout",
            str(binding.service.ready_timeout_seconds),
            "--memory-mib",
            str(binding.service.memory_mib),
            "--",
            *binding.service.command,
        ]
        read_fd, write_fd = os.pipe()
        try:
            gate = 'import os,sys; fd=int(sys.argv[1]); ok=os.read(fd,1); os.close(fd); os.execvpe(sys.argv[2],sys.argv[2:],os.environ) if ok == b"1" else sys.exit(125)'
            self.process = subprocess.Popen(
                [sys.executable, "-c", gate, str(read_fd), *command],
                pass_fds=(read_fd,),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            identity = process_identity(self.process.pid)
            if identity is None:
                raise GlobalFailure("controller_identity_unavailable")
            self.write(
                resource / "controller.json",
                {"identity": identity, "binding": binding.model_dump()},
            )
            os.write(write_fd, b"1")
        finally:
            os.close(read_fd)
            os.close(write_fd)
        deadline = time.monotonic() + binding.service.ready_timeout_seconds + 15
        while self.process.poll() is None and time.monotonic() < deadline:
            if (resource / "record.json").exists():
                record = _read(resource / "record.json")
                if record.get("state") == "ready":
                    return
            time.sleep(0.1)
        raise GlobalFailure("resident_service_not_ready")

    def run(self, work: Work, intent: AttemptIntent) -> TerminalAttempt:
        from matric_eval.studies.preflight import execute_target_checks

        binding = self.config.bindings[work.key]
        if self.process is None or self.process.poll() is not None or self.resource is None:
            raise GlobalFailure("resident_service_lost")
        attempt = self.directory / "tasks" / intent.attempt_id
        attempt.mkdir(parents=True, mode=0o700)
        target = execute_target_checks(
            binding.preflight,
            attempt / "target-preflight.json",
            self.admissions[work.key],
            max_age_seconds=binding.admission_max_age_seconds,
        )
        if not target.get("completed"):
            raise SuiteFailure("target_preflight_failed")
        request, response = attempt / "request.json", attempt / "terminal.json"
        self.write(
            request,
            {
                "work": work.model_dump(),
                "intent": intent.model_dump(),
                "resource_record": str(self.resource / "record.json"),
            },
        )
        env = {
            **os.environ,
            "MATRIC_SCHEDULE_REQUEST": str(request),
            "MATRIC_SCHEDULE_TERMINAL": str(response),
        }
        try:
            diagnostic = _run_task(
                binding.command, binding.timeout_seconds, env, attempt / "controller.json"
            )
            self.write(attempt / "command.json", diagnostic)
        except subprocess.CalledProcessError as error:
            # Detailed bounded tails are retained through the existing sanitized diagnostic contract.
            from matric_eval.studies.run_status import sanitize

            secrets = [
                value
                for key, value in env.items()
                if any(word in key.lower() for word in ("key", "token", "secret", "password"))
            ]
            self.write(
                attempt / "command.json",
                {
                    "exit_code": error.returncode,
                    "stdout": sanitize(str(error.stdout or ""), secrets),
                    "stderr": sanitize(str(error.stderr or ""), secrets),
                },
            )
            if error.returncode in binding.suite_failure_exit_codes:
                raise SuiteFailure("declared_adapter_failure") from error
            raise GlobalFailure("task_command_failed") from error
        if self.process.poll() is not None:
            raise GlobalFailure("resident_service_lost")
        return TerminalAttempt.model_validate(_read(response))

    def stop(self) -> bool:
        if self.resource is None:
            return True
        resource = self.resource
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        self.process = None
        self.resource = None
        if not (resource / "record.json").exists():
            return False
        return _read(resource / "record.json").get("cleanup") == "complete"


def run_command_plan(
    action: str, source: Path, journal_path: Path, directory: Path
) -> dict[str, Any]:
    config = CommandPlan.model_validate(_read(source))
    adapter = CommandAdapter(config, directory)
    with ObservationJournal(journal_path) as journal:
        if action == "plan":
            report = plan(config.schedule, journal, adapter.preflight)
            adapter.write(directory / "plan.json", report)
        else:
            report = execute(
                config.schedule,
                journal,
                adapter,
                directory / "execution.jsonl",
                reconcile=adapter.reconcile,
            )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "execute"])
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    report = run_command_plan(args.action, args.plan, args.journal, args.directory)
    print(json.dumps(report, allow_nan=False))
    return (
        1
        if report.get("global_stop")
        or any(
            row["disposition"] in {"failed", "invalidated", "blocked"} for row in report["entries"]
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
