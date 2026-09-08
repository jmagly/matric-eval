"""Scoped on-host broker identity; never an executed-weight attestation."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

PUBLIC = "http://127.0.0.1:11434"
UNIT = "ollama-unify-negotiator.service"
SOURCE = Path("/usr/local/libexec/ollama-unify-gpu-negotiator")
CONFIGURATION = (
    Path("/etc/default/ollama-unify-negotiator"),
    Path("/etc/default/ollama-unify-obliteratus"),
)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def capture_local_broker() -> dict[str, Any]:
    """Bind current systemd process, broker source and loaded configuration inputs.

    Configuration contents and environment values are hashed in memory only.
    Files changed since process startup cannot attest that running process.
    """
    properties = subprocess.check_output(
        [
            "systemctl",
            "show",
            UNIT,
            "--no-pager",
            "--property=MainPID,FragmentPath,DropInPaths,EnvironmentFiles,Environment,ExecStart",
        ],
        timeout=10,
        text=True,
    )
    fields: dict[str, str] = {}
    for line in properties.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = (fields.get(key, "") + " " + value).strip()
    pid = int(fields["MainPID"])
    if pid <= 0:
        raise ValueError("broker process absent")
    process = Path(f"/proc/{pid}")
    stat_before = (process / "stat").read_text().rsplit(")", 1)[1].split()
    command = (process / "cmdline").read_bytes().split(b"\0")
    if str(SOURCE).encode() not in command or b"serve" not in command:
        raise ValueError("broker process command mismatch")
    if stat_before[0] == "Z":
        raise ValueError("broker process exited")
    boot_epoch = int(
        next(
            row.split()[1]
            for row in Path("/proc/stat").read_text().splitlines()
            if row.startswith("btime ")
        )
    )
    started = boot_epoch + int(stat_before[19]) / os.sysconf("SC_CLK_TCK")
    # Fixed owner configuration paths plus the actual loaded unit and drop-ins.
    paths = {SOURCE, *CONFIGURATION, Path(fields["FragmentPath"])}
    paths.update(Path(path) for path in fields.get("DropInPaths", "").split())
    expected_environment = {str(path) for path in CONFIGURATION}
    actual_environment = {
        part for part in fields.get("EnvironmentFiles", "").split() if part.startswith("/")
    }
    if actual_environment != expected_environment:
        raise ValueError("broker configuration source set changed")
    files = []
    for path in sorted(paths):
        if not path.exists() and path == CONFIGURATION[1]:
            files.append({"path": str(path), "sha256": None})
            continue
        before = path.stat()
        content = path.read_bytes()
        after = path.stat()
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (
            any(getattr(before, key) != getattr(after, key) for key in stable)
            or max(after.st_mtime, after.st_ctime) > started + 2
        ):
            raise ValueError("broker configuration changed after process start")
        files.append({"path": str(path), "sha256": _digest(content)})
    stat_after = (process / "stat").read_text().rsplit(")", 1)[1].split()
    if stat_before[19] != stat_after[19] or stat_after[0] == "Z":
        raise ValueError("broker process changed during capture")
    return {
        "kind": "local_process_source_configuration",
        "host": socket.gethostname(),
        "unit": UNIT,
        "pid": pid,
        "start_ticks": stat_before[19],
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "source_sha256": next(row["sha256"] for row in files if row["path"] == str(SOURCE)),
        "files": files,
        "unit_configuration_sha256": _digest(
            json.dumps(
                {key: value for key, value in fields.items() if key != "MainPID"}, sort_keys=True
            ).encode()
        ),
        "execution_digest_binding": "unverified",
    }


def verify_broker_identity(profile: Any) -> dict[str, Any]:
    """Fail closed on a changed source, configuration, host or broker process."""
    from matric_eval.studies.client_conformance import ConformanceError

    expected = profile.broker_runtime
    if expected is None:
        if profile.api_base.rstrip("/") == PUBLIC:
            raise ConformanceError("live_broker_identity_binding_required")
        return {"kind": "controlled_endpoint_declared_identity", "verified": False}
    if profile.api_base.rstrip("/") != PUBLIC:
        raise ConformanceError("local_broker_identity_endpoint_mismatch")
    try:
        observed = capture_local_broker()
    except Exception:
        raise ConformanceError("live_broker_identity_unavailable") from None
    if (
        expected != observed
        or profile.broker_revision != observed["source_sha256"]
        or profile.broker_identity != f"{observed['host']}-public-ollama-unify"
    ):
        raise ConformanceError("live_broker_identity_changed")
    return observed
