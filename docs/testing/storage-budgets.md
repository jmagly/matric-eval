# Storage admission and bounded supervision

`python -m matric_eval.storage plan.json` resolves existing paths against Linux
mount information and reports estimates (including explicit unknown demand),
byte/inode allowances, and unique device capacity. It checks existing reservations
under a host-wide file lock. It never creates storage paths, migrates assets,
imports pools, or deletes artifacts.

Every cooperating run must use the **same ledger directory on the same host**.
Reservations contain boot ID, PID, process start time, and an unguessable owner ID.
Dead process identities are recovered under the lock; a reused PID is insufficient
proof of ownership. Attached process groups must also be gone; surviving or
unobservable groups retain their reservations even after their leaders exit.
Each reservation records its per-device headroom: admission preserves the largest
live headroom floor in addition to the sum of all live allocations. Capacity is
sampled inside the reservation lock. Reservations are conservative until released. This is not a
cross-host/distributed allocator. Production reservation additionally verifies
kernel bounds: every growing class, including evidence, must reside on a filesystem
whose total byte and inode capacities fit its budgets, on a different device from
the emergency diagnostics ledger. Admission returns `storage_enforcement_required` when this proof is
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
returns 75. The ledger device reserves an additional 1 MiB and four inodes per run
for emergency diagnostics and ledger updates, apart from configured headroom.
Before releasing capacity, the supervisor writes an exclusive owner-named JSON
receipt there with mode 0600 and fsyncs both the file and directory entry before
reporting durable diagnostic success. A directory-sync failure remains a typed
storage error. The final receipt also goes to stdout. Ledger-release
errors retain the original failure and report cleanup errors with the active
reservation; they cannot suppress output. The durable receipt reflects the state
before release; the stdout receipt includes the release outcome.
Capacity, phase elapsed times, named process `/proc/PID/io`, and sampled peak
scratch are retained. For integration, use `StorageSession.admit(reserve=True)`,
`check(phase, pid)`, `phase(name, pid)`, `receipt()`, and `release()` in a finally
block. A model-loader PID must be supplied to attribute model-load I/O; supervisor
I/O is not model-load I/O.

Kernel filesystem limits bound bursts between checks. Headroom is reserved on the
emergency diagnostics device; bounded scratch or evidence may reach its kernel limit and is then
classified `storage_bound_exhausted`, while diagnostics remain writable on the
separate emergency device. Retained samples are bounded to the first and latest
63 observations; the peak scratch counter covers all observations. The library's `require_enforced_bounds=False` supports
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
isolated `issue160-storage-20260908` checkout. Aggregate multi-file byte
exhaustion, empty-file inode exhaustion, and evidence-volume exhaustion hit kernel ENOSPC, produced typed
`storage_bound_exhausted`, released their reservations, and successfully retained
diagnostics on the separate emergency device. The mount namespaces disappeared
when their fixture processes exited. No shared mount, model, or protected asset
was changed. Raw [byte](evidence/issue160/bytes-receipt.json),
[inode](evidence/issue160/inodes-receipt.json), and
[evidence exhaustion](evidence/issue160/evidence-receipt.json) receipts retain before/after capacity,
sampled peak scratch, elapsed times, and fixture process I/O. Eighteen focused unit
tests, Ruff, and strict mypy also passed on Python 3.11.15 on A100.

These are bounded no-model qualifications. Actual model-load I/O and paired
placement measurements remain unqualified; no performance improvement is claimed.

## Correlated run status

The storage wrapper can run inside `matric-eval study-run supervise`. It inherits
`MATRIC_RUN_STATUS_DIR` and records admission, current usage, reservation ownership,
and the emergency receipt path in that run's atomic status document. Storage
failures retain their typed reason and actor/stage without changing task counts.
The outer supervisor reports cleanup pending while a storage reservation remains
active, including after an interrupted wrapper leaves a separately supervised
writer group. A successful process exit alone cannot discharge that obligation.

The status directory must remain writable on the separately reserved emergency
filesystem. A failure to publish storage ownership before starting the child
prevents child dispatch. A status write failure during cleanup is retained in the
storage receipt and produces a nonzero exit. This integration does not authorize
new task scheduling or certify GPU lease cleanup.
