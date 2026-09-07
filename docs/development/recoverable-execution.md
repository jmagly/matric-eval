# Explicit sample and trial recovery

`EvaluationEngine.run_recoverable_benchmark` connects the [observation journal](./observation-journal.md)
to a deliberately bounded Inspect execution profile. The caller supplies a frozen
`Task`, a stable `run_id`, a dedicated `recovery_dir`, a primary metric and complete
direct metric descriptor mapping, and a nonempty unique `generation_seeds` list.
`selection_seed`, `generation_config`, `model_base_url`, and `model_args` are explicit
inputs. No existing benchmark or study run is migrated automatically.

The initial profile supports text samples with explicit unique integer/string IDs,
one registered `generate()` solver, and the reviewed registered `match`/`includes`
scorers with decomposable mean/accuracy descriptors. Unsupported executable task
features and opaque closures are rejected before dispatch. Provider adapters,
implicit thinking overrides, and judge overrides are rejected by the engine API.
Generated-code sandbox recovery is **not supported** by this profile: an image and
worker cleanup identity must be integrated before that capability can be added.

The dataset is materialized exactly once into a private `MemoryDataset` before
validation and capture; dynamic `sample_source` callbacks are rejected before
materialization. Retained native input, target, choices and sample metadata must
match the exact frozen dispatch sample, in addition to its typed ID and epoch.
Registered or cached Inspect hooks are rejected, including a repeated check after
model initialization and immediately before dispatch.

Each sample is dispatched separately for one Inspect epoch, once per frozen outer
trial (`trial-0`, `trial-1`, ...). Inspect sample retries, model retries and Inspect
checkpoints are disabled. A directory-wide nonblocking process lock prevents two
controllers from dispatching into this recovery directory simultaneously. The
journal's storage gate remains Linux local ext4 with DELETE/EXTRA semantics; these
settings do not qualify power-loss behavior.

## Durable boundary and identity

Before dispatch, the executor captures the actual task, descriptor, provider,
configuration and environment evidence through `execution_fingerprint`. It checks
the complete existing frozen plan before dispatching any new scope. The seven
components are model, dataset, prompt, scorer, sampler, environment and protocol.
No caller-supplied opaque digest can mark a component verified. The default
first-party fixed-output `mockllm/model` is the initial controlled provider profile.
Ollama metadata observed before and after a request does not bind that request to
an immutable model: a tag can change and change back. Ollama therefore remains
unverified even when both observations agree. Real-provider first dispatch may
retain measurements, but qualified reuse remains blocked until an actual immutable
request/native-artifact binding is implemented. No live-provider qualification is
claimed here. The actual explicit
endpoint is used to construct a nonmemoized provider Model instance. That same
instance is checked by capture and passed to Inspect; a string-keyed provider
cache cannot substitute an unchecked implementation. Identity is captured again after
dispatch; changed evidence prevents terminal acceptance.

The executor commits a complete named-metric intent before calling Inspect. It
then copies the returned native `.eval` bytes from the owned dispatch directory
into `native/<sha256>.eval`, fsyncs the file, publishes without replacing an
existing file, and fsyncs the directory. It decodes these retained bytes, checks the
single native sample/epoch, aligns observation identities to the outer trial,
and commits the complete direct metric set atomically. Native named metrics,
derived summaries, statuses and metadata remain in the retained artifact and
per-sample `BenchmarkResult`; no fake derived sample measurements are invented.

A successful same-dispatch commit receipt binds the exact terminal digest and
complete logical identity set. This allows the current dispatch to report accepted
measurements even when evidence was explicitly unverified. It does **not** authorize
future reuse. Later calls use `load_accepted`, which verifies identity, acceptance,
complete metrics and artifact bytes. Unknown or changed identity blocks reuse.

A process interruption before the terminal acceptance leaves an intent requiring
manual external reconciliation. The process lock releasing after a crash does not
prove that an external request stopped. No replay or worker cleanup is invented.
A lost commit acknowledgement may be recovered through the qualified acceptance
index on a later call. Orphan native logs are retained as diagnostic evidence and
never treated as acceptance on their own.

## Recovery report version 1

The returned object has `recovery_schema_version: "1"`, stable `run_id`, `model_id`,
`benchmark_id`, `selection_seed`, the full `generation_seeds` schedule, `limitations`
and ordered `sample_results`. `recovery_status` is `complete` only when every
requested scope has accepted measurements; otherwise it is
`manual_recovery_required`. `journal_capture_complete` records that persistence
boundary separately from `execution`, job `status` (`success`, `partial`, `error`)
and `eligibility`. A captured failed or cancelled native attempt never becomes
a successful job. Unknown effective identity makes report eligibility false even
when the same-dispatch measurements were accepted. Native outcome fields retain
model correctness separately.

Each sample result includes:

- `sample_id` (canonical JSON encoding of the original typed ID), `trial_id`,
  `generation_seed`, `attempt_id`, and captured `fingerprint_sha256`.
- `reuse_eligibility` with an explicit boolean and reasons.
- `disposition`: `executed`, `reused`, or `manual`, plus `reasons`.
- `acceptance_basis`: `same_dispatch_commit_receipt`, `qualified_journal_reuse`,
  or null when acceptance cannot be established.
- `observations`: the complete accepted direct measurements, or an empty list
  when acceptance is not established; `native_result`: the full typed native
  `BenchmarkResult` decoded from the accepted artifact, or null.
- `diagnostic_artifacts`: retained native references from the current dispatch,
  including unaccepted evidence; these never authorize reuse by themselves.

There is no across-trial or across-sample aggregate in this recovery schema. A
consumer must select an explicit estimator and eligibility policy separately.
Infrastructure exceptions before any durable request may raise. Interrupts are
propagated so callers can stop promptly; they do not erase durable intent.

## Historical benchmark checkpoints

`run_all` treats a previously attempted coarse checkpoint as `legacy_unverified`,
with `execution: unknown`, a null score, false eligibility and an actionable manual
recovery message. Its prior payload is available only as `historical_result`, not
as an observation result eligible for ranking. It neither dispatches that benchmark
nor rewrites a historical result artifact. Before untouched benchmarks mutate the
shared live model/run state, their full original bytes are retained under
`legacy-history/<sha256>.json`, with source paths and digests in
`legacy_checkpoint_artifacts`. Previously untouched benchmarks may
still execute. Start a new run to evaluate again, or opt into this API with a new
recovery directory. CLI `--resume` refuses previously attempted coarse state before
provider creation or report rewriting; `--fill-gaps` does not bypass this rule.
New generic runs publish explicit pending model/benchmark scopes before their
pending run state. A missing model or benchmark record is unknown, never proof
of untouched work. CLI coarse resume requires a wholly pristine pending run;
attempted lifecycle markers or incomplete initialization require manual recovery.
Existing study journals and the frozen study remain unchanged.

## Validation boundary

`tests/integration/test_recovery_execution.py` uses the actual pinned Inspect
`mockllm/model` provider, with no inference service, for first acceptance, later
reuse, interrupted dispatch, lost acknowledgement, changed identity, artifact
mutation, and unknown-component behavior. Spawned controllers are killed before
intent, before dispatch, after execution, after durable native artifact retention,
and between accepted samples; only scopes with no prior intent or qualified
acceptance may proceed automatically. A private storage seam permits transaction
semantics tests on other filesystems and records that weaker scope in JUnit.
Execution and final qualification are performed on A100; this document does not
claim a passed run or power-loss qualification without its retained receipt.
