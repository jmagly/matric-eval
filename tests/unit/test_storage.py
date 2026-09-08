"""Bounded filesystem fixtures for cooperative storage admission."""

import json
import os
from pathlib import Path

import pytest

from matric_eval.storage import (
    CLASSES,
    DIAGNOSTIC_BYTES,
    Allocation,
    StorageBlocker,
    StorageSession,
)


def session(tmp_path, **kwargs):
    roots = []
    for kind in sorted(CLASSES):
        path = tmp_path / kind
        path.mkdir(exist_ok=True)
        roots.append(
            Allocation(
                kind,
                str(path),
                16384 if kind == "scratch" else 0,
                4 if kind == "scratch" else 0,
                disposable=True,
            )
        )
    return StorageSession(
        roots,
        tmp_path,
        tmp_path,
        require_enforced_bounds=False,
        **{"headroom_bytes": 0, "headroom_inodes": 0, **kwargs},
    )


def test_filesystems_are_counted_once_and_unknown_demand_explicit(tmp_path):
    run = session(tmp_path)
    plan = run.admit()
    assert len(plan["filesystems"]) == 1
    assert next(iter(plan["filesystems"].values()))["reserved_bytes"] == 16384 + DIAGNOSTIC_BYTES
    assert all(item["demand"] == "unknown" for item in plan["classes"])
    assert not run.active


def test_production_refuses_unenforced_scratch_before_load(tmp_path):
    run = session(tmp_path)
    run.require_enforced_bounds = True
    with pytest.raises(StorageBlocker, match="storage_enforcement_required"):
        run.admit(reserve=True)
    assert not run.active


def test_aggregate_growth_retains_diagnostics(tmp_path):
    run = session(tmp_path)
    run.admit(reserve=True)
    for index in range(3):
        (tmp_path / "scratch" / str(index)).write_bytes(b"x" * 8192)
    with pytest.raises(StorageBlocker, match="storage_budget_exceeded"):
        run.check("fixture_growth")
    assert run.receipt()["samples"][-1]["usage"]["scratch"]["bytes"] >= 24576
    assert len(list((tmp_path / "scratch").iterdir())) == 3
    run.release()
    assert json.loads((tmp_path / "reservations.json").read_text()) == {}


def test_inode_growth_is_independent_of_bytes(tmp_path):
    run = session(tmp_path)
    for index in range(5):
        (tmp_path / "scratch" / str(index)).touch()
    with pytest.raises(StorageBlocker, match="storage_budget_exceeded"):
        run.check("fixture_inodes")
    assert run.samples[-1]["usage"]["scratch"]["inodes"] == 5


def test_concurrent_reservation_and_identity_recovery(tmp_path):
    run = session(tmp_path)
    run.admit(reserve=True)
    other = session(tmp_path)
    plan = other.plan()
    volume = next(iter(plan["filesystems"].values()))
    volume["free_bytes"] = volume["reserved_bytes"]
    with other.locked() as state:
        with pytest.raises(StorageBlocker, match="storage_insufficient_bytes"):
            other._admit(plan, state)
        # Reused PID alone cannot hold stale reservations forever.
        state[run.token]["identity"] = "old-boot:old-process"
    with other.locked() as state:
        assert run.token not in state
        other._admit(plan, state)


def test_cleanup_preview_excludes_shared_evidence_and_escape(tmp_path):
    run = session(tmp_path)
    assert run.cleanup_preview() == []
    run.claim_empty_scratch()
    assert {Path(item["path"]).name for item in run.cleanup_preview()} == {"scratch", "temporary"}
    run.paths["scratch"] = tmp_path.parent
    assert {Path(item["path"]).name for item in run.cleanup_preview()} == {"temporary"}


def test_mount_change_is_typed_blocker(tmp_path, monkeypatch):
    run = session(tmp_path)
    import matric_eval.storage as storage

    real = storage.filesystem
    monkeypatch.setattr(storage, "filesystem", lambda path: {**real(path), "mount_id": "changed"})
    with pytest.raises(StorageBlocker, match="storage_mount_changed"):
        run.check("load")


def test_insufficient_inodes_refused_before_reservation(tmp_path):
    run = session(tmp_path, headroom_inodes=10**18)
    with pytest.raises(StorageBlocker, match="storage_insufficient_inodes"):
        run.admit(reserve=True)
    assert not run.active


def test_read_only_and_io_are_typed(tmp_path, monkeypatch):
    import matric_eval.storage as storage

    real = os.statvfs(tmp_path)

    class ReadOnly:
        f_flag = os.ST_RDONLY

    monkeypatch.setattr(os, "statvfs", lambda path: ReadOnly())
    with pytest.raises(StorageBlocker, match="storage_read_only"):
        storage.filesystem(tmp_path)
    monkeypatch.setattr(os, "statvfs", lambda path: real)
    with pytest.raises(StorageBlocker, match="storage_io"):
        storage.filesystem(tmp_path / "missing")


def test_cli_configuration_failure_is_typed(tmp_path, monkeypatch, capsys):
    import sys

    from matric_eval.storage import main

    monkeypatch.setattr(sys, "argv", ["storage", str(tmp_path / "missing.json")])
    assert main() == 75
    assert json.loads(capsys.readouterr().out)["failure_class"] == "storage_configuration"


@pytest.mark.parametrize("release_failure", [False, True])
def test_supervisor_stops_owned_writer_and_retains_receipt(
    tmp_path, monkeypatch, capsys, release_failure
):
    import sys
    import time
    from dataclasses import asdict

    from matric_eval.storage import main

    run = session(tmp_path)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "allocations": [asdict(a) for a in run.allocations],
                "ledger": str(tmp_path),
                "ownership": str(tmp_path),
                "headroom_bytes": 0,
                "headroom_inodes": 0,
            }
        )
    )
    # Only this bounded fixture bypasses production enforcement to exercise polling.
    monkeypatch.setattr(StorageSession, "verify_bounds", lambda self, plan: None)
    if release_failure:

        def failed_release(self):
            raise StorageBlocker("storage_ledger_io", "fixture release failure")

        monkeypatch.setattr(StorageSession, "release", failed_release)
    script = (
        "from pathlib import Path; import time; "
        f"root=Path({str(tmp_path / 'scratch')!r}); "
        "[(root/str(i)).write_bytes(b'x'*8192) for i in range(3)]; "
        "time.sleep(10); (root/'should-not-exist').touch()"
    )
    monkeypatch.setattr(sys, "argv", ["storage", str(plan), "--", sys.executable, "-c", script])
    started = time.monotonic()
    assert main() == 75
    assert time.monotonic() - started < 8
    output = capsys.readouterr().out
    assert "storage_budget_exceeded" in output
    assert "storage_receipt" in output
    assert not (tmp_path / "scratch" / "should-not-exist").exists()
    retained = json.loads(next(tmp_path.glob("*.receipt.json")).read_text())
    assert retained["failure"]["failure_class"] == "storage_budget_exceeded"
    if release_failure:
        assert "fixture release failure" in output
        assert json.loads((tmp_path / "reservations.json").read_text())
    else:
        assert json.loads((tmp_path / "reservations.json").read_text()) == {}


@pytest.mark.parametrize("unit", ["bytes", "inodes"])
def test_existing_headroom_cannot_be_spent_by_new_run(tmp_path, unit):
    first = session(tmp_path, **{f"headroom_{unit}": 100})
    first.admit(reserve=True)
    other = session(tmp_path)
    plan = other.plan()
    volume = next(iter(plan["filesystems"].values()))
    volume[f"free_{unit}"] = 2 * volume[f"reserved_{unit}"] + 50
    with other.locked() as state:
        assert next(iter(state[first.token]["volumes"].values()))[f"headroom_{unit}"] == 100
        with pytest.raises(StorageBlocker, match=f"storage_insufficient_{unit}"):
            other._admit(plan, state)
    first.release()


def test_capacity_is_refreshed_inside_reservation_lock(tmp_path, monkeypatch):
    from contextlib import contextmanager

    run = session(tmp_path)
    real_lock, real_plan = run.locked, run.plan
    locked = False

    @contextmanager
    def lock():
        nonlocal locked
        with real_lock() as state:
            locked = True
            try:
                yield state
            finally:
                locked = False

    def plan():
        assert locked, "free capacity was sampled outside the reservation lock"
        return real_plan()

    monkeypatch.setattr(run, "locked", lock)
    monkeypatch.setattr(run, "plan", plan)
    run.admit(reserve=True)
    run.release()


def test_release_retains_surviving_descendant_until_reaped(tmp_path):
    import ctypes
    import signal
    import subprocess
    import sys

    libc = ctypes.CDLL(None)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    child = None
    run = session(tmp_path)
    leader = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os,sys,time; input(); child=os.fork(); "
            "os._exit(0) if child else None; print(os.getpid(),flush=True); time.sleep(60)",
        ],
        start_new_session=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        run.admit(reserve=True)
        run.attach_process_group(leader.pid)
        leader.stdin.write("\n")
        leader.stdin.flush()
        child = int(leader.stdout.readline())
        leader.wait(timeout=5)
        run.release()
        assert run.active
        assert run.token in json.loads((tmp_path / "reservations.json").read_text())
        os.kill(child, signal.SIGKILL)
        os.waitpid(child, 0)
        child = None
        run.release()
        assert not run.active
        assert json.loads((tmp_path / "reservations.json").read_text()) == {}
    finally:
        if child is not None:
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)
        if leader.poll() is None:
            leader.kill()
            leader.wait()
        leader.stdin.close()
        leader.stdout.close()
        run.release()
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


def test_unknown_group_state_retains_reservation(tmp_path, monkeypatch):
    import errno

    import matric_eval.storage as storage

    run = session(tmp_path)
    run.admit(reserve=True)
    with run.locked() as state:
        state[run.token]["process_group"] = 12345

    def unknown(group, sig):
        raise OSError(errno.EIO, "cannot establish liveness")

    monkeypatch.setattr(os, "killpg", unknown)
    assert storage.group_alive(12345)
    run.release()
    assert run.active
    assert run.token in json.loads((tmp_path / "reservations.json").read_text())


def test_evidence_growth_also_requires_kernel_bounds(tmp_path):
    from dataclasses import replace

    run = session(tmp_path)
    run.allocations = [
        replace(a, budget_bytes=4096, budget_inodes=2)
        if a.kind == "evidence"
        else replace(a, budget_bytes=0, budget_inodes=0)
        for a in run.allocations
    ]
    run.require_enforced_bounds = True
    with pytest.raises(StorageBlocker, match="evidence: require"):
        run.admit(reserve=True)
