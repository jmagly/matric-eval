"""Unit coverage for study run residue reclamation."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from matric_eval.studies import run_residue


class _Recorder:
    """Minimal ``subprocess.run`` stand-in that records argv."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, argv, **_kwargs):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(
            argv, self.returncode, stdout=self.stdout, stderr=self.stderr
        )


def _workspace(root: Path, name: str, age_hours: float, *, marker: str | None = None) -> Path:
    path = root / name
    path.mkdir()
    (path / "payload.bin").write_bytes(b"x" * 1024)
    if marker is not None:
        (path / marker).write_text("")
    stamp = time.time() - age_hours * 3600
    os.utime(path, (stamp, stamp))
    return path


def test_failed_units_filters_to_prefix():
    recorder = _Recorder(
        stdout=(
            "matric-eval-replay-a.service loaded failed failed desc\n"
            "unrelated.service loaded failed failed desc\n"
        )
    )
    assert run_residue.failed_units(run=recorder) == ["matric-eval-replay-a.service"]
    assert "--state=failed" in recorder.calls[0]


def test_reset_failed_units_is_a_noop_without_units():
    recorder = _Recorder()
    outcome = run_residue.reset_failed_units([], run=recorder)
    assert outcome.ok and outcome.units == ()
    assert recorder.calls == []


def test_reset_failed_units_passes_every_unit():
    recorder = _Recorder()
    outcome = run_residue.reset_failed_units(["a.service", "", "b.service"], run=recorder)
    assert outcome.ok
    assert outcome.units == ("a.service", "b.service")
    assert recorder.calls[0][-2:] == ["a.service", "b.service"]
    assert recorder.calls[0][:3] == ["sudo", "-n", "systemctl"]


def test_reset_failed_units_reports_rejection_without_raising():
    recorder = _Recorder(returncode=1, stderr="Interactive authentication required.")
    outcome = run_residue.reset_failed_units(["a.service"], run=recorder)
    assert not outcome.ok
    assert "Interactive authentication" in outcome.error


def test_reset_failed_units_survives_a_missing_binary():
    def explode(argv, **_kwargs):
        raise OSError("systemctl absent")

    outcome = run_residue.reset_failed_units(["a.service"], run=explode)
    assert not outcome.ok
    assert "systemctl absent" in outcome.error


def test_stale_workspaces_retains_newest_and_young_trees(tmp_path):
    for index in range(6):
        _workspace(tmp_path, f"run-{index}", age_hours=100 + index)
    _workspace(tmp_path, "fresh", age_hours=1)

    candidates = run_residue.stale_workspaces(tmp_path, keep_last=2, min_age_hours=24)
    names = {candidate.path.name for candidate in candidates}

    # keep_last=2 retains the two newest by mtime: "fresh" and "run-0".
    assert "fresh" not in names, "a tree inside keep_last must be retained"
    assert "run-0" not in names, "the newest aged tree is inside keep_last"
    assert names == {"run-1", "run-2", "run-3", "run-4", "run-5"}


def test_stale_workspaces_never_offers_a_version_controlled_tree(tmp_path):
    _workspace(tmp_path, "deployment", age_hours=5000, marker=".git")
    _workspace(tmp_path, "plain", age_hours=5000)

    candidates = run_residue.stale_workspaces(tmp_path, keep_last=0, min_age_hours=0)

    assert [candidate.path.name for candidate in candidates] == ["plain"]


@pytest.mark.parametrize("marker", run_residue.PROTECTED_MARKERS)
def test_every_protection_marker_is_honoured(tmp_path, marker):
    _workspace(tmp_path, "guarded", age_hours=5000, marker=marker)
    assert run_residue.stale_workspaces(tmp_path, keep_last=0, min_age_hours=0) == []


def test_explicit_protect_names_are_excluded(tmp_path):
    _workspace(tmp_path, "keepme", age_hours=5000)
    _workspace(tmp_path, "dropme", age_hours=5000)

    candidates = run_residue.stale_workspaces(
        tmp_path, keep_last=0, min_age_hours=0, protect=["keepme"]
    )

    assert [candidate.path.name for candidate in candidates] == ["dropme"]


def test_symlinks_are_never_candidates(tmp_path):
    target = _workspace(tmp_path, "real", age_hours=5000)
    (tmp_path / "link").symlink_to(target)

    candidates = run_residue.stale_workspaces(tmp_path, keep_last=0, min_age_hours=0)

    assert [candidate.path.name for candidate in candidates] == ["real"]


def test_reclaim_workspaces_dry_run_removes_nothing(tmp_path):
    _workspace(tmp_path, "old", age_hours=5000)

    candidates = run_residue.reclaim_workspaces(tmp_path, keep_last=0, min_age_hours=0)

    assert [candidate.path.name for candidate in candidates] == ["old"]
    assert (tmp_path / "old").exists()


def test_reclaim_workspaces_apply_removes_only_candidates(tmp_path):
    _workspace(tmp_path, "old", age_hours=5000)
    _workspace(tmp_path, "deployment", age_hours=5000, marker=".git")

    run_residue.reclaim_workspaces(tmp_path, keep_last=0, min_age_hours=0, dry_run=False)

    assert not (tmp_path / "old").exists()
    assert (tmp_path / "deployment").exists()


def test_candidate_reports_tree_size(tmp_path):
    _workspace(tmp_path, "old", age_hours=5000)
    (candidate,) = run_residue.stale_workspaces(tmp_path, keep_last=0, min_age_hours=0)
    assert candidate.size_bytes >= 1024


@pytest.mark.parametrize("keep_last,min_age", [(-1, 0), (0, -1)])
def test_negative_retention_bounds_are_rejected(tmp_path, keep_last, min_age):
    with pytest.raises(ValueError):
        run_residue.stale_workspaces(tmp_path, keep_last=keep_last, min_age_hours=min_age)


def test_missing_workspace_root_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_residue.stale_workspaces(tmp_path / "absent")


def test_assert_free_space_passes_above_the_floor(tmp_path):
    run_residue.assert_free_space([tmp_path], floor_gib=0.0)


def test_assert_free_space_raises_below_the_floor(tmp_path):
    with pytest.raises(RuntimeError, match="Free space below"):
        run_residue.assert_free_space([tmp_path], floor_gib=10**9)
