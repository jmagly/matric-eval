"""Controller tests mock Docker; generated code is never executed by these tests."""

import copy
import json
from typing import Any
from unittest.mock import Mock

import pytest

from matric_eval.scorers import isolated_execution as runner

IMAGE = "python@sha256:" + "a" * 64
IMAGE_ID = "sha256:" + "b" * 64
CONTAINER_ID = "c" * 64


def runtime() -> dict[str, Any]:
    return {
        "SecurityOptions": ["name=seccomp,profile=builtin", "name=apparmor"],
        "OSType": "linux",
        "MemoryLimit": True,
        "SwapLimit": True,
        "PidsLimit": True,
        "CpuCfsQuota": True,
        "CpuCfsPeriod": True,
        "Runtimes": {"runc": {}},
        "ServerVersion": "test",
        "CgroupVersion": "2",
    }


def container(name: str) -> dict[str, Any]:
    return {
        "Id": CONTAINER_ID,
        "Image": IMAGE_ID,
        "Name": f"/{name}",
        "State": {"Status": "created"},
        "Mounts": [],
        "NetworkSettings": {"Networks": {"none": {}}},
        "HostConfig": {
            "Privileged": False,
            "ReadonlyRootfs": True,
            "NetworkMode": "none",
            "Memory": runner.MEMORY_BYTES,
            "MemorySwap": runner.MEMORY_BYTES,
            "NanoCpus": 1000000000,
            "PidsLimit": 32,
            "Init": True,
            "IpcMode": "private",
            "CgroupnsMode": "private",
            "Runtime": "runc",
            "ShmSize": runner.TMPFS_BYTES,
            "PublishAllPorts": False,
            "CapDrop": ["ALL"],
            "CapAdd": None,
            "SecurityOpt": ["no-new-privileges", "apparmor=docker-default"],
            "PidMode": "",
            "UTSMode": "",
            "UsernsMode": "",
            "Tmpfs": {"/tmp": runner.TMPFS},
            "LogConfig": {"Type": "none"},
            "RestartPolicy": {"Name": "no"},
        },
        "Config": {
            "User": "65534:65534",
            "WorkingDir": "/tmp",
            "Tty": False,
            "Entrypoint": ["/usr/bin/env"],
            "Cmd": runner.COMMAND,
            "Labels": {runner.LABEL: name},
        },
    }


class Docker:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.name = ""
        self.inspections = 0
        self.exit_code = 0
        self.execution_limit: str | None = None
        self.create_limit: str | None = None
        self.cleanup_remaining = False
        self.mutation: Any = None
        self.cancel = False
        self.oom = False

    def __call__(self, args: list[str], **kwargs: Any) -> runner.CommandResult:
        self.calls.append((args, kwargs))
        if "info" in args:
            return self.json(runtime())
        if "version" in args:
            return self.json({"Components": [{"Name": "runc", "Version": "test-runc"}]})
        if "image" in args:
            return self.json(
                [
                    {
                        "Id": IMAGE_ID,
                        "RepoDigests": [IMAGE],
                        "Os": "linux",
                        "Architecture": "amd64",
                        "Config": {},
                    }
                ]
            )
        if "create" in args:
            self.name = args[args.index("--name") + 1]
            return runner.CommandResult(0, CONTAINER_ID.encode(), b"", self.create_limit)
        if "inspect" in args:
            self.inspections += 1
            data = container(self.name)
            if self.inspections == 1 and self.mutation is not None:
                self.mutation(data)
            if self.inspections > 1:
                data["State"] = {
                    "Status": "exited",
                    "ExitCode": self.exit_code,
                    "Error": "",
                    "OOMKilled": self.oom,
                }
            return self.json([data])
        if "start" in args:
            if self.cancel:
                raise KeyboardInterrupt
            return runner.CommandResult(self.exit_code, b"answer\n", b"", self.execution_limit)
        if "rm" in args:
            return runner.CommandResult(0, b"", b"")
        if "ls" in args:
            return runner.CommandResult(
                0, CONTAINER_ID.encode() if self.cleanup_remaining else b"", b""
            )
        raise AssertionError("unexpected controller operation")

    @staticmethod
    def json(value: Any) -> runner.CommandResult:
        return runner.CommandResult(0, json.dumps(value).encode(), b"")


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> Docker:
    monkeypatch.setenv("MATRIC_EVAL_SANDBOX_IMAGE", IMAGE)
    monkeypatch.delenv("MATRIC_EVAL_SANDBOX_COMMAND", raising=False)
    monkeypatch.delenv("MATRIC_EVAL_SANDBOX_SOCKET", raising=False)
    monkeypatch.delenv("MATRIC_EVAL_SANDBOX_PLATFORM", raising=False)
    fake = Docker()
    monkeypatch.setattr(runner, "_command", fake)
    return fake


def test_only_fixed_bootstrap_is_argv_and_payload_uses_stdin(docker: Docker) -> None:
    generated = "print('not executed locally')"
    result = runner.execute_python(generated, stdin_input="hello")
    assert result["status"] == "passed"
    assert result["stdout"] == "answer\n"
    assert result["provenance"]["cleanup"] == "verified_absent"
    assert result["provenance"]["container_id"] == CONTAINER_ID
    assert result["provenance"]["image_id"] == IMAGE_ID
    assert len(result["provenance"]["bootstrap_sha256"]) == 64
    assert len(result["provenance"]["profile_sha256"]) == 64
    assert result["provenance"]["runc_version"] == "test-runc"
    created = next(args for args, _ in docker.calls if "create" in args)
    assert generated not in created
    assert "--pull=never" in created
    assert "--user=65534:65534" in created
    assert "--memory-swap=268435456" in created
    assert "--network=none" in created
    assert "--pids-limit=32" in created
    assert "--entrypoint=/usr/bin/env" in created
    attached, options = next((args, kw) for args, kw in docker.calls if "start" in args)
    assert attached[-1] == docker.name
    assert json.loads(options["payload"]) == {"code": generated, "stdin": "hello"}
    assert options["output_limit"] == runner.OUTPUT_BYTES
    removed = next(args for args, _ in docker.calls if "rm" in args)
    assert removed[-1] == CONTAINER_ID


@pytest.mark.parametrize("status", ["timeout", "output_limit"])
def test_resource_limits_require_verified_cleanup(docker: Docker, status: str) -> None:
    docker.execution_limit = status
    result = runner.execute_python("pass")
    assert result["status"] == status
    assert result["provenance"]["cleanup"] == "verified_absent"
    docker.inspections = 0
    docker.cleanup_remaining = True
    result = runner.execute_python("pass")
    assert result["status"] == "infrastructure_error"
    assert result["error"] == "cleanup_unverified"


def test_incorrect_exit_and_oom_are_distinct(docker: Docker) -> None:
    docker.exit_code = 1
    result = runner.execute_python("assert False")
    assert result["status"] == "incorrect"
    assert result["error"] == "generated_process_failed"
    docker.inspections = 0
    docker.oom = True
    assert runner.execute_python("pass")["status"] == "infrastructure_error"


def test_uncertain_creation_still_removes_unique_name(docker: Docker) -> None:
    docker.create_limit = "timeout"
    result = runner.execute_python("pass")
    assert result["status"] == "unavailable"
    assert not any("start" in args for args, _ in docker.calls)
    assert next(args for args, _ in docker.calls if "rm" in args)[-1] == docker.name
    assert result["provenance"]["cleanup"] == "verified_absent"


def test_cancellation_removes_container_before_propagating(docker: Docker) -> None:
    docker.cancel = True
    with pytest.raises(KeyboardInterrupt):
        runner.execute_python("pass")
    assert any("rm" in args for args, _ in docker.calls)
    assert any("ls" in args for args, _ in docker.calls)


@pytest.mark.parametrize(
    "field,value",
    [
        ("Privileged", True),
        ("ReadonlyRootfs", False),
        ("NetworkMode", "host"),
        ("Memory", 0),
        ("MemorySwap", -1),
        ("NanoCpus", 0),
        ("PidsLimit", -1),
        ("CapAdd", ["SYS_ADMIN"]),
        ("Devices", [{"PathOnHost": "/dev/nvidia0"}]),
        ("Binds", ["/home:/host"]),
        ("PidMode", "host"),
        ("UTSMode", "host"),
        ("SecurityOpt", ["seccomp=unconfined"]),
        ("Runtime", "unexpected"),
        ("Tmpfs", {"/tmp": "rw"}),
        ("GroupAdd", ["0"]),
    ],
)
def test_effective_policy_drift_prevents_start(docker: Docker, field: str, value: Any) -> None:
    docker.mutation = lambda item: item["HostConfig"].update({field: value})
    result = runner.execute_python("pass")
    assert result["status"] == "policy_denied"
    assert result["provenance"]["cleanup"] == "verified_absent"
    assert not any("start" in args for args, _ in docker.calls)


@pytest.mark.parametrize(
    "change",
    [
        lambda item: item["Config"].update(User="0"),
        lambda item: item["Config"].update(Cmd=["evil"]),
        lambda item: item.update(Image="sha256:" + "d" * 64),
        lambda item: item.update(Mounts=[{"Type": "bind", "Source": "/"}]),
        lambda item: item["NetworkSettings"].update(Networks={"bridge": {}}),
    ],
)
def test_process_image_mount_and_network_drift_prevent_start(docker: Docker, change: Any) -> None:
    docker.mutation = change
    assert runner.execute_python("pass")["status"] == "policy_denied"
    assert not any("start" in args for args, _ in docker.calls)


@pytest.mark.parametrize("timeout", [0, -1, 31, True, float("nan"), float("inf")])
def test_invalid_requests_do_not_call_runtime(docker: Docker, timeout: float) -> None:
    assert runner.execute_python("pass", timeout=timeout)["status"] == "policy_denied"
    assert not docker.calls


def test_oversized_input_is_not_transferred(docker: Docker) -> None:
    assert runner.execute_python("x" * runner.INPUT_BYTES)["error"] == "input_limit_exceeded"
    assert not docker.calls


def test_missing_image_and_invalid_launcher_never_fall_back(
    monkeypatch: pytest.MonkeyPatch, docker: Docker
) -> None:
    monkeypatch.delenv("MATRIC_EVAL_SANDBOX_IMAGE")
    assert runner.execute_python("pass")["error"] == "pinned_image_required"
    monkeypatch.setenv("MATRIC_EVAL_SANDBOX_IMAGE", IMAGE)
    monkeypatch.setenv("MATRIC_EVAL_SANDBOX_COMMAND", "sudo docker")
    assert runner.execute_python("pass")["error"] == "invalid_launcher"
    assert not docker.calls


def test_explicit_launcher_local_socket_and_empty_config_override_ambient(
    monkeypatch: pytest.MonkeyPatch, docker: Docker
) -> None:
    monkeypatch.setenv("MATRIC_EVAL_SANDBOX_COMMAND", '["sudo", "-n", "docker"]')
    monkeypatch.setenv("DOCKER_HOST", "tcp://untrusted:2375")
    monkeypatch.setenv("DOCKER_CONTEXT", "ambient")
    monkeypatch.setenv("MATRIC_EVAL_SANDBOX_SOCKET", "/run/qualified.sock")
    assert runner.execute_python("pass")["status"] == "passed"
    for args, _ in docker.calls:
        assert args[:3] == ["sudo", "-n", "docker"]
        assert args[args.index("--host") + 1] == "unix:///run/qualified.sock"
        assert "--config" in args
        assert "untrusted" not in " ".join(args)


def test_runtime_security_and_controller_support_are_required() -> None:
    good = runtime()
    runner._verify_runtime(good)
    for field in (
        "SecurityOptions",
        "MemoryLimit",
        "SwapLimit",
        "PidsLimit",
        "CpuCfsQuota",
        "CpuCfsPeriod",
    ):
        bad = copy.deepcopy(good)
        bad[field] = [] if field == "SecurityOptions" else False
        with pytest.raises(runner.PolicyError):
            runner._verify_runtime(bad)


def test_missing_runtime_is_unavailable(monkeypatch: pytest.MonkeyPatch, docker: Docker) -> None:
    monkeypatch.setattr(runner, "_command", Mock(side_effect=FileNotFoundError()))
    result = runner.execute_python("pass")
    assert result["status"] == "unavailable"
    assert result["provenance"]["cleanup"] == "not_created"


def test_temporary_configuration_failure_is_unscored(
    monkeypatch: pytest.MonkeyPatch, docker: Docker
) -> None:
    monkeypatch.setattr(
        runner.tempfile, "TemporaryDirectory", Mock(side_effect=OSError("private detail"))
    )
    result = runner.execute_python("pass")
    assert result["status"] == "infrastructure_error"
    assert result["error"] == "controller_operation_failed"
    assert "private detail" not in str(result)
    assert not docker.calls


def test_invalid_utf8_cannot_expand_returned_text_beyond_output_cap() -> None:
    raw_stdout = b"\xff" * (runner.OUTPUT_BYTES // 2)
    raw_stderr = b"\xfe" * (runner.OUTPUT_BYTES // 2)
    stdout, stderr, evidence = runner._decode_output(raw_stdout, raw_stderr)
    assert len(stdout.encode()) + len(stderr.encode()) <= runner.OUTPUT_BYTES
    assert evidence["invalid_utf8_replaced"]
    assert evidence["text_truncated"]
    assert evidence["stdout_raw_bytes"] + evidence["stderr_raw_bytes"] == runner.OUTPUT_BYTES
    assert len(evidence["stdout_raw_sha256"]) == 64


def test_nonbuiltin_seccomp_profile_is_not_implicitly_qualified() -> None:
    info = runtime()
    info["SecurityOptions"] = ["name=seccomp,profile=custom", "name=apparmor"]
    with pytest.raises(runner.PolicyError, match="security_profiles_unavailable"):
        runner._verify_runtime(info)


@pytest.mark.parametrize("exit_code", [126, 127, 137, 143])
def test_abnormal_native_exit_is_not_a_measured_failure(docker: Docker, exit_code: int) -> None:
    docker.exit_code = exit_code
    result = runner.execute_python("pass")
    assert result["status"] == "infrastructure_error"
    assert result["error"] == "abnormal_process_exit"
    assert result["provenance"]["native_exit_code"] == exit_code
    assert result["provenance"]["cleanup"] == "verified_absent"
