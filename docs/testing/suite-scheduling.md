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

## Supported command adapter

Use `matric-eval study-run schedule plan PLAN.json --journal JOURNAL.sqlite
--directory PRIVATE_RUN_DIRECTORY`, then use `execute` with the identical inputs
and selected policy. `python -m matric_eval.studies.schedule_cli` exposes the same
operations with `--plan PLAN.json`. A nonzero exit means at least one failed,
blocked or invalidated disposition remains; deferred work alone is not an error.
The directory must be private (0700), and each run must have its own directory.

The JSON document validates against `schedule_cli.CommandPlan`: `schedule` is the
`Schedule` document described above; `bindings` maps work keys to `Binding`
documents. Each binding includes the full preflight plan, target service command,
exact GPU UUID, broker socket, Docker endpoint, requested MiB, readiness timeout,
task command, task timeout and optional explicitly suite-local exit codes. Use `capture_binding(binding)` before freezing work; its digest includes argv,
resolved executable bytes, declared input/code bytes and scheduler/lifecycle code.
That digest must equal the work's captured
`fingerprint.environment.document.scheduler_binding_sha256`; the work's
`residency` must exactly equal its service document. These checks prevent command
changes or incompatible runtime placement from silently preserving reuse or
resident grouping. Keep the binding in the frozen protocol capture rather than
editing hashes after a run.

The service command runs under `resource_lifecycle`, which expands `{container}`,
`{resource_id}` and `{ready_base}`, owns the lease and confirms readiness. The
scheduler registers its lifecycle controller before dispatch and polls the durable
ready state. It runs target checks before each native task command. Task commands
receive `MATRIC_SCHEDULE_REQUEST` (a private JSON file with work, journal intent and
resource-record path) and `MATRIC_SCHEDULE_TERMINAL` (a fresh output path). They must
emit the existing `TerminalAttempt` JSON contract, referencing retained native
artifacts. They must not manufacture a successful observation for missing native
evidence. Each command gets a fresh attempt directory and process group.

Both controller and task groups are registered behind a pipe gate before their
first instruction. Restart reconciliation runs under the journal engine lock,
stops only attested process identities, checks remaining task groups, and invokes
the existing lifecycle reconciliation before considering new allocation. Unknown
ownership remains a global blocker. Runtime output is drained into bounded,
sanitized tails, and task/controller groups are cleaned up before later work.
The CLI qualification exercises the actual subprocess entry point, Unix broker
RPC, lifecycle controller, preflight stages and journal across process restarts;
its Docker command shim is explicitly synthetic and does not qualify GPU cleanup.

For prior #124 Direct/BFCL journal scopes, use `reuse_only: true` with the current
fingerprint captured by the existing recovery profile. This preserves the prior
identity documents without adding a new command-adapter fingerprint component.
No command binding is required, and missing/incompatible acceptance blocks the
entry rather than making it executable. This mode trusts the supplied current
fingerprint to the same extent as the existing journal API; it does not synthesize
current capture from old evidence. Native artifact hashes are still verified by
`load_accepted`. Use a freshly captured fingerprint, never a copied historical one.
For `recoverable-text-sample/1`, copy the current captured sampler's complete
`effective_config` into `scoring_budget`; the existing fingerprint is retained
without adding a new protocol field. The scheduler validates exact equality.
