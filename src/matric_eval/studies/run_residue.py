"""Reclaim systemd and workspace residue left behind by study runs.

Study runs create one transient systemd unit per server or replay attempt and
one workspace tree per run. A transient unit that exits non-zero holds failed
state in the manager until it is explicitly reset, and workspace trees are never
pruned. Both accumulate until free space becomes a scheduling risk and until
``--state=failed`` stops being a usable health signal for the next run.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

#: Injection point for tests; matches the parts of ``subprocess.run`` used here.
Runner = Callable[..., "subprocess.CompletedProcess[str]"]

UNIT_PREFIX = "matric-eval-"
DEFAULT_KEEP_LAST = 10
DEFAULT_MIN_AGE_HOURS = 24.0
DEFAULT_FLOOR_GIB = 40.0
GIB = 1024**3

#: A workspace holding any of these is never a reclamation candidate. The
#: deployment checkout itself lives inside ``workspaces/``; losing it would take
#: the host offline, so a version-controlled tree is always retained.
PROTECTED_MARKERS = (".git", ".keep", "KEEP")


@dataclass(frozen=True)
class ResetOutcome:
    """Result of clearing failed state for a set of transient units."""

    units: tuple[str, ...]
    ok: bool
    error: str = ""


@dataclass(frozen=True)
class WorkspaceCandidate:
    """A workspace directory eligible for reclamation."""

    path: Path
    age_hours: float
    size_bytes: int

    @property
    def size_gib(self) -> float:
        return self.size_bytes / GIB


def failed_units(
    prefix: str = UNIT_PREFIX,
    *,
    run: Runner = subprocess.run,
) -> list[str]:
    """Return failed units whose names start with ``prefix``."""
    completed = run(
        [
            "systemctl",
            "list-units",
            f"{prefix}*",
            "--state=failed",
            "--no-legend",
            "--no-pager",
            "--plain",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    names: list[str] = []
    for line in (completed.stdout or "").splitlines():
        fields = line.split()
        if fields and fields[0].startswith(prefix):
            names.append(fields[0])
    return names


def reset_failed_units(units: Iterable[str], *, run: Runner = subprocess.run) -> ResetOutcome:
    """Clear failed state for ``units``.

    Never raises. Teardown calls this on the failure path, where raising would
    mask the original error; the outcome is returned so callers can record it.
    """
    wanted = tuple(unit for unit in units if unit)
    if not wanted:
        return ResetOutcome(units=(), ok=True)
    try:
        completed = run(
            ["sudo", "-n", "systemctl", "reset-failed", *wanted],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return ResetOutcome(units=wanted, ok=False, error=str(error))
    if completed.returncode:
        return ResetOutcome(
            units=wanted,
            ok=False,
            error=(completed.stderr or "").strip() or f"exit {completed.returncode}",
        )
    return ResetOutcome(units=wanted, ok=True)


def _tree_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path, onerror=lambda _error: None):
        for name in files:
            candidate = Path(root) / name
            try:
                total += candidate.lstat().st_size
            except OSError:
                continue
    return total


def protected(path: Path) -> bool:
    """True when ``path`` carries a marker that forbids reclamation."""
    return any((path / marker).exists() for marker in PROTECTED_MARKERS)


def stale_workspaces(
    root: Path,
    *,
    keep_last: int = DEFAULT_KEEP_LAST,
    min_age_hours: float = DEFAULT_MIN_AGE_HOURS,
    protect: Sequence[str] = (),
    now: float | None = None,
) -> list[WorkspaceCandidate]:
    """Return reclaimable workspaces, newest-first retention applied first.

    A workspace is a candidate only when it survives every guard: it is a plain
    directory, carries no protection marker, is not named in ``protect``, falls
    outside the ``keep_last`` newest, and is older than ``min_age_hours``.
    """
    if keep_last < 0:
        raise ValueError("keep_last must not be negative")
    if min_age_hours < 0:
        raise ValueError("min_age_hours must not be negative")
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"workspace root is not a directory: {root}")
    reference = time.time() if now is None else now
    excluded = set(protect)

    entries: list[tuple[float, Path]] = []
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        if child.name in excluded or protected(child):
            continue
        try:
            entries.append((child.stat().st_mtime, child))
        except OSError:
            continue

    entries.sort(key=lambda item: item[0], reverse=True)
    candidates: list[WorkspaceCandidate] = []
    for mtime, path in entries[keep_last:]:
        age_hours = max(0.0, (reference - mtime) / 3600.0)
        if age_hours < min_age_hours:
            continue
        candidates.append(
            WorkspaceCandidate(path=path, age_hours=age_hours, size_bytes=_tree_size(path))
        )
    return candidates


def reclaim_workspaces(
    root: Path,
    *,
    keep_last: int = DEFAULT_KEEP_LAST,
    min_age_hours: float = DEFAULT_MIN_AGE_HOURS,
    protect: Sequence[str] = (),
    dry_run: bool = True,
    now: float | None = None,
) -> list[WorkspaceCandidate]:
    """Report, and when ``dry_run`` is false remove, reclaimable workspaces."""
    candidates = stale_workspaces(
        root,
        keep_last=keep_last,
        min_age_hours=min_age_hours,
        protect=protect,
        now=now,
    )
    if dry_run:
        return candidates
    for candidate in candidates:
        shutil.rmtree(candidate.path)
    return candidates


def free_gib(path: Path | str) -> float:
    """Free space in GiB available to an unprivileged writer at ``path``."""
    capacity = os.statvfs(path)
    return capacity.f_bavail * capacity.f_frsize / GIB


def assert_free_space(
    paths: Iterable[Path | str],
    *,
    floor_gib: float = DEFAULT_FLOOR_GIB,
) -> None:
    """Raise when any path has less than ``floor_gib`` free.

    Parallel suites multiply workspace and cache growth, so a study that starts
    below the floor risks ENOSPC mid-run, which corrupts results instead of
    failing cleanly.
    """
    for path in paths:
        available = free_gib(path)
        if available < floor_gib:
            raise RuntimeError(
                f"Free space below {floor_gib:g} GiB at {path} ({available:.1f} GiB available)"
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspaces", type=Path, default=Path("/srv/matric-eval/workspaces"))
    parser.add_argument("--unit-prefix", default=UNIT_PREFIX)
    parser.add_argument("--keep-last", type=int, default=DEFAULT_KEEP_LAST)
    parser.add_argument("--min-age-hours", type=float, default=DEFAULT_MIN_AGE_HOURS)
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--floor-gib", type=float, default=DEFAULT_FLOOR_GIB)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the reclamation; without it the run only reports",
    )
    arguments = parser.parse_args(argv)

    stale = failed_units(arguments.unit_prefix)
    if stale:
        print(f"failed units ({len(stale)}): {' '.join(stale)}")
        if arguments.apply:
            outcome = reset_failed_units(stale)
            print("reset-failed:", "ok" if outcome.ok else f"FAILED {outcome.error}")
            if not outcome.ok:
                return 1
    else:
        print("failed units: none")

    candidates = reclaim_workspaces(
        arguments.workspaces,
        keep_last=arguments.keep_last,
        min_age_hours=arguments.min_age_hours,
        protect=arguments.protect,
        dry_run=not arguments.apply,
    )
    reclaimed = sum(candidate.size_bytes for candidate in candidates) / GIB
    verb = "reclaimed" if arguments.apply else "reclaimable"
    print(f"{verb} workspaces: {len(candidates)} ({reclaimed:.1f} GiB)")
    for candidate in candidates:
        print(f"  {candidate.path.name}  {candidate.age_hours:.0f}h  {candidate.size_gib:.2f} GiB")

    for path in (arguments.workspaces, "/"):
        print(f"free at {path}: {free_gib(path):.1f} GiB")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
