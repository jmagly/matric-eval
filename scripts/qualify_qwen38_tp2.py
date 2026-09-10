#!/usr/bin/env python3
"""Qualify two-A100 TP2 execution and cleanup on Basilisk."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence

from matric_eval.studies.resource_lifecycle import Broker
from matric_eval.studies.tp2_qualification import (
    QUALIFICATION_SCHEMA,
    TAU_DIAGNOSTIC_IDS,
    build_tp2_agentic_inputs_overlay,
    build_tp2_protocol_overlay,
    content_free_inference_canary,
    sanitize_broker_status,
    validate_host_topology,
    validate_tau_diagnostic_receipt,
    write_private_json,
)

STUDY = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
TAU = Path("/srv/matric-eval/benchmarks/tau2-qwen38-simulator-guard-v3")
MODEL_ROOT = Path("/srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B")
MODEL_PATH = MODEL_ROOT / "snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
MODEL_ID = "qwen38-27b-source-bf16"
PYTHON = Path("/srv/matric-eval/workspaces/matric-eval-157-status/.venv311/bin/python")
DOCKER_HOST = "unix:///run/matric-eval-docker.sock"
BROKER_SOCKET = "/run/ollama-unify/gpu-negotiator.sock"
BROKER_EXECUTABLE = Path("/usr/local/libexec/ollama-unify-gpu-negotiator")
IMAGE = "vllm/vllm-openai@sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b"
SOURCE_PROTOCOL = "studies/qwen38-obliteration-2026-09/protocol.yaml"
SOURCE_MANIFEST = STUDY / "pilot-manifest.json"
SOURCE_SUMMARY = STUDY / "pilot-agentic-inputs/agentic-inputs-summary.json"
SCORED_IDS = STUDY / "pilot-agentic-inputs/tau3-scored-ids.json"
QUALIFICATION = STUDY / "source-model-qualification.json"
CHAT_TEMPLATE = STUDY / "chat_template.jinja"
STORAGE_SIZES = {
    "temporary": 8 * 2**30,
    "download_cache": 16 * 2**30,
    "scratch": 8 * 2**30,
    "logs": 1024 * 2**20,
    "evidence": 1024 * 2**20,
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_resolved_executable(path: Path) -> Path:
    """Validate an executable, allowing a symlink to a regular-file target."""
    if not path.exists():
        raise RuntimeError(f"required qualification input is unavailable: {path}")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise RuntimeError(f"required qualification input is unavailable: {path}") from error
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise RuntimeError(f"required qualification input is unavailable: {path}")
    return resolved


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _command(
    ledger: list[dict[str, Any]],
    name: str,
    arguments: Sequence[str | Path],
    *,
    timeout: int = 30,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    argv = [str(value) for value in arguments]
    started = time.time()
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    ledger.append(
        {
            "name": name,
            "argv": argv,
            "started_at": started,
            "completed_at": time.time(),
            "exit_code": result.returncode,
        }
    )
    if check and result.returncode:
        raise RuntimeError(f"{name} failed with exit {result.returncode}")
    return result


def _sudo(arguments: Sequence[str | Path]) -> list[str]:
    prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
    return [*prefix, *(str(value) for value in arguments)]


def _git(workspace: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(workspace), *arguments], text=True, timeout=15
    ).strip()


def _inventory(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = _command(
        ledger,
        "nvidia-inventory",
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total,memory.used,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ],
    )
    rows: list[dict[str, Any]] = []
    for row in csv.reader(result.stdout.splitlines(), skipinitialspace=True):
        if len(row) != 7:
            raise RuntimeError("nvidia-smi returned a malformed inventory row")
        rows.append(
            {
                "index": int(row[0]),
                "uuid": row[1],
                "name": row[2],
                "memory_mib": int(row[3]),
                "used_mib": int(row[4]),
                "free_mib": int(row[5]),
                "driver_version": row[6],
                "pci_bus_id": _command(
                    ledger,
                    f"nvidia-pci-{row[0]}",
                    [
                        "nvidia-smi",
                        "--id",
                        row[1],
                        "--query-gpu=pci.bus_id",
                        "--format=csv,noheader",
                    ],
                ).stdout.strip(),
            }
        )
    return rows


def _compute_process_gpu_uuids(output: str) -> set[str]:
    gpu_uuids: set[str] = set()
    for row in csv.reader(output.splitlines(), skipinitialspace=True):
        if not row:
            continue
        if len(row) != 2 or not row[0].startswith("GPU-") or not row[1].strip().isdigit():
            raise RuntimeError("nvidia-smi returned a malformed compute-process row")
        gpu_uuids.add(row[0])
    return gpu_uuids


def _active_compute_gpu_uuids(ledger: list[dict[str, Any]]) -> set[str]:
    result = _command(
        ledger,
        "nvidia-compute-processes",
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid",
            "--format=csv,noheader,nounits",
        ],
    )
    return _compute_process_gpu_uuids(result.stdout)


def _pair_is_available(
    inventory: list[dict[str, Any]],
    gpus: tuple[str, str],
    active_compute_gpu_uuids: set[str],
) -> bool:
    by_uuid = {item["uuid"]: item for item in inventory}
    return all(
        gpu in by_uuid
        and type(by_uuid[gpu].get("free_mib")) is int
        and by_uuid[gpu]["free_mib"] >= 37_500
        and gpu not in active_compute_gpu_uuids
        for gpu in gpus
    )


def _wait_for_pair(
    ledger: list[dict[str, Any]], gpus: tuple[str, str], wait_seconds: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    deadline = time.monotonic() + wait_seconds
    while True:
        inventory = _inventory(ledger)
        active_compute_gpu_uuids = _active_compute_gpu_uuids(ledger)
        status = Broker(BROKER_SOCKET).call("status")
        selected_leases = [
            lease
            for lease in status.get("leases", [])
            if isinstance(lease, dict) and set(lease.get("gpu_uuids", [])) & set(gpus)
        ]
        if _pair_is_available(inventory, gpus, active_compute_gpu_uuids) and not selected_leases:
            return inventory, status
        if time.monotonic() >= deadline:
            raise TimeoutError("qualified GPU pair did not become available before the deadline")
        time.sleep(min(30, max(1, int(deadline - time.monotonic()))))


def _host_evidence(
    workspace: Path,
    revision: str,
    gpus: tuple[str, str],
    wait_seconds: int,
    ledger: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    inventory, broker = _wait_for_pair(ledger, gpus, wait_seconds)
    topology = _command(ledger, "nvidia-topology", ["nvidia-smi", "topo", "-m"]).stdout
    p2p_read = _command(ledger, "nvidia-p2p-read", ["nvidia-smi", "topo", "-p2p", "r"]).stdout
    p2p_write = _command(ledger, "nvidia-p2p-write", ["nvidia-smi", "topo", "-p2p", "w"]).stdout
    p2p_nvlink = _command(ledger, "nvidia-p2p-nvlink", ["nvidia-smi", "topo", "-p2p", "n"]).stdout
    binding = validate_host_topology(
        gpu_uuids=gpus,
        inventory=inventory,
        topology=topology,
        p2p_read=p2p_read,
        p2p_write=p2p_write,
        p2p_nvlink=p2p_nvlink,
    )
    image = _command(
        ledger,
        "runtime-image",
        _sudo(
            [
                "docker",
                "--host",
                DOCKER_HOST,
                "image",
                "inspect",
                IMAGE,
                "--format",
                "{{.Id}}",
            ]
        ),
    ).stdout.strip()
    if image != IMAGE.split("@", 1)[1]:
        raise RuntimeError("Docker image ID does not match the pinned image digest")
    runtime = _command(
        ledger,
        "nvidia-container-runtime",
        ["nvidia-container-cli", "--version"],
    ).stdout.strip()
    service = _command(
        ledger,
        "broker-service",
        ["systemctl", "is-active", "ollama-unify-negotiator.service"],
    ).stdout.strip()
    if service != "active":
        raise RuntimeError("GPU broker service is not active")
    selected = [{**item} for item in inventory if item["uuid"] in gpus]
    selected.sort(key=lambda item: gpus.index(item["uuid"]))
    private = {
        "captured_at": time.time(),
        "hostname": platform.node(),
        "workspace": str(workspace),
        "revision": revision,
        "git_status": _git(workspace, "status", "--porcelain"),
        "inventory": inventory,
        "topology_raw": topology,
        "p2p_read_raw": p2p_read,
        "p2p_write_raw": p2p_write,
        "p2p_nvlink_raw": p2p_nvlink,
        "binding": binding,
        "broker_status": sanitize_broker_status(broker),
        "broker_executable": str(BROKER_EXECUTABLE),
        "broker_sha256": _sha256_file(BROKER_EXECUTABLE),
        "broker_service": service,
        "python_executable": str(PYTHON),
        "python_resolved": str(PYTHON.resolve(strict=True)),
        "python_sha256": _sha256_file(PYTHON),
        "runtime_image": IMAGE,
        "runtime_image_id": image,
        "nvidia_container_runtime": runtime,
        "commands": ledger,
    }
    public = {
        "captured_at": private["captured_at"],
        "hostname": private["hostname"],
        "revision": revision,
        "gpu_rank_order": selected,
        "binding": binding,
        "broker_sha256": private["broker_sha256"],
        "broker_service": service,
        "python_resolved": private["python_resolved"],
        "python_sha256": private["python_sha256"],
        "runtime_image": IMAGE,
        "runtime_image_id": image,
        "nvidia_container_runtime": runtime,
        "broker_backend_available": broker.get("backend_available"),
    }
    return private, public


def _prepare_storage(attempt: Path, ledger: list[dict[str, Any]]) -> tuple[Path, list[Path]]:
    (attempt / "ledger").mkdir(mode=0o700)
    volumes = attempt / "volumes"
    volumes.mkdir(mode=0o700)
    mounts: list[Path] = []
    try:
        for kind, size in STORAGE_SIZES.items():
            path = volumes / kind
            path.mkdir(mode=0o700)
            if kind == "evidence":
                backing = attempt / "evidence.ext4"
                with backing.open("xb") as handle:
                    handle.truncate(size)
                _command(
                    ledger,
                    "evidence-mkfs",
                    _sudo(["mkfs.ext4", "-q", "-F", "-N", "16384", backing]),
                    timeout=120,
                )
                _command(
                    ledger,
                    "evidence-mount",
                    _sudo(["mount", "-o", "loop,nosuid,nodev", backing, path]),
                )
            else:
                _command(
                    ledger,
                    f"{kind}-mount",
                    _sudo(
                        [
                            "mount",
                            "-t",
                            "tmpfs",
                            "-o",
                            f"size={size},nr_inodes=65536,mode=0700",
                            f"matric183-{attempt.name}-{kind}",
                            path,
                        ]
                    ),
                )
            mounts.append(path)
            _command(
                ledger,
                f"{kind}-ownership",
                _sudo(["chown", f"{os.getuid()}:{os.getgid()}", path]),
            )
            path.chmod(0o700)
    except BaseException:
        for path in reversed(mounts):
            if os.path.ismount(path):
                subprocess.run(_sudo(["umount", path]), check=False, timeout=60)
        raise
    allocations = [
        {
            "kind": kind,
            "path": str(volumes / kind),
            "budget_bytes": size,
            "budget_inodes": 16384 if kind == "evidence" else 65536,
            "estimated_bytes": None,
            "disposable": kind in {"scratch", "temporary", "download_cache"},
        }
        for kind, size in STORAGE_SIZES.items()
    ]
    allocations.extend(
        [
            {
                "kind": "models",
                "path": str(MODEL_ROOT),
                "budget_bytes": 0,
                "budget_inodes": 0,
                "estimated_bytes": 0,
            },
            {
                "kind": "docker",
                "path": "/srv/obliteratus/matric-eval/docker/data",
                "budget_bytes": 256 * 2**20,
                "budget_inodes": 65536,
                "estimated_bytes": 64 * 2**20,
            },
        ]
    )
    storage = {
        "allocations": allocations,
        "ledger": str(attempt / "ledger"),
        "ownership": str(attempt),
        "headroom_bytes": 10 * 2**30,
        "headroom_inodes": 65536,
    }
    write_private_json(attempt / "storage.json", storage)
    return volumes / "evidence", mounts


def _preflight_plan(
    *,
    workspace: Path,
    revision: str,
    protocol: Path,
    attempt: Path,
    evidence: Path,
    gpus: tuple[str, str],
    port: int,
) -> Path:
    checker = workspace / "scripts/check_qwen38_tp2_preflight.py"
    common = [
        "--workspace",
        workspace,
        "--revision",
        revision,
        "--protocol",
        protocol,
        "--resource-directory",
        attempt / "resources",
        "--model-id",
        MODEL_ID,
        "--model-path",
        MODEL_PATH,
        "--qualification",
        QUALIFICATION,
        "--server-receipt",
        evidence / "server.json",
        "--port",
        str(port),
    ]
    for gpu in gpus:
        common.extend(["--gpu", gpu])
    inputs = [
        str(checker),
        str(protocol),
        str(QUALIFICATION),
        str(MODEL_PATH / "config.json"),
        str(MODEL_PATH / "model.safetensors.index.json"),
    ]
    checks = []
    for stage in ("static", "cpu", "auxiliary", "target"):
        checks.append(
            {
                "id": f"tp2-{stage}",
                "stage": stage,
                "command": [str(PYTHON), str(checker), stage, *(str(x) for x in common)],
                "inputs": inputs,
                "timeout_seconds": 900 if stage == "static" else 60,
                "freshness_seconds": 1800,
                "deterministic": False,
                "receipt_contract": {
                    "schema": "matric-eval.basilisk-tp2-preflight/1",
                    "stage": stage,
                    "passed": True,
                },
            }
        )
    path = attempt / "preflight-plan.json"
    write_private_json(path, {"schema": "matric-eval.study-preflight/1", "checks": checks})
    return path


def _stop_controller(record: dict[str, Any], signum: signal.Signals = signal.SIGTERM) -> None:
    identity = record.get("controller")
    if not isinstance(identity, dict) or type(identity.get("pid")) is not int:
        raise RuntimeError("resource record lacks an exact controller identity")
    pid = identity["pid"]
    try:
        descriptor = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        stat_fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        start_ticks = stat_fields[19]
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if start_ticks != identity.get("start_ticks") or boot_id != identity.get("boot_id"):
            raise RuntimeError("controller identity changed; refusing to signal it")
        signal.pidfd_send_signal(descriptor, signum)
    except (FileNotFoundError, ProcessLookupError):
        pass
    finally:
        os.close(descriptor)


def _wait_state(
    process: subprocess.Popen[Any], record_path: Path, wanted: str, timeout: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    transitions: list[dict[str, Any]] = []
    previous: object = object()
    record: dict[str, Any] = {}
    while time.monotonic() < deadline:
        if record_path.exists():
            record = _load_object(record_path)
            state = record.get("state")
            if state != previous:
                transitions.append({"state": state, "observed_at": time.time()})
                previous = state
            if state == wanted:
                return record, transitions
        if process.poll() is not None:
            raise RuntimeError(f"controller exited before {wanted} with {process.returncode}")
        time.sleep(0.5)
    if record.get("controller"):
        _stop_controller(record)
    raise TimeoutError(f"controller did not reach {wanted} before the deadline")


def _verify_cleanup(
    attempt: Path,
    owner: str,
    process: subprocess.Popen[Any],
    ledger: list[dict[str, Any]],
    timeout: int = 180,
) -> dict[str, Any]:
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        record = _load_object(attempt / "resources/record.json")
        _stop_controller(record, signal.SIGKILL)
        process.wait(timeout=30)
        raise RuntimeError("controller did not finish cleanup before the deadline") from error
    record = _load_object(attempt / "resources/record.json")
    if (
        record.get("cleanup") != "complete"
        or record.get("storage_reservation_active") is not False
        or record.get("surviving_cuda_allocations") not in (None, [])
    ):
        raise RuntimeError("resource lifecycle did not establish complete atomic cleanup")
    status = Broker(BROKER_SOCKET).call("status")
    if any(
        isinstance(lease, dict) and lease.get("owner") == owner
        for lease in status.get("leases", [])
    ):
        raise RuntimeError("owned GPU lease remains after cleanup")
    containers = _command(
        ledger,
        "verify-container-absent",
        _sudo(
            [
                "docker",
                "--host",
                DOCKER_HOST,
                "container",
                "ls",
                "-a",
                "--format",
                "{{.Names}}",
            ]
        ),
    ).stdout.splitlines()
    if record.get("container") in containers:
        raise RuntimeError("owned container remains after cleanup")
    owned_pids = set(record.get("cuda_pids", []))
    cuda = _command(
        ledger,
        "verify-cuda-absent",
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid",
            "--format=csv,noheader,nounits",
        ],
    ).stdout.splitlines()
    surviving_pids = {
        int(row.rsplit(",", 1)[1].strip()) for row in cuda if row.strip() and "," in row
    }
    if owned_pids & surviving_pids:
        raise RuntimeError("owned CUDA process remains after cleanup")
    return {
        "wrapper_exit": process.returncode,
        "resource_state": record.get("state"),
        "cleanup": record.get("cleanup"),
        "storage_reservation_active": record.get("storage_reservation_active"),
        "owned_lease_absent": True,
        "owned_container_absent": True,
        "owned_cuda_absent": True,
        "resource_record_sha256": _sha256_file(attempt / "resources/record.json"),
    }


def _unmount_storage(attempt: Path, mounts: list[Path], ledger: list[dict[str, Any]]) -> None:
    for path in reversed(mounts):
        if os.path.ismount(path):
            _command(ledger, f"unmount-{path.name}", _sudo(["umount", path]), timeout=60)
    volumes = attempt / "volumes"
    for path in reversed(mounts):
        if path.exists() and not path.is_symlink():
            path.rmdir()
    if volumes.exists() and not volumes.is_symlink():
        volumes.rmdir()


def _run_attempt(
    *,
    kind: str,
    workspace: Path,
    revision: str,
    protocol: Path,
    manifest: Path,
    summary: Path,
    gpus: tuple[str, str],
    root: Path,
    port: int,
) -> dict[str, Any]:
    attempt = root / kind
    attempt.mkdir(mode=0o700)
    ledger: list[dict[str, Any]] = []
    mounts: list[Path] = []
    process: subprocess.Popen[Any] | None = None
    log_path = attempt / "controller.log"
    evidence: Path | None = None
    owner = f"matric-issue183-{root.name}-{kind}"
    transitions: list[dict[str, Any]] = []
    result: dict[str, Any] = {"kind": kind, "started_at": time.time()}
    failure: BaseException | None = None
    try:
        evidence, mounts = _prepare_storage(attempt, ledger)
        plan = _preflight_plan(
            workspace=workspace,
            revision=revision,
            protocol=protocol,
            attempt=attempt,
            evidence=evidence,
            gpus=gpus,
            port=port,
        )
        command = [
            "bash",
            workspace / "scripts/serve_qwen38_container.sh",
            "--broker-acquire-timeout",
            "300",
            "--run-id",
            "issue183-tp2-qualification",
            "--attempt-id",
            f"{root.name}-{kind}",
            "--resource-directory",
            attempt / "resources",
            "--preflight-plan",
            plan,
            "--storage-plan",
            attempt / "storage.json",
            "--parallelism-profile",
            "a100-80gb-pcie-tp2/1",
            "--protocol",
            protocol,
            "--owner",
            owner,
            "--model-id",
            MODEL_ID,
            "--model-path",
            MODEL_PATH,
            "--qualification",
            QUALIFICATION,
            "--lease-receipt",
            evidence / "lease.private.json",
            "--server-receipt",
            evidence / "server.json",
            "--ready-base",
            attempt / "ready",
            "--container-name",
            f"matric-issue183-{kind}-{os.getpid()}",
            "--port",
            str(port),
        ]
        for gpu in gpus:
            insertion = command.index("--parallelism-profile")
            command[insertion:insertion] = ["--gpu", gpu]
        ledger.append(
            {
                "name": "server-controller",
                "argv": [str(value) for value in command],
                "started_at": time.time(),
                "exit_code": None,
            }
        )
        log = log_path.open("xb")
        process = subprocess.Popen(
            [str(value) for value in command],
            cwd=workspace,
            env={
                **os.environ,
                "MATRIC_LIFECYCLE_PYTHON": str(PYTHON),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            record, transitions = _wait_state(
                process, attempt / "resources/record.json", "ready", 1200
            )
            canary = content_free_inference_canary(f"http://127.0.0.1:{port}/v1", MODEL_ID)
            result["content_free_inference"] = canary
            if kind == "success":
                tau_receipt = evidence / "tau-receipt.private.json"
                tau_command: list[str | Path] = [
                    TAU / ".venv/bin/python",
                    workspace / "scripts/run_qwen38_tau.py",
                    protocol,
                    manifest,
                    "--model-id",
                    MODEL_ID,
                    "--model-path",
                    MODEL_PATH,
                    "--server-receipt",
                    evidence / "server.json",
                    "--endpoint",
                    f"http://127.0.0.1:{port}/v1",
                    "--tau-checkout",
                    TAU,
                    "--chat-template",
                    CHAT_TEMPLATE,
                    "--inputs-summary",
                    summary,
                    "--scored-ids",
                    SCORED_IDS,
                    "--local-simulator",
                    "--user-model",
                    "ollama_chat/matric-eval-tau-simulator:2026-09-07",
                    "--nl-evaluator-model",
                    "ollama_chat/matric-eval-tau-simulator:2026-09-07",
                ]
                for diagnostic_id in TAU_DIAGNOSTIC_IDS:
                    tau_command.extend(["--diagnostic-id", diagnostic_id])
                tau_command.extend(
                    [
                        "--result-dir",
                        evidence / "tau-raw",
                        "--receipt",
                        tau_receipt,
                    ]
                )
                tau_log = evidence / "tau.log"
                tau_exit: int | None = None
                tau_failure: str | None = None
                with tau_log.open("xb") as output:
                    started = time.time()
                    try:
                        tau = subprocess.run(
                            [str(value) for value in tau_command],
                            cwd=workspace,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                            stdout=output,
                            stderr=subprocess.STDOUT,
                            timeout=7200,
                        )
                        tau_exit = tau.returncode
                    except (OSError, subprocess.TimeoutExpired) as error:
                        tau_failure = type(error).__name__
                ledger.append(
                    {
                        "name": "tau-diagnostic",
                        "argv": [str(value) for value in tau_command],
                        "started_at": started,
                        "completed_at": time.time(),
                        "exit_code": tau_exit,
                        "failure_type": tau_failure,
                    }
                )
                if tau_exit == 0 and tau_receipt.is_file():
                    result["tau_diagnostic"] = {
                        "status": "parsed",
                        **validate_tau_diagnostic_receipt(_load_object(tau_receipt), MODEL_ID),
                        "private_receipt_sha256": _sha256_file(tau_receipt),
                    }
                else:
                    result["tau_diagnostic"] = {
                        "status": "typed-blocker",
                        "failure_type": tau_failure or "TauDiagnosticExecutionFailed",
                        "exit_code": tau_exit,
                        "log_sha256": _sha256_file(tau_log),
                        "model_score_assigned": False,
                        "raw_content_retained": False,
                    }
                _stop_controller(record)
            else:
                container = str(record["container"])
                container_id = str(record["container_id"])
                injected = _command(
                    ledger,
                    "inject-container-stop",
                    _sudo(
                        [
                            "docker",
                            "--host",
                            DOCKER_HOST,
                            "stop",
                            "--time",
                            "10",
                            container_id,
                        ]
                    ),
                    timeout=30,
                )
                if injected.stdout.strip() not in {container, container_id}:
                    raise RuntimeError(
                        "Docker did not acknowledge the exact injected-failure target"
                    )
                result["injected_failure"] = {
                    "kind": "owned-container-stop-after-content-free-inference",
                    "container_id": container_id,
                    "exit_code": injected.returncode,
                }
            cleanup = _verify_cleanup(attempt, owner, process, ledger)
            result["cleanup"] = cleanup
        finally:
            log.close()
        result.update(
            {
                "state_transitions": transitions,
                "commands": ledger,
                "completed_at": time.time(),
                "passed": True,
            }
        )
    except BaseException as error:
        failure = error
        result.update(
            {
                "state_transitions": transitions,
                "commands": ledger,
                "completed_at": time.time(),
                "passed": False,
                "failure_type": type(error).__name__,
                "failure": str(error)[:500],
            }
        )
        if process is not None and process.poll() is None:
            record_path = attempt / "resources/record.json"
            if record_path.exists():
                try:
                    _stop_controller(_load_object(record_path))
                except (OSError, ValueError, RuntimeError):
                    pass
            else:
                process.terminate()
        if process is not None:
            try:
                process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=30)
    finally:
        if process is not None:
            for row in ledger:
                if row.get("name") == "server-controller":
                    row["completed_at"] = time.time()
                    row["exit_code"] = process.returncode
        if evidence is not None and evidence.is_dir() and os.path.ismount(evidence):
            if log_path.is_file() and not (evidence / "controller.log").exists():
                shutil.copyfile(log_path, evidence / "controller.log")
                (evidence / "controller.log").chmod(0o600)
            if not (evidence / "attempt-summary.json").exists():
                write_private_json(evidence / "attempt-summary.json", result)
        if mounts:
            _unmount_storage(attempt, mounts, ledger)
            result["mounts_absent"] = all(not os.path.ismount(path) for path in mounts)
            result["temporary_storage_absent"] = not (attempt / "volumes").exists()
        if not (attempt / "command-ledger.json").exists():
            write_private_json(attempt / "command-ledger.json", {"commands": ledger})
        if not (attempt / "public-attempt.json").exists():
            public: dict[str, Any] = {
                key: result[key]
                for key in (
                    "kind",
                    "started_at",
                    "completed_at",
                    "passed",
                    "content_free_inference",
                    "tau_diagnostic",
                    "injected_failure",
                    "cleanup",
                    "mounts_absent",
                    "temporary_storage_absent",
                    "state_transitions",
                    "failure_type",
                    "failure",
                )
                if key in result
            }
            write_private_json(attempt / "public-attempt.json", public)
    if failure is not None:
        raise failure
    return _load_object(attempt / "public-attempt.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--revision")
    parser.add_argument("--gpu", action="append", required=True)
    parser.add_argument("--wait-seconds", type=int, default=3600)
    parser.add_argument("--port", type=int, default=18093)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workspace = args.workspace.resolve()
    if platform.node() != "basilisk":
        raise RuntimeError("TP2 hardware qualification requires host basilisk")
    if len(args.gpu) != 2 or len(set(args.gpu)) != 2:
        raise ValueError("repeat --gpu with exactly two distinct UUIDs in rank order")
    if not 1024 <= args.port <= 65534:
        raise ValueError("port must leave room for the second qualification attempt")
    if _git(workspace, "status", "--porcelain"):
        raise RuntimeError("qualification checkout must be clean")
    revision = args.revision or _git(workspace, "rev-parse", "HEAD")
    if _git(workspace, "rev-parse", "HEAD") != revision or len(revision) != 40:
        raise RuntimeError("qualification checkout does not match the exact requested revision")
    source_protocol = workspace / SOURCE_PROTOCOL
    for required in (
        source_protocol,
        SOURCE_MANIFEST,
        SOURCE_SUMMARY,
        SCORED_IDS,
        QUALIFICATION,
        CHAT_TEMPLATE,
        MODEL_PATH,
        BROKER_EXECUTABLE,
    ):
        if not required.exists() or required.is_symlink():
            raise RuntimeError(f"required qualification input is unavailable: {required}")
    # Virtual environments conventionally expose their interpreter through a
    # symlink. Resolve and attest its regular executable target instead of
    # rejecting a healthy venv before any hardware resources are acquired.
    _require_resolved_executable(PYTHON)

    root = STUDY / "run-control" / f"issue183-tp2-{time.time_ns()}"
    root.mkdir(mode=0o700)
    ledger: list[dict[str, Any]] = []
    protocol = root / "protocol-tp2.private.json"
    manifest = root / "pilot-manifest-tp2.private.json"
    summary = root / "agentic-inputs-summary-tp2.private.json"
    protocol_overlay = build_tp2_protocol_overlay(source_protocol, protocol)
    inputs_overlay = build_tp2_agentic_inputs_overlay(
        protocol=protocol,
        source_manifest=SOURCE_MANIFEST,
        source_summary=SOURCE_SUMMARY,
        output_manifest=manifest,
        output_summary=summary,
    )
    private_host, public_host = _host_evidence(
        workspace,
        revision,
        tuple(args.gpu),
        args.wait_seconds,
        ledger,
    )
    write_private_json(root / "host.private.json", private_host)
    attempts = [
        _run_attempt(
            kind="success",
            workspace=workspace,
            revision=revision,
            protocol=protocol,
            manifest=manifest,
            summary=summary,
            gpus=tuple(args.gpu),
            root=root,
            port=args.port,
        ),
        _run_attempt(
            kind="injected-failure",
            workspace=workspace,
            revision=revision,
            protocol=protocol,
            manifest=manifest,
            summary=summary,
            gpus=tuple(args.gpu),
            root=root,
            port=args.port + 1,
        ),
    ]
    receipt = {
        "schema": QUALIFICATION_SCHEMA,
        "issue": 183,
        "qualification_root": str(root),
        "source_revision": revision,
        "source_clean": True,
        "host": public_host,
        "protocol_overlay": {
            key: protocol_overlay[key]
            for key in (
                "source_file_sha256",
                "source_protocol_sha256",
                "overlay_file_sha256",
                "overlay_protocol_sha256",
                "changed_paths",
                "profile",
            )
        },
        "agentic_inputs_overlay": {
            key: inputs_overlay[key]
            for key in (
                "source_manifest_sha256",
                "source_summary_sha256",
                "protocol_sha256",
                "manifest_sha256",
                "manifest_file_sha256",
                "summary_file_sha256",
                "changed_paths",
            )
        },
        "attempts": attempts,
        "public_receipt_contains_raw_prompts_or_outputs": False,
        "public_receipt_contains_lease_credentials": False,
        "passed": all(attempt.get("passed") for attempt in attempts),
        "completed_at": time.time(),
    }
    public_path = root / "public-receipt.json"
    write_private_json(public_path, receipt)
    print(json.dumps({"public_receipt": str(public_path), "passed": receipt["passed"]}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
