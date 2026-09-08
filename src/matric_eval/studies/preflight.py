"""Service-context admission before target allocation, with bounded check receipts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from matric_eval.studies.run_status import RunStatus, diagnostic, sanitize

SCHEMA = "matric-eval.study-preflight/1"
STAGES = ("static", "cpu", "auxiliary", "target")
LIMIT = 8192


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def mount_identity(path: Path) -> str:
    resolved = str(path.resolve())
    matches = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        mount = fields[4].replace(r"\040", " ")
        if resolved == mount or resolved.startswith(mount.rstrip("/") + "/"):
            matches.append((len(mount), line))
    return max(matches)[1]


def context() -> dict[str, Any]:
    """Capture actual inherited context; environment values are never persisted."""
    mask = os.umask(0)
    os.umask(mask)
    return {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "groups": os.getgroups(),
        "cwd": os.getcwd(),
        "python": sys.executable,
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "tmpdir": tempfile.gettempdir(),
        "umask": oct(mask),
        "environment_sha256": digest(dict(os.environ)),
        "mounts_sha256": digest(
            [mount_identity(Path.cwd()), mount_identity(Path(tempfile.gettempdir()))]
        ),
        "limits": {
            str(key): list(resource.getrlimit(key))
            for key in (resource.RLIMIT_NOFILE, resource.RLIMIT_AS, resource.RLIMIT_NPROC)
        },
        "packages_sha256": digest(
            sorted(
                (item.metadata["Name"], item.version) for item in importlib.metadata.distributions()
            )
        ),
    }


def write_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".preflight-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, sort_keys=True, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
        parent = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        Path(name).unlink(missing_ok=True)


def manifest_order(
    manifest: dict[str, Any], scored_ids: list[str], allocation_id: str
) -> list[str]:
    allocations = [row for row in manifest["allocations"] if row["allocation_id"] == allocation_id]
    if len(allocations) != 1:
        raise ValueError("manifest must contain exactly one selected allocation")
    selected = allocations[0]["selected_ids"]
    if (
        not isinstance(selected, list)
        or not all(isinstance(item, str) and item for item in selected)
        or len(selected) != len(set(selected))
        or len(scored_ids) != len(set(scored_ids))
        or set(selected) != set(scored_ids)
    ):
        raise ValueError("scored IDs do not exactly match the study manifest")
    return list(selected)


def _contract(actual: Any, expected: Any) -> None:
    """Explicit recursive required-field/type contract, not permissive truthiness."""
    types: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "object": dict,
        "array": list,
        "integer": int,
        "boolean": bool,
        "number": (int, float),
    }
    if isinstance(expected, dict) and set(expected) == {"type"}:
        wanted = types[expected["type"]]
        if (
            not isinstance(actual, wanted)
            or isinstance(actual, bool)
            and expected["type"] in {"integer", "number"}
        ):
            raise ValueError("incompatible receipt field type")
    elif isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise ValueError("incompatible receipt object")
        for key, value in expected.items():
            if key not in actual:
                raise ValueError(f"missing receipt field: {key}")
            _contract(actual[key], value)
    elif actual != expected:
        raise ValueError("incompatible receipt field value")


def _validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema") != SCHEMA:
        raise ValueError("unsupported preflight plan schema")
    checks = plan.get("checks")
    if not isinstance(checks, list) or not 1 <= len(checks) <= 64:
        raise ValueError("plan requires 1..64 checks")
    ids = [check["id"] for check in checks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate preflight check ID")
    for stage in STAGES[:3]:
        if not any(check.get("stage") == stage for check in checks):
            raise ValueError(f"plan must explicitly qualify {stage}")
    for check in checks:
        if check.get("stage") not in STAGES:
            raise ValueError("unknown preflight stage")
        if not isinstance(check["id"], str) or not check["id"] or len(check["id"]) > 128:
            raise ValueError("invalid check ID")
        for key in ("timeout_seconds", "freshness_seconds"):
            value = check.get(key)
            if (
                not isinstance(value, (float, int))
                or not math.isfinite(value)
                or not 0 < value <= 86400
            ):
                raise ValueError(f"invalid {key}")
        count = check.get("repetitions", 1)
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError("repetitions must be 1..10")
        if not isinstance(check.get("inputs"), list) or not check["inputs"]:
            raise ValueError("each check requires declared input/code/dependency files")
        if (
            not isinstance(check.get("command"), list)
            or not check["command"]
            or not all(isinstance(item, str) for item in check["command"])
        ):
            raise ValueError("check requires an argv command")
        if not isinstance(check.get("receipt_contract"), dict) or not check["receipt_contract"]:
            raise ValueError("each check requires a receipt contract")


def check_fingerprint(check: dict[str, Any], runtime: dict[str, Any]) -> str:
    return digest(
        {
            "check": check,
            "runtime": runtime,
            "engine": file_digest(Path(__file__)),
            "inputs": {
                name: {"sha256": file_digest(Path(name)), "mount": mount_identity(Path(name))}
                for name in check["inputs"]
            },
        }
    )


def _run(command: list[str], timeout: float, env: dict[str, str]) -> dict[str, Any]:
    """Continuously drain both streams into bounded tails; timeout kills owned group."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, start_new_session=True
    )
    tails = [bytearray(), bytearray()]

    def drain(stream: Any, tail: bytearray) -> None:
        try:
            while chunk := stream.read(4096):
                tail.extend(chunk)
                del tail[:-LIMIT]
        finally:
            stream.close()

    threads = [
        threading.Thread(target=drain, args=(stream, tails[index]), daemon=True)
        for index, stream in enumerate((process.stdout, process.stderr))
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        # No check may leave a background child behind, including successful parents.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for thread in threads:
            thread.join(timeout=5)
    stdout, stderr = (tail.decode("utf-8", errors="replace") for tail in tails)
    if timed_out or process.returncode:
        error = subprocess.CalledProcessError(
            process.returncode, command, output=stdout, stderr=stderr
        )
        if timed_out:
            error.add_note("preflight check timed out")
        raise error
    secrets = [
        value
        for key, value in env.items()
        if any(word in key.lower() for word in ("key", "token", "secret", "password"))
    ]
    return {
        "exit_code": process.returncode,
        "stdout": sanitize(stdout, secrets),
        "stderr": sanitize(stderr, secrets),
    }


def _execute_checks(
    plan: dict[str, Any],
    stage: str,
    runtime: dict[str, Any],
    previous: dict[str, Any],
    result: dict[str, Any],
    receipt_path: Path,
    secrets: list[str],
) -> None:
    for check in (item for item in plan["checks"] if item["stage"] == stage):
        for repetition in range(check.get("repetitions", 1)):
            row: dict[str, Any] = {
                "id": check["id"],
                "stage": stage,
                "repetition": repetition,
                "evidence_id": uuid.uuid4().hex,
                "status": "failed",
                "reused": False,
            }
            result["checks"].append(row)
            try:
                row["fingerprint"] = check_fingerprint(check, runtime)
                cached = next(
                    (
                        item
                        for item in previous.get("checks", [])
                        if item.get("id") == check["id"]
                        and item.get("repetition") == repetition
                        and item.get("fingerprint") == row["fingerprint"]
                        and item.get("status") == "completed"
                        and 0
                        <= time.time() - item.get("completed_at", 0)
                        <= check["freshness_seconds"]
                    ),
                    None,
                )
                # Only explicit deterministic checks reuse successes from complete admitted runs.
                if (
                    cached
                    and check.get("deterministic") is True
                    and stage == "static"
                    and previous.get("admitted") is True
                    and previous.get("completed") is True
                ):
                    row.update(cached, reused=True)
                    result["checks_reused"] += 1
                    continue
                result["checks_reexecuted"] += 1
                with tempfile.TemporaryDirectory(prefix="matric-preflight-") as temporary:
                    output = Path(temporary) / "receipt.json"
                    env = {
                        **os.environ,
                        "MATRIC_PREFLIGHT_RECEIPT": str(output),
                        "MATRIC_PREFLIGHT_EVIDENCE_ID": row["evidence_id"],
                    }
                    try:
                        row.update(_run(check["command"], check["timeout_seconds"], env))
                    finally:
                        if output.exists() and output.stat().st_size <= 1024 * 1024:
                            raw_receipt = output.read_text(errors="replace")
                            row["receipt_sha256"] = file_digest(output)
                            excerpt = sanitize(raw_receipt, secrets)
                            row["receipt_excerpt"] = excerpt[:LIMIT]
                            row["receipt_excerpt_truncated"] = len(excerpt) > LIMIT
                    if output.stat().st_size > 1024 * 1024:
                        raise ValueError("check receipt exceeds 1 MiB")
                    evidence = json.loads(output.read_text())
                    _contract(evidence, check["receipt_contract"])
                    row["completed_at"] = time.time()
                    row["status"] = "completed"
            except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
                row["diagnostic"] = diagnostic(
                    error,
                    actor=check["id"],
                    stage=stage,
                    reason="preflight-check-failed",
                    secrets=secrets,
                )
            write_receipt(receipt_path, result)


def execute_plan(
    plan: dict[str, Any], receipt_path: Path, *, launch: bool = False
) -> dict[str, Any]:
    """Qualify in the caller's service context; acquisition is unreachable on failure."""
    started = time.monotonic()
    runtime = context()
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "plan_fingerprint": digest(plan),
        "context": runtime,
        "checks": [],
        "admitted": False,
        "completed": False,
        "target_launches": 0,
        "target_loads_avoided": 0,
        "checks_reused": 0,
        "checks_reexecuted": 0,
    }
    previous: dict[str, Any] = {}
    if receipt_path.exists():
        try:
            previous = json.loads(receipt_path.read_text())
        except (ValueError, OSError):
            pass
    secrets = [
        value
        for key, value in os.environ.items()
        if any(word in key.lower() for word in ("key", "token", "secret", "password"))
    ]
    try:
        _validate_plan(plan)
        if launch:
            for key in ("target_launch", "target_cleanup", "adapter"):
                if (
                    not isinstance(plan.get(key), list)
                    or not plan[key]
                    or not all(isinstance(arg, str) for arg in plan[key])
                ):
                    raise ValueError(f"launch requires {key} argv")
            if (
                not isinstance(plan.get("adapter_receipt_contract"), dict)
                or not plan["adapter_receipt_contract"]
            ):
                raise ValueError("launch requires adapter receipt contract")
        for stage in STAGES:
            if stage == "target":
                result["admitted"] = all(row["status"] == "completed" for row in result["checks"])
                if result["admitted"]:
                    result["completed_at"] = time.time()
                    try:
                        validate_admission(result, plan, 86400)
                    except (ValueError, OSError, KeyError) as error:
                        result["admitted"] = False
                        raise ValueError(
                            "preflight inputs/context changed during qualification"
                        ) from error
                if not result["admitted"] or not launch:
                    break
                command = plan.get("target_launch")
                if not isinstance(command, list) or not command:
                    raise ValueError("launch requires target_launch argv")
                result["target_launches"] += 1
                # Target launch must return after durable lifecycle ownership registration.
                _run(command, plan.get("launch_timeout_seconds", 300), dict(os.environ))
            _execute_checks(plan, stage, runtime, previous, result, receipt_path, secrets)
        result["completed"] = result["admitted"] and all(
            row["status"] == "completed" for row in result["checks"]
        )
        if launch and result["completed"]:
            if not plan.get("adapter"):
                raise ValueError("launch requires adapter argv")
            with tempfile.TemporaryDirectory(prefix="matric-preflight-adapter-") as temporary:
                output = Path(temporary) / "receipt.json"
                result["adapter"] = _run(
                    plan["adapter"],
                    plan.get("adapter_timeout_seconds", 300),
                    {**os.environ, "MATRIC_PREFLIGHT_RECEIPT": str(output)},
                )
                if output.stat().st_size > 1024 * 1024:
                    raise ValueError("adapter receipt exceeds 1 MiB")
                _contract(json.loads(output.read_text()), plan["adapter_receipt_contract"])
                result["adapter"]["receipt_sha256"] = file_digest(output)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result["completed"] = False
        result["diagnostic"] = diagnostic(
            error,
            actor="launcher",
            stage="preflight",
            reason="preflight-plan-failed",
            secrets=secrets,
        )
    finally:
        if result["target_launches"]:
            try:
                result["cleanup"] = _run(
                    plan["target_cleanup"],
                    plan.get("cleanup_timeout_seconds", 60),
                    dict(os.environ),
                )
            except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
                result["completed"] = False
                result["cleanup"] = diagnostic(
                    error,
                    actor="launcher",
                    stage="cleanup",
                    reason="target-cleanup-failed",
                    secrets=secrets,
                )
    result["target_loads_avoided"] = int(not result["admitted"])
    result["elapsed_seconds"] = time.monotonic() - started
    result["completed_at"] = time.time()
    write_receipt(receipt_path, result)
    if directory := os.environ.get("MATRIC_RUN_STATUS_DIR"):
        status = RunStatus(Path(directory))
        if not result["completed"]:
            status.phase("preflight-blocked" if not result["target_launches"] else "failed")
        for row in result["checks"]:
            if "diagnostic" in row:
                with status.update() as data:
                    data["diagnostics"].append(row["diagnostic"])
    return result


def validate_admission(
    receipt: dict[str, Any], plan: dict[str, Any], max_age_seconds: float
) -> None:
    """Recheck the complete pre-target evidence in the same effective service context."""
    _validate_plan(plan)
    if (
        receipt.get("schema") != SCHEMA
        or receipt.get("admitted") is not True
        or receipt.get("plan_fingerprint") != digest(plan)
        or not 0 <= time.time() - receipt.get("completed_at", 0) <= max_age_seconds
    ):
        raise ValueError("missing, stale or incompatible preflight admission")
    runtime = context()
    if runtime != receipt.get("context"):
        changed = [key for key in runtime if runtime[key] != receipt.get("context", {}).get(key)]
        raise ValueError("runtime context changed: " + ", ".join(changed))
    evidence_ids = set()
    for check in (item for item in plan["checks"] if item["stage"] != "target"):
        for repetition in range(check.get("repetitions", 1)):
            matches = [
                row
                for row in receipt["checks"]
                if row["id"] == check["id"] and row["repetition"] == repetition
            ]
            if len(matches) != 1:
                raise ValueError("missing or duplicate preflight repetition")
            row = matches[0]
            if (
                row["status"] != "completed"
                or row["fingerprint"] != check_fingerprint(check, runtime)
                or not 0 <= time.time() - row["completed_at"] <= check["freshness_seconds"]
                or row["evidence_id"] in evidence_ids
            ):
                raise ValueError("stale, changed or duplicated check evidence")
            evidence_ids.add(row["evidence_id"])


def tau_plan(
    *,
    python: Path,
    checkout: Path,
    protocol: Path,
    model_id: str,
    manifest: Path,
    inputs_summary: Path,
    scored_ids: Path,
    tau_checkout: Path,
    patch_manifest: Path,
    launcher_smoke: dict[str, Any] | None = None,
    auxiliary_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the supported Tau pre-target profile without opening a model endpoint.

    The smoke is the adapter's controlled-endpoint, real-input-shape command, not
    a fabricated successful client receipt. Simulator and embedder checks must
    use their actual scored-path client profile. All live checks rerun.
    """
    if {check.get("role") for check in auxiliary_checks} != {"simulator", "embedder"}:
        raise ValueError("Tau plan requires simulator and embedder client checks")
    script = checkout / "scripts/preflight_qwen38_tau.py"
    arguments = [
        "--protocol",
        str(protocol),
        "--model-id",
        model_id,
        "--manifest",
        str(manifest),
        "--inputs-summary",
        str(inputs_summary),
        "--scored-ids",
        str(scored_ids),
        "--tau-checkout",
        str(tau_checkout),
        "--tau-patch-manifest",
        str(patch_manifest),
    ]
    inputs = [
        str(path)
        for path in (
            python,
            script,
            checkout / "scripts/run_qwen38_tau.py",
            checkout / "scripts/qwen38_tau_context.py",
            checkout / "uv.lock",
            protocol,
            manifest,
            inputs_summary,
            scored_ids,
            patch_manifest,
        )
    ]
    checks: list[dict[str, Any]] = []
    for mode, stage in (
        ("inputs", "static"),
        ("patch", "static"),
        ("dependencies", "cpu"),
        ("tasks", "cpu"),
        ("sandbox", "cpu"),
    ):
        checks.append(
            {
                "id": f"tau-{mode}",
                "stage": stage,
                "command": [str(python), str(script), mode, *arguments],
                "inputs": inputs,
                "timeout_seconds": 120,
                "freshness_seconds": 300,
                "deterministic": False,
                "receipt_contract": {
                    "schema": "matric-eval.tau-preflight/1",
                    "mode": mode,
                    "passed": True,
                },
            }
        )
    if launcher_smoke is None:
        launcher_smoke = {
            "command": [str(python), str(script), "launcher", *arguments],
            "inputs": inputs,
            "timeout_seconds": 120,
            "freshness_seconds": 300,
            "repetitions": 3,
            "receipt_contract": {
                "schema": "matric-eval.tau-preflight/1",
                "mode": "launcher",
                "passed": True,
                "launcher": {"http_requests": 1, "scored_tasks_executed": 0},
            },
        }
    checks.append(
        {
            **launcher_smoke,
            "id": "launcher-adapter-receipt-smoke",
            "stage": "cpu",
            "deterministic": False,
        }
    )
    checks.extend(
        {**check, "id": f"auxiliary-{check['role']}", "stage": "auxiliary", "deterministic": False}
        for check in auxiliary_checks
    )
    plan = {"schema": SCHEMA, "checks": checks}
    _validate_plan(plan)
    return plan


def execute_target_checks(
    plan: dict[str, Any],
    receipt_path: Path,
    admission_receipt: dict[str, Any],
    *,
    max_age_seconds: float = 300,
) -> dict[str, Any]:
    """Qualify an already-owned resident target; never acquire or launch a service."""
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "plan_fingerprint": digest(plan),
        "checks": [],
        "completed": False,
        "target_launches": 0,
        "checks_reused": 0,
        "checks_reexecuted": 0,
    }
    secrets = [
        value
        for key, value in os.environ.items()
        if any(word in key.lower() for word in ("key", "token", "secret", "password"))
    ]
    try:
        validate_admission(admission_receipt, plan, max_age_seconds)
        result["context"] = context()
        if not any(check["stage"] == "target" for check in plan["checks"]):
            raise ValueError("resident qualification requires explicit target checks")
        _execute_checks(plan, "target", result["context"], {}, result, receipt_path, secrets)
        result["completed"] = all(row["status"] == "completed" for row in result["checks"])
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result["diagnostic"] = diagnostic(
            error,
            actor="launcher",
            stage="target",
            reason="target-preflight-failed",
            secrets=secrets,
        )
    result["elapsed_seconds"] = time.monotonic() - started
    result["completed_at"] = time.time()
    write_receipt(receipt_path, result)
    return result


def auxiliary_client_check(
    *, python: Path, checkout: Path, profile: Path, role: str = "simulator"
) -> dict[str, Any]:
    """Use the scored client profile and real broker canary, preserving evidence limits."""
    if role not in {"simulator", "embedder"}:
        raise ValueError("unknown auxiliary role")
    operation = "embedding" if role == "embedder" else "completion"
    script = checkout / "scripts/preflight_auxiliary_client.py"
    canary = checkout / (
        "scripts/qualify_embedding_client.py"
        if operation == "embedding"
        else "scripts/qualify_auxiliary_client.py"
    )
    return {
        "id": f"auxiliary-{role}",
        "role": role,
        "stage": "auxiliary",
        "command": [
            str(python),
            str(script),
            "--profile",
            str(profile),
            "--canary-script",
            str(canary),
            "--operation",
            operation,
        ],
        "inputs": [
            str(path)
            for path in (
                python,
                profile,
                script,
                canary,
                checkout / "src/matric_eval/studies/client_conformance.py",
                checkout / "src/matric_eval/studies/broker_admission.py",
                checkout / "src/matric_eval/studies/auxiliary_runtime.py",
                checkout / "src/matric_eval/studies/embedding_transport.py",
            )
        ],
        "timeout_seconds": 420,
        "freshness_seconds": 300,
        "deterministic": False,
        "receipt_contract": {
            "schema": "matric-eval.auxiliary-preflight/1",
            "transport_passed": True,
            "execution_digest_binding": "unverified",
            "qualification_scope": "actual_client_transport_and_own_request_correlation",
        },
    }
