"""Bounded filesystem fixtures for cooperative storage admission."""

import json
import os
from pathlib import Path

import pytest

from matric_eval.storage import CLASSES, Allocation, StorageBlocker, StorageSession


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
    assert next(iter(plan["filesystems"].values()))["reserved_bytes"] == 16384
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
    volume["free_bytes"] = 16384
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


def test_supervisor_stops_owned_writer_and_retains_receipt(tmp_path, monkeypatch, capsys):
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
    assert json.loads((tmp_path / "reservations.json").read_text()) == {}
