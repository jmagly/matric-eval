import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from matric_eval.storage import StorageBlocker
from matric_eval.studies.storage_lifecycle import docker_control_contract


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "matric_eval.studies.storage_lifecycle.require_daemon_mount_namespace", lambda host: None
    )
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
        lambda command, **kwargs: (
            json.dumps([{"Id": "sha256:" + "a" * 64, "Config": {"Volumes": None}}])
            if "inspect" in command
            else str(tmp_path / "docker")
        ),
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
        "--ipc",
        "private",
        "--mount",
        f"type=bind,src={path},dst=/tmp",
        "--mount",
        f"type=bind,src={path},dst=/dev/shm",
        "image@sha256:" + "a" * 64,
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
        ["--ipc", "host"],
        ["--ipc", "container:foreign"],
    ],
)
def test_unbounded_docker_variants_cannot_use_control_metadata_allowance(fixture, extra):
    command, config, docker = fixture
    with pytest.raises(StorageBlocker, match="storage_docker_contract"):
        docker_control_contract(command[:-1] + extra + command[-1:], config, docker)


def test_undeclared_writable_mount_rejected(fixture):
    command, config, docker = fixture
    with pytest.raises(StorageBlocker, match="outside declared"):
        docker_control_contract(
            command[:-1] + ["--mount", "type=bind,src=/,dst=/host"] + command[-1:], config, docker
        )


def test_container_arguments_cannot_satisfy_docker_controls(fixture):
    command, config, docker = fixture
    reordered = command[:4] + command[-1:] + command[4:-1]
    with pytest.raises(StorageBlocker, match="before IMAGE"):
        docker_control_contract(reordered, config, docker)


def test_image_implicit_writable_volume_is_rejected(fixture, monkeypatch):
    command, config, docker = fixture
    monkeypatch.setattr(
        "matric_eval.studies.storage_lifecycle.subprocess.check_output",
        lambda *args, **kwargs: json.dumps(
            [{"Id": "sha256:" + "a" * 64, "Config": {"Volumes": {"/unbounded": {}}}}]
        ),
    )
    with pytest.raises(StorageBlocker, match="image-declared"):
        docker_control_contract(command, config, docker)


@pytest.mark.parametrize("failure_point", ["ledger", "status"])
def test_crash_reconciliation_retries_storage_projection_failure(
    tmp_path, monkeypatch, failure_point
):
    import matric_eval.studies.resource_lifecycle as module
    from matric_eval.storage import filesystem
    from matric_eval.studies.resource_lifecycle import ResourceLifecycle
    from matric_eval.studies.run_status import RunStatus

    status = RunStatus.create(
        tmp_path / "status",
        run_id="r",
        attempt_id="a",
        tasks=[{"model_id": "m", "suite_id": "s", "task_id": "t"}],
    )
    monkeypatch.setenv("MATRIC_RUN_STATUS_DIR", str(status.directory))
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    resource = ResourceLifecycle(
        tmp_path / "resource",
        SimpleNamespace(call=lambda *args, **kwargs: {"leases": []}),
        SimpleNamespace(inspect=lambda name: None, cuda=lambda: []),
    )
    try:
        resource.prepare("r", "a", "GPU-owned", "owner")
        reservation = {
            "ledger": str(ledger),
            "ledger_identity": filesystem(ledger),
            "owner": "owned-storage",
        }
        resource.save(
            cleanup="complete", storage_reservation=reservation, storage_reservation_active=True
        )
        with status.update() as data:
            data["storage"] = {"owner": "owned-storage", "reservation_active": True}
        ledger_path = ledger / "reservations.json"
        ledger_path.write_text(
            json.dumps(
                {
                    "owned-storage": {
                        "pid": 99999999,
                        "identity": "dead-controller",
                        "resource_record": str(resource.path.resolve()),
                    },
                    "unrelated": {"pid": 1},
                }
            )
        )
        failed = False
        original_atomic = module.atomic
        original_update = RunStatus.update

        def atomic(path, value):
            nonlocal failed
            if failure_point == "ledger" and path == ledger_path and not failed:
                failed = True
                raise OSError("ledger unavailable")
            original_atomic(path, value)

        def update(instance):
            nonlocal failed
            if failure_point == "status" and not failed:
                failed = True
                raise OSError("status unavailable")
            return original_update(instance)

        monkeypatch.setattr(module, "atomic", atomic)
        monkeypatch.setattr(RunStatus, "update", update)
        assert not resource.reconcile()
        assert resource.record["cleanup"] == "pending"
        assert resource.reconcile()
        assert resource.record["storage_reservation_active"] is False
        assert status.read(reconcile=False)["storage"]["reservation_active"] is False
        assert set(json.loads(ledger_path.read_text())) == {"unrelated"}
    finally:
        resource.close()


def test_private_client_mount_view_is_not_a_daemon_storage_bound(fixture, monkeypatch):
    command, config, docker = fixture

    def reject(host):
        raise StorageBlocker("storage_docker_contract", "mount views differ")

    monkeypatch.setattr(
        "matric_eval.studies.storage_lifecycle.require_daemon_mount_namespace", reject
    )
    with pytest.raises(StorageBlocker, match="mount views differ"):
        docker_control_contract(command, config, docker)
