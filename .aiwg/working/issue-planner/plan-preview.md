# Native 1+ GPU execution: filing preview

Status: approved and filed 2026-09-09.

Live mapping:

- MGPU-EPIC: #178
- MGPU-01: #179
- MGPU-02: #181
- MGPU-03: #180
- MGPU-04: #182
- MGPU-05: #183
- MGPU-06: #184

## Scope and disposition

This backlog makes exact one-or-more GPU allocations a native execution
contract while keeping one-GPU runs supported. It does not redesign the
deployed broker: the Basilisk broker already accepts repeated exact UUIDs and
checks requested memory against their aggregate free memory. It does not claim
TAU qualification or resume issue #154 merely by landing infrastructure code.

Related existing work:

- #154 remains deferred until the target-independent TAU checks and the new TP2
  qualification gates pass.
- #114 remains the parent study whose diagnostic replay may consume the
  qualified profile.
- Closed #156 supplies the single-GPU lifecycle baseline and cleanup evidence;
  the proposed work extends that contract instead of reopening it.
- Closed #159 supplies the public-broker client qualification baseline.
- #92-#94 remain the release/publication path. This backlog does not duplicate
  package validation or release publication.

## Proposed issues

### MGPU-EPIC

Title: `epic(gpu): make resident execution native to exact 1+ GPU allocations`

Labels: `type:epic`, `infrastructure`, `priority:must`

Purpose: own the cross-cutting contract, implementation waves, evidence gates,
and relationship to #154 and #114.

Acceptance:

- Every scalar GPU boundary is either migrated or documented as an intentional
  compatibility input.
- Exact ordered UUID sets remain consistent across request, lease, container,
  CUDA visibility, server receipt, report, and cleanup.
- Single-GPU regression coverage and a qualified two-A100 TP2 path both pass.
- Unsupported device counts/topologies fail closed rather than silently
  expanding visibility or changing parallelism.
- All child issues are closed with evidence links before the epic closes.

### MGPU-01

Title: `refactor(gpu): define versioned allocation and parallelism profile contracts`

Labels: `infrastructure`, `priority:must`

Depends on: none. Parent: MGPU-EPIC.

Scope:

- Add a canonical non-empty ordered `GpuAllocation` with unique exact UUIDs,
  aggregate requested MiB, and optional topology policy.
- Add a distinct stable `ParallelismProfile` with TP/PP sizes, required device
  count, supported accelerator model, and topology policy.
- Define serialization, validation, fingerprinting, and compatibility reading
  for legacy scalar `gpu` records without rewriting immutable evidence.

Acceptance:

- Empty, duplicate, malformed, count-mismatched, and unsupported allocations
  are rejected with typed diagnostics.
- UUID ordering is stable and evidence-bearing; normalization never sorts or
  widens the requested set.
- Initial profiles are TP1 on one A100 and TP2 on two A100s; TP3 is rejected
  until separately qualified.
- Schema/version and compatibility behavior have focused unit tests.

### MGPU-02

Title: `refactor(runs): make lifecycle and suite scheduling GPU-set native`

Labels: `infrastructure`, `priority:must`

Depends on: MGPU-01. Parent: MGPU-EPIC.

Scope:

- Replace scalar lifecycle/scheduler storage and CLI flow with repeated exact
  GPU UUIDs while retaining a deliberate one-GPU compatibility path.
- Send the complete ordered set and aggregate memory in one broker request.
- Make overlap detection, lost-ack recovery, evidence, and cleanup operate on
  the allocation as one atomic set.

Acceptance:

- Scheduler fingerprints and resource records bind the exact ordered set.
- Broker request/receipt and `CUDA_VISIBLE_DEVICES` agree exactly and in order.
- Partial acquisition is impossible; any surviving member blocks release of
  the allocation and produces actionable evidence.
- Multi-worker/cgroup failure injection covers normal stop, supervisor loss,
  partial CUDA survival, stale lease recovery, and overlapping attempts.
- Existing single-GPU lifecycle tests remain green.

### MGPU-03

Title: `feat(studies): authorize and attest multi-GPU vLLM profiles`

Labels: `agentic`, `infrastructure`, `priority:must`

Depends on: MGPU-01. Parent: MGPU-EPIC.

Scope:

- Replace the protocol's hard-coded TP1 restriction with a declared profile
  allowlist and validate it against the selected allocation.
- Derive vLLM TP/PP arguments from that declared profile, not an undocumented
  runtime override.
- Record effective parallelism, exact visible UUIDs, runtime/image identity,
  and profile identity in server/readiness evidence.

Acceptance:

- TP1 and TP2 configurations validate; incompatible counts, models, topology
  policies, and unregistered profiles fail before model acquisition.
- Study identity/fingerprint changes when the parallelism profile changes.
- Receipts and reports can distinguish declared from effective settings and
  reject disagreement.
- No automatic selection of every host-visible GPU is permitted.

### MGPU-04

Title: `refactor(studies): migrate GPU wrappers, replay, storage, and reporting to exact sets`

Labels: `agentic`, `infrastructure`, `priority:must`

Depends on: MGPU-02, MGPU-03. Parent: MGPU-EPIC.

Scope:

- Migrate resident and offline Qwen wrappers, Docker device selection, paired
  replay, storage lifecycle parsing, report rendering, examples, and fixtures.
- Keep secrets and lease tokens out of public evidence.

Acceptance:

- Docker receives exactly the declared comma-separated UUID selector with no
  quoting-based widening.
- Replay compares ordered sets rather than a singleton literal.
- Reports render the attested effective profile/allocation, not only protocol
  defaults.
- Shell and Python tests cover repeated options, duplicates, malformed input,
  unsupported profiles, exact argv, and TP1 compatibility.

### MGPU-05

Title: `test(studies): qualify two-A100 TP2 execution and cleanup on Basilisk`

Labels: `agentic`, `benchmark`, `infrastructure`, `priority:must`

Depends on: MGPU-02, MGPU-03, MGPU-04. Parent: MGPU-EPIC. Relates to #154.

Scope:

- Qualify the preferred GPU0/GPU2 NVLink pair on Basilisk using one exact
  scoped lease and the pinned Qwen3.8/vLLM environment.
- Run topology/P2P and communication smoke checks, model readiness,
  content-free inference, bounded TAU diagnostics, and set-atomic cleanup.

Acceptance:

- Evidence records clean commit, exact UUID/rank order, topology/P2P, driver,
  runtime, broker hash, image digest, aggregate request, timestamps, commands,
  exit states, and cleanup.
- The container sees only the two selected A100s and vLLM reports TP2.
- A content-free inference canary succeeds before any sensitive evaluation.
- Required bounded TAU admission trajectories produce parseable evidence or a
  typed blocker; infrastructure failure is not reported as model score.
- Both ranks, all CUDA allocations, container, lease, mounts, and temporary
  storage are proven gone after success and injected failure.
- Raw prompts, outputs, and lease credentials are not published.

### MGPU-06

Title: `docs(gpu): publish 1+ GPU configuration, migration, and operations guidance`

Labels: `infrastructure`, `maintenance`, `priority:should`

Depends on: MGPU-02, MGPU-03, MGPU-04, MGPU-05. Parent: MGPU-EPIC.

Scope:

- Document repeated UUID configuration, aggregate-memory semantics, profile
  selection, topology qualification, evidence handling, troubleshooting,
  rollback, and legacy scalar deprecation.
- Update the Qwen study runbooks only with qualified commands and receipts.

Acceptance:

- TP1 and qualified TP2 examples are reproducible and do not expose tokens.
- Operators can distinguish capacity rejection, topology/profile mismatch,
  readiness failure, and cleanup failure.
- Migration and rollback retain immutable legacy evidence.
- Docs and CLI help agree with executable behavior.

## Dependency waves

1. File MGPU-EPIC, then MGPU-01.
2. Implement MGPU-02 and MGPU-03 after MGPU-01; they may proceed independently.
3. Implement MGPU-04 after both execution contracts stabilize.
4. Execute MGPU-05 only from the exact reviewed implementation commit.
5. Complete MGPU-06, close the epic, then decide whether #154 can be resumed.

## Recommended decisions

- Treat allocation and parallelism as separate contracts and cross-validate
  them; aggregate memory alone must not imply tensor-parallel behavior.
- Preserve caller-supplied UUID order because it defines CUDA rank order.
- Qualify only TP1 and TP2 initially. Do not infer TP3 support from three A100s.
- Use GPU0/GPU2 as the first Basilisk TP2 target because the observed topology
  provides NVLink; require fresh topology evidence at qualification time.
- Keep #154 deferred while infrastructure lands. Resume it only after MGPU-05
  passes both target-independent TAU admission and TP2 lifecycle gates.

## Filing verification

Operator approval was received. The epic and six child issues were created in
dependency order. The filed issue bodies use live issue references; #154 and
#114 were cross-linked to the new backlog. Final readback on 2026-09-09 verified
all seven issues are open, their labels and artifact links are present, symbolic
keys are absent, and every dependency reference resolves within the filed graph.
