# Storage admission and bounded supervision

`python -m matric_eval.storage plan.json` resolves existing paths against Linux
mount information and reports estimates (including explicit unknown demand),
byte/inode allowances, and unique device capacity. It checks existing reservations
under a host-wide file lock. It never creates storage paths, migrates assets,
imports pools, or deletes artifacts.

Every cooperating run must use the **same ledger directory on the same host**.
Reservations contain boot ID, PID, process start time, and an unguessable owner ID.
Dead process identities are recovered under the lock; a reused PID is insufficient
proof of ownership. Reservations are conservative until released. This is not a
cross-host/distributed allocator. Production reservation additionally verifies
kernel bounds: every growing class except evidence must reside on a filesystem
whose total byte and inode capacities fit its budgets, on a different device from
evidence. Admission returns `storage_enforcement_required` when this proof is
absent. This version supports bounded filesystems (for example an operator-created
tmpfs); project-quota attestations are not yet supported. It never creates mounts.

The JSON plan contains `ledger` and `ownership` (existing directory paths),
`headroom_bytes`, `headroom_inodes`, and `allocations`. Declare exactly one of
each kind: `models`, `download_cache`, `docker`, `scratch`, `temporary`, `logs`,
`evidence`. Each allocation requires `path`, `budget_bytes`, `budget_inodes`;
`estimated_bytes` defaults to null (unknown), `disposable` defaults to false.
Budgets bound additional allocated blocks/inodes above the initial measurement.
Writable directories must not overlap. Zero means no growth allowed, not unlimited.
Immutable weights can remain on configured storage with zero growth allowances.
Directory scans include all files but do not follow symlinks. Use dedicated roots:
a shared cache's unrelated growth can conservatively stop a run.

Run a command with:

```bash
python -m matric_eval.storage --interval 0.25 plan.json -- your-command arguments
```

The command starts only after atomic reservation and enforced-bound verification. The supervisor checks aggregate
allocated blocks and unique inodes, detects changed mounts, and reports typed
`storage_*` infrastructure blockers. Budget failure terminates the owned process
group, escalating from TERM to KILL after five seconds, retains artifacts, and
returns 75. The JSON receipt goes to stdout, so arrange durable capture in the
reserved evidence path through the calling lifecycle before starting work.
Capacity, phase elapsed times, named process `/proc/PID/io`, and sampled peak
scratch are retained. For integration, use `StorageSession.admit(reserve=True)`,
`check(phase, pid)`, `phase(name, pid)`, `receipt()`, and `release()` in a finally
block. A model-loader PID must be supplied to attribute model-load I/O; supervisor
I/O is not model-load I/O.

Kernel filesystem limits bound bursts between checks. Headroom is reserved on the
evidence device; bounded scratch is allowed to reach its kernel limit and is then
classified `storage_bound_exhausted`, while diagnostics remain writable on the
separate evidence device. The library's `require_enforced_bounds=False` supports
small controlled monitoring fixtures only; the production CLI never disables
enforcement. This does not sandbox commands: callers must constrain their writable
paths to the declared allocations and size their evidence output allowance.
Descendant I/O and between-sample peaks are not claimed as measured. Placement
improvements require comparable before/after load measurements; this feature makes
no SATA/NVMe throughput claim.

`claim_empty_scratch()` records inode lineage only for initially empty disposable
scratch/temporary directories inside the ownership boundary, excluding overlapping
shared asset roots. `cleanup_preview()` lists only those still-owned directories,
with `policy_required`; it never executes deletion. Evidence, weights, shared
cache/Docker roots, named protected assets, replaced paths, and external paths are
excluded. The operator must separately review directory contents before authorizing
any removal; the preview is not a deletion authorization.

Executable qualification follows [the A100 policy](a100-execution.md). The unit
fixtures use small owned directories and never load a model or alter shared assets.

On September 8, 2026, `tests/unit/storage_bounded_fixture.py` ran on Basilisk with
private mount namespaces, each containing a 1 MiB tmpfs with 32 inodes in the
isolated `issue160-storage-20260908` checkout. Both aggregate multi-file byte
exhaustion and empty-file inode exhaustion hit kernel ENOSPC, produced typed
`storage_bound_exhausted`, released their reservations, and successfully retained
diagnostics on the separate evidence device. The mount namespaces disappeared
when their fixture processes exited. No shared mount, model, or protected asset
was changed. Raw [byte](evidence/issue160/bytes-receipt.json) and
[inode](evidence/issue160/inodes-receipt.json) receipts retain before/after capacity,
sampled peak scratch, elapsed times, and fixture process I/O. Eleven focused unit
tests, Ruff, and strict mypy also passed on Python 3.11.15 on A100.

These are bounded no-model qualifications. Actual model-load I/O and paired
placement measurements remain unqualified; no performance improvement is claimed.
