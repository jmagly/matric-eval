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

    from matric_eval.studies.resource_lifecycle import Broker, BrokerRejected

    path = str(tmp_path / "broker.sock")
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(path)
        server.listen()

        def respond():
            client, _ = server.accept()
            with client:
                client.recv(4096)
                client.sendall(
                    b'{"ok":false,"error":"private-token","error_type":"CapacityError"}\n'
                )

        worker = threading.Thread(target=respond)
        worker.start()
        with pytest.raises(BrokerRejected, match="broker release rejected") as error:
            Broker(path).call("release", token="private-token")
        assert "private-token" not in str(error.value)
        worker.join()


@pytest.mark.parametrize(
    "response",
    [
        b'{"ok":false,"error":"denied"}\n',
        b'{"ok":false,"error_type":"CapacityError"}\n',
        b'{"ok":"false","error":"denied","error_type":"CapacityError"}\n',
    ],
)
def test_incomplete_broker_rejection_is_not_terminal(tmp_path, response):
    import socket
    import threading

    from matric_eval.studies.resource_lifecycle import Broker, BrokerRejected

    path = str(tmp_path / "broker.sock")
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(path)
        server.listen()

        def respond():
            client, _ = server.accept()
            with client:
                client.recv(4096)
                client.sendall(response)

        worker = threading.Thread(target=respond)
        worker.start()
        with pytest.raises(RuntimeError) as error:
            Broker(path).call("acquire", owner="owned", requested_mib=1)
        assert not isinstance(error.value, BrokerRejected)
        worker.join()


def test_structured_acquire_rejection_is_settled(lifecycle):
    from matric_eval.studies.resource_lifecycle import BrokerRejected

    original = lifecycle.broker.call

    def reject(action, **fields):
        if action == "acquire":
            raise BrokerRejected("broker acquire rejected request")
        return original(action, **fields)

    lifecycle.broker.call = reject
    with pytest.raises(BrokerRejected, match="acquire rejected"):
        lifecycle.acquire()
    assert lifecycle.record["acquisition_outcome"] == "rejected"
    assert lifecycle.record["acquisition_rejection_acknowledged_at"] > 0
    assert lifecycle.reconcile()
    assert lifecycle.record["cleanup"] == "complete"


def test_real_unix_acquire_rejection_reconciles_without_lease(tmp_path):
    import json
    import socket
    import threading

    from matric_eval.studies.resource_lifecycle import Broker, BrokerRejected

    path = str(tmp_path / "broker.sock")
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(path)
        server.listen()

        def respond():
            for index in range(2):
                client, _ = server.accept()
                with client:
                    request = json.loads(client.recv(4096))
                    if index == 0:
                        assert request["action"] == "acquire"
                        response = {
                            "ok": False,
                            "error": "capacity unavailable",
                            "error_type": "CapacityError",
                        }
                    else:
                        assert request["action"] == "status"
                        response = {"ok": True, "leases": []}
                    client.sendall(json.dumps(response).encode() + b"\n")

        worker = threading.Thread(target=respond)
        worker.start()
        value = ResourceLifecycle(tmp_path / "owned", Broker(path), FakeDocker())
        try:
            value.prepare("run", "attempt", "GPU-owned", "test")
            with pytest.raises(BrokerRejected):
                value.acquire()
            assert value.reconcile()
            assert value.record["cleanup"] == "complete"
            assert value.record["acquisition_outcome"] == "rejected"
        finally:
            value.close()
            worker.join(timeout=5)
        assert not worker.is_alive()


def test_rejection_after_persisted_lease_is_recovered(lifecycle):
    from matric_eval.studies.resource_lifecycle import BrokerRejected

    original = lifecycle.broker.call

    def reject_after_grant(action, **fields):
        if action == "acquire":
            original(action, **fields)
            raise BrokerRejected("broker acquire rejected request")
        return original(action, **fields)

    lifecycle.broker.call = reject_after_grant
    with pytest.raises(BrokerRejected, match="acquire rejected"):
        lifecycle.acquire()
    assert lifecycle.record["acquisition_outcome"] == "rejected"
    assert lifecycle.reconcile()
    assert lifecycle.record["acquisition_outcome"] == "acknowledged"
    assert lifecycle.broker.released == ["private-token"]


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


def test_resident_preflight_age_includes_readiness_window(lifecycle, admission_plan, monkeypatch):
    import sys

    import matric_eval.studies.resource_lifecycle as resource_lifecycle

    attach_owned_container(lifecycle)
    observed = {}

    def qualify(plan, receipt_path, admission, *, max_age_seconds):
        observed["max_age_seconds"] = max_age_seconds
        return {"completed": True}

    monkeypatch.setattr(resource_lifecycle, "execute_target_checks", qualify)
    code = """
import hashlib,json,os,pathlib,time
token=os.environ['OLLAMA_UNIFY_GPU_LEASE']
pathlib.Path('{ready_base}.'+token+'.ready').write_text(json.dumps({'lease_token_sha256':hashlib.sha256(token.encode()).hexdigest()}))
time.sleep(.2)
"""
    assert (
        lifecycle.run([sys.executable, "-c", code], timeout=12.5, preflight_plan=admission_plan)
        == 0
    )
    assert observed == {"max_age_seconds": 312.5}
    assert lifecycle.record["cleanup"] == "complete"


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


def test_new_boot_still_checks_current_owned_cuda(lifecycle):
    lifecycle.acquire()
    attach_owned_container(lifecycle)
    lifecycle.save(boot_id="old-boot")
    lifecycle.docker.allocations = [("GPU-owned", 99999999)]
    lifecycle.docker.cgroup = lambda pid: "owned-container-id" if pid == 99999999 else ""
    assert not lifecycle.reconcile()
    assert lifecycle.record["reason"] == "owned CUDA allocation remains"
    assert not lifecycle.broker.released


@pytest.mark.parametrize("owned", [True, False])
def test_orphan_launcher_session_is_extinct_before_release(lifecycle, tmp_path, owned):
    import os
    import signal
    import subprocess
    import sys

    from matric_eval.studies.resource_lifecycle import process_identity

    lifecycle.acquire()
    attach_owned_container(lifecycle)
    path = tmp_path / "orphan.pid"
    environment = {
        **os.environ,
        "MATRIC_RESOURCE_ID": lifecycle.record["resource_id"] if owned else "another-attempt",
    }
    command = f'import subprocess,sys,pathlib,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); pathlib.Path({str(path)!r}).write_text(str(p.pid)); time.sleep(0.2)'
    leader = subprocess.Popen(
        [sys.executable, "-c", command], start_new_session=True, env=environment
    )
    identity = process_identity(leader.pid)
    leader.wait(timeout=5)
    orphan = int(path.read_text())
    lifecycle.save(launcher=identity, state_before_launch="launched")
    lifecycle.docker.cuda = lambda: [("GPU-owned", orphan)] if process_identity(orphan) else []
    try:
        result = lifecycle.reconcile()
        if owned:
            assert result
            assert process_identity(orphan) is None
            assert lifecycle.broker.released == ["private-token"]
            assert (
                lifecycle.record["launcher_extinct_at"]
                <= lifecycle.record["lease_release_acknowledged_at"]
            )
        else:
            assert not result
            assert process_identity(orphan) is not None
            assert not lifecycle.broker.released
            assert lifecycle.record["cleanup"] == "pending"
    finally:
        try:
            os.killpg(leader.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_pidfd_fallback_signals_exact_process(monkeypatch):
    import os
    import signal
    import subprocess
    import sys

    from matric_eval.studies.resource_lifecycle import _pidfd_open, _pidfd_send_signal

    monkeypatch.delattr(os, "pidfd_open", raising=False)
    monkeypatch.delattr(signal, "pidfd_send_signal", raising=False)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    descriptor = _pidfd_open(child.pid)
    try:
        _pidfd_send_signal(descriptor, signal.SIGTERM)
        assert child.wait(timeout=5) == -signal.SIGTERM
    finally:
        os.close(descriptor)
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


@pytest.mark.parametrize("operation", ["inspect", "stop", "remove", "cuda"])
def test_docker_and_cuda_tools_have_real_subprocess_deadlines(tmp_path, monkeypatch, operation):
    import os
    import subprocess
    import sys
    import time

    from matric_eval.studies.resource_lifecycle import Docker

    executable = tmp_path / ("nvidia-smi" if operation == "cuda" else "docker")
    executable.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    docker = Docker("unix:///fixture", timeout=0.1)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        if operation == "cuda":
            docker.cuda()
        else:
            getattr(docker, operation)("fixture-owned")
    assert time.monotonic() - started < 3


def test_tool_timeout_retains_lease_obligation(lifecycle, tmp_path, monkeypatch):
    import os
    import sys

    from matric_eval.studies.resource_lifecycle import Docker

    executable = tmp_path / "docker"
    executable.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    lifecycle.acquire()
    lifecycle.docker = Docker("unix:///fixture", timeout=0.1)
    assert not lifecycle.reconcile()
    assert lifecycle.record["reason"] == "TimeoutExpired"
    assert not lifecycle.broker.released
    assert lifecycle.private.exists()


def test_delayed_unix_acquisition_cannot_be_discharged_by_empty_status(tmp_path):
    import json
    import socket
    import threading

    from matric_eval.studies.resource_lifecycle import Broker

    path = str(tmp_path / "delayed.sock")
    errors = []
    delayed = []
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(path)
        server.listen()
        server.settimeout(20)

        def respond():
            leases = []
            pending = None
            try:
                for index in range(5):
                    client, _ = server.accept()
                    request = json.loads(client.recv(4096))
                    if index == 0:
                        assert request["action"] == "acquire"
                        pending = {
                            "owner": request["owner"],
                            "gpu_uuids": request["gpu_uuids"],
                            "token": "delayed-private-token",
                        }
                        # Keep the real RPC unanswered beyond its 10-second
                        # deadline. The server has not granted anything yet.
                        delayed.append(client)
                        continue
                    with client:
                        if index == 2:
                            leases.append(pending)
                        if request["action"] == "release":
                            assert request["token"] == "delayed-private-token"
                            leases.clear()
                        client.sendall(json.dumps({"ok": True, "leases": leases}).encode() + b"\n")
            except Exception as error:
                errors.append(error)
            finally:
                for client in delayed:
                    client.close()

        worker = threading.Thread(target=respond, daemon=True)
        worker.start()
        value = ResourceLifecycle(tmp_path / "owned", Broker(path), FakeDocker())
        try:
            value.prepare("run", "attempt", "GPU-owned", "test")
            with pytest.raises(TimeoutError):
                value.acquire()
            assert value.record["acquisition_outcome"] == "unknown"
            assert not value.reconcile()  # First status is empty, request still running.
            assert value.record["cleanup"] == "pending"
            with pytest.raises(RuntimeError, match="already attempted"):
                value.acquire()
            value.close()
            value = ResourceLifecycle(tmp_path / "owned", Broker(path), FakeDocker())
            assert value.reconcile()  # Later status exposes the exact owner's late grant.
            assert value.record["acquisition_outcome"] == "acknowledged"
            assert value.record["lease_release_acknowledged_at"] > 0
            assert value.reconcile()
            assert "delayed-private-token" not in value.path.read_text()
            assert not value.private.exists()
        finally:
            value.close()
            worker.join(timeout=20)
        assert not worker.is_alive()
        assert not errors


def test_legacy_false_complete_is_reopened_and_blocks_other_acquisition(lifecycle, tmp_path):
    import json

    lifecycle.record.pop("acquisition_outcome")
    lifecycle.save(state="stopped", cleanup="complete")
    other = ResourceLifecycle(tmp_path / "other", FakeBroker(), FakeDocker())
    try:
        other.prepare("run", "new", "GPU-owned", "test")
        with pytest.raises(RuntimeError, match="unresolved"):
            other.acquire()
        assert not lifecycle.reconcile()
        # Neither age nor repeated empty statuses resolves an unknown request.
        lifecycle.save(updated_at=0, cuda_release_verified_at=0)
        assert not lifecycle.reconcile()
        lifecycle.broker.call("acquire", owner=lifecycle.record["owner"], gpu_uuids=["GPU-owned"])
        assert lifecycle.reconcile()
        assert lifecycle.broker.released == ["private-token"]
        assert json.loads(lifecycle.path.read_text())["cleanup"] == "complete"
    finally:
        other.close()


@pytest.mark.parametrize("value", [0, -1, 301, float("inf"), float("nan")])
def test_acquire_wait_is_finite_and_bounded(value):
    from matric_eval.studies.resource_lifecycle import Broker

    with pytest.raises(ValueError, match="acquire timeout"):
        Broker("/unused.sock", acquire_timeout=value)


def test_acquire_wait_configuration_does_not_shorten_status_timeout(tmp_path):
    import socket
    import threading
    import time

    from matric_eval.studies.resource_lifecycle import Broker

    path = str(tmp_path / "broker.sock")
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(path)
        server.listen()
        server.settimeout(5)

        def respond():
            for _ in range(2):
                client, _ = server.accept()
                with client:
                    client.recv(4096)
                    time.sleep(0.15)
                    try:
                        client.sendall(b'{"ok":true,"leases":[]}\n')
                    except BrokenPipeError:
                        pass

        worker = threading.Thread(target=respond)
        worker.start()
        broker = Broker(path, acquire_timeout=0.05)
        assert broker.call("status")["leases"] == []
        with pytest.raises(TimeoutError):
            broker.call("acquire", owner="owned", requested_mib=1)
        worker.join(timeout=5)
        assert not worker.is_alive()


@pytest.mark.parametrize("change", ["source", "expiry"])
def test_admission_changes_during_acquire_prevent_dispatch(
    lifecycle, admission_plan, tmp_path, monkeypatch, change
):
    import sys
    from pathlib import Path

    validation_calls = 0
    if change == "expiry":
        from matric_eval.studies import resource_lifecycle as lifecycle_module

        original_validate = lifecycle_module.validate_admission

        def expire_on_post_acquire_validation(receipt, plan, max_age_seconds):
            nonlocal validation_calls
            validation_calls += 1
            if validation_calls == 2:
                # Deterministically model the wall clock advancing while the
                # acquire RPC is outstanding. A real sleep made the first
                # validation expire under suite load before any lease existed.
                receipt["completed_at"] -= max_age_seconds + 1
            return original_validate(receipt, plan, max_age_seconds)

        monkeypatch.setattr(
            lifecycle_module, "validate_admission", expire_on_post_acquire_validation
        )
    original = lifecycle.broker.call

    def acquire_then_change(action, **fields):
        response = original(action, **fields)
        if action == "acquire":
            if change == "source":
                script = Path(admission_plan["checks"][0]["inputs"][0])
                script.write_text(script.read_text() + "\n# changed during broker acquire\n")
        return response

    lifecycle.broker.call = acquire_then_change
    launched = tmp_path / "launched"
    with pytest.raises(ValueError, match="stale|changed"):
        lifecycle.run(
            [sys.executable, "-c", f"from pathlib import Path; Path({str(launched)!r}).touch()"],
            preflight_plan=admission_plan,
        )
    assert not launched.exists()
    assert "launcher" not in lifecycle.record
    assert "state_before_launch" not in lifecycle.record
    assert lifecycle.broker.released == ["private-token"]
    assert lifecycle.record["cleanup"] == "complete"
    assert not lifecycle.private.exists()
    if change == "expiry":
        assert validation_calls == 2


@pytest.mark.parametrize("exits", [True, False])
def test_launcher_exit_during_ownership_read_still_proves_cleanup(lifecycle, monkeypatch, exits):
    """A zombie has an empty environ despite owning the preceding live stat."""
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    from matric_eval.studies.resource_lifecycle import process_identity

    lifecycle.acquire()
    attach_owned_container(lifecycle)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
        env={**os.environ, "MATRIC_RESOURCE_ID": lifecycle.record["resource_id"]},
    )
    lifecycle.save(launcher=process_identity(child.pid), state_before_launch="launched")
    original_read = Path.read_bytes
    raced = False

    def exit_before_environ(path):
        nonlocal raced
        if path == Path(f"/proc/{child.pid}/environ") and not raced:
            raced = True
            if not exits:
                raise PermissionError("live process environ is inaccessible")
            child.terminate()
            deadline = time.monotonic() + 5
            # Do not poll/wait the child here: keep its real zombie /proc entry
            # so the environ read races exit, not disappearance of the PID.
            while process_identity(child.pid) is not None:
                assert time.monotonic() < deadline, "child did not exit"
                time.sleep(0.001)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", exit_before_environ)
    try:
        cleaned = lifecycle.reconcile()
        assert raced
        if exits:
            assert cleaned, lifecycle.record.get("reason")
            assert process_identity(child.pid) is None
            assert lifecycle.broker.released == ["private-token"]
            assert (
                lifecycle.record["launcher_extinct_at"]
                <= lifecycle.record["lease_release_acknowledged_at"]
            )
        else:
            assert not cleaned
            assert process_identity(child.pid) is not None
            assert lifecycle.record["reason"] == "PermissionError"
            assert lifecycle.record["cleanup"] == "pending"
            assert not lifecycle.broker.released
    finally:
        child.kill()
        child.wait(timeout=5)
