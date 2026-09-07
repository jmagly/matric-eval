# Observation journal core

The observation journal implements the persistence core of
[#124](https://git.integrolabs.net/roctinam/matric-eval/issues/124), following the
[reviewed recovery design](./observation-recovery-design.md). It is an opt-in API
in `matric_eval.state.journal`. The separate [explicit recovery executor](./recoverable-execution.md)
connects it to bounded sample/trial dispatch and effective identity capture.
The core itself does not install Inspect callbacks or migrate historical checkpoints.

Existing benchmark checkpoints, study journals, native logs, and historical
reports are unchanged. The SQLite database is a separate authoritative journal;
there is no second JSON acceptance index.

## API and first dispatch

`AttemptIntent` declares one sample/trial scope and its complete named-metric
identity set. It includes a stable attempt ID, optional predecessor, execution
fingerprint, and replay capability. `record_intent` commits that declaration
before an adapter may dispatch work. It does not itself dispatch anything or
establish that provider evidence is verified.

The following sequence assumes an adapter has supplied `identities`,
`fingerprint`, and `capability`, and that first dispatch has already been
authorized. The directory must exist on supported storage. `execute_once` is an
adapter operation, not a journal API; it returns a `TerminalAttempt` with the
same attempt ID, full observation set, and applicable evidence/cleanup receipt.

```python
from pathlib import Path

from matric_eval.state.journal import AttemptIntent, ObservationJournal

directory = Path("/qualified-local-directory/recovery")
intent = AttemptIntent(
    attempt_id=stable_attempt_id,
    previous_attempt_id=None,
    identities=identities,
    fingerprint=fingerprint,
    replay_capability=capability,
)

with ObservationJournal(directory / "observations.sqlite") as journal:
    intent_receipt = journal.record_intent(intent)
    # Dispatch only after the durable intent receipt, under the adapter policy.
    terminal = execute_once(intent_receipt.attempt_id)
    acceptance_receipt = journal.commit_terminal(terminal)
    accepted = journal.load_accepted(identities, current_fingerprint=fingerprint)
```

This is a first-dispatch example, not a recovery loop. Repeating `record_intent`
is idempotent; repeating `execute_once` may have external effects. After an
interruption, inspect retained state and apply the recovery policy before any
further dispatch. An intent without a terminal remains uncertain even if the
process might have died before making the external request.

`commit_terminal` requires the durable intent, exact full identity documents,
complete metric set, matching predecessor, and matching cleanup attempt ID.
Only `completed`, `failed`, or `cancelled` execution states constitute terminal
evidence. Unknown, not-attempted, or partial execution cannot complete an intent.
The entire metric set is accepted atomically.

## Candidate evidence and acceptance

Immutable terminal payloads store every observation with `accepted=False`.
`commit_terminal` normalizes this field on a validated copy, so caller-owned
observations are not modified. The acceptance table separately identifies the
winning attempt for each logical observation.

`list_attempts()` exposes immutable candidate evidence, including losing
attempts, with `accepted=False`. `load_accepted(...)` returns a fresh projection
with `accepted=True` only after validating the complete acceptance index, full
requested identity set, current fingerprint, artifacts, and applicable cleanup.
The projection does not rewrite stored history. A durable terminal record alone
is not proof of acceptance.

Persistence retries use the same attempt ID and identical canonical request:

- A commit that succeeded before its acknowledgement was lost returns the same
  receipt when retried, without creating another acceptance.
- A different terminal payload under an existing attempt ID raises
  `JournalConflict` and retains a conflict disposition without overwriting the
  original payload.
- A distinct attempt losing an acceptance race retains its terminal payload and
  conflict disposition in a committed transaction before `JournalConflict` is
  raised. The winning acceptance remains unchanged, even if both scores match.

`dispositions()` returns the append-only diagnostic records. `audit()` checks
SQLite integrity, canonical payload digests, full identities, predecessor
lineage, and complete acceptance sets. It refuses inconsistent records rather
than selecting a convenient replacement. Hashes are consistency checks, not
authentication against an actor able to rewrite the database.

## Fingerprints and recovery decisions

`ExecutionFingerprint` has exactly seven components: model, dataset, prompt,
scorer, sampler, environment, and protocol. Each component contains a nonempty
structured JSON document and an explicit verified/unverified status. Unverified
components require an unavailable reason. Nested nulls and empty configuration
values are preserved; nonfinite numbers and Python-only values are rejected.
The versioned canonical encoding computes the digest internally. Comparisons
also check canonical documents directly, preserving distinctions such as JSON
booleans versus numbers.

These models validate declarations; constructing a verified component does not
capture or attest an effective model, provider, environment, or dataset revision.
Adapters still need evidence mechanisms. Unknown fingerprints can be persisted
as truthful history, but `load_accepted` raises `ReuseRefused` with ordered
component-specific reasons when either retained or current evidence is unknown
or their effective documents differ.

`recovery_decision` separates first execution, possible isolated replay, and
manual recovery. An isolated replay requires a verified-absent cleanup receipt
bound to the expected attempt and exact worker, with a digest-bearing evidence
reference. Uncertain cleanup blocks replay. An idempotency key alone does not
establish external reconciliation; the helper returns manual recovery with
`reconciliation_required`. Undeclared/non-idempotent external replay remains
manual.

For a committed terminal, the helper returns the **non-authorizing** action
`check_acceptance`, subject to immediate cleanup checks. It cannot grant reuse
because it has neither the acceptance index nor the current fingerprint.
Callers must use `load_accepted` for those checks. In particular, a losing
terminal cannot acquire reuse permission through this helper.

## Storage boundary and diagnostics

The writer observes Linux mount information and supports the local ext4 profile
with writable storage and no explicitly disabled barriers. There is no public
caller-supplied attestation override. The runtime observation selects the profile;
it does not establish that every ext4 device, mount, or hardware configuration
has been qualified. Delivery evidence must retain the actual validation mount,
options, Python/SQLite versions, and storage assumptions.

Connections verify `journal_mode=DELETE`, `synchronous=EXTRA`, and foreign keys,
with a bounded busy timeout and `BEGIN IMMEDIATE` for writes. Immutable-table
triggers reject updates and deletions. A new database is initialized in a unique
temporary file, synchronized, published by an atomic non-overwriting hard link,
and followed by directory synchronization. Racing initializers cannot replace
an existing journal. The existing directory must be prepared separately.

SQLite owns transaction synchronization and rollback-journal ordering. These
settings depend on functioning filesystem locks and honored synchronization
requests. Process-kill qualification does not simulate power loss, controller
cache loss, or dishonest storage acknowledgements. The storage evidence records
`power_loss_qualified=False`.

On unsupported storage, writes and verified reuse fail with
`UnsupportedStorage`. An existing database may be opened with
`ObservationJournal(path, read_only=True)` for `list_attempts`, `dispositions`,
and integrity diagnosis. Read-only mode does not bypass schema or corruption
checks and does not authorize reuse on unsupported storage. Unknown schema
versions are refused; no migration is guessed.

Digest-bearing artifact references must identify regular local files whose
content can be rehashed before acceptance and reuse. Missing or changed files
block those operations. Explicitly unavailable references stay unavailable.
The core does not publish or synchronize native artifacts; their producer owns
the separate durable publication protocol described in the design.

## Validation coverage

The focused A100 run passed 57 tests: 26 journal, 27 identity, and four Inspect
hook tests. This records focused qualification, not the outcome of subsequent
full CI or future engine integration.

Relevant fixtures are in
[`test_observation_journal.py`](../../tests/unit/test_observation_journal.py):

- `test_process_kills_and_lost_ack` kills owned child processes at terminal
  insertion, before commit, after commit before acknowledgement, and after the
  receipt. It checks exact accepted counts and idempotent retry.
- `test_independent_writers_preserve_loser_history` races independent processes
  with equal/different attempt IDs and payloads, retaining losing history.
- `test_durable_intent_atomic_named_metrics_and_idempotent_receipt` verifies
  pre-dispatch intent and rejects partial metric acceptance.
- `test_changed_effective_component_refused_through_storage` exercises all seven
  fingerprint components through the public load path.
- Artifact, schema, corruption, unsupported-storage, and nonterminal-state
  fixtures check fail-closed behavior.

On CI overlay filesystems, a private fixture seam exercises SQLite transaction
semantics without skipping the core fault/race suite. JUnit records distinguish
`sqlite_transaction_semantics_only` from `actual_ext4`; the seam does not qualify
an unsupported filesystem and is not exposed by the production API.

[`test_inspect_recovery_hooks.py`](../../tests/integration/test_inspect_recovery_hooks.py)
uses real Inspect 0.3.263 evaluations with mockllm and no model network requests.
It qualifies sample logging/callback ordering, per-epoch completion and retry
lineage, overlapping evaluation identity routing, and swallowed hook failures.
A native successful evaluation can coexist with a failed hook write, so future
engine integration needs an independent failure latch and durable receipt checks.
Callback order does not establish a final archive hash or power-loss durability.
