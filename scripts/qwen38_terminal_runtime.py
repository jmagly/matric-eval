"""Pinned Harbor runtime and parent-watchdog support for the Qwen3.8 study."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence, TextIO

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class HarborPatchContract:
    """Content-addressed contract for the pinned Harbor source patch."""

    upstream_revision: str
    patch_path: Path
    patch_sha256: str
    patched_diff_sha256: str
    changed_paths: tuple[str, ...]
    package_version: str


@dataclass(frozen=True)
class WatchdogResult:
    """Outcome of one process-group invocation under the parent watchdog."""

    returncode: int
    timed_out: bool
    sent_sigterm: bool
    sent_sigkill: bool
    wall_seconds: float


INVALID_CLASSIFICATIONS: Mapping[str, tuple[str, str, str, str]] = {
    "ContextPreflightError": (
        "context_preflight",
        "context-runtime",
        "target-model",
        "context-budget",
    ),
    "ContextRecoveryExhaustedError": (
        "context_recovery_exhausted",
        "context-runtime",
        "target-model",
        "recovery",
    ),
    "OutputRecoveryExhaustedError": (
        "output_recovery_exhausted",
        "mixed-uncertain",
        "target-model",
        "recovery",
    ),
    "LLMResponseTimeoutError": (
        "llm_response_timeout",
        "context-runtime",
        "target-model",
        "generation",
    ),
    "CommandTimeoutError": (
        "command_timeout",
        "context-runtime",
        "tool-service",
        "tool-execution",
    ),
    "AgentNoSubmitError": (
        "agent_no_submit",
        "target-model",
        "target-model",
        "termination",
    ),
    "AgentTimeoutError": (
        "agent_no_submit",
        "mixed-uncertain",
        "target-model",
        "termination",
    ),
    "HarborResultMissingError": (
        "missing_reward",
        "harness-interface",
        "runner",
        "result-ingest",
    ),
    "JSONDecodeError": (
        "harbor_result_decode",
        "harness-interface",
        "runner",
        "result-ingest",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _git(checkout: Path, arguments: Sequence[str], *, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(checkout), *arguments],
        check=True,
        capture_output=True,
        text=text,
        timeout=60,
    )
    stdout = result.stdout
    if text:
        if not isinstance(stdout, str):
            raise TypeError("text Git command returned non-text output")
        return stdout
    if not isinstance(stdout, bytes):
        raise TypeError("binary Git command returned non-binary output")
    return stdout


def load_patch_contract(manifest_path: Path) -> HarborPatchContract:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1":
        raise ValueError("Harbor patch manifest must be a schema-version 1 object")
    patch_name = payload.get("patch_file")
    if not isinstance(patch_name, str) or Path(patch_name).name != patch_name:
        raise ValueError("Harbor patch filename must be a basename")
    patch_path = (manifest_path.parent / patch_name).resolve()
    patch_sha256 = sha256_file(patch_path)
    hashes = (payload.get("patch_sha256"), payload.get("patched_diff_sha256"))
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
        raise ValueError("Harbor patch hashes must be lowercase SHA-256 values")
    if patch_sha256 != payload["patch_sha256"]:
        raise ValueError("Harbor patch SHA-256 does not match its manifest")
    revision = payload.get("upstream_revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Harbor upstream revision must be a full lowercase Git SHA")
    changed_paths = payload.get("changed_paths")
    if not isinstance(changed_paths, list) or changed_paths != sorted(set(changed_paths)):
        raise ValueError("Harbor changed paths must be a sorted unique list")
    if not all(isinstance(path, str) and path for path in changed_paths):
        raise ValueError("Harbor changed paths must contain nonempty strings")
    package_version = payload.get("package_version")
    if not isinstance(package_version, str) or not package_version:
        raise ValueError("Harbor patch manifest must pin a package version")
    return HarborPatchContract(
        upstream_revision=revision,
        patch_path=patch_path,
        patch_sha256=patch_sha256,
        patched_diff_sha256=str(payload["patched_diff_sha256"]),
        changed_paths=tuple(changed_paths),
        package_version=package_version,
    )


def verify_harbor_checkout(checkout: Path, contract: HarborPatchContract) -> JsonObject:
    revision = str(_git(checkout, ["rev-parse", "HEAD"])).strip()
    if revision != contract.upstream_revision:
        raise RuntimeError("Harbor checkout is not at the patch contract revision")
    status = str(_git(checkout, ["status", "--porcelain=v1", "--untracked-files=all"]))
    changed_paths = tuple(
        sorted(line[3:].strip() for line in status.splitlines() if len(line) >= 4)
    )
    if changed_paths != contract.changed_paths:
        raise RuntimeError("Harbor checkout changed paths do not match the patch contract")
    diff = _git(checkout, ["diff", "HEAD", "--binary", "--", *changed_paths], text=False)
    assert isinstance(diff, bytes)
    diff_sha256 = hashlib.sha256(diff).hexdigest()
    if diff_sha256 != contract.patched_diff_sha256:
        raise RuntimeError("Harbor checkout diff does not match the content-addressed patch")
    return {
        "upstream_revision": revision,
        "package_version": contract.package_version,
        "patch_sha256": contract.patch_sha256,
        "applied_diff_sha256": diff_sha256,
        "changed_paths": list(changed_paths),
    }


def apply_harbor_patch(checkout: Path, contract: HarborPatchContract) -> JsonObject:
    revision = str(_git(checkout, ["rev-parse", "HEAD"])).strip()
    status = str(_git(checkout, ["status", "--porcelain=v1", "--untracked-files=all"]))
    if revision != contract.upstream_revision or status.strip():
        raise RuntimeError("Harbor patch application requires the exact clean upstream checkout")
    subprocess.run(
        ["git", "-C", str(checkout), "apply", "--check", str(contract.patch_path)],
        check=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "apply", str(contract.patch_path)],
        check=True,
        timeout=60,
    )
    return verify_harbor_checkout(checkout, contract)


def _wait_for_process_group_exit(process: subprocess.Popen[str], deadline: float) -> bool:
    """Reap the leader while waiting for every member of its process group to exit."""
    while True:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))


def run_with_watchdog(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    stdout: TextIO | BinaryIO,
    stderr: TextIO | BinaryIO,
    timeout_seconds: float,
    teardown_grace_seconds: float,
) -> WatchdogResult:
    """Run one process group and bound TERM/KILL teardown after timeout."""
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        for value in (timeout_seconds, teardown_grace_seconds)
    ):
        raise ValueError("watchdog and teardown grace must be positive")
    started = time.monotonic()
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env),
        stdout=stdout,
        stderr=stderr,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    sent_sigterm = False
    sent_sigkill = False
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
            sent_sigterm = True
        except ProcessLookupError:
            pass
        if not _wait_for_process_group_exit(process, time.monotonic() + teardown_grace_seconds):
            try:
                os.killpg(process.pid, signal.SIGKILL)
                sent_sigkill = True
            except ProcessLookupError:
                pass
            if not _wait_for_process_group_exit(process, time.monotonic() + teardown_grace_seconds):
                raise RuntimeError("parent watchdog process group survived bounded teardown")
        returncode = process.wait(timeout=teardown_grace_seconds)
    return WatchdogResult(
        returncode=returncode,
        timed_out=timed_out,
        sent_sigterm=sent_sigterm,
        sent_sigkill=sent_sigkill,
        wall_seconds=time.monotonic() - started,
    )


def classify_trial(
    *,
    exception_type: str | None,
    rewards: Mapping[str, Any] | None,
    harbor_exit_code: int | None,
    watchdog_timed_out: bool,
) -> JsonObject:
    """Classify validity without converting infrastructure failures to score zero."""
    if watchdog_timed_out:
        classification = (
            "parent_watchdog_timeout",
            "context-runtime",
            "runner",
            "termination",
        )
        detail = "parent_watchdog"
    elif exception_type is not None:
        classification = INVALID_CLASSIFICATIONS.get(
            exception_type,
            ("harbor_trial_exception", "mixed-uncertain", "runner", "termination"),
        )
        detail = exception_type
    elif harbor_exit_code not in (None, 0):
        classification = (
            "harbor_subprocess_error",
            "harness-interface",
            "runner",
            "termination",
        )
        detail = "nonzero_exit"
    else:
        reward = rewards.get("reward") if rewards is not None else None
        if (
            not isinstance(reward, (int, float))
            or isinstance(reward, bool)
            or not math.isfinite(float(reward))
        ):
            classification = (
                "missing_reward",
                "evaluator",
                "evaluator",
                "verification",
            )
            detail = "official_reward_absent"
        else:
            return {
                "status": "valid",
                "reason": None,
                "detail": None,
                "owner": None,
                "actor": None,
                "stage": None,
                "exception_chain": [],
            }
    reason, owner, actor, stage = classification
    return {
        "status": "invalid",
        "reason": reason,
        "detail": detail,
        "owner": owner,
        "actor": actor,
        "stage": stage,
        "exception_chain": ([{"type": exception_type}] if exception_type else []),
    }


def timing_summary(
    records: Sequence[Mapping[str, Any]], invocation_wall_seconds: float
) -> JsonObject:
    fresh = [record for record in records if not record["recovered_existing_trial"]]
    recovered = [record for record in records if record["recovered_existing_trial"]]
    fresh_durations = [record["task_wall_seconds"] for record in fresh]
    recovered_durations = [record["task_wall_seconds"] for record in recovered]
    unknown_count = sum(value is None for value in [*fresh_durations, *recovered_durations])

    def total(values: Sequence[Any]) -> float | None:
        if any(value is None for value in values):
            return None
        return sum(float(value) for value in values)

    fresh_wall = total(fresh_durations)
    recovered_wall = total(recovered_durations)
    total_wall = (
        None if fresh_wall is None or recovered_wall is None else fresh_wall + recovered_wall
    )
    return {
        "invocation_wall_seconds": invocation_wall_seconds,
        "fresh_attempt_count": len(fresh),
        "recovered_attempt_count": len(recovered),
        "total_attempt_count": len(records),
        "unknown_timing_count": unknown_count,
        "fresh_wall_seconds": fresh_wall,
        "recovered_wall_seconds": recovered_wall,
        "total_wall_seconds": total_wall,
    }
