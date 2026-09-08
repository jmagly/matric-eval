"""Manual A100 fixture: run inside a private mount namespace with bounded scratch.

Usage: python tests/unit/storage_bounded_fixture.py OWNED_ROOT bytes|inodes|evidence
Mount OWNED_ROOT/scratch (or /evidence for that mode) as tmpfs size=1M,nr_inodes=32.
"""

import errno
import json
import sys
from pathlib import Path

from matric_eval.storage import CLASSES, Allocation, StorageBlocker, StorageSession

root = Path(sys.argv[1])
mode = sys.argv[2]
growth_kind = "evidence" if mode == "evidence" else "scratch"
allocations = []
for kind in sorted(CLASSES):
    path = root / kind
    path.mkdir(exist_ok=True)
    allocations.append(
        Allocation(
            kind,
            str(path),
            1048576 if kind == growth_kind else 0,
            32 if kind == growth_kind else 0,
            disposable=True,
        )
    )
run = StorageSession(allocations, root, root, headroom_bytes=1048576, headroom_inodes=128)
run.admit(reserve=True)
run.claim_empty_scratch()
run.check("fixture:before")
try:
    for index in range(1024):
        try:
            (root / growth_kind / str(index)).write_bytes(b"x" * 65536 if mode != "inodes" else b"")
        except OSError as exc:
            assert exc.errno == errno.ENOSPC
            break
    else:
        raise AssertionError("Kernel failed to enforce the bound")
    try:
        run.check(f"fixture:{mode}:exhausted")
    except StorageBlocker as exc:
        assert exc.code == "storage_bound_exhausted"
        receipt = {"blocker": exc.code, "mode": mode, **run.receipt()}
        # Even exhausted evidence cannot consume the emergency diagnostic device.
        diagnostic = run.write_diagnostics(receipt)
        assert json.loads(diagnostic.read_text())["blocker"] == exc.code
        print(json.dumps(receipt))
    else:
        raise AssertionError("Storage exhaustion was not classified")
finally:
    run.release()
