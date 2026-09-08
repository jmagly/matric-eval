# Study preflight before target allocation

`matric-eval study-run preflight PLAN.json RECEIPT.json` runs static, CPU/sandbox,
and auxiliary checks in that order, without invoking the target acquisition command.
Execute this entry point **inside the intended service**, after setting its user,
working directory, environment, TMPDIR, umask, mounts and limits. The receipt
records the observed context; executing it in a developer shell does not qualify
another service. Environment values are hashed rather than written to receipts.

The `matric_eval.studies.preflight.tau_plan` builder requires independent frozen
input, patch, dependency, official task-loading, sandbox, launcher/adapter smoke,
simulator and embedder checks. Its Tau commands run in the specified interpreter,
using `scripts/preflight_qwen38_tau.py`. The simulator/embedder commands must use
actual broker client qualification with the same arguments as the intended run.
A fabricated receipt or mocked success is not live-client qualification. The
builder does not start deferred TAU scoring or change any protocol input.

The input check and actual Tau adapter share exact unique membership validation.
Domain-grouped input is reordered in memory to the manifest's interleaved order;
frozen input files are never rewritten. Duplicate allocations/IDs, substituted
or missing tasks, manifest hash tampering, summary/input and protocol hash
mismatches fail before acquisition.

## Plan contract

The schema is `matric-eval.study-preflight/1`. `checks` is a list of at most 64
checks, each with these fields:

```json
{
  "id": "banking-sandbox",
  "stage": "cpu",
  "command": ["/absolute/venv/bin/python", "/absolute/check.py"],
  "inputs": ["/absolute/check.py", "/absolute/runtime-lock.json"],
  "timeout_seconds": 120,
  "freshness_seconds": 300,
  "repetitions": 3,
  "deterministic": false,
  "receipt_contract": {"schema": "sandbox/1", "passed": true}
}
```

Stages are `static`, `cpu`, `auxiliary`, and `target`. The first three must be
explicitly present. A check receives a fresh private `MATRIC_PREFLIGHT_RECEIPT`
path and distinct `MATRIC_PREFLIGHT_EVIDENCE_ID`. It must exit successfully and
write JSON matching its required receipt fields and values; type constraints use
`{"type":"string"}` (also object/array/integer/number/boolean). This catches obsolete
receipt fields even after the behavioral assertion succeeds. Receipts are limited
to 1 MiB; stdout/stderr are continuously drained into 8 KiB tails. Failed commands
retain sanitized exit code, signal, stdout/stderr and exception attribution. All
independent pre-target checks continue after a failure.

Fingerprint inputs must include every relevant source, dependency lock/runtime
inventory and input artifact, including code executed by another interpreter.
The engine also fingerprints itself and the actual caller's package inventory,
Python, environment, mount table, user, cwd, limits and umask. Unknown dependency
closure is a reason to leave `deterministic: false`. The Tau builder conservatively
reruns all checks because its external benchmark environment is independently
managed. Only explicitly deterministic static checks may reuse matching success
from a completed admitted receipt; CPU and live checks always rerun. Each reused
repetition retains its original evidence ID and completion time. Expired evidence,
changed fingerprints, failed/incomplete runs and duplicate repetition IDs cannot
qualify admission. No source-only digest is claimed as runtime qualification.

Call `validate_admission(receipt, plan, max_age_seconds)` immediately before target
acquisition in the same service context. It rehashes declared files and actual
runtime context, verifies every required repetition and enforces both overall and
per-check freshness. If the lifecycle changes the execution environment, qualify
again in that environment.

## Complete launcher smoke

`--launch` additionally requires `target_launch`, `target_cleanup`, and `adapter`
argv lists and an `adapter_receipt_contract`. It invokes target acquisition only
when all pre-target checks passed, runs target-resident checks, invokes the
adapter, validates its serialized receipt, and invokes cleanup even on failure.
These commands must be lifecycle controllers with durable external ownership;
raw background servers are unsuitable because check command process groups are
terminated on return or timeout. The lifecycle subsystem remains responsible for
crash/restart and GPU ownership recovery.

Before using a costly target, include a CPU-stage smoke that invokes the actual
adapter against a controlled endpoint and validates the same receipt contract.
Target-resident checks qualify only after an admitted launch. A pre-target
receipt does not claim target-context, model-quality or live broker qualification.

The report includes elapsed time, checks reused/reexecuted, target launch command
count and refused target attempts (`target_loads_avoided`). The last metric counts
an admission refusal, not an inferred GPU hardware event. Controlled failing
fixtures additionally assert that their acquisition marker was never created.

The A100 test suite exercises the actual public CLI, subprocess adapter, real HTTP
socket with chat request shape, and receipt serialization. It also exercises
missing dependencies, subprocess failure/timeouts, incompatible receipt schema,
independent diagnostics, three distinct repetitions, runtime/input changes and
freshness. This controlled endpoint qualifies launcher mechanics, not the live
LiteLLM broker path, which is covered by the separate client conformance profile.

For lifecycle/scheduler integration, `execute_target_checks(plan, target_receipt,
admission_receipt, max_age_seconds=300)` validates admission and runs only the
explicit target checks against an already-owned resident. It never reacquires,
launches, invokes the scored adapter or releases a lease. Its receipt is separate
from pre-target admission; the lifecycle controller owns cleanup on rejection.

The `launcher` mode of `preflight_qwen38_tau.py` loads one selected immutable task
through the official loader, roundtrips the actual `TextRunConfig` schema, calls
Tau's actual `generate` and `UserMessage` serialization against a controlled HTTP
endpoint, and writes the task/config/response through the production adapter's
private receipt serializer. It does not call `run_single_task` or score the task.
Missing imports in the resolved Tau environment therefore fail this check before
any target acquisition.

`auxiliary_client_check(python=..., checkout=..., profile=..., role="simulator")`
produces the simulator command check; `role="embedder"` invokes the embedding CLI
and requires its measured dimensions. It invokes the existing `qualify_auxiliary_client.py`
public-broker canary with the exact profile, validates the returned own logical
and broker request IDs and lane, and emits a bounded preflight receipt. Its
`transport_passed` field means actual client transport and own-request correlation;
`execution_digest_binding` remains explicitly `unverified`, and semantic
calibration is not performed. A completion probe cannot be labeled an embedding
qualification. The embedder check must separately exercise the actual embedding
client, dimensions and broker evidence required by the selected profile.
