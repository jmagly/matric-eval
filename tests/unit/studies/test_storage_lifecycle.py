from pathlib import Path
from types import SimpleNamespace

import pytest

from matric_eval.storage import StorageBlocker
from matric_eval.studies.storage_lifecycle import docker_control_contract


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    path = tmp_path / "scratch"
    path.mkdir()
    config = {
        "allocations": [
            {"kind": "scratch", "path": str(path), "budget_bytes": 1024, "budget_inodes": 4}
        ]
    }
    docker = SimpleNamespace(host="unix:///owned.sock", command=lambda *args: ["docker", *args])
    monkeypatch.setattr(
        "matric_eval.studies.storage_lifecycle.subprocess.check_output",
        lambda *args, **kwargs: str(tmp_path / "docker"),
    )
    command = [
        "docker",
        "--host",
        docker.host,
        "run",
        "--read-only",
        "--pull",
        "never",
        "--log-driver",
        "none",
        "--mount",
        f"type=bind,src={path},dst=/tmp",
        "pinned-image",
    ]
    return command, config, docker


def test_finite_docker_contract_reports_actual_daemon_root(fixture):
    command, config, docker = fixture
    result = docker_control_contract(command, config, docker)
    assert Path(result["root"]).name == "docker"
    assert result["container_limit"] == 1
    assert "not a kernel quota" in result["enforcement"]


@pytest.mark.parametrize(
    "extra",
    [
        ["--pull", "always"],
        ["--log-driver=json-file"],
        ["--privileged=true"],
        ["--mount=type=bind,src=/,dst=/host"],
        ["--volume", "/:/host"],
        ["--read-only=false"],
        ["--tmpfs", "/tmp"],
        ["--restart", "always"],
    ],
)
def test_unbounded_docker_variants_cannot_use_control_metadata_allowance(fixture, extra):
    command, config, docker = fixture
    with pytest.raises(StorageBlocker, match="storage_docker_contract"):
        docker_control_contract(command + extra, config, docker)


def test_undeclared_writable_mount_rejected(fixture):
    command, config, docker = fixture
    with pytest.raises(StorageBlocker, match="outside declared"):
        docker_control_contract(command + ["--mount", "type=bind,src=/,dst=/host"], config, docker)
