# Calibration v2 execution contract

`calibration-v2-plan.yaml` is a versioned execution amendment, not a replacement
for `protocol.yaml` or a reassessment of historical official rewards. Its strict
loader is `matric_eval.studies.calibration_plan`. The loader checks the canonical
base-protocol hash, three immutable checkpoint pins, seed, every allocation,
all four stages, thresholds, canaries, attribution and replay controls. Unknown
or missing fields and scalar type changes are rejected. The canonical plan hash
must be bound into all new evidence and gate decisions.

```bash
PYTHONPATH=src python -m matric_eval.studies.calibration_plan \
  studies/qwen38-obliteration-2026-09/calibration-v2-plan.yaml \
  --protocol studies/qwen38-obliteration-2026-09/protocol.yaml
```

This command is local validation only. It does not load models, contact inference
services, authorize an expansion, write evidence, or change scores.

## Stages and paired execution

The 100, 300, 600 and 1,200 counts are cumulative unique scored tasks **per model**.
Each stage uses the declared prefix of each allocation's sealed full manifest.
Canonical IDs and generation seeds remain paired across all three checkpoints;
the existing protocol's hash selection and seed algorithm remain authoritative.
The BFCL selection continues round-robin across its five official categories;
prerequisite and prior-scenario turns run in order as unscored overhead. No failed
task may be replaced with a more favorable item.

The 100-task calibration establishes pipeline validity and cost, not a winner or
new acceptance thresholds. Before any execution, seal model/GPU crossover blocks,
fixed ordered request-batch boundaries, replicate selection and seeds, and exact
effective runtime receipts. Direct generation remains offline; agentic generation
is serialized online. Only A100 is authorized for actual model generation.

Stages release only after all three models have complete paired coverage, a
mechanical go decision and explicit operator approval. A stage-1,200 go means
ready for analysis, not authorization to extend the study. Do not increase sample
size until significance or change thresholds based on observed model scores.

## Validity gates and denominator

All critical **pipeline** identity, context-budget and termination defects must
be zero. Direct generation validity and parse validity must each be at least 99%;
agentic trajectory validity must be at least 98%, separately for every model.
These are engineering validity rates, not answer accuracy or task success rates.
A wrong answer or target timeout with intact, attributable evidence can be a valid
trajectory and still receive quality score zero. A simulator loop after successful
repair is a pipeline termination defect, not evidence of failed target reasoning.

Direct denominators count every planned primary call, including MT-Bench turn two.
Thus stage 100 requires 85 direct calls plus 20 agent trajectories per model;
stage 1,200 requires 1,000 direct calls plus 250 agent trajectories. No rounding
down is allowed: at stage 100, one invalid direct call or agent trajectory fails
its rate gate. Missing first attempts remain in the planned denominator. Replays,
retries and BFCL support turns do not inflate the scored denominator. All support
turns still require provenance, attribution and timing in the attempt ledger.

Parse validity means the expected response/scorer format can be interpreted, not
that the model was correct. Attribution owners are exactly `target-model`,
`simulator`, `evaluator`, `context-runtime`, `harness-interface`, and
`mixed-uncertain`. Record actor and failure stage separately from causal owner:
a tool actor or parse-stage exception does not establish model blame. Store task, model,
replicate, seed, actual request settings, timestamps, partial trace, exception,
official reward/termination and analytic status. Preserve unresolved cases and
missingness bounds; never infer target blame from an error-only JSON artifact.

## Canary evidence

All twelve declared fixtures must pass three repetitions before calibration and each
expansion gate. Fixtures are unscored and are not chosen for target-model success.

- Terminal reference and invalid solutions test the official verifier; command
  JSON and completion fixtures use a scripted responder. These checks must be
  model-independent and prove that a valid solution can complete within the pinned
  runtime budget. A target timeout is separately classified by phase (generation,
  command execution, summarization, setup, or verifier).
- JSON transport and malformed-tool fixtures must fail closed. Terminal recovery
  is limited to one attempt inside the existing pinned task wall-clock watchdog;
  context/output recovery cannot enlarge the budget. HTTP timeouts must cancel
  work and must not submit an unverified answer. Any retry after a potential side
  effect requires demonstrated idempotency; absent that proof, preserve the
  uncertain result and stop. These fixtures use model-independent responders.
- Tau fixtures test nonempty user content or valid tool calls, explicit STOP,
  TRANSFER and OUT-OF-SCOPE handling, user-tool ownership/persona, and bounded
  termination after a known successful state. They must detect repeated payment
  checks and goodbye loops. Check effective simulator thinking and output limits,
  not only requested settings. A verified-state success latch must prevent further
  side-effecting actions and drive bounded termination. It does not overwrite the
  official evaluator reward. A post-success simulator/runtime-invalid trajectory
  remains analytically invalid and is excluded as a paired task, with its official
  zero and secondary verified-state evidence both preserved.
- Context fixtures cover near-boundary tool payloads with output reserve; the
  fixed 32K context cannot be overbooked. BFCL fixtures exercise all five backends,
  usable search/fetch responses and complete isolated dependency/memory state.

Canary producers and ledger validators must verify artifact contents and hashes;
the mechanical gate below checks supplied counters, attestations and hash shape,
not the truth of files it has not read. A fabricated hash is not evidence. Runner
integration and execution of these canaries are separate implementation work.

## Gate evidence interface

`CalibrationPlan.evaluate_gate(evidence)` accepts exactly these keys:

- `plan_sha256`: the validated plan's canonical hash.
- `stage`: integer 100, 300, 600 or 1200.
- `models`: all three exact model IDs, each mapping to nonnegative integer counts
  `direct_attempted`, `direct_generation_valid`, `direct_parse_valid`,
  `agentic_attempted`, `agentic_trajectory_valid`, `attributed_attempts`.
  Attribution covers direct calls plus scored agent trajectories; the ledger
  separately validates support turns. Attempted counts must equal planned counts.
- `critical_defects`: exact keys `identity`, `context`, `termination`, integer counts.
- `canaries`: every `required_canaries` ID mapping to exactly three literal booleans.
- `artifacts`: every `required_artifacts` ID mapping to its lowercase SHA-256 digest.

Absent evidence yields `no-go`; malformed counts/stages are rejected. A no-go CLI
decision exits 1. For a prepared JSON evidence file, append `--gate-evidence PATH`
to the validation command. The decision is necessary but not sufficient for release.

## Amendment, replay and measurement

Any runtime, parser, simulator, termination, dataset or scorer repair gets a new
sealed execution identity before replay. Replay **all three models for every
affected task or request batch**, preserving the original evidence and linkage.
Never pool incompatible executions or keep only successful retries. Unaffected
data may be reused only with matching full identity, hashes and batching contract.
Historical pilot scores remain diagnostic; new compatible nested calibration
observations may enter the full study without selecting items by their outcomes.

Repeat every deterministic scorer twice. Replay complete direct request batches
with the same seeds; subset replay is not an exact reproducibility test because
the runtime is not batch-invariant. Hash-select five agentic tasks and twenty
alternate-seed tasks before execution. Replicate seeds are domain-separated by
the plan's replicate domain and replicate index; they are identical across models.
Repeat scores never replace primary scores or increase the independent sample count.

Capture cold/warm load, queue, context preparation, generation, tool, simulator,
judge, setup, verifier, prerequisite, replay and recovery time separately; retain
tokens, truncation, retries and GPU lease hours. Report invocation wall time,
fresh/recovered/total attempt counts and wall times, and an explicit unknown-timing
count. Recovered result latency is historical, never new invocation latency.
Unknown durations are null and counted, never fabricated as zero. Total attempt
count equals fresh plus recovered attempts; invocation wall time is measured
independently and need not equal summed task durations. Forecast by stratum and
dependency closure using median/P90, not one
global task average. Dollar costs require declared GPU-hour and API-token rates.
Preserve the base protocol's paired bootstrap, McNemar/Holm, missingness bounds and
fixed noninferiority margin. Full human double-label calibration is a separate
100-outcome artifact, not the 100-task/model execution calibration.
