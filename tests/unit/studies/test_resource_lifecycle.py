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
            self.leases = [
                lease for lease in self.leases if lease["token"] != fields["token"]
            ]
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
    lifecycle.broker.call(
        "acquire", owner=lifecycle.record["owner"], gpu_uuids=["GPU-owned"]
    )
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
        for key in ("container", "unit", "readiness", "owner"):
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
