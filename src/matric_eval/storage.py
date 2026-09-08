"""Linux storage admission, cooperative reservations, and bounded run monitoring.

Run ``python -m matric_eval.storage plan.json`` for an admission plan.
Use ``-- command ...`` to reserve capacity and supervise a process group.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

from matric_eval.studies.run_status import RunStatus, diagnostic

CLASSES = {"models", "download_cache", "docker", "scratch", "temporary", "logs", "evidence"}
DIAGNOSTIC_BYTES = 1024 * 1024


class StorageBlocker(RuntimeError):
    """An actionable infrastructure failure, never a model-quality score."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class Allocation:
    kind: str
    path: str
    budget_bytes: int
    budget_inodes: int
    estimated_bytes: int | None = None
    disposable: bool = False


def filesystem(path: Path, *, allow_read_only: bool = False) -> dict[str, Any]:
    """Resolve the real Linux mount, including bind mounts, without creating paths."""
    try:
        resolved = path.resolve(strict=True)
        stat = resolved.stat()
        capacity = os.statvfs(resolved)
        mounts = []
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            fields = line.split()
            target = fields[4].replace("\\040", " ").replace("\\134", "\\")
            if resolved == Path(target) or Path(target) in resolved.parents:
                split = fields.index("-")
                mounts.append((len(target), fields[0], target, fields[split + 2]))
        _, mount_id, target, source = max(mounts)
        if capacity.f_flag & os.ST_RDONLY and not allow_read_only:
            raise StorageBlocker("storage_read_only", str(resolved))
        return {
            "device": str(stat.st_dev),
            "mount_id": mount_id,
            "mount": target,
            "source": source,
            "free_bytes": capacity.f_bavail * capacity.f_frsize,
            "free_inodes": capacity.f_favail,
            "capacity_bytes": capacity.f_blocks * capacity.f_frsize,
            "capacity_inodes": capacity.f_files,
        }
    except OSError as exc:
        raise StorageBlocker("storage_io", f"{path}: {exc}") from exc


def usage(path: Path, *, backing_device_only: bool = False) -> tuple[int, int]:
    """Allocated blocks and unique inodes; links never traverse ownership boundaries."""
    seen: set[tuple[int, int]] = set()
    size = 0
    try:
        device = path.stat().st_dev
        for root, dirs, files in os.walk(
            path, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)
        ):
            if backing_device_only:
                # Docker merged overlay mounts expose existing image blocks again;
                # account the backing data root, not those virtual filesystem views.
                dirs[:] = [name for name in dirs if (Path(root) / name).lstat().st_dev == device]
            for entry in [Path(root), *(Path(root) / name for name in dirs + files)]:
                stat = entry.lstat()
                if backing_device_only and stat.st_dev != device:
                    continue
                key = (stat.st_dev, stat.st_ino)
                if key not in seen:
                    seen.add(key)
                    size += stat.st_blocks * 512
        return size, len(seen)
    except OSError as exc:
        raise StorageBlocker("storage_io", f"{path}: {exc}") from exc


def process_identity(pid: int) -> str | None:
    try:
        # comm can contain spaces and parentheses; starttime is field 22.
        start = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip() + ":" + start
    except FileNotFoundError:
        return None


def group_alive(group: int) -> bool:
    """Conservatively retain a dead supervisor's reservation while writers remain."""
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


class StorageSession:
    """One host-wide ledger directory must be shared by all cooperating runs.

    Reservations remain conservative (full remaining allowances) until release.
    Recovery requires proof that the reserving PID identity has disappeared.
    """

    def __init__(
        self,
        allocations: list[Allocation],
        ledger: Path,
        ownership: Path,
        headroom_bytes: int,
        headroom_inodes: int,
        require_enforced_bounds: bool = True,
        docker_control: dict[str, Any] | None = None,
    ):
        if {a.kind for a in allocations} != CLASSES or len(allocations) != len(CLASSES):
            raise ValueError(f"Declare each storage class exactly once: {sorted(CLASSES)}")
        if min(headroom_bytes, headroom_inodes) < 0:
            raise ValueError("Headroom must be nonnegative")
        self.docker_control = docker_control
        self.allocations = allocations
        self.ledger = ledger.resolve(strict=True)
        self.ledger_mount = filesystem(self.ledger)
        self.ownership = ownership.resolve(strict=True)
        self.headroom_bytes = headroom_bytes
        self.headroom_inodes = headroom_inodes
        self.require_enforced_bounds = require_enforced_bounds
        self.token = uuid.uuid4().hex
        self.active = False
        self.started = time.monotonic()
        self.samples: list[dict[str, Any]] = []
        self.peak_scratch_bytes = 0
        self.paths: dict[str, Path] = {}
        self.baselines: dict[str, tuple[int, int]] = {}
        self.mounts: dict[str, dict[str, Any]] = {}
        for allocation in allocations:
            if min(allocation.budget_bytes, allocation.budget_inodes) < 0:
                raise ValueError("Budgets must be nonnegative")
            if (
                allocation.estimated_bytes is not None
                and not 0 <= allocation.estimated_bytes <= allocation.budget_bytes
            ):
                raise ValueError("Estimated demand must fit the budget")
            path = Path(allocation.path).resolve(strict=True)
            if not path.is_dir():
                raise ValueError(f"Storage path must be an existing directory: {path}")
            self.paths[allocation.kind] = path
            self.mounts[allocation.kind] = filesystem(
                path, allow_read_only=not (allocation.budget_bytes or allocation.budget_inodes)
            )
            self.baselines[allocation.kind] = usage(
                path, backing_device_only=bool(self.docker_control and allocation.kind == "docker")
            )
        mutable = [self.paths[a.kind] for a in allocations if a.budget_bytes or a.budget_inodes]
        if any(
            a == b or a in b.parents or b in a.parents
            for i, a in enumerate(mutable)
            for b in mutable[i + 1 :]
        ):
            raise ValueError("Writable storage roots must not overlap")
        self.before = self.plan()
        self.owned: dict[str, tuple[int, int]] = {}

    def claim_empty_scratch(self) -> None:
        """Record lineage only for empty, dedicated scratch directories we can own."""
        protected = [
            self.paths[a.kind]
            for a in self.allocations
            if a.kind not in {"scratch", "temporary", "download_cache"} or not a.disposable
        ]
        for allocation in self.allocations:
            path = self.paths[allocation.kind]
            if (
                allocation.disposable
                and allocation.kind in {"scratch", "temporary", "download_cache"}
                and self.ownership in path.parents
                and not any(path == p or path in p.parents or p in path.parents for p in protected)
                and not any(path.iterdir())
            ):
                stat = path.stat()
                self.owned[allocation.kind] = (stat.st_dev, stat.st_ino)

    @contextmanager
    def locked(self) -> Iterator[dict[str, Any]]:
        try:
            with (self.ledger / "reservations.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                path = self.ledger / "reservations.json"
                state = json.loads(path.read_text()) if path.exists() else {}
                for key, record in list(state.items()):
                    if process_identity(record["pid"]) != record["identity"] and not (
                        record.get("process_group") and group_alive(record["process_group"])
                    ):
                        resource = record.get("resource_record")
                        if resource and (
                            not Path(resource).exists()
                            or json.loads(Path(resource).read_text()).get("cleanup") != "complete"
                        ):
                            continue
                        del state[key]
                yield state
                temporary = self.ledger / f".{self.token}.tmp"
                with temporary.open("w") as output:
                    json.dump(state, output)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(path)
        except OSError as exc:
            raise StorageBlocker("storage_ledger_io", str(exc)) from exc

    def plan(self) -> dict[str, Any]:
        volumes: dict[str, dict[str, Any]] = {}
        classes = []
        for allocation in self.allocations:
            current = filesystem(
                self.paths[allocation.kind],
                allow_read_only=not (allocation.budget_bytes or allocation.budget_inodes),
            )
            initial = self.mounts[allocation.kind]
            if any(current[key] != initial[key] for key in ("device", "mount_id", "mount")):
                raise StorageBlocker("storage_mount_changed", allocation.kind)
            volume = volumes.setdefault(
                current["device"], {**current, "reserved_bytes": 0, "reserved_inodes": 0}
            )
            protect = (
                not self.require_enforced_bounds
                or current["device"] == self.ledger_mount["device"]
                or (self.docker_control is not None and allocation.kind == "docker")
            )
            volume["headroom_bytes"] = max(
                volume.get("headroom_bytes", 0), self.headroom_bytes if protect else 0
            )
            volume["headroom_inodes"] = max(
                volume.get("headroom_inodes", 0), self.headroom_inodes if protect else 0
            )
            baseline = self.baselines[allocation.kind]
            volume["reserved_bytes"] += min(
                allocation.budget_bytes,
                current["free_bytes"]
                if self.require_enforced_bounds
                and allocation.kind != "docker"
                and current["device"] != self.ledger_mount["device"]
                else max(0, current["capacity_bytes"] - baseline[0]),
            )
            volume["reserved_inodes"] += min(
                allocation.budget_inodes,
                current["free_inodes"]
                if self.require_enforced_bounds
                and allocation.kind != "docker"
                and current["device"] != self.ledger_mount["device"]
                else max(0, current["capacity_inodes"] - baseline[1]),
            )
            classes.append(
                {
                    **asdict(allocation),
                    **current,
                    "demand": "unknown" if allocation.estimated_bytes is None else "estimated",
                    "baseline_bytes": baseline[0],
                    "baseline_inodes": baseline[1],
                }
            )
        diagnostic = filesystem(self.ledger)
        if any(
            diagnostic[key] != self.ledger_mount[key] for key in ("device", "mount_id", "mount")
        ):
            raise StorageBlocker("storage_mount_changed", "emergency diagnostics ledger")
        volume = volumes.setdefault(
            diagnostic["device"], {**diagnostic, "reserved_bytes": 0, "reserved_inodes": 0}
        )
        volume["reserved_bytes"] += DIAGNOSTIC_BYTES
        volume["reserved_inodes"] += 16
        volume["headroom_bytes"] = self.headroom_bytes
        volume["headroom_inodes"] = self.headroom_inodes
        return {
            "classes": classes,
            "filesystems": volumes,
            "emergency_diagnostics": {
                "path": str(self.ledger),
                "reserved_bytes": DIAGNOSTIC_BYTES,
                "reserved_inodes": 16,
            },
        }

    def _admit(self, plan: dict[str, Any], state: dict[str, Any]) -> None:
        for device, volume in plan["filesystems"].items():
            for unit in ("bytes", "inodes"):
                # The shared free-space floor is the strictest live run's floor;
                # budgets are additive, while one free byte satisfies all floors.
                headroom = max(
                    [volume[f"headroom_{unit}"]]
                    + [
                        record["volumes"].get(device, {}).get(f"headroom_{unit}", 0)
                        for key, record in state.items()
                        if key != self.token
                    ]
                )
                reserved = sum(
                    record["volumes"].get(device, {}).get(f"reserved_{unit}", 0)
                    for key, record in state.items()
                    if key != self.token
                )
                if volume[f"free_{unit}"] < headroom + volume[f"reserved_{unit}"] + reserved:
                    raise StorageBlocker(
                        f"storage_insufficient_{unit}",
                        f"device {device}: free={volume[f'free_{unit}']}, budget={volume[f'reserved_{unit}']}, concurrent={reserved}, headroom={headroom}",
                    )

    def admit(self, reserve: bool = False) -> dict[str, Any]:
        with self.locked() as state:
            plan = self.plan()
            self._admit(plan, state)
            if reserve:
                if self.require_enforced_bounds:
                    self.verify_bounds(plan)
                state[self.token] = {
                    "pid": os.getpid(),
                    "identity": process_identity(os.getpid()),
                    "volumes": plan["filesystems"],
                }
                self.active = True
        return plan

    def bind_resource(self, path: Path) -> None:
        """Keep a dead controller's reservation until owned daemon cleanup is proven."""
        if not self.active:
            raise ValueError("resource binding requires an active reservation")
        with self.locked() as state:
            state[self.token]["resource_record"] = str(path.resolve())

    def attach_process_group(self, pid: int) -> None:
        """Attach a dedicated child process group before allowing its writers to run."""
        if not self.active or os.getpgid(pid) != pid:
            raise ValueError("An active reservation and dedicated process group are required")
        with self.locked() as state:
            state[self.token]["process_group"] = pid

    def verify_bounds(self, plan: dict[str, Any]) -> None:
        """Fail closed unless volatile writers have kernel-bounded filesystems.

        A configured byte allowance alone is not proof of an enforced quota.
        Emergency diagnostics use a different device from all growing allocations.
        This implementation supports bounded filesystems, not quota attestations.
        """
        diagnostic_device = self.ledger_mount["device"]
        for item in plan["classes"]:
            if not (item["budget_bytes"] or item["budget_inodes"]):
                continue
            if item["kind"] == "docker" and self.docker_control is not None:
                if (
                    Path(self.docker_control["root"]).resolve() != self.paths["docker"]
                    or item["budget_bytes"] < 64 * 1024 * 1024
                    or item["budget_inodes"] < 4096
                ):
                    raise StorageBlocker(
                        "storage_docker_control_bound",
                        "reserve at least 64 MiB/4096 inodes for the validated single-container daemon contract",
                    )
                continue
            if (
                item["device"] == diagnostic_device
                or item["capacity_bytes"] > item["budget_bytes"]
                or not item["capacity_inodes"]
                or item["capacity_inodes"] > item["budget_inodes"]
            ):
                raise StorageBlocker(
                    "storage_enforcement_required",
                    f"{item['kind']}: require a byte/inode bounded filesystem on a different device from emergency diagnostics; configured budgets are not kernel quotas",
                )

    def check(
        self, phase: str, pid: int | None = None, *, container_id: str | None = None
    ) -> dict[str, Any]:
        plan = self.plan()
        measured = {}
        blocker = None
        for allocation in self.allocations:
            current = usage(
                self.paths[allocation.kind],
                backing_device_only=bool(self.docker_control and allocation.kind == "docker"),
            )
            baseline = self.baselines[allocation.kind]
            delta = tuple(max(0, value - base) for value, base in zip(current, baseline))
            measured[allocation.kind] = {"bytes": delta[0], "inodes": delta[1]}
            if delta[0] > allocation.budget_bytes or delta[1] > allocation.budget_inodes:
                blocker = StorageBlocker(
                    "storage_budget_exceeded", f"{allocation.kind}: {measured[allocation.kind]}"
                )
        process_io = {}
        for process_id in {os.getpid(), pid} - {None}:
            try:
                process_io[str(process_id)] = Path(f"/proc/{process_id}/io").read_text()
            except FileNotFoundError:
                process_io[str(process_id)] = "process_exited_before_sample"
            except OSError as exc:
                raise StorageBlocker("storage_io", str(exc)) from exc
        container_io: dict[str, Any] = {}
        if pid and container_id:
            try:
                lines = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
                unified = next(line.split(":", 2)[2] for line in lines if line.startswith("0::"))
                if container_id not in unified or ".." in Path(unified).parts:
                    raise StorageBlocker(
                        "storage_io_identity", "PID is not in the owned container cgroup"
                    )
                cgroup = Path("/sys/fs/cgroup") / unified.lstrip("/")
                container_io = {
                    "container_id": container_id,
                    "pid": pid,
                    "cgroup": unified,
                    "io_stat": (cgroup / "io.stat").read_text(),
                }
            except FileNotFoundError:
                container_io = {
                    "container_id": container_id,
                    "pid": pid,
                    "state": "exited-before-sample",
                }
            except (OSError, StopIteration) as error:
                raise StorageBlocker("storage_io", "owned cgroup counters unavailable") from error
        sample = {
            "phase": phase,
            "elapsed_seconds": time.monotonic() - self.started,
            "usage": measured,
            "filesystems": plan["filesystems"],
            "process_io": process_io,
            "container_io": container_io,
        }
        self.samples.append(sample)
        self.peak_scratch_bytes = max(self.peak_scratch_bytes, measured["scratch"]["bytes"])
        if len(self.samples) > 64:
            del self.samples[1]
        for volume in plan["filesystems"].values():
            if (
                self.require_enforced_bounds
                and volume["device"] != self.ledger_mount["device"]
                and not (
                    self.docker_control and volume["device"] == self.mounts["docker"]["device"]
                )
            ):
                if volume["free_bytes"] == 0 or volume["free_inodes"] == 0:
                    blocker = StorageBlocker("storage_bound_exhausted", str(volume))
                continue
            if (
                volume["free_bytes"] < self.headroom_bytes
                or volume["free_inodes"] < self.headroom_inodes
            ):
                blocker = StorageBlocker("storage_headroom_exhausted", str(volume))
        if blocker:
            raise blocker
        return sample

    @contextmanager
    def phase(self, name: str, pid: int | None = None) -> Iterator[None]:
        """Capture load or task boundaries; caller still checks during long phases."""
        self.check(f"{name}:before", pid)
        try:
            yield
        finally:
            self.check(f"{name}:after", pid)

    def cleanup_preview(self) -> list[dict[str, str]]:
        """Only explicitly declared owned scratch is eligible; this API never deletes."""

        def still_owned(kind: str) -> bool:
            path = self.paths[kind]
            try:
                stat = path.lstat()
                return not path.is_symlink() and self.owned.get(kind) == (stat.st_dev, stat.st_ino)
            except OSError:
                return False

        return [
            {"path": str(self.paths[a.kind]), "owner": self.token, "action": "policy_required"}
            for a in self.allocations
            if a.disposable
            and a.kind in {"scratch", "temporary", "download_cache"}
            and still_owned(a.kind)
            and self.ownership in self.paths[a.kind].parents
            and not any(
                word in str(self.paths[a.kind]).lower()
                for word in (
                    "omnius",
                    "lance",
                    "credential",
                    "weights",
                    "models",
                    "docker",
                    "evidence",
                )
            )
        ]

    def release(self) -> None:
        if self.active:
            with self.locked() as state:
                record = state.get(self.token)
                if (
                    record
                    and record["pid"] == os.getpid()
                    and record["identity"] == process_identity(os.getpid())
                ):
                    resource = record.get("resource_record")
                    if resource and (
                        not Path(resource).exists()
                        or json.loads(Path(resource).read_text()).get("cleanup") != "complete"
                    ):
                        return
                    if record.get("process_group") and group_alive(record["process_group"]):
                        return
                    del state[self.token]
                elif record:
                    # An ownership mismatch cannot authorize releasing capacity.
                    return
            self.active = False

    def receipt(self) -> dict[str, Any]:
        return {
            "owner": self.token,
            "reservation_active": self.active,
            "before": self.before,
            "samples": self.samples,
            "peak_scratch_bytes": self.peak_scratch_bytes,
            "cleanup_preview": self.cleanup_preview(),
            "elapsed_seconds": time.monotonic() - self.started,
            "docker_control": self.docker_control,
            "measurement_scope": "sampled allocated blocks/inodes, named PID I/O and exact owned container cgroup I/O when available; cgroup counters include descendants; between-sample filesystem peaks are not included; no throughput improvement is inferred",
        }

    def write_diagnostics(self, receipt: dict[str, Any]) -> Path:
        """Write within the separately reserved emergency area, never a fallback path."""
        current = filesystem(self.ledger)
        if any(current[key] != self.ledger_mount[key] for key in ("device", "mount_id", "mount")):
            raise StorageBlocker("storage_mount_changed", "emergency diagnostics ledger")
        encoded = json.dumps(receipt)
        if len(encoded.encode()) > DIAGNOSTIC_BYTES:
            raise StorageBlocker("storage_diagnostic_budget", "receipt exceeds reserved 1 MiB")
        path = self.ledger / f"{self.token}.receipt.json"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            directory_fd = os.open(self.ledger, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise StorageBlocker("storage_diagnostic_io", str(exc)) from exc
        return path


def publish_run_status(
    session: StorageSession | None,
    stage: str,
    *,
    error: BaseException | None = None,
    receipt_path: Path | None = None,
) -> None:
    """Project storage ownership into the same supervisor status, never task progress."""
    directory = os.environ.get("MATRIC_RUN_STATUS_DIR")
    if not directory:
        return
    status = RunStatus(Path(directory))
    try:
        with status.update() as data:
            previous = data.get("storage", {})
            data["storage"] = {
                "owner": session.token if session else None,
                "reservation_active": session.active if session else False,
                "stage": stage,
                "updated_at": time.time(),
                "diagnostic_receipt": str(receipt_path)
                if receipt_path
                else previous.get("diagnostic_receipt"),
                "last_sample": session.samples[-1] if session and session.samples else None,
                "peak_scratch_bytes": session.peak_scratch_bytes if session else 0,
            }
            if error is not None:
                reason = (
                    error.code if isinstance(error, StorageBlocker) else "storage_configuration"
                )
                item = diagnostic(error, actor="storage", stage=stage, reason=reason)
                item["cleanup_disposition"] = (
                    "pending" if session and session.active else "not-required"
                )
                data["diagnostics"] = (data["diagnostics"] + [item])[-16:]
                if data["terminal_event"] is None:
                    data["phase"] = (
                        "preflight-blocked" if stage in {"configuration", "admission"} else "failed"
                    )
                    data["phase_timestamps"][data["phase"]] = time.time()
    except (OSError, ValueError, KeyError) as exc:
        raise StorageBlocker(
            "storage_status_io", "cannot persist correlated storage state"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if not math.isfinite(args.interval) or args.interval <= 0:
            raise ValueError("storage monitor interval must be finite and positive")
        config = json.loads(args.plan.read_text())
        session = StorageSession(
            [Allocation(**item) for item in config["allocations"]],
            Path(config["ledger"]),
            Path(config["ownership"]),
            config["headroom_bytes"],
            config["headroom_inodes"],
        )
    except (StorageBlocker, OSError, ValueError, KeyError, TypeError) as exc:
        code = exc.code if isinstance(exc, StorageBlocker) else "storage_configuration"
        print(json.dumps({"failure_class": code, "detail": str(exc)}), flush=True)
        publish_run_status(None, "configuration", error=exc)
        return 75
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    process = None
    failure = None
    cleanup_errors: list[str] = []
    stage = "admission"
    receipt_path = None
    try:
        plan = session.admit(reserve=bool(command))
        if not command:
            print(json.dumps(plan, indent=2))
            return 0
        publish_run_status(session, stage)
        session.claim_empty_scratch()
        reader, writer = os.pipe()
        try:
            # EOF on supervisor death prevents unregistered writers from starting.
            launcher = (
                "import os,sys; fd=int(sys.argv[1]); ready=os.read(fd,1); os.close(fd); "
                "sys.exit(75) if ready != b'1' else os.execvp(sys.argv[2],sys.argv[2:])"
            )
            process = subprocess.Popen(
                [sys.executable, "-c", launcher, str(reader), *command],
                pass_fds=(reader,),
                start_new_session=True,
            )
            session.attach_process_group(process.pid)
            stage = "execution"
            publish_run_status(session, stage)
            os.write(writer, b"1")
        finally:
            os.close(reader)
            os.close(writer)
        while process.poll() is None:
            session.check("running", process.pid)
            publish_run_status(session, stage)
            time.sleep(max(0.01, args.interval))
        session.check("finished")
        return int(process.returncode)
    except StorageBlocker as exc:
        failure = {"failure_class": exc.code, "detail": str(exc)}
        try:
            publish_run_status(session, stage, error=exc)
        except StorageBlocker as status_error:
            cleanup_errors.append(str(status_error))
        print(json.dumps({"failure_class": exc.code, "detail": str(exc)}), flush=True)
        return 75
    finally:
        if process is not None and group_alive(process.pid):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            if group_alive(process.pid):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        receipt = {**session.receipt(), "failure": failure, "cleanup_errors": cleanup_errors}
        if process is not None or failure:
            try:
                receipt_path = session.write_diagnostics(receipt)
            except (StorageBlocker, OSError) as exc:
                cleanup_errors.append(str(exc))
        try:
            session.release()
        except (StorageBlocker, OSError) as exc:
            cleanup_errors.append(str(exc))
        try:
            publish_run_status(session, "cleanup", receipt_path=receipt_path)
        except StorageBlocker as exc:
            cleanup_errors.append(str(exc))
        receipt["reservation_active"] = session.active
        print(json.dumps({"storage_receipt": receipt}), flush=True)
        if cleanup_errors or session.active:
            return 75


if __name__ == "__main__":
    raise SystemExit(main())
