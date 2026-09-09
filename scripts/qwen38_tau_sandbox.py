"""Pinned Tau banking-sandbox dependency and Unix-socket path checks."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

SANDBOX_RUNTIME_PACKAGE_VERSION = "0.0.23"
RANK_BM25_PACKAGE_VERSION = "0.2.2"
LINUX_UNIX_SOCKET_PATH_LIMIT_BYTES = 107
_BRIDGE_SOCKET_BASENAMES = (
    "claude-http-" + "0" * 16 + ".sock",
    "claude-socks-" + "0" * 16 + ".sock",
)


def sandbox_socket_path_evidence(temp_dir: Path | None = None) -> dict[str, int]:
    """Fail before SRT when its bridge socket cannot fit Linux ``sun_path``."""
    effective = temp_dir
    if effective is None:
        configured = os.environ.get("TMPDIR")
        effective = Path(configured) if configured else Path(tempfile.gettempdir())
    if not effective.is_absolute():
        raise RuntimeError("Tau sandbox TMPDIR must be absolute")
    path_lengths = [len(os.fsencode(effective / name)) for name in _BRIDGE_SOCKET_BASENAMES]
    longest = max(path_lengths)
    if longest > LINUX_UNIX_SOCKET_PATH_LIMIT_BYTES:
        raise RuntimeError(
            "Tau sandbox bridge socket path exceeds the Linux Unix-socket path limit"
        )
    return {
        "tmpdir_path_bytes": len(os.fsencode(effective)),
        "longest_bridge_socket_path_bytes": longest,
        "linux_limit_bytes": LINUX_UNIX_SOCKET_PATH_LIMIT_BYTES,
    }


def knowledge_dependency_evidence() -> dict[str, Any]:
    """Exercise the pinned sandbox runtime without a target model or GPU."""
    socket_path_budget = sandbox_socket_path_evidence()
    binaries = {name: shutil.which(name) for name in ("srt", "rg", "bwrap", "socat")}
    missing = [name for name, path in binaries.items() if path is None]
    if missing:
        raise RuntimeError("tau banking sandbox dependencies are missing: " + ", ".join(missing))
    npm = subprocess.run(
        ["npm", "list", "-g", "--json", "@anthropic-ai/sandbox-runtime"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    npm_payload = json.loads(npm.stdout)
    dependencies = npm_payload.get("dependencies") if isinstance(npm_payload, dict) else None
    package = (
        dependencies.get("@anthropic-ai/sandbox-runtime")
        if isinstance(dependencies, dict)
        else None
    )
    npm_version = package.get("version") if isinstance(package, dict) else None
    if npm_version != SANDBOX_RUNTIME_PACKAGE_VERSION:
        raise RuntimeError("sandbox-runtime package version does not match the tau contract")
    rank_bm25_version = importlib.metadata.version("rank-bm25")
    if rank_bm25_version != RANK_BM25_PACKAGE_VERSION:
        raise RuntimeError("rank-bm25 package version does not match the tau contract")

    from tau2.knowledge.sandbox_manager import SandboxManager

    with tempfile.TemporaryDirectory(prefix="tau-sandbox-canary-") as base:
        with SandboxManager(base_temp_dir=base) as sandbox:
            code, stdout, stderr = sandbox.run_command("printf sandbox-canary")
    if code != 0 or stdout != "sandbox-canary" or stderr:
        raise subprocess.CalledProcessError(
            code, "tau banking sandbox execution canary", output=stdout, stderr=stderr
        )
    return {
        "binaries": binaries,
        "sandbox_runtime_npm_version": npm_version,
        "rank_bm25_version": rank_bm25_version,
        "socket_path_budget": socket_path_budget,
        "execution_canary": "passed",
    }


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    """Exclusively persist a private content-free sandbox receipt."""
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite sandbox receipt: {path}")
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt: dict[str, Any] = {
        "schema": "matric-eval.tau-sandbox-preflight/1",
        "passed": False,
        "sandbox": None,
        "failure": None,
    }
    try:
        receipt["sandbox"] = knowledge_dependency_evidence()
        receipt["passed"] = True
    except BaseException as exc:
        receipt["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc)[:500],
        }
    _write_receipt(args.receipt, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
