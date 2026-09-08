# Independent suite scheduling

`matric_eval.studies.suite_schedule` schedules explicit `Schedule` / `Work`
records through an `Adapter` implementation. This is a serial executor. Each work
record contains the complete observation identities, verified execution
fingerprint, seed, scoring budget, declared replay capability, dependencies and
resident-model constraints. Seed and scoring budget must agree with the captured
fingerprint. Deferred work remains untouched even if its suite appears in the
explicit authorization list.

Call `plan(schedule, journal, adapter.preflight)` to produce a dry-run report.
Preflight must validate current admission evidence (#155), without loading a
target model. Planning checks all eligible work before selecting an order. Its
report includes frozen order, chosen order, reused accepted observation IDs,
fingerprint invalidation reasons, blocked/deferred dispositions, and expected
model loads. Only work opting into `group_resident` may share a resident model;
model identity and runtime/placement/isolation documents must match exactly.
Dependencies constrain grouping. The explicit amendment reason travels with the
plan: order changes are study amendments, not a claim of statistical equivalence.

Call `execute(schedule, journal, adapter, receipt_path)` only with an adapter
implementing current preflight, lifecycle start/stop (#156), and task execution.
The adapter must reset task state per call and preserve the supplied identities,
seed and scoring budget. Its terminal evidence must satisfy the existing
`TerminalAttempt` contract, including exact metric set, predecessor lineage and
native artifact hashes. The scheduler checks admission again before and after
each task. The stop method must return `True` only after verified cleanup;
exceptions and uncertain cleanup trigger a global stop. Partial acquisition also
receives cleanup. A suite-specific failure must be explicitly classified as
`SuiteFailure`; arbitrary exceptions are global resource/integrity failures.

Under `continue-independent`, a failed suite blocks its remaining work and true
dependents, while independently qualified suites continue. Under `stop`, any
suite failure blocks the remaining work. Shared integrity/resource failures stop
all subsequent work under either policy. No policy authorizes deferred TAU.

Recovery uses the #124 `ObservationJournal`, including its native-artifact
verification and immutable acceptance index. Matching completed Direct/BFCL work
already captured there can be reused without dispatch. A fingerprint mismatch
invalidates the requested reuse and never overwrites the prior scope; a changed
protocol needs an explicitly amended run/allocation identity. An interrupted
external intent remains blocked for review, including idempotent adapters whose
external reconciliation has not been proved. Completed acknowledgments lost after
journal commit are reused rather than executed again. Invalid terminals can be
retained without claiming acceptance via `retain_invalid_terminal`; only isolated
work with verified cleanup may get a new attempt with the previous attempt ID.
Previously accepted invalid outcomes remain blocked for explicit review.

Execution holds the same `.engine.lock` as the existing recovery executor, and
writes the journal intent before task dispatch. The private append-only receipt
records each plan, observed dispatch order, dispositions and final accounting,
with file and directory fsync. Receipt failures stop execution. Receipts are
projections; journal acceptance remains authoritative after process restart.
Storage budgeting must bound receipt growth and preserve emergency headroom.

A100 validation uses `tests/unit/studies/test_suite_schedule.py` and the existing
journal tests. The service qualification starts actual loopback HTTP worker
processes, rejects one suite's admission with HTTP 503, completes the independent
suite, restarts the scheduler in a separate process, and checks exact reuse and
dispatch accounting. It does not run TAU scoring or load a model. Real adapter
integration and active-study qualification must use the preflight/lifecycle
contracts and the authorized A100 launcher; these fixtures do not attest a GPU
service or historical evidence that was never committed to the journal.
