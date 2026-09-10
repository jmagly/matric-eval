#!/usr/bin/env python3
"""Supervise a fresh, bounded diagnostic replay without replacing prior evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import time
import urllib.request
from pathlib import Path

from qwen38_tau_sandbox import sandbox_socket_path_evidence

from matric_eval.studies import StudyProtocol
from matric_eval.studies.wrapper import WrapperGpuContract, resolve_wrapper_gpu_contract

ROOT = Path(__file__).resolve().parents[1]
STUDY = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
OUT = STUDY / "replay-20260909-r7"
RUNTIME_TMP_ROOT = Path("/srv/matric-eval/runtime-tmp")
RUNTIME_TMP = RUNTIME_TMP_ROOT / OUT.name
ADMISSION_IDS = ("banking_knowledge:task_021", "airline:3")
ADMISSION_RECEIPT = STUDY / "tau-admission-20260909/source-tau-receipt.json"
TAU = Path("/srv/matric-eval/benchmarks/tau2-qwen38-simulator-guard-v3")
HARBOR = Path("/srv/matric-eval/benchmarks/harbor-qwen38-terminal-runtime-guard")
TERMINAL = Path("/srv/matric-eval/benchmarks/terminal-bench-2-1-5c8eadf1")
DEFAULT_GPU_UUIDS = ("GPU-170a99ee-850f-2182-1050-4e8d3c87b6b0",)
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
STATUS: dict = {"status": "preflight", "operations": []}


def save(**fields):
    STATUS.update(fields, updated_at=time.time())
    temporary = OUT / "status.tmp"
    temporary.write_text(json.dumps(STATUS, indent=2) + "\n")
    temporary.replace(OUT / "status.json")
    print(json.dumps(fields), flush=True)


def execute(name, command, timeout):
    save(phase=name)
    if name.startswith(
        ("tau-interface-canary-", "tau-context-canary-", "terminal-runtime-canary-")
    ):
        receipt = STUDY / "replay-20260908-r2/canaries" / Path(command[-1]).name
        data = json.loads(receipt.read_text())
        if data.get("status") != "passed" or not data.get("source_sha256"):
            raise RuntimeError("Prior runner validation did not pass")
        unchanged = all(
            hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == digest
            for source, digest in data["source_sha256"].items()
        )
        if unchanged:
            STATUS["operations"].append(
                {
                    "name": name,
                    "exit_code": 0,
                    "reused_receipt": str(receipt),
                    "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                }
            )
            save()
            return
    with (OUT / (name + ".log")).open("xb") as log:
        process = subprocess.Popen(
            [str(x) for x in command],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    STATUS["operations"].append({"name": name, "exit_code": code})
    save()
    if code:
        raise RuntimeError(f"{name} failed with exit {code}; see its retained log")


def check_space():
    for path, floor in (("/", 40), ("/srv", 40)):
        st = os.statvfs(path)
        if st.f_bavail * st.f_frsize < floor * 1024**3:
            raise RuntimeError(f"Free space below {floor} GiB at {path}")


def prepare_runtime_tmp():
    """Create a private short path whose SRT bridge sockets fit Linux ``sun_path``."""
    RUNTIME_TMP_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    root_stat = RUNTIME_TMP_ROOT.stat()
    if root_stat.st_uid != os.getuid() or stat.S_IMODE(root_stat.st_mode) != 0o700:
        raise RuntimeError("runtime temporary root must be private and owned by the runner")
    if RUNTIME_TMP.exists() or RUNTIME_TMP.is_symlink():
        raise RuntimeError("refusing to reuse a replay runtime temporary directory")
    evidence = sandbox_socket_path_evidence(RUNTIME_TMP)
    RUNTIME_TMP.mkdir(mode=0o700)
    return evidence


def cleanup_runtime_tmp():
    """Remove only this replay's verified private runtime directory."""
    if not RUNTIME_TMP.exists() and not RUNTIME_TMP.is_symlink():
        return
    if RUNTIME_TMP.is_symlink() or RUNTIME_TMP.parent.resolve() != RUNTIME_TMP_ROOT.resolve():
        raise RuntimeError("refusing unsafe replay runtime temporary cleanup")
    shutil.rmtree(RUNTIME_TMP)


def validate_admission_receipt(expected_model_id):
    """Require two valid bounded trajectories before scheduling the paired replay."""
    if ADMISSION_RECEIPT.is_symlink() or not ADMISSION_RECEIPT.is_file():
        raise RuntimeError("reviewed Tau admission receipt is missing")
    payload = json.loads(ADMISSION_RECEIPT.read_text())
    if not isinstance(payload, dict):
        raise RuntimeError("Tau admission receipt must contain an object")
    execution = payload.get("execution")
    scope = execution.get("scope") if isinstance(execution, dict) else None
    results = payload.get("scored_results") if isinstance(payload, dict) else None
    if (
        payload.get("model_id") != expected_model_id
        or payload.get("scored_samples") != len(ADMISSION_IDS)
        or payload.get("analytic_status_counts") != {"valid": len(ADMISSION_IDS)}
        or not isinstance(scope, dict)
        or scope.get("kind") != "diagnostic-subset"
        or scope.get("official_comparison") is not False
        or scope.get("selected_ids") != list(ADMISSION_IDS)
        or not isinstance(results, list)
        or [row.get("canonical_id") for row in results if isinstance(row, dict)]
        != list(ADMISSION_IDS)
        or any(
            not isinstance(row, dict)
            or row.get("analytic_status") != "valid"
            or not isinstance(row.get("raw_result_sha256"), str)
            or len(row["raw_result_sha256"]) != 64
            or not set(row["raw_result_sha256"]) <= set("0123456789abcdef")
            for row in results
        )
    ):
        raise RuntimeError("Tau admission receipt does not prove two valid trajectories")
    return {
        "receipt_sha256": hashlib.sha256(ADMISSION_RECEIPT.read_bytes()).hexdigest(),
        "model_id": expected_model_id,
        "selected_ids": list(ADMISSION_IDS),
        "valid_trajectories": len(ADMISSION_IDS),
    }


def load_launch_contract(prefix):
    """Require a fresh bounded-storage and preflight contract for one model load."""
    attempt = STUDY / "run-control" / f"{OUT.name}-{prefix}"
    storage_plan = attempt / "storage.json"
    preflight_plan = attempt / "preflight-plan.json"
    evidence = attempt / "volumes" / "evidence"
    for path in (storage_plan, preflight_plan):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"reviewed {prefix} launch contract is missing")
    storage = json.loads(storage_plan.read_text())
    allocations = storage.get("allocations") if isinstance(storage, dict) else None
    if not isinstance(allocations, list):
        raise RuntimeError(f"reviewed {prefix} storage plan is malformed")
    declared_evidence = [
        row.get("path")
        for row in allocations
        if isinstance(row, dict) and row.get("kind") == "evidence"
    ]
    if declared_evidence != [str(evidence)]:
        raise RuntimeError(f"reviewed {prefix} evidence allocation does not match")
    if not evidence.is_dir() or evidence.is_symlink():
        raise RuntimeError(f"reviewed {prefix} evidence allocation is unavailable")
    return {
        "attempt": attempt,
        "storage_plan": storage_plan,
        "preflight_plan": preflight_plan,
        "resource_directory": attempt / "resources",
        "lease_receipt": evidence / "lease.private.json",
        "server_receipt": evidence / "server.json",
    }


def replay_gpu_contract(
    gpu_uuids: list[str] | None = None,
    *,
    parallelism_profile: str | None = None,
    protocol: Path = PROTOCOL,
) -> WrapperGpuContract:
    return resolve_wrapper_gpu_contract(
        StudyProtocol.from_yaml(protocol),
        gpu_uuids or DEFAULT_GPU_UUIDS,
        parallelism_profile=parallelism_profile,
    )


def stop_server(unit, gpu_uuids):
    subprocess.run(["sudo", "-n", "systemctl", "stop", unit], check=True, timeout=150)
    containers = subprocess.check_output(
        [
            "sudo",
            "-n",
            "docker",
            "--host",
            "unix:///run/matric-eval-docker.sock",
            "ps",
            "-a",
            "--format",
            "{{.Names}}",
        ],
        text=True,
    ).splitlines()
    if unit in containers:
        raise RuntimeError("Run container remains; refusing to release its GPU lease")
    leases = json.loads(
        subprocess.check_output(["sudo", "-n", "docker", "gpu", "status"], text=True)
    )["leases"]
    for lease in leases:
        if lease.get("owner") != unit:
            continue
        if lease.get("gpu_uuids") != list(gpu_uuids):
            raise RuntimeError("Run GPU lease allocation changed; refusing partial release")
        result = subprocess.run(
            ["sudo", "-n", "docker", "gpu", "release", lease["token"]],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError("Run GPU lease release failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--gpu", action="append")
    parser.add_argument("--parallelism-profile")
    args = parser.parse_args(argv)
    protocol = args.protocol.resolve()
    gpu_contract = replay_gpu_contract(
        args.gpu,
        parallelism_profile=args.parallelism_profile,
        protocol=protocol,
    )
    gpu_uuids = gpu_contract.binding.allocation.gpu_uuids
    profile_id = gpu_contract.binding.profile.id
    wrapper_gpu_arguments = []
    for gpu_uuid in gpu_uuids:
        wrapper_gpu_arguments.extend(["--gpu", gpu_uuid])

    os.umask(0o077)

    def terminate(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    OUT.mkdir(mode=0o750, exist_ok=True)
    if (OUT / "status.json").exists():
        raise RuntimeError("Refusing to reuse an existing replay")
    (OUT / "canaries").mkdir(mode=0o750, exist_ok=True)
    runtime_tmp_evidence = sandbox_socket_path_evidence(RUNTIME_TMP)
    os.environ.update(
        PYTHONDONTWRITEBYTECODE="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
        TOKENIZERS_PARALLELISM="false",
        TMPDIR=str(RUNTIME_TMP),
        PYTHONPATH=str(ROOT / "src") + ":" + str(ROOT / "scripts"),
        TAU2_DATA_DIR=str(TAU / "data"),
        DOCKER_HOST="unix:///run/matric-eval-docker.sock",
    )
    os.environ.pop("OPENAI_API_KEY", None)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise RuntimeError("Replay code is not sealed")
    schedule = []
    for prefix in ("source", "e03", "pliny"):
        old = json.loads((STUDY / (prefix + "-tau-local-server.json")).read_text())
        schedule.append(
            {
                "prefix": prefix,
                "model_id": old["model_id"],
                "model_path": old["runtime"]["arguments"][0],
                "gpu_uuids": list(gpu_uuids),
                "parallelism_profile": profile_id,
            }
        )
    plan = {
        "revision": revision,
        "schedule": schedule,
        "kind": "paired-diagnostic-replay",
        "scope": {"tau_per_model": 10, "terminal_per_model": 5},
        "manifest_sha256": hashlib.sha256((STUDY / "pilot-manifest.json").read_bytes()).hexdigest(),
        "calibration_stage_release": False,
        "started_at": time.time(),
        "terminal_controls": {
            "watchdog_seconds": 5400,
            "llm_response_timeout_seconds": 180,
            "max_turns": 200,
            "official_task_budgets": "unchanged",
        },
        "tau_local": {"target_max_tokens": 4096, "native_broker_thinking": False},
        "runtime_tmp": {
            "strategy": "short-private-attempt-directory",
            **runtime_tmp_evidence,
        },
        "admission": {
            "required_before_gpu_allocation": True,
            "selected_ids": list(ADMISSION_IDS),
            "official_comparison": False,
        },
        "known_limit": "Full calibration-v2 semantic/termination gates are not certified by this diagnostic replay.",
    }
    (OUT / "execution-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    save(revision=revision, status="validating")
    unit = None
    try:
        if prepare_runtime_tmp() != runtime_tmp_evidence:
            raise RuntimeError("runtime temporary path evidence changed after validation")
        check_space()
        for rep in range(1, 4):
            execute(
                f"tau-sandbox-canary-{rep}",
                [
                    TAU / ".venv/bin/python",
                    ROOT / "scripts/qwen38_tau_sandbox.py",
                    "--receipt",
                    OUT / f"canaries/tau-sandbox-{rep}.json",
                ],
                180,
            )
            execute(
                f"tau-interface-canary-{rep}",
                [
                    TAU / ".venv/bin/python",
                    ROOT / "scripts/canary_qwen38_tau_simulator.py",
                    "--tau-checkout",
                    TAU,
                    "--output",
                    OUT / f"canaries/tau-interface-{rep}.json",
                ],
                300,
            )
            execute(
                f"tau-context-canary-{rep}",
                [
                    TAU / ".venv/bin/python",
                    ROOT / "scripts/canary_qwen38_tau_context.py",
                    "--tau-checkout",
                    TAU,
                    "--model-path",
                    schedule[0]["model_path"],
                    "--chat-template",
                    STUDY / "chat_template.jinja",
                    "--server-receipt",
                    STUDY / "source-tau-local-server.json",
                    "--output",
                    OUT / f"canaries/tau-context-{rep}.json",
                ],
                300,
            )
            execute(
                f"terminal-runtime-canary-{rep}",
                [
                    HARBOR / ".venv/bin/python",
                    ROOT / "scripts/canary_qwen38_terminal_runtime.py",
                    "--harbor-checkout",
                    HARBOR,
                    "--docker-host",
                    "unix:///run/matric-eval-docker.sock",
                    "--output",
                    OUT / f"canaries/terminal-runtime-{rep}.json",
                ],
                600,
            )
        execute(
            "local-simulator-canary",
            [
                TAU / ".venv/bin/python",
                ROOT / "scripts/canary_qwen38_tau_local.py",
                "--output",
                OUT / "canaries/local-simulator.json",
            ],
            600,
        )
        admission = validate_admission_receipt(schedule[0]["model_id"])
        STATUS["operations"].append(
            {"name": "source-tau-admission-receipt", "exit_code": 0, **admission}
        )
        save(admission=admission)
        for entry in schedule:
            check_space()
            prefix = entry["prefix"]
            unit = f"matric-eval-{OUT.name}-{prefix}"
            launch = load_launch_contract(prefix)
            receipt = launch["server_receipt"]
            execute(
                f"{prefix}-server-launch",
                [
                    "sudo",
                    "-n",
                    "systemd-run",
                    "--unit",
                    unit,
                    "--uid=roctinam",
                    f"--working-directory={ROOT}",
                    "--property=RuntimeMaxSec=10h",
                    "--property=TimeoutStopSec=120",
                    "--property=KillMode=control-group",
                    "--property=LimitFSIZE=536870912",
                    "--setenv=PYTHONDONTWRITEBYTECODE=1",
                    "/bin/bash",
                    ROOT / "scripts/serve_qwen38_container.sh",
                    "--run-id",
                    OUT.name,
                    "--attempt-id",
                    launch["attempt"].name,
                    "--resource-directory",
                    launch["resource_directory"],
                    "--preflight-plan",
                    launch["preflight_plan"],
                    "--storage-plan",
                    launch["storage_plan"],
                    *wrapper_gpu_arguments,
                    "--parallelism-profile",
                    profile_id,
                    "--owner",
                    unit,
                    "--model-id",
                    entry["model_id"],
                    "--model-path",
                    entry["model_path"],
                    "--qualification",
                    STUDY / f"{prefix}-model-qualification.json",
                    "--lease-receipt",
                    launch["lease_receipt"],
                    "--server-receipt",
                    receipt,
                    "--ready-base",
                    STUDY / f"run-control/{OUT.name}-{prefix}",
                    "--container-name",
                    unit,
                ],
                60,
            )
            save(status="loading", model=prefix)
            deadline = time.monotonic() + 1000
            while time.monotonic() < deadline:
                active = subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0
                if not active:
                    raise RuntimeError(f"{unit} stopped during model loading")
                if receipt.exists():
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:18083/health", timeout=5
                        ) as response:
                            if response.status == 200:
                                break
                    except Exception:
                        pass
                time.sleep(5)
            else:
                raise RuntimeError("Model readiness timed out")
            common = [
                protocol,
                STUDY / "pilot-manifest.json",
                "--model-id",
                entry["model_id"],
                "--model-path",
                entry["model_path"],
                "--server-receipt",
                receipt,
                "--inputs-summary",
                STUDY / "pilot-agentic-inputs/agentic-inputs-summary.json",
            ]
            save(status="running", model=prefix)
            execute(
                f"{prefix}-tau",
                [
                    TAU / ".venv/bin/python",
                    ROOT / "scripts/run_qwen38_tau.py",
                    *common,
                    "--tau-checkout",
                    TAU,
                    "--chat-template",
                    STUDY / "chat_template.jinja",
                    "--scored-ids",
                    STUDY / "pilot-agentic-inputs/tau3-scored-ids.json",
                    "--local-simulator",
                    "--user-model",
                    "ollama_chat/matric-eval-tau-simulator:2026-09-07",
                    "--nl-evaluator-model",
                    "ollama_chat/matric-eval-tau-simulator:2026-09-07",
                    "--result-dir",
                    OUT / f"{prefix}-tau-raw",
                    "--receipt",
                    OUT / f"{prefix}-tau-receipt.json",
                ],
                7200,
            )
            execute(
                f"{prefix}-terminal",
                [
                    HARBOR / ".venv/bin/python",
                    ROOT / "scripts/run_qwen38_terminal.py",
                    *common,
                    "--terminal-checkout",
                    TERMINAL,
                    "--harbor-checkout",
                    HARBOR,
                    "--harbor-python",
                    HARBOR / ".venv/bin/python",
                    "--harbor-executable",
                    HARBOR / ".venv/bin/harbor",
                    "--scored-ids",
                    STUDY / "pilot-agentic-inputs/terminal-bench-scored-ids.json",
                    "--result-dir",
                    OUT / f"{prefix}-terminal-raw",
                    "--receipt",
                    OUT / f"{prefix}-terminal-receipt.json",
                    "--watchdog-seconds",
                    "5400",
                    "--llm-response-timeout-seconds",
                    "180",
                    "--max-turns",
                    "200",
                ],
                29000,
            )
            stop_server(unit, gpu_uuids)
            unit = None
        save(status="complete", model=None)
    except BaseException as error:
        save(status="failed", error=str(error), error_type=type(error).__name__)
        raise
    finally:
        try:
            if unit:
                stop_server(unit, gpu_uuids)
        finally:
            cleanup_runtime_tmp()


if __name__ == "__main__":
    main()
