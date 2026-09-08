#!/usr/bin/env python3
"""Supervise a fresh, bounded diagnostic replay without replacing prior evidence."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
OUT = STUDY / "replay-20260908"
TAU = Path("/srv/matric-eval/benchmarks/tau2-qwen38-simulator-guard-v3")
HARBOR = Path("/srv/matric-eval/benchmarks/harbor-qwen38-terminal-runtime-guard")
TERMINAL = Path("/srv/matric-eval/benchmarks/terminal-bench-2-1-5c8eadf1")
GPU = "GPU-170a99ee-850f-2182-1050-4e8d3c87b6b0"
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


def main():
    os.umask(0o077)

    def terminate(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    OUT.mkdir(mode=0o750, exist_ok=True)
    if (OUT / "status.json").exists():
        raise RuntimeError("Refusing to reuse an existing replay")
    (OUT / "canaries").mkdir(mode=0o750, exist_ok=True)
    (OUT / "tmp").mkdir(mode=0o750, exist_ok=True)
    os.environ.update(
        PYTHONDONTWRITEBYTECODE="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
        TOKENIZERS_PARALLELISM="false",
        TMPDIR=str(OUT / "tmp"),
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
                "gpu": GPU,
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
        "known_limit": "Full calibration-v2 semantic/termination gates are not certified by this diagnostic replay.",
    }
    (OUT / "execution-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    save(revision=revision, status="validating")
    unit = None
    try:
        check_space()
        for rep in range(1, 4):
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
        for entry in schedule:
            check_space()
            prefix = entry["prefix"]
            unit = f"matric-eval-replay-20260908-{prefix}"
            receipt = OUT / f"{prefix}-server.json"
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
                    "--gpu",
                    GPU,
                    "--owner",
                    unit,
                    "--model-id",
                    entry["model_id"],
                    "--model-path",
                    entry["model_path"],
                    "--qualification",
                    STUDY / f"{prefix}-model-qualification.json",
                    "--lease-receipt",
                    OUT / f"{prefix}-lease.json",
                    "--server-receipt",
                    receipt,
                    "--ready-base",
                    STUDY / f"run-control/replay-20260908-{prefix}",
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
                PROTOCOL,
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
            subprocess.run(["sudo", "-n", "systemctl", "stop", unit], check=True, timeout=150)
            unit = None
        save(status="complete", model=None)
    except BaseException as error:
        save(status="failed", error=str(error), error_type=type(error).__name__)
        raise
    finally:
        if unit:
            subprocess.run(["sudo", "-n", "systemctl", "stop", unit], timeout=150)


if __name__ == "__main__":
    main()
