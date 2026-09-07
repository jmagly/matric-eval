"""Bounded generated Python execution in an explicitly configured Docker runtime.

The controller never executes generated code on the host. Docker/runc shares the
host kernel; this profile is a restricted container, not a virtual machine.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

PROFILE = "python-restricted/1"
MEMORY_BYTES = 256 * 1024 * 1024
TMPFS_BYTES = 16 * 1024 * 1024
OUTPUT_BYTES = 64 * 1024
INPUT_BYTES = 1024 * 1024
MAX_WALL_SECONDS = 30.0
CONTROL_SECONDS = 10.0
CONTROL_OUTPUT_BYTES = 1024 * 1024
LABEL = "org.matric-eval.generated-execution"
PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
TMPFS = "rw,noexec,nosuid,nodev,size=16777216,mode=1777"
BOOTSTRAP = """import io,json,sys
payload=json.loads(sys.stdin.buffer.read(1048577))
sys.stdin=io.TextIOWrapper(io.BytesIO(payload['stdin'].encode('utf-8')),encoding='utf-8')
sys.argv=['<generated>']
exec(compile(payload['code'],'<generated>','exec'),{'__name__':'__main__'})
"""
COMMAND = ["-i", f"PATH={PATH}", "LANG=C.UTF-8", "python3", "-I", "-u", "-c", BOOTSTRAP]


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    limit: str | None = None


class PolicyError(Exception):
    """A fixed profile invariant was not demonstrated."""


def _command(
    argv: list[str],
    *,
    payload: bytes = b"",
    timeout: float = CONTROL_SECONDS,
    output_limit: int = CONTROL_OUTPUT_BYTES,
) -> CommandResult:
    """Bound controller I/O without buffering an untrusted output stream."""
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": PATH, "LANG": "C", "LC_ALL": "C"},
        start_new_session=True,
    )
    output = bytearray()
    errors = bytearray()
    limit = None
    deadline = time.monotonic() + timeout
    offset = 0
    try:
        assert (
            process.stdin is not None and process.stdout is not None and process.stderr is not None
        )
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdin, process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
            if payload:
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    limit = "timeout"
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    if key.data == "stdin":
                        try:
                            offset += os.write(key.fd, payload[offset : offset + 16384])
                        except BrokenPipeError:
                            offset = len(payload)
                        except BlockingIOError:
                            continue
                        if offset == len(payload):
                            selector.unregister(key.fd)
                            process.stdin.close()
                    else:
                        try:
                            chunk = os.read(key.fd, 16384)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            selector.unregister(key.fd)
                            continue
                        available = output_limit - len(output) - len(errors)
                        target = output if key.data == "stdout" else errors
                        target.extend(chunk[:available])
                        if len(chunk) > available:
                            limit = "output_limit"
                            break
                if limit is not None:
                    break
            if limit is None:
                try:
                    process.wait(timeout=max(0.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    limit = "timeout"
    finally:
        # This stops the CLI only. The container is removed separately even on
        # interruption: killing a client is not evidence of sandbox cleanup.
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=CONTROL_SECONDS)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
    return CommandResult(process.returncode, bytes(output), bytes(errors), limit)


def _decode_output(stdout: bytes, stderr: bytes) -> tuple[str, str, dict[str, Any]]:
    """Bound returned UTF-8 text as well as captured bytes; retain raw digests."""
    decoded = []
    remaining = OUTPUT_BYTES
    invalid = False
    truncated = False
    for raw in (stdout, stderr):
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            invalid = True
            text = raw.decode("utf-8", errors="replace")
        encoded = text.encode("utf-8")
        if len(encoded) > remaining:
            truncated = True
            text = encoded[:remaining].decode("utf-8", errors="ignore")
        remaining -= len(text.encode("utf-8"))
        decoded.append(text)
    return (
        decoded[0],
        decoded[1],
        {
            "stdout_raw_bytes": len(stdout),
            "stderr_raw_bytes": len(stderr),
            "stdout_raw_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_raw_sha256": hashlib.sha256(stderr).hexdigest(),
            "invalid_utf8_replaced": invalid,
            "text_truncated": truncated,
        },
    )


def _json(result: CommandResult) -> Any:
    if result.returncode != 0 or result.limit is not None:
        raise PolicyError("runtime_query_failed")
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise PolicyError("runtime_query_invalid") from exc


def _settings() -> tuple[list[str], str, str, str]:
    try:
        launcher = json.loads(os.environ.get("MATRIC_EVAL_SANDBOX_COMMAND", '["docker"]'))
    except ValueError as exc:
        raise PolicyError("invalid_launcher") from exc
    if (
        not isinstance(launcher, list)
        or not launcher
        or any(not isinstance(item, str) or not item or "\x00" in item for item in launcher)
    ):
        raise PolicyError("invalid_launcher")
    image = os.environ.get("MATRIC_EVAL_SANDBOX_IMAGE", "")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[a-f0-9]{64}", image):
        raise PolicyError("pinned_image_required")
    platform = os.environ.get("MATRIC_EVAL_SANDBOX_PLATFORM", "linux/amd64")
    if platform not in {"linux/amd64", "linux/arm64"}:
        raise PolicyError("unsupported_platform")
    socket = os.environ.get("MATRIC_EVAL_SANDBOX_SOCKET", "/var/run/docker.sock")
    if not socket.startswith("/") or "\x00" in socket:
        raise PolicyError("local_socket_required")
    return launcher, image, platform, socket


def _verify_runtime(info: Any) -> None:
    if not isinstance(info, dict):
        raise PolicyError("runtime_info_invalid")
    security = info.get("SecurityOptions", [])
    if (
        not isinstance(security, list)
        or "name=seccomp,profile=builtin" not in security
        or "name=apparmor" not in security
    ):
        raise PolicyError("security_profiles_unavailable")
    if info.get("OSType") != "linux" or not all(
        info.get(key) is True for key in ("MemoryLimit", "SwapLimit", "PidsLimit")
    ):
        raise PolicyError("resource_controllers_unavailable")
    if not (info.get("CpuCfsQuota") is True and info.get("CpuCfsPeriod") is True):
        raise PolicyError("cpu_controller_unavailable")
    if "runc" not in info.get("Runtimes", {}):
        raise PolicyError("qualified_runtime_unavailable")


def _verify_image(images: Any, image: str, platform: str) -> dict[str, Any]:
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise PolicyError("image_inspect_invalid")
    item = images[0]
    if not any(
        ref.endswith("@" + image.rsplit("@", 1)[1]) for ref in item.get("RepoDigests", [])
    ) or not re.fullmatch(r"sha256:[a-f0-9]{64}", item.get("Id", "")):
        raise PolicyError("image_digest_unverified")
    if f"{item.get('Os')}/{item.get('Architecture')}" != platform:
        raise PolicyError("image_platform_mismatch")
    config = item.get("Config", {})
    if config.get("Volumes") or config.get("OnBuild"):
        raise PolicyError("image_declares_mounts_or_build_hooks")
    return item


def _create_args(name: str, image: str, platform: str) -> list[str]:
    return [
        "container",
        "create",
        "--pull=never",
        "--name",
        name,
        "--label",
        f"{LABEL}={name}",
        "--platform",
        platform,
        "--runtime=runc",
        "--user=65534:65534",
        "--read-only",
        "--network=none",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--security-opt=apparmor=docker-default",
        "--init",
        "--ipc=private",
        "--cgroupns=private",
        "--memory=268435456",
        "--memory-swap=268435456",
        "--cpus=1",
        "--pids-limit=32",
        "--tmpfs",
        f"/tmp:{TMPFS}",
        "--shm-size=16777216",
        "--log-driver=none",
        "--restart=no",
        "--no-healthcheck",
        "--ulimit",
        "core=0:0",
        "--workdir=/tmp",
        "--entrypoint=/usr/bin/env",
        "--interactive",
        image,
        *COMMAND,
    ]


def _verify_container(items: Any, *, name: str, image_id: str) -> dict[str, Any]:
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise PolicyError("container_inspect_invalid")
    item = items[0]
    host = item.get("HostConfig", {})
    config = item.get("Config", {})
    required = {
        "Privileged": False,
        "ReadonlyRootfs": True,
        "NetworkMode": "none",
        "Memory": MEMORY_BYTES,
        "MemorySwap": MEMORY_BYTES,
        "NanoCpus": 1000000000,
        "PidsLimit": 32,
        "Init": True,
        "IpcMode": "private",
        "CgroupnsMode": "private",
        "Runtime": "runc",
        "ShmSize": TMPFS_BYTES,
        "PublishAllPorts": False,
    }
    if any(host.get(key) != expected for key, expected in required.items()):
        raise PolicyError("effective_restrictions_differ")
    if set(host.get("CapDrop") or []) != {"ALL"} or host.get("CapAdd"):
        raise PolicyError("effective_capabilities_differ")
    if set(host.get("SecurityOpt") or []) != {"no-new-privileges", "apparmor=docker-default"}:
        raise PolicyError("effective_security_profiles_differ")
    if host.get("PidMode") not in ("", "private") or host.get("UTSMode") not in ("", "private"):
        raise PolicyError("shared_namespace_denied")
    if host.get("UsernsMode") not in ("", "private"):
        raise PolicyError("host_user_namespace_denied")
    for field in (
        "Binds",
        "Mounts",
        "VolumesFrom",
        "Devices",
        "DeviceRequests",
        "DeviceCgroupRules",
        "PortBindings",
        "Links",
        "ExtraHosts",
        "GroupAdd",
    ):
        if host.get(field):
            raise PolicyError("unexpected_host_resource")
    if host.get("Tmpfs") != {"/tmp": TMPFS} or item.get("Mounts"):
        raise PolicyError("unexpected_mount")
    if (
        host.get("LogConfig", {}).get("Type") != "none"
        or host.get("RestartPolicy", {}).get("Name") != "no"
    ):
        raise PolicyError("persistent_runtime_policy_denied")
    if (
        config.get("User") != "65534:65534"
        or config.get("WorkingDir") != "/tmp"
        or config.get("Tty") is not False
    ):
        raise PolicyError("effective_process_identity_differ")
    if config.get("Entrypoint") != ["/usr/bin/env"] or config.get("Cmd") != COMMAND:
        raise PolicyError("effective_bootstrap_differ")
    if config.get("Labels", {}).get(LABEL) != name or item.get("Name") != f"/{name}":
        raise PolicyError("container_ownership_unverified")
    if item.get("Image") != image_id or not re.fullmatch(r"[a-f0-9]{64}", item.get("Id", "")):
        raise PolicyError("container_image_unverified")
    if item.get("State", {}).get("Status") != "created":
        raise PolicyError("container_already_started")
    networks = item.get("NetworkSettings", {}).get("Networks", {})
    if set(networks) - {"none"}:
        raise PolicyError("unexpected_network")
    return item


def _started(state: dict[str, Any]) -> bool:
    """Require native start evidence, not merely an attempted attach command."""
    timestamp = state.get("StartedAt")
    if not isinstance(timestamp, str) or state.get("Status") not in {"running", "exited"}:
        return False
    try:
        started = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return started.year > 1970 and started.tzinfo is not None


def _cleanup(command: list[str], name: str) -> bool:
    """Remove only our unique name, then verify absence via a successful list query."""
    try:
        removed = _command([*command, "container", "rm", "--force", "--volumes", name])
        # Successful listing distinguishes absence from daemon/auth failures.
        listed = _command(
            [
                *command,
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                (f"id={name}" if re.fullmatch(r"[a-f0-9]{64}", name) else f"name=^/{name}$"),
            ]
        )
        return (
            removed.limit is None
            and listed.returncode == 0
            and listed.limit is None
            and not listed.stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _execute_python(
    code: str, stdin_input: str = "", timeout: float = MAX_WALL_SECONDS
) -> dict[str, Any]:
    """Execute in the fixed container profile or return an explicit unscored status.

    ``passed`` means the generated process exited zero. The caller owns test or
    output comparison semantics. Resource failures never imply a measured zero.
    """
    provenance: dict[str, Any] = {
        "profile": PROFILE,
        "bootstrap_sha256": hashlib.sha256(BOOTSTRAP.encode()).hexdigest(),
        "profile_sha256": hashlib.sha256(
            json.dumps(
                {
                    "create_arguments": _create_args("<container>", "<pinned-image>", "<platform>"),
                    "input_bytes": INPUT_BYTES,
                    "output_bytes": OUTPUT_BYTES,
                    "max_wall_seconds": MAX_WALL_SECONDS,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "runc_version": None,
        "runc_version_unavailable_reason": "runtime_version_not_recorded",
        "cleanup": "not_created",
        "isolation": "docker-runc-shared-kernel",
        "resources": {
            "memory_bytes": MEMORY_BYTES,
            "memory_swap_bytes": MEMORY_BYTES,
            "cpus": 1,
            "pids": 32,
            "tmpfs_bytes": TMPFS_BYTES,
            "output_bytes": OUTPUT_BYTES,
            "input_bytes": INPUT_BYTES,
        },
    }
    result: dict[str, Any] = {
        "status": "unavailable",
        "stdout": "",
        "stderr": "",
        "error": None,
        "provenance": provenance,
    }
    if (
        not isinstance(code, str)
        or not isinstance(stdin_input, str)
        or isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= MAX_WALL_SECONDS
    ):
        result.update(status="policy_denied", error="invalid_execution_request")
        return result
    if len(code) + len(stdin_input) > INPUT_BYTES:
        result.update(status="policy_denied", error="input_limit_exceeded")
        return result
    try:
        payload = json.dumps({"code": code, "stdin": stdin_input}, ensure_ascii=False).encode(
            "utf-8"
        )
    except UnicodeError:
        result.update(status="policy_denied", error="invalid_unicode_input")
        return result
    if len(payload) > INPUT_BYTES:
        result.update(status="policy_denied", error="input_limit_exceeded")
        return result
    provenance["resources"]["wall_seconds"] = timeout
    try:
        launcher, image, platform, socket = _settings()
    except PolicyError as exc:
        result.update(status="unavailable", error=str(exc))
        return result
    provenance.update(image_reference=image, platform=platform)
    name = f"matric-eval-{uuid.uuid4().hex}"
    created = False
    execution_attempted = False
    cleanup_identifier = name
    with tempfile.TemporaryDirectory(prefix="matric-docker-config-") as config_dir:
        command = [*launcher, "--config", config_dir, "--host", f"unix://{socket}"]
        try:
            runtime_query = _command([*command, "info", "--format", "{{json .}}"])
            if runtime_query.returncode != 0 or runtime_query.limit is not None:
                raise PolicyError("runtime_unavailable")
            runtime = _json(runtime_query)
            _verify_runtime(runtime)
            provenance.update(
                server_version=runtime.get("ServerVersion"),
                cgroup_version=runtime.get("CgroupVersion"),
                runtime="runc",
            )
            version_query = _command([*command, "version", "--format", "{{json .Server}}"])
            if version_query.returncode == 0 and version_query.limit is None:
                versions = _json(version_query)
                if isinstance(versions, dict):
                    for component in versions.get("Components", []):
                        if (
                            isinstance(component, dict)
                            and component.get("Name") == "runc"
                            and isinstance(component.get("Version"), str)
                        ):
                            provenance["runc_version"] = component["Version"]
                            provenance["runc_version_unavailable_reason"] = None
            image_query = _command([*command, "image", "inspect", image])
            if image_query.returncode != 0 or image_query.limit is not None:
                raise PolicyError("image_unavailable")
            inspected_image = _verify_image(_json(image_query), image, platform)
            provenance["image_id"] = inspected_image["Id"]
            # Mark attempted creation before invoking the daemon: a controller
            # timeout can leave a created container despite no returned ID.
            created = True
            creation = _command([*command, *_create_args(name, image, platform)])
            if creation.returncode != 0 or creation.limit is not None:
                result.update(status="unavailable", error="container_create_failed")
            else:
                container = _verify_container(
                    _json(_command([*command, "container", "inspect", name])),
                    name=name,
                    image_id=inspected_image["Id"],
                )
                provenance["container_id"] = container["Id"]
                cleanup_identifier = container["Id"]
                provenance["restrictions_verified"] = True
                execution_attempted = True
                execution = _command(
                    [*command, "container", "start", "--attach", "--interactive", name],
                    payload=payload,
                    timeout=float(timeout),
                    output_limit=OUTPUT_BYTES,
                )
                stdout, stderr, output_evidence = _decode_output(execution.stdout, execution.stderr)
                result["stdout"] = stdout
                result["stderr"] = stderr
                provenance["output"] = output_evidence
                execution_limit = execution.limit or (
                    "output_limit" if output_evidence["text_truncated"] else None
                )
                final_items = _json(
                    _command([*command, "container", "inspect", cleanup_identifier])
                )
                if (
                    not isinstance(final_items, list)
                    or len(final_items) != 1
                    or not isinstance(final_items[0], dict)
                    or final_items[0].get("Id") != cleanup_identifier
                    or not isinstance(final_items[0].get("State"), dict)
                ):
                    raise PolicyError("native_state_unverified")
                state = final_items[0]["State"]
                provenance["native_state"] = state.get("Status")
                provenance["native_started_at"] = state.get("StartedAt")
                provenance["native_exit_code"] = (
                    state.get("ExitCode") if state.get("Status") == "exited" else None
                )
                provenance["oom_killed"] = state.get("OOMKilled")
                if not _started(state) or state.get("Error") or state.get("OOMKilled"):
                    result.update(
                        status="infrastructure_error", error="native_execution_unavailable"
                    )
                elif execution_limit is not None:
                    result.update(status=execution_limit, error=execution_limit)
                elif (
                    state.get("Status") != "exited"
                    or not isinstance(state.get("ExitCode"), int)
                    or isinstance(state.get("ExitCode"), bool)
                ):
                    result.update(
                        status="infrastructure_error", error="native_execution_unavailable"
                    )
                elif state["ExitCode"] == 0 and execution.returncode == 0:
                    result.update(status="passed", error=None)
                elif state["ExitCode"] >= 126 or state["ExitCode"] < 0:
                    result.update(status="infrastructure_error", error="abnormal_process_exit")
                elif state["ExitCode"] != 0:
                    result.update(status="incorrect", error="generated_process_failed")
                else:
                    result.update(status="infrastructure_error", error="runtime_client_failed")
        except PolicyError as exc:
            result.update(
                status="infrastructure_error"
                if execution_attempted
                else "unavailable"
                if str(exc) in {"runtime_unavailable", "image_unavailable"}
                else "policy_denied",
                error=str(exc),
            )
        except FileNotFoundError:
            result.update(
                status="infrastructure_error" if execution_attempted else "unavailable",
                error="runtime_unavailable",
            )
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            TypeError,
            IndexError,
            AttributeError,
        ):
            result.update(status="infrastructure_error", error="runtime_operation_failed")
        finally:
            if created:
                cleaned = _cleanup(command, cleanup_identifier)
                provenance["cleanup"] = "verified_absent" if cleaned else "uncertain"
                if not cleaned:
                    result.update(status="infrastructure_error", error="cleanup_unverified")
    return result


def execute_python(
    code: str, stdin_input: str = "", timeout: float = MAX_WALL_SECONDS
) -> dict[str, Any]:
    """Public controller boundary: filesystem/runtime failures are unscored."""
    try:
        return _execute_python(code, stdin_input=stdin_input, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return {
            "status": "infrastructure_error",
            "stdout": "",
            "stderr": "",
            "error": "controller_operation_failed",
            "provenance": {
                "profile": PROFILE,
                "cleanup": "uncertain",
                "isolation": "docker-runc-shared-kernel",
            },
        }
