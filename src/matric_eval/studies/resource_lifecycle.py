"""Durable, fail-closed ownership of one study model container and GPU lease."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from matric_eval.studies.preflight import (
    execute_plan,
    execute_target_checks,
    validate_admission,
)
from matric_eval.studies.run_status import RunStatus


def process_identity(pid: int) -> dict[str, Any] | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return {
            "pid": pid,
            "start_ticks": fields[19],
            "boot_id": boot(),
            "host": socket.gethostname(),
        }
    except FileNotFoundError:
        return None


def alive(identity: dict[str, Any]) -> bool:
    return process_identity(identity["pid"]) == identity


def atomic(path: Path, value: dict[str, Any]) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def boot() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


class Broker:
    def __init__(self, path: str) -> None:
        self.path = path

    def call(self, action: str, **fields: Any) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(10)
            client.connect(self.path)
            client.sendall(json.dumps({"action": action, **fields}).encode() + b"\n")
            with client.makefile("rb") as stream:
                result = json.loads(stream.readline(1024 * 1024))
        if not isinstance(result, dict) or result.get("ok") is not True:
            # Broker errors may echo lease tokens. Never persist or print them.
            raise RuntimeError(f"broker {action} failed")
        return result


class Docker:
    def __init__(self, host: str) -> None:
        self.host = host

    def command(self, *args: str) -> list[str]:
        return ["docker", "--host", self.host, *args]

    def inspect(self, name: str) -> dict[str, Any] | None:
        result = subprocess.run(
            self.command("container", "ls", "-a", "--no-trunc", "--format", "{{.Names}}"),
            check=True,
            capture_output=True,
            text=True,
        )
        if name not in result.stdout.splitlines():
            return None
        return json.loads(subprocess.check_output(self.command("inspect", name)))[0]  # type: ignore[no-any-return]

    def stop(self, identifier: str) -> None:
        subprocess.run(
            self.command("stop", "--time", "10", identifier),
            check=True,
            capture_output=True,
        )

    def remove(self, identifier: str) -> None:
        subprocess.run(self.command("rm", identifier), check=True, capture_output=True)

    def cuda(self) -> list[tuple[str, int]]:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
        return [
            (row.split(",")[0].strip(), int(row.split(",")[1]))
            for row in output.splitlines()
            if row.strip()
        ]

    def cgroup(self, pid: int) -> str:
        return Path(f"/proc/{pid}/cgroup").read_text()


class ResourceLifecycle:
    """The directory is private; record.json contains no lease token.

    A single flock serializes launch and reconciliation. An acquiring intent is
    committed before the RPC, so a lost acknowledgment can be recovered by the
    attempt-unique owner. New attempts in the same directory cannot bypass an
    unresolved obligation.
    """

    def __init__(self, directory: Path, broker: Broker, docker: Docker) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.stat().st_mode & 0o077:
            raise ValueError("resource directory must be private (0700)")
        self.broker, self.docker = broker, docker
        self.path = directory / "record.json"
        self.private = directory / "lease.private.json"
        self.lock = (directory / "lock").open("a+")
        os.chmod(directory / "lock", 0o600)
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.record: dict[str, Any] = (
            json.loads(self.path.read_text()) if self.path.exists() else {}
        )

    def close(self) -> None:
        self.lock.close()

    def save(self, **fields: Any) -> None:
        self.record.update(fields)
        atomic(self.path, self.record)
        status_directory = os.environ.get("MATRIC_RUN_STATUS_DIR")
        if status_directory:
            with RunStatus(Path(status_directory)).update() as status:
                if (status["run_id"], status["attempt_id"]) != (
                    self.record["run_id"],
                    self.record["attempt_id"],
                ):
                    raise ValueError("resource status run/attempt mismatch")
                status["resources"] = {
                    "resource_id": self.record["resource_id"],
                    "record": str(self.path),
                    "state": self.record["state"],
                    "cleanup": self.record["cleanup"],
                }

    def prepare(self, run_id: str, attempt_id: str, gpu: str, owner: str) -> None:
        if self.record:
            raise RuntimeError(
                "resource directory already used; reconcile and use a new attempt directory"
            )
        if not run_id or not attempt_id or not gpu or not gpu.startswith("GPU-"):
            raise ValueError("run, attempt and exact GPU UUID are required")
        identity = uuid.uuid4().hex
        self.save(
            schema="matric-eval.resource-lifecycle/1",
            run_id=run_id,
            attempt_id=attempt_id,
            resource_id=identity,
            owner=f"{owner}:{identity}",
            gpu_uuids=[gpu],
            container=f"matric-{identity}",
            controller_type="process",
            controller=process_identity(os.getpid()),
            controller_unit=None,
            host=socket.gethostname(),
            readiness=str(self.directory / f"{identity}.ready"),
            boot_id=boot(),
            state="planned",
            cleanup="pending",
            cuda_pids=[],
        )

    def acquire(self, mib: int = 75000) -> str:
        with (self.directory.parent / ".allocation.lock").open("a+") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX)
            return self._acquire(mib)

    def _acquire(self, mib: int) -> str:
        for candidate in self.directory.parent.glob("*/record.json"):
            if candidate == self.path:
                continue
            existing = json.loads(candidate.read_text())
            if existing.get("cleanup") != "complete" and set(existing.get("gpu_uuids", [])) & set(
                self.record["gpu_uuids"]
            ):
                raise RuntimeError("another attempt has an unresolved cleanup obligation")
        self.save(state="acquiring")
        response = self.broker.call(
            "acquire",
            owner=self.record["owner"],
            requested_mib=mib,
            ttl=300,
            gpu_uuids=self.record["gpu_uuids"],
        )
        lease = response["lease"]
        self.accept_lease(lease)
        return str(lease["token"])

    def accept_lease(self, lease: dict[str, Any]) -> None:
        if lease["owner"] != self.record["owner"] or lease["gpu_uuids"] != self.record["gpu_uuids"]:
            raise RuntimeError("broker lease ownership mismatch")
        atomic(self.private, {"token": lease["token"]})
        self.save(
            state="leased",
            lease_sha256=hashlib.sha256(lease["token"].encode()).hexdigest(),
        )

    def owned_lease(self) -> dict[str, Any] | None:
        leases = self.broker.call("status")["leases"]
        matches = [lease for lease in leases if lease.get("owner") == self.record["owner"]]
        if len(matches) > 1:
            raise RuntimeError("ambiguous lease ownership")
        if not matches:
            return None
        lease = matches[0]
        if lease["gpu_uuids"] != self.record["gpu_uuids"]:
            raise RuntimeError("lease scope changed")
        if (
            self.private.exists()
            and json.loads(self.private.read_text())["token"] != lease["token"]
        ):
            raise RuntimeError("lease token changed")
        return lease  # type: ignore[no-any-return]

    def reconcile(self) -> bool:
        if not self.record:
            return True
        try:
            if self.record.get("host", socket.gethostname()) != socket.gethostname():
                raise RuntimeError("reconciliation requires the owning host")
            if self.record.get("cleanup") == "complete":
                return True
            self.save(state="cleanup-pending", cleanup="pending")
            launcher = self.record.get("launcher")
            if launcher and alive(launcher):
                os.killpg(launcher["pid"], signal.SIGTERM)
                deadline = time.monotonic() + 10
                while alive(launcher) and time.monotonic() < deadline:
                    time.sleep(0.1)
                if alive(launcher):
                    os.killpg(launcher["pid"], signal.SIGKILL)
            info = self.docker.inspect(self.record["container"])
            owned_pids = (
                set(self.record["cuda_pids"]) if self.record["boot_id"] == boot() else set()
            )
            if info is not None:
                if (
                    info["Config"].get("Labels", {}).get("matric.resource")
                    != self.record["resource_id"]
                ):
                    raise RuntimeError("container ownership mismatch")
                identifier = info["Id"]
                if self.record.get("container_id") and self.record["container_id"] != identifier:
                    raise RuntimeError("container identity changed")
                self.save(container_id=identifier, stopped_container_pid=info["State"].get("Pid"))
                # Capture actual per-process CUDA ownership before container teardown.
                for gpu, pid in self.docker.cuda():
                    if gpu in self.record["gpu_uuids"] and identifier in self.docker.cgroup(pid):
                        owned_pids.add(pid)
                self.save(cuda_pids=sorted(owned_pids))
                if info["State"]["Running"]:
                    self.docker.stop(identifier)
                after = self.docker.inspect(self.record["container"])
                if after is not None and (after["Id"] != identifier or after["State"]["Running"]):
                    raise RuntimeError("container stop not established")
                # Docker stopped state plus empty container cgroups is the ownership
                # proof; free VRAM is deliberately never used as a release predicate.
                for process in Path("/proc").iterdir():
                    if process.name.isdigit():
                        try:
                            if identifier in self.docker.cgroup(int(process.name)):
                                raise RuntimeError("owned descendant remains alive")
                        except FileNotFoundError:
                            pass
            elif (
                self.record.get("state_before_launch") == "launched"
                and not self.record.get("container_stopped")
                and self.record["boot_id"] == boot()
            ):
                # We never run with --rm; disappearing containers invalidate proof.
                raise RuntimeError("owned container disappeared; cleanup proof unavailable")
            if any(pid in owned_pids for _, pid in self.docker.cuda()):
                raise RuntimeError("owned CUDA allocation remains")
            if info is not None:
                self.save(container_stopped=info["Id"])
            self.save(cuda_release_verified_at=time.time())
            lease = self.owned_lease()
            if lease is not None:
                self.broker.call("release", token=lease["token"])
                self.save(lease_release_acknowledged_at=time.time())
                if self.owned_lease() is not None:
                    raise RuntimeError("lease release not established")
            private_token = (
                json.loads(self.private.read_text()).get("token") if self.private.exists() else None
            )
            marker_token = lease["token"] if lease is not None else private_token
            if marker_token:
                Path(f"{self.record['readiness']}.{marker_token}.ready").unlink(missing_ok=True)
            if info is not None:
                self.docker.remove(info["Id"])
            self.private.unlink(missing_ok=True)
            Path(self.record["readiness"]).unlink(missing_ok=True)
            self.save(state="stopped", cleanup="complete", reason=None)
            return True
        except (
            OSError,
            ValueError,
            KeyError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as error:
            self.save(
                state="cleanup-pending",
                cleanup="pending",
                reason=str(error) if type(error) is RuntimeError else type(error).__name__,
            )
            return False

    def run(
        self,
        command: list[str],
        timeout: float = 900,
        mib: int = 75000,
        *,
        preflight_plan: dict[str, Any],
        storage_plan: dict[str, Any] | None = None,
    ) -> int:
        child = None
        storage = None
        handlers: dict[int, Any] = {}
        heartbeat_stop = threading.Event()
        heartbeat_failed = threading.Event()
        heartbeat_worker = None
        try:

            def cancel(signum: int, frame: Any) -> None:
                raise InterruptedError(f"cancelled by signal {signum}")

            for signum in (signal.SIGINT, signal.SIGTERM):
                handlers[signum] = signal.signal(signum, cancel)
            if storage_plan is not None:
                from matric_eval.studies.storage_lifecycle import ResidentStorage

                storage = ResidentStorage(storage_plan, self, command)
                storage.admit()
            receipt_directory = storage.session.paths["evidence"] if storage else self.directory
            preflight_plan = {
                **preflight_plan,
                "resource_binding": {
                    "run_id": self.record["run_id"],
                    "attempt_id": self.record["attempt_id"],
                    "gpu_uuids": self.record["gpu_uuids"],
                    "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                },
            }
            admission = execute_plan(
                preflight_plan, receipt_directory / "preflight.json", launch=False
            )
            validate_admission(admission, preflight_plan, 300)
            self.save(
                preflight_fingerprint=admission["plan_fingerprint"],
                preflight_binding=preflight_plan["resource_binding"],
            )
            token = self.acquire(mib)

            def keep_lease() -> None:
                while not heartbeat_stop.wait(30):
                    try:
                        self.broker.call("heartbeat", token=token)
                    except (OSError, ValueError, RuntimeError):
                        heartbeat_failed.set()
                        if child is not None and child.poll() is None:
                            try:
                                os.killpg(child.pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                        return

            heartbeat_worker = threading.Thread(target=keep_lease, daemon=True)
            heartbeat_worker.start()
            env = {
                **os.environ,
                "OLLAMA_UNIFY_GPU_LEASE": token,
                "CUDA_VISIBLE_DEVICES": ",".join(self.record["gpu_uuids"]),
                "MATRIC_RESOURCE_ID": self.record["resource_id"],
            }
            replacements = {
                "{container}": self.record["container"],
                "{resource_id}": self.record["resource_id"],
                "{ready_base}": self.record["readiness"],
            }
            for key, value in replacements.items():
                command = [arg.replace(key, value) for arg in command]
            # Persist potential container creation before dispatch. A missing
            # container before dispatch is safe; lost launch acknowledgment stays pending.
            self.save(state="launching", state_before_launch="launched")
            read_fd, write_fd = os.pipe()
            try:
                gate = 'import os,sys; fd=int(sys.argv[1]); ok=os.read(fd,1); os.close(fd); os.execvpe(sys.argv[2],sys.argv[2:],os.environ) if ok == b"1" else sys.exit(125)'
                child = subprocess.Popen(
                    [sys.executable, "-c", gate, str(read_fd), *command],
                    env=env,
                    start_new_session=True,
                    pass_fds=(read_fd,),
                    stdout=storage.log if storage else None,
                    stderr=subprocess.STDOUT if storage else None,
                )
                self.save(state="loading", launcher=process_identity(child.pid))
                if storage:
                    storage.session.check("before-target-load")
                os.write(write_fd, b"1")
                if storage:
                    storage.start()
            finally:
                os.close(read_fd)
                os.close(write_fd)

            deadline, heartbeat = time.monotonic() + timeout, 0.0
            ready = False
            marker = Path(f"{self.record['readiness']}.{token}.ready")
            while child.poll() is None:
                if storage:
                    storage.check_failure()
                if heartbeat_failed.is_set():
                    raise RuntimeError("lease heartbeat failed")
                now = time.monotonic()
                if now >= heartbeat:
                    self.broker.call("heartbeat", token=token)
                    heartbeat = now + 30
                if not ready and marker.exists():
                    value = json.loads(marker.read_text())
                    if value["lease_token_sha256"] != self.record["lease_sha256"]:
                        raise RuntimeError("readiness lease mismatch")
                    self.broker.call("ready", token=token)
                    self.save(state="qualifying-target")
                    target = execute_target_checks(
                        preflight_plan,
                        receipt_directory / "target-preflight.json",
                        admission,
                    )
                    if heartbeat_failed.is_set():
                        raise RuntimeError("lease heartbeat failed during target qualification")
                    if not target["completed"]:
                        raise RuntimeError("resident target preflight failed")
                    ready = True
                    info = self.docker.inspect(self.record["container"])
                    if info is None:
                        raise RuntimeError("ready container absent")
                    self.save(
                        state="ready",
                        container_id=info["Id"],
                        container_pid=info["State"].get("Pid"),
                    )
                if not ready and now >= deadline:
                    raise TimeoutError("model readiness timeout")
                time.sleep(0.2)
            if storage:
                storage.check_failure()
            if not ready:
                raise RuntimeError("model exited before readiness")
            return child.returncode
        finally:
            heartbeat_stop.set()
            if heartbeat_worker is not None:
                heartbeat_worker.join(timeout=11)
            # Stop the docker client group before container cleanup. Docker stop
            # remains required because a daemon-owned container outlives its client.
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            for original_signum, handler in handlers.items():
                signal.signal(original_signum, handler)
            if storage:
                storage.before_cleanup()
            resource_cleanup = self.reconcile()
            if storage:
                storage.finish(resource_cleanup)
            if not resource_cleanup:
                raise RuntimeError("resource cleanup pending; run reconcile before new allocation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "reconcile"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--broker-socket", default="/run/ollama-unify/gpu-negotiator.sock")
    parser.add_argument("--docker-host", default="unix:///run/matric-eval-docker.sock")
    parser.add_argument("--preflight-plan", type=Path)
    parser.add_argument("--storage-plan", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--owner", default="matric-eval")
    parser.add_argument("--gpu")
    parser.add_argument("--ready-timeout", type=float, default=900)
    parser.add_argument("--memory-mib", type=int, default=75000)
    args, command = parser.parse_known_args()
    lifecycle = ResourceLifecycle(
        args.directory, Broker(args.broker_socket), Docker(args.docker_host)
    )
    try:
        if args.action == "reconcile":
            return 0 if lifecycle.reconcile() else 1
        if args.preflight_plan is None:
            raise ValueError("run requires --preflight-plan")
        plan = json.loads(args.preflight_plan.read_text())
        lifecycle.prepare(args.run_id, args.attempt_id, args.gpu, args.owner)
        command = command[1:] if command[:1] == ["--"] else command
        return lifecycle.run(
            command,
            args.ready_timeout,
            args.memory_mib,
            preflight_plan=plan,
            storage_plan=json.loads(args.storage_plan.read_text()) if args.storage_plan else None,
        )
    finally:
        lifecycle.close()


if __name__ == "__main__":
    raise SystemExit(main())
