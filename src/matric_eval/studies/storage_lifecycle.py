"""Storage admission and measurements for the owned resident-container lifecycle."""

from __future__ import annotations

import json
import os
import signal
import socket
import struct
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, BinaryIO, Sequence

from matric_eval.storage import Allocation, StorageBlocker, StorageSession, publish_run_status
from matric_eval.studies.gpu import read_gpu_allocation


def require_daemon_mount_namespace(host: str) -> None:
    """Client filesystem bounds must describe the actual local Docker daemon view."""
    if not host.startswith("unix:///"):
        raise StorageBlocker("storage_docker_contract", "local Unix Docker socket required")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(host.removeprefix("unix://"))
            pid, _, _ = struct.unpack(
                "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
        if pid <= 0:
            raise StorageBlocker("storage_docker_contract", "Docker peer PID unavailable")
        identity = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        if Path(f"/proc/{pid}/comm").read_text().strip() != "dockerd" or os.readlink(
            f"/proc/{pid}/ns/mnt"
        ) != os.readlink("/proc/self/ns/mnt"):
            raise StorageBlocker(
                "storage_docker_contract", "Docker daemon and controller mount views differ"
            )
        if Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19] != identity:
            raise StorageBlocker("storage_docker_contract", "Docker peer identity changed")
    except OSError as error:
        raise StorageBlocker(
            "storage_docker_contract", "Docker daemon mount identity unavailable"
        ) from error


def docker_control_contract(
    command: list[str],
    config: dict[str, Any],
    docker: Any,
    *,
    gpu_uuids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate Docker options before IMAGE and every implicit writable image volume."""
    if (
        len(command) < 5
        or Path(command[0]).name != "docker"
        or command[1:4] != ["--host", docker.host, "run"]
    ):
        raise StorageBlocker(
            "storage_docker_contract", "expected one explicit daemon/container run"
        )
    valued = {
        "--name",
        "--label",
        "--network",
        "--hostname",
        "--runtime",
        "--gpus",
        "--ipc",
        "--ulimit",
        "--mount",
        "--workdir",
        "--env",
        "--entrypoint",
        "--pull",
        "--log-driver",
        "--pids-limit",
    }
    options: dict[str, list[str]] = {}
    index = 4
    while index < len(command) and command[index].startswith("-"):
        flag = command[index]
        if flag == "--":
            index += 1
            break
        if flag == "--read-only":
            options.setdefault(flag, []).append("true")
            index += 1
        elif flag in valued and index + 1 < len(command):
            options.setdefault(flag, []).append(command[index + 1])
            index += 2
        else:
            raise StorageBlocker(
                "storage_docker_contract", "unsupported or incomplete Docker option"
            )
    if index >= len(command) or "@sha256:" not in command[index]:
        raise StorageBlocker(
            "storage_docker_contract", "an existing digest-pinned image is required"
        )
    image = command[index]
    if gpu_uuids is not None:
        expected_selector = "device=" + ",".join(gpu_uuids)
        if options.get("--gpus") != [expected_selector]:
            raise StorageBlocker(
                "storage_docker_contract",
                "Docker GPU selector must exactly match the ordered lifecycle allocation",
            )
    for flag, value in (
        ("--read-only", "true"),
        ("--pull", "never"),
        ("--log-driver", "none"),
        ("--ipc", "private"),
    ):
        if options.get(flag) != [value]:
            raise StorageBlocker(
                "storage_docker_contract", f"{flag} {value} is required before IMAGE"
            )
    writable = {
        str(Path(item["path"]).resolve())
        for item in config["allocations"]
        if item["kind"] != "docker" and (item["budget_bytes"] or item["budget_inodes"])
    }
    required = {
        str(Path(item["path"]).resolve())
        for item in config["allocations"]
        if item["kind"] not in ("docker", "logs")
        and (item["budget_bytes"] or item["budget_inodes"])
    }
    seen: set[str] = set()
    destinations: set[str] = set()
    bounded_destinations: set[str] = set()
    for mount in options.get("--mount", []):
        fields = {}
        for part in mount.split(","):
            key, _, value = part.partition("=")
            if key in fields:
                raise StorageBlocker("storage_docker_contract", "duplicate mount option")
            fields[key] = value or "true"
        if fields.get("type") != "bind":
            raise StorageBlocker(
                "storage_docker_contract", "only declared bind mounts are supported"
            )
        source = str(Path(fields.get("src", fields.get("source", ""))).resolve())
        destination = fields.get("dst", fields.get("destination", fields.get("target", "")))
        if not destination.startswith("/") or destination in destinations:
            raise StorageBlocker(
                "storage_docker_contract", "unique absolute mount destinations are required"
            )
        destinations.add(destination)
        if source == "/run/ollama-unify/gpu-negotiator.sock":
            continue
        if Path(source).is_socket():
            raise StorageBlocker("storage_docker_contract", "undeclared control socket")
        if fields.get("readonly") == "true" or fields.get("ro") == "true":
            continue
        if source not in writable:
            raise StorageBlocker(
                "storage_docker_contract", "writable bind is outside declared bounded storage"
            )
        seen.add(source)
        bounded_destinations.add(destination)
    if "/dev/shm" not in bounded_destinations:
        raise StorageBlocker(
            "storage_docker_contract", "private IPC requires a declared bounded /dev/shm bind"
        )
    if not required <= seen:
        raise StorageBlocker(
            "storage_docker_contract", "all application writer paths require bounded binds"
        )
    require_daemon_mount_namespace(docker.host)
    metadata = json.loads(
        subprocess.check_output(docker.command("image", "inspect", image), text=True, timeout=15)
    )[0]
    volumes = sorted((metadata.get("Config") or {}).get("Volumes") or {})
    if any(volume not in destinations for volume in volumes):
        raise StorageBlocker(
            "storage_docker_contract",
            "image-declared writable volume lacks an explicit bounded or read-only bind",
        )
    root = subprocess.check_output(
        docker.command("info", "--format", "{{.DockerRootDir}}"), text=True, timeout=15
    ).strip()
    return {
        "root": root,
        "image": image,
        "image_id": metadata["Id"],
        "image_volumes": volumes,
        "container_limit": 1,
        "rootfs": "read-only",
        "pull": "never",
        "daemon_logs": "none",
        "writable_binds": sorted(seen),
        "enforcement": "finite single-container control metadata; reserved and monitored, not a kernel quota",
    }


class ResidentStorage:
    def __init__(self, config: dict[str, Any], resource: Any, command: list[str]) -> None:
        allocation = read_gpu_allocation(resource.record).allocation
        contract = docker_control_contract(
            command,
            config,
            resource.docker,
            gpu_uuids=allocation.gpu_uuids,
        )
        self.resource = resource
        self.session = StorageSession(
            [Allocation(**item) for item in config["allocations"]],
            Path(config["ledger"]),
            Path(config["ownership"]),
            config["headroom_bytes"],
            config["headroom_inodes"],
            docker_control=contract,
        )
        self.stop = threading.Event()
        self.failure: BaseException | None = None
        self.worker: threading.Thread | None = None
        self.receipt_path: Path | None = None
        self.log: BinaryIO | None = None
        self.environment: dict[str, str | None] = {}
        self.previous_tempdir = tempfile.tempdir

    def admit(self) -> None:
        self.session.admit(reserve=True)
        self.session.bind_resource(self.resource.path)
        self.session.claim_empty_scratch()
        for key, value in {
            "TMPDIR": str(self.session.paths["temporary"]),
            "HOME": str(self.session.paths["download_cache"]),
            "XDG_CACHE_HOME": str(self.session.paths["download_cache"]),
        }.items():
            self.environment[key] = os.environ.get(key)
            os.environ[key] = value
        tempfile.tempdir = None
        self.session.check("before-preflight")
        publish_run_status(self.session, "admission")
        self.resource.save(
            storage_reservation={
                "ledger": str(self.session.ledger),
                "owner": self.session.token,
                "ledger_identity": self.session.ledger_mount,
            }
        )
        self.resource.save(
            readiness=str(
                self.session.paths["evidence"] / f"{self.resource.record['resource_id']}.ready"
            )
        )
        self.log = (self.session.paths["logs"] / f"{self.resource.record['resource_id']}.log").open(
            "xb", buffering=0
        )

    def start(self) -> None:
        def monitor() -> None:
            while not self.stop.wait(0.5):
                try:
                    info = self.resource.docker.inspect(self.resource.record["container"])
                    pid, identifier = None, None
                    if info is not None:
                        if (
                            info["Config"].get("Labels", {}).get("matric.resource")
                            != self.resource.record["resource_id"]
                        ):
                            raise StorageBlocker(
                                "storage_io_identity", "container ownership changed"
                            )
                        pid, identifier = info["State"].get("Pid"), info["Id"]
                    self.session.check(
                        self.resource.record["state"], pid or None, container_id=identifier
                    )
                    publish_run_status(self.session, self.resource.record["state"])
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    self.failure = error
                    # This worker belongs to the controller process. Deliver its
                    # installed cancellation handler without addressing a stale PID/group.
                    if not self.stop.is_set():
                        signal.raise_signal(signal.SIGTERM)
                    return

        self.worker = threading.Thread(target=monitor, daemon=True)
        self.worker.start()

    def check_failure(self) -> None:
        if self.failure:
            raise StorageBlocker("storage_runtime", str(self.failure))

    def restore_environment(self) -> None:
        for key, value in self.environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tempfile.tempdir = self.previous_tempdir

    def before_cleanup(self) -> None:
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=30)
            if self.worker.is_alive():
                self.failure = self.failure or StorageBlocker(
                    "storage_monitor_pending", "monitor did not stop"
                )
        try:
            info = self.resource.docker.inspect(self.resource.record["container"])
            pid = info["State"].get("Pid") if info else None
            self.session.check(
                "before-resource-cleanup", pid or None, container_id=info["Id"] if info else None
            )
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            self.failure = self.failure or error

    def finish(self, resource_cleanup: bool) -> None:
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=30)
            if self.worker.is_alive():
                raise StorageBlocker("storage_monitor_pending", "monitor did not stop")
        if self.log:
            self.log.close()
        try:
            self.session.check("after-resource-cleanup")
        except StorageBlocker as error:
            self.failure = self.failure or error
        self.receipt_path = self.session.write_diagnostics(
            {
                **self.session.receipt(),
                "resource_cleanup": resource_cleanup,
                "failure": str(self.failure) if self.failure else None,
            }
        )
        if resource_cleanup:
            self.session.release()
        publish_run_status(self.session, "cleanup", receipt_path=self.receipt_path)
        self.resource.save(
            storage_receipt=str(self.receipt_path), storage_reservation_active=self.session.active
        )
        if self.session.active:
            raise StorageBlocker(
                "storage_cleanup_pending", "owned resources retain their storage reservation"
            )


def recover_resource_storage(resource: Any) -> None:
    """Discharge exactly one dead controller's storage obligation after CUDA cleanup."""
    import fcntl

    from matric_eval.storage import filesystem, process_identity
    from matric_eval.studies.resource_lifecycle import atomic
    from matric_eval.studies.run_status import RunStatus, group_alive

    reservation = resource.record.get("storage_reservation")
    if not reservation:
        return
    ledger = Path(reservation["ledger"])
    current = filesystem(ledger)
    expected = reservation["ledger_identity"]
    if any(current[key] != expected[key] for key in ("device", "mount_id", "mount")):
        raise StorageBlocker("storage_mount_changed", "reservation ledger moved")
    with (ledger / "reservations.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = ledger / "reservations.json"
        state = json.loads(path.read_text())
        owned = state.get(reservation["owner"])
        if owned:
            if owned.get("resource_record") != str(resource.path.resolve()):
                raise StorageBlocker(
                    "storage_owner_mismatch", "reservation belongs to another resource"
                )
            if process_identity(owned["pid"]) == owned["identity"]:
                raise StorageBlocker("storage_owner_alive", "storage owner has not exited")
            del state[reservation["owner"]]
            atomic(path, state)
    directory = os.environ.get("MATRIC_RUN_STATUS_DIR") or resource.record.get("status_directory")
    if directory:
        with RunStatus(Path(directory)).update() as status:
            storage = status.get("storage", {})
            if storage.get("owner") != reservation["owner"]:
                raise StorageBlocker(
                    "storage_owner_mismatch", "status belongs to another storage owner"
                )
            storage.update(reservation_active=False, stage="reconciled")
            worker = status.get("worker")
            if resource.record.get("cleanup") == "complete" and (
                worker is None or not group_alive(worker["pid"])
            ):
                status["cleanup"] = "complete"
                if status["phase"] == "cleanup-pending" and status.get("terminal_event"):
                    status["phase"] = status["terminal_event"]["phase"]
    resource.save(storage_reservation_active=False)
