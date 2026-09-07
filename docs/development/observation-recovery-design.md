# Proposed observation recovery design

Status: design proposal for [#124](https://git.integrolabs.net/roctinam/matric-eval/issues/124),
under [#118](https://git.integrolabs.net/roctinam/matric-eval/issues/118). The journal,
fingerprint checks, and recovery integration described here are **not implemented
or qualified**. This document does not establish completion of an acceptance
criterion through design alone.

Construction depends on the result and execution contracts from #119 and #120,
and the isolated execution work in #123, delivered through
[PR #136](https://git.integrolabs.net/roctinam/matric-eval/pulls/136) at merge
`67e0cea2c39f7eae0f8db32bb0eb5b0229ed12cb`. Its qualified cleanup evidence supplies
the worker boundary; it does not itself establish journal recovery.
The public sample hooks in pinned Inspect 0.3.263 have been inspected on A100;
their ordering relative to durable native-log publication still needs executable
qualification before engine integration.

## Problem and preserved boundaries

Current checkpoints preserve completed benchmark results, with metric declaration
and optional comparison-configuration checks before reuse. They do not implement
an immutable sample/trial journal or prove effective runtime identity. Current
JSON state writes use a temporary file and rename; they do not establish the
power-loss durability proposed below. Declared registry revisions and model names
are insufficient evidence that an effective execution is unchanged.

The new journal would live separately from benchmark checkpoint files and study
journals. Existing study data, hashes, row order, native logs, and historical
reports remain authoritative and unchanged. Legacy checkpoint readers continue
to work. A readable historical result does not acquire verified per-sample
provenance merely because a new serializer can represent it.

This design promises idempotent persistence of accepted observations within a
qualified local filesystem boundary. It does not promise exactly-once model
requests or exactly-once external side effects, distributed orchestration,
network-filesystem durability, or safe replay of arbitrary agent tasks.

## Proposed records and identities

Use a dedicated SQLite database through Python's standard-library `sqlite3`, with
an independently versioned schema and explicit migration dispatch. Store the
schema version in database metadata and reject unknown newer versions. Keep
SQLite implementation details out of ordinary benchmark output.

The existing logical observation identity remains the tuple of run, model,
benchmark, allocation, sample, trial, and metric identities. Its canonical digest
must remain compatible with the versioned result contract. The persistence API
must validate the full tuple rather than trusting a caller-supplied digest.
Retries retain that logical identity and receive distinct attempt identifiers.

Proposed immutable records:

- **Execution identity:** a versioned canonical fingerprint document, its digest,
  and references supporting each effective identity component.
- **Attempt intent:** logical identity, stable attempt identifier, predecessor,
  execution fingerprint and adapter replay capability; committed durably before
  dispatching any work that can have external effects. An intent does not prove
  dispatch occurred; an intent without a terminal record represents uncertain
  work and requires the declared reconciliation or replay policy.
- **Terminal attempt:** a separate immutable record referencing that intent, with
  versioned outcome payload, canonical payload digest, native evidence references
  and any worker cleanup receipt. Completion appends this record rather than
  changing the original intent.
- **Acceptance:** one logical identity mapped to one immutable attempt and its
  payload digest, created in the same transaction as any newly inserted attempt.
- **Recovery disposition:** append-only reasons for conflict, unverifiable
  identity, incompatible identity, interrupted work, or manual recovery required.

A predecessor must belong to the same logical identity. Reject cycles, missing
predecessors, reused attempt identifiers with different payloads, and acceptance
of an attempt under a different execution fingerprint. When the result contract
requires several named metrics for one sample attempt, persist the completed
metric set together; do not expose a partially committed sample as complete.

Canonical encoding must specify UTF-8, key ordering, numeric rules, and schema
version. It must reject nonfinite numbers and ambiguous coercions. Artifact paths
and display labels do not substitute for verified content identity. Raw prompts,
responses, credentials, and generated programs need not be copied into the
journal: retain content digests and access-controlled native artifact references.
Hashes support consistency checks, not a claim of confidentiality or authenticity.

## Atomic acceptance and recovery invariants

The database is the authoritative journal and acceptance index. Avoid a separate
JSON index whose update would require a second atomicity mechanism. A transaction
starts with `BEGIN IMMEDIATE`, validates the fingerprint and predecessor, inserts
the immutable terminal attempt if absent, and inserts acceptance subject to a
unique constraint on the logical key. A durable pre-dispatch intent must already
exist. Foreign keys and uniqueness constraints reinforce
application validation. Commit acknowledgement occurs only after SQLite reports
successful commit under the qualified durability configuration.

Required behavior:

1. A crash before commit leaves no accepted observation from that transaction.
2. A crash after commit but before acknowledgement leaves one accepted
   observation. Retrying the identical commit request returns the existing
   receipt after validating all identifiers and payload digests.
3. Reusing an attempt identifier with a changed payload is a conflict. A second
   attempt cannot silently replace an already accepted outcome, even if its
   numeric score happens to match.
4. Concurrent writers serialize acceptance and receive either a matching
   idempotent receipt or an explicit conflict. They never use last-writer-wins.
   When another attempt is already accepted, commit the losing terminal attempt
   and an append-only conflict disposition without changing acceptance, then
   report the acceptance conflict after that transaction commits. Do not raise
   a uniqueness exception that rolls back the losing attempt history. A reused
   attempt ID with a different payload records a conflict disposition rather
   than overwriting its immutable terminal record.
5. Attempts recorded before acceptance remain available for diagnosis. An
   interrupted attempt cannot be promoted into a terminal observation without
   terminal evidence. Recovery cannot reconstruct an execution that was never
   durably recorded.
6. Cached aggregate indexes are disposable projections. Recovery derives them
   from validated committed records and fails closed on corruption or conflicting
   identity; it does not silently repair disagreement by choosing a row.

The request must carry a stable attempt identifier across lost-ack retries.
Generating a new attempt identifier on every persistence retry would destroy
idempotency. Execution retries and persistence retries are distinct operations.
A process crash during an external action remains an uncertain action even when
its local acceptance transaction did not commit. Dispatch requires a successful
durable intent receipt first. A crash between that receipt and actual dispatch
is conservatively uncertain too; local state cannot establish exactly when an
external service acted. Missing acceptance alone never authorizes replay.

## Filesystem and durability boundary

Choose one initial profile: SQLite `journal_mode=DELETE` with
`PRAGMA synchronous=EXTRA`, foreign keys enabled, an explicit bounded busy timeout,
and local filesystem storage. EXTRA includes FULL synchronization and additionally
synchronizes the containing directory after rollback-journal deletion. Verify the
requested journal and synchronous modes were actually applied. This proposal
uses rollback mode to avoid introducing WAL sidecar/shared-memory lifecycle and
backup rules in its first profile. SQLite documents the synchronization modes in
[the pragma reference](https://www.sqlite.org/pragma.html#pragma_synchronous) and
WAL's same-host/shared-memory boundary in
[the WAL documentation](https://www.sqlite.org/wal.html).

SQLite owns journal ordering and database synchronization. Its
[atomic-commit guarantees](https://www.sqlite.org/atomiccommit.html) depend on
operating-system, filesystem and hardware behavior, including functioning locks
and honored synchronization requests. Application code must
not claim that atomic rename alone guarantees durability. Initial database
creation and separately written receipt/artifact files need a reviewed creation
protocol: write to a unique temporary file, flush and fsync its data, publish
atomically on the same filesystem, and fsync the containing directory where
supported. Recovery must tolerate an orphaned durable artifact when its database
transaction did not commit; an accepted row may not claim a missing artifact was
verified. Do not use the existing fixed `.tmp` naming pattern for concurrent
writers.

Qualification must record the A100 test filesystem, mount configuration, SQLite
and Python versions, selected pragmas, and storage assumptions. The standard-library
SQLite version comes from the interpreter's linked runtime, not a separately
pinned Python package; record the effective `sqlite3.sqlite_version` in addition
to the Python version. The supported
boundary is the specifically validated local Linux filesystem with functioning
locking and sync semantics. Network filesystems and storage whose guarantees
cannot be established return an actionable unsupported-storage state. Do not
infer support from a path prefix or filesystem name alone.

Process-kill tests establish crash recovery at the tested process boundaries.
They do not emulate sudden power loss, controller cache loss, filesystem defects,
or dishonest storage acknowledgements. Any stronger durability claim needs
separate evidence. Document these limitations alongside the tested guarantees.

## Effective execution fingerprint

Compute a canonical fingerprint before authorizing reuse, with evidence for each
required component. Include:

| Component | Required identity evidence |
| --- | --- |
| Model | Effective provider and immutable model revision or weights digest; relevant tokenizer/quantization identity and effective generation configuration |
| Dataset | Ordered selected manifest, stable sample identities, content hashes, partition references, and resolved dataset revision |
| Prompt and solver | Effective prompt/template content, solver implementation identity and configuration, tool definitions and relevant execution configuration |
| Scorer and judge | Scorer implementation identity, named metric descriptors, grading configuration, effective judge revision/configuration when applicable |
| Sampler | Selection algorithm/version, selection seed, selected order, generation seed schedule, epoch/trial protocol and retry policy |
| Environment | Source/lock identity, effective dependency/runtime versions, execution image digest and platform, verified resource/isolation profile |
| Protocol | Result, journal, fingerprint and trial protocol versions; explicit missingness, timeout and aggregation policies where they affect retained observations |

Compare the canonical documents as well as validated digests at the boundary.
Separate declared metadata from observed runtime identity. An unavailable model
revision, unresolved dataset content, unverified environment, or unsupported
provider evidence blocks verified reuse with a component-specific reason. A
provider recording a seed does not prove that it honored the seed or that trials
are statistically independent.

Pre-execution evidence and post-execution receipts may differ in availability.
The implementation must define which evidence is required to authorize a request
and which is required before accepting its terminal observation. Resolve and
validate that distinction before enabling a provider adapter. A caller-provided
opaque hash alone is not sufficient proof of effective identity.

## Legacy handling and replay capabilities

Keep legacy benchmark files readable in place. Record quarantine dispositions in
the new recovery area rather than rewriting, deleting, or moving source evidence.
An incompatible checkpoint may be displayed as historical data while remaining
ineligible for verified reuse. Import requires actual per-sample evidence and
verified fingerprint components; unknown values must remain unknown.

Each execution adapter must declare a versioned recovery capability:

- Replay safe within the isolated, side-effect-bounded profile.
- Replay only with a supported idempotency key and reconciliation mechanism.
- Manual recovery required, including undeclared or non-idempotent adapters.

An interrupted external task with unknown completion must return actionable
recovery state identifying the attempt, available evidence, and required adapter
reconciliation. It must not automatically rerun on a missing acceptance row.
Capability declarations alone do not prove an external service's behavior; the
adapter needs fixtures covering the mechanism it claims.

For isolated workers, bind cleanup receipts to the exact owned worker/container
identity and attempt. A verified-absent receipt permits consideration of replay
under the declared capability. Cleanup uncertainty blocks automatic replay and
cannot turn a timeout or output-limit event into an accepted model failure. A
successful container-CLI exit is not a cleanup receipt. Integrate the actual #123
receipt contract after its delivery and qualification.

## Inspect integration findings and remaining checks

Read-only inspection of installed Inspect 0.3.263 on A100 identified public
`SampleEnd` events carrying `eval_set_id`, `run_id`, `eval_id`, `sample_id`, and
the full `EvalSample`. `on_sample_end` occurs after final success or exhausted
retries, once per epoch. `SampleAttemptStart` and `SampleAttemptEnd` expose a
one-based attempt number and attempt summary/error suitable for retaining native
retry lineage. These findings identify an integration candidate; they do not
prove durable ordering or complete attempt capture under abrupt termination.

Hooks are registered as import-time singletons and can observe concurrent runs.
Route each event through an explicit registered run/evaluation identity mapping;
do not use a process-global mutable “current run.” Verify the mapping against
sample, epoch and outer-trial identity before persistence. Copy event data rather
than mutating Inspect-owned samples. Unmatched or ambiguous events must not be
committed to another run's journal.

Inspect logs and swallows hook exceptions. Consequently, raising inside a hook
is insufficient to prevent a successful-looking engine result. Latch journal
write failures in the corresponding run's recovery state, expose that state on
return, and refuse verified reuse even if Inspect reports successful execution.
The engine must independently check durable acceptance receipts before declaring
recovery coverage. A received hook callback is not evidence of successful commit.

Integration fixtures must establish callback ordering before/after native-log
commit, simulate swallowed hook write failures, and exercise concurrent run
routing and repeated native sample IDs across epochs/outer trials. Until this
ordering is qualified, retain explicit unavailable native-artifact identity where
appropriate and do not treat a future artifact path as a verified content digest.

## Acceptance fixtures and evidence

Run executable validation only on the authorized A100 infrastructure, with
synthetic workers and temporary local storage. Retain exact source, lock,
profile, fixture and database hashes where meaningful; commands, exit status,
JUnit output, initial failures, skips and reviewer identity accompany delivery.
Expected outcomes must be specified independently of the journal implementation.

| #124 acceptance criterion | Proposed proving fixtures |
| --- | --- |
| Crash and lost acknowledgement preserve one acceptance and attempt history | Kill before/after intent commit, around dispatch, during terminal insertion, before/after acceptance commit and before acknowledgement; retry the same persistence request; verify one acceptance and all durably recorded intent/terminal history |
| Conflicting concurrent writers are detected | Independent processes race equal and differing payloads, reused attempt IDs, and different attempts on one logical key; assert exact receipts or conflicts, both differing terminal attempts retained, one acceptance and no overwrite |
| Fingerprint changes block reuse | Change each model, dataset-content/order, prompt, scorer, sampler, environment and protocol component independently; add missing/unverified component fixtures |
| Legacy checkpoints are readable without invented provenance | Read historical benchmark checkpoints and study artifacts; compare bytes/hashes before and after; assert no verified observation is created without evidence |
| Documented filesystem durability boundary is tested | Record effective SQLite modes and filesystem; inject process termination and interrupted artifact publication; reject unsupported storage and corrupt records; distinguish process crash from untested power failure |
| Unsafe external replay is refused | Synthetic non-idempotent action loses acknowledgement; assert no second action, actionable manual state; test supported keyed reconciliation and uncertain isolated cleanup separately |

Also test invalid schemas, truncated/corrupt payloads, predecessor cycles,
integer/string sample identity distinction, named-metric atomicity, model names
that collide under legacy filename sanitization, and aggregate index rebuilds.
The logical-key journal must not inherit legacy model-directory collisions.

## Proposed delivery sequence

1. Review this persistence design, the filesystem boundary, fingerprint contract,
   adapter capability states, and fixture expectations. Confirm #123 delivery and
   the remaining pinned Inspect hook ordering before construction dependent on those interfaces.
2. Deliver the versioned journal and recovery core in a separate PR, with synthetic
   fault/concurrency fixtures and a documented tested boundary. Keep it opt-in;
   this PR alone does not complete engine-level recovery.
3. Deliver effective identity capture and engine/adapter integration, including
   sample completion, native evidence linking, cleanup receipts, legacy
   quarantine and replay refusal. Validate all six acceptance criteria through
   their actual public execution paths before closing #124.

No live benchmark rerun or new model credentials are needed to qualify the
persistence invariants. Real provider identity support is enabled only when its
adapter can supply the required evidence; unsupported adapters retain explicit
unverified recovery state.
