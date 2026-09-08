"""Storage admission and measurements for the owned resident-container lifecycle."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any, BinaryIO

from matric_eval.storage import Allocation, StorageBlocker, StorageSession, publish_run_status


def docker_control_contract(
    command: list[str], config: dict[str, Any], docker: Any
) -> dict[str, Any]:
    """Validate the finite daemon write path; arbitrary daemon workloads cannot opt in.

    Writable application paths are separately kernel bounded. Docker metadata is
    reserved and observed conservatively across the real shared daemon root, not
    described as a kernel quota or zero-growth immutable image directory.
    """
    if (
        len(command) < 5
        or Path(command[0]).name != "docker"
        or command[1:4] != ["--host", docker.host, "run"]
    ):
        raise StorageBlocker(
            "storage_docker_contract", "expected one explicit daemon/container run"
        )
    if (
        "--read-only" not in command
        or any(
            arg.startswith(
                ("--tmpfs", "--privileged", "--volume", "--mount=", "--read-only=", "--restart")
            )
            or arg.startswith("-v")
            for arg in command
        )
        or any(arg in command for arg in ("--privileged", "-v", "--volume", "--mount=type=volume"))
    ):
        raise StorageBlocker(
            "storage_docker_contract", "read-only root and declared bind mounts are required"
        )
    for flag, value in (("--pull", "never"), ("--log-driver", "none")):
        if (
            command.count(flag) != 1
            or command.index(flag) + 1 >= len(command)
            or command[command.index(flag) + 1] != value
            or any(arg.startswith(flag + "=") for arg in command)
        ):
            raise StorageBlocker("storage_docker_contract", f"{flag} {value} is required")
    writable = {
        str(Path(item["path"]).resolve())
        for item in config["allocations"]
        if item["kind"] != "docker" and (item["budget_bytes"] or item["budget_inodes"])
    }
    seen = set()
    for index, argument in enumerate(command):
        if argument != "--mount":
            continue
        if index + 1 >= len(command):
            raise StorageBlocker("storage_docker_contract", "mount argument missing")
        fields = dict(
            (part.split("=", 1)[0], part.split("=", 1)[1]) if "=" in part else (part, "true")
            for part in command[index + 1].split(",")
        )
        if fields.get("type") != "bind":
            raise StorageBlocker(
                "storage_docker_contract", "only declared bind mounts are supported"
            )
        if fields.get("readonly") == "true" or fields.get("ro") == "true":
            continue
        source = str(Path(fields.get("src", fields.get("source", ""))).resolve())
        if source == "/run/ollama-unify/gpu-negotiator.sock":
            continue
        if source not in writable:
            raise StorageBlocker(
                "storage_docker_contract", "writable bind is outside declared bounded storage"
            )
        seen.add(source)
    required = {
        str(Path(item["path"]).resolve())
        for item in config["allocations"]
        if item["kind"] not in ("docker", "logs")
        and (item["budget_bytes"] or item["budget_inodes"])
    }
    if not required <= seen:
        raise StorageBlocker(
            "storage_docker_contract",
            "all application storage budgets must bind their actual writer paths",
        )
    root = subprocess.check_output(
        docker.command("info", "--format", "{{.DockerRootDir}}"), text=True, timeout=15
    ).strip()
    return {
        "root": root,
        "container_limit": 1,
        "rootfs": "read-only",
        "pull": "never",
        "daemon_logs": "none",
        "writable_binds": sorted(seen),
        "enforcement": "finite single-container control metadata; reserved and monitored, not a kernel quota",
    }


class ResidentStorage:
    def __init__(self, config: dict[str, Any], resource: Any, command: list[str]) -> None:
        contract = docker_control_contract(command, config, resource.docker)
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

    def admit(self) -> None:
        self.session.admit(reserve=True)
        self.session.bind_resource(self.resource.path)
        self.session.claim_empty_scratch()
        self.session.check("before-preflight")
        publish_run_status(self.session, "admission")
        self.resource.save(
            storage_reservation={"ledger": str(self.session.ledger), "owner": self.session.token}
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
                    launcher = self.resource.record.get("launcher")
                    if launcher:
                        try:
                            os.killpg(launcher["pid"], signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    return

        self.worker = threading.Thread(target=monitor, daemon=True)
        self.worker.start()

    def check_failure(self) -> None:
        if self.failure:
            raise StorageBlocker("storage_runtime", str(self.failure))

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
