import pytest

from matric_eval.studies.resource_lifecycle import ResourceLifecycle


class FakeBroker:
    def __init__(self):
        self.leases = []
        self.released = []
        self.offline = False

    def call(self, action, **fields):
        if self.offline:
            raise OSError("offline")
        if action == "acquire":
            lease = {
                "owner": fields["owner"],
                "gpu_uuids": fields["gpu_uuids"],
                "token": "private-token",
            }
            self.leases.append(lease)
            return {"lease": lease}
        if action == "release":
            self.released.append(fields["token"])
            self.leases = [lease for lease in self.leases if lease["token"] != fields["token"]]
        return {"leases": self.leases}


class FakeDocker:
    def __init__(self):
        self.info = None
        self.allocations = []
        self.stopped = []

    def inspect(self, name):
        return self.info

    def cuda(self):
        return self.allocations

    def cgroup(self, pid):
        return ""

    def stop(self, identifier):
        self.stopped.append(identifier)
        self.info["State"]["Running"] = False


@pytest.fixture
def lifecycle(tmp_path):
    broker, docker = FakeBroker(), FakeDocker()
    value = ResourceLifecycle(tmp_path / "owned", broker, docker)
    value.prepare("existing-run", "existing-attempt", "GPU-owned", "qualification")
    yield value
    value.close()


def test_private_exact_lease_and_idempotent_release(lifecycle):
    lifecycle.acquire()
    assert "private-token" not in lifecycle.path.read_text()
    assert lifecycle.private.stat().st_mode & 0o077 == 0
    assert lifecycle.reconcile()
    assert lifecycle.reconcile()
    assert lifecycle.broker.released == ["private-token"]


def test_outage_retains_obligation_and_reconnect(lifecycle):
    lifecycle.acquire()
    lifecycle.broker.offline = True
    assert not lifecycle.reconcile()
    assert lifecycle.record["cleanup"] == "pending"
    assert lifecycle.private.exists()
    lifecycle.broker.offline = False
    assert lifecycle.reconcile()


def test_lost_acquire_ack_recovered_by_exact_owner(lifecycle):
    lifecycle.save(state="acquiring")
    lifecycle.broker.call("acquire", owner=lifecycle.record["owner"], gpu_uuids=["GPU-owned"])
    assert lifecycle.reconcile()
    assert lifecycle.broker.released == ["private-token"]


def test_unrelated_container_never_stopped_or_released(lifecycle):
    lifecycle.acquire()
    lifecycle.docker.info = {"Config": {"Labels": {"matric.resource": "unrelated"}}}
    assert not lifecycle.reconcile()
    assert not lifecycle.docker.stopped
    assert not lifecycle.broker.released


def test_live_cuda_prevents_release(lifecycle):
    lifecycle.acquire()
    lifecycle.save(cuda_pids=[12345])
    lifecycle.docker.allocations = [("GPU-owned", 12345)]
    assert not lifecycle.reconcile()
    assert not lifecycle.broker.released


def test_disappearing_launched_container_fails_closed(lifecycle):
    lifecycle.acquire()
    lifecycle.save(state_before_launch="launched")
    assert not lifecycle.reconcile()
    assert not lifecycle.broker.released


def test_scope_mismatch_never_released(lifecycle):
    lifecycle.acquire()
    lifecycle.broker.leases[0]["gpu_uuids"] = ["GPU-other"]
    assert not lifecycle.reconcile()
    assert not lifecycle.broker.released


def test_unique_names_and_no_reused_directory(lifecycle, tmp_path):
    other = ResourceLifecycle(tmp_path / "other", FakeBroker(), FakeDocker())
    try:
        other.prepare("existing-run", "next-attempt", "GPU-owned", "qualification")
        for key in ("container", "readiness", "owner"):
            assert lifecycle.record[key] != other.record[key]
        with pytest.raises(RuntimeError):
            lifecycle.prepare("r", "a", "GPU-owned", "owner")
    finally:
        other.close()


def test_other_pending_attempt_blocks_acquire(lifecycle, tmp_path):
    other = ResourceLifecycle(tmp_path / "next", FakeBroker(), FakeDocker())
    try:
        other.prepare("existing-run", "next", "GPU-owned", "qualification")
        with pytest.raises(RuntimeError, match="unresolved"):
            other.acquire()
        assert not other.broker.leases
    finally:
        other.close()


def test_real_unix_transport_redacts_broker_error(tmp_path):
    import socket
    import threading

    from matric_eval.studies.resource_lifecycle import Broker

    path = str(tmp_path / "broker.sock")
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(path)
        server.listen()

        def respond():
            client, _ = server.accept()
            with client:
                client.recv(4096)
                client.sendall(b'{"ok":false,"error":"private-token"}\n')

        worker = threading.Thread(target=respond)
        worker.start()
        with pytest.raises(RuntimeError, match="broker release failed") as error:
            Broker(path).call("release", token="private-token")
        assert "private-token" not in str(error.value)
        worker.join()


def test_owned_container_stopped_before_release(lifecycle):
    lifecycle.acquire()
    lifecycle.docker.info = {
        "Id": "owned-container-id",
        "Config": {"Labels": {"matric.resource": lifecycle.record["resource_id"]}},
        "State": {"Running": True, "Pid": 1234},
    }
    events = []
    original_stop = lifecycle.docker.stop

    def stop(identifier):
        events.append("stop")
        original_stop(identifier)

    lifecycle.docker.stop = stop
    lifecycle.docker.remove = lambda identifier: events.append("remove")
    original_call = lifecycle.broker.call

    def call(action, **fields):
        if action == "release":
            assert not lifecycle.docker.info["State"]["Running"]
            assert lifecycle.record["cuda_release_verified_at"] > 0
            events.append("release")
        return original_call(action, **fields)

    lifecycle.broker.call = call
    assert lifecycle.reconcile()
    assert events == ["stop", "release", "remove"]


def attach_owned_container(lifecycle):
    lifecycle.docker.info = {
        "Id": "owned-container-id",
        "Config": {"Labels": {"matric.resource": lifecycle.record["resource_id"]}},
        "State": {"Running": True, "Pid": 1234},
    }
    lifecycle.docker.remove = lambda identifier: None


def test_readiness_timeout_stops_real_child_and_cleans_lease(lifecycle, admission_plan):
    import sys

    from matric_eval.studies.resource_lifecycle import alive

    attach_owned_container(lifecycle)
    with pytest.raises(TimeoutError, match="readiness"):
        lifecycle.run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.1,
            preflight_plan=admission_plan,
        )
    assert not alive(lifecycle.record["launcher"])
    assert lifecycle.record["cleanup"] == "complete"
    assert lifecycle.broker.released == ["private-token"]


def test_sigterm_stops_real_child_and_cleans_lease(lifecycle, admission_plan):
    import os
    import signal
    import sys
    import threading

    from matric_eval.studies.resource_lifecycle import alive

    attach_owned_container(lifecycle)
    stop = threading.Event()

    def cancel_when_loading():
        while not stop.wait(0.05):
            if lifecycle.record.get("state") == "loading":
                os.kill(os.getpid(), signal.SIGTERM)
                return

    timer = threading.Thread(target=cancel_when_loading)
    timer.start()
    try:
        with pytest.raises(InterruptedError):
            lifecycle.run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                preflight_plan=admission_plan,
            )
    finally:
        stop.set()
        timer.join()
    assert not alive(lifecycle.record["launcher"])
    assert lifecycle.record["cleanup"] == "complete"


def test_changed_boot_reconciles_absent_old_container(lifecycle):
    lifecycle.acquire()
    lifecycle.save(boot_id="previous-boot", state_before_launch="launched")
    assert lifecycle.reconcile()
    assert lifecycle.broker.released == ["private-token"]


@pytest.fixture
def admission_plan(tmp_path):
    import sys

    from matric_eval.studies.preflight import SCHEMA

    script = tmp_path / "check.py"
    script.write_text(
        "import os,json,pathlib; pathlib.Path(os.environ['MATRIC_PREFLIGHT_RECEIPT']).write_text(json.dumps({'passed':True}))"
    )
    return {
        "schema": SCHEMA,
        "checks": [
            {
                "id": stage,
                "stage": stage,
                "command": [sys.executable, str(script)],
                "inputs": [str(script)],
                "timeout_seconds": 5,
                "freshness_seconds": 60,
                "deterministic": False,
                "receipt_contract": {"passed": True},
            }
            for stage in ("static", "cpu", "auxiliary", "target")
        ],
    }


def test_failed_preflight_never_acquires(lifecycle, admission_plan):
    import sys

    admission_plan["checks"][0]["command"] = [
        sys.executable,
        "-c",
        "raise SystemExit(1)",
    ]
    with pytest.raises(ValueError, match="admission"):
        lifecycle.run([sys.executable, "-c", "pass"], preflight_plan=admission_plan)
    assert not lifecycle.broker.leases
    assert not lifecycle.broker.released
    assert lifecycle.record["cleanup"] == "complete"


def test_other_host_fails_closed(lifecycle):
    lifecycle.acquire()
    lifecycle.save(host="another-host")
    assert not lifecycle.reconcile()
    assert not lifecycle.broker.released


def test_failed_resident_preflight_stops_loaded_child(lifecycle, admission_plan):
    import sys

    attach_owned_container(lifecycle)
    admission_plan["checks"][-1]["command"] = [
        sys.executable,
        "-c",
        "raise SystemExit(7)",
    ]
    code = "import hashlib,json,os,pathlib,time; token=os.environ['OLLAMA_UNIFY_GPU_LEASE']; pathlib.Path('{ready_base}.'+token+'.ready').write_text(json.dumps({'lease_token_sha256':hashlib.sha256(token.encode()).hexdigest()})); time.sleep(30)"
    with pytest.raises(RuntimeError, match="resident target preflight failed"):
        lifecycle.run([sys.executable, "-c", code], preflight_plan=admission_plan)
    assert lifecycle.record["cleanup"] == "complete"
    assert lifecycle.broker.released == ["private-token"]


def test_lost_release_ack_removes_owned_readiness(lifecycle):
    from pathlib import Path

    token = lifecycle.acquire()
    marker = Path(f"{lifecycle.record['readiness']}.{token}.ready")
    marker.touch()
    lifecycle.broker.leases.clear()
    assert lifecycle.reconcile()
    assert not marker.exists()
    assert not lifecycle.broker.released


def test_replaced_container_identity_is_not_stopped(lifecycle):
    lifecycle.acquire()
    attach_owned_container(lifecycle)
    lifecycle.save(container_id="original-id")
    assert not lifecycle.reconcile()
    assert lifecycle.record["reason"] == "container identity changed"
    assert not lifecycle.docker.stopped
    assert not lifecycle.broker.released
