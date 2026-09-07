# Evaluation result v2 preview and ADR-EI-001

Status: implementation proposed for acceptance through the #119 pull request.
This document makes the contract decision concrete; merging the PR accepts the
additive preview. It does not select a default-format release or qualify a model.

The decision is to retain Inspect as the execution substrate and preserve
content-free observations before reducing them. Python callers opt in with
`matric_eval.results.read_result` / `write_result`; TypeScript callers use
`readResult` / `writeResult`. The published structural schema is
[evaluation-result-v2.schema.json](../../schemas/evaluation-result-v2.schema.json).
The readers additionally enforce cross-record invariants described below.
The sanitized [mixed fixture](../../tests/fixtures/results/v2/mixed.json) is shared
by both implementations. Engine emission is integrated by #120 and named reducers
by #121; this contract alone does not correct existing engine accounting.

`result_schema_version: "2"` is independent of provenance version, study protocol
version, and partition vocabulary version. Unsupported versions and unknown
fields fail explicitly. Core schema fields are required; legitimate absence uses
null, with an explicit reason for missing estimates and measurements. Recognized
optional extensions carry derived-input links, native estimates, aggregation
declarations and comparison identities; older v2 records preserve their shape. Readers
reject numeric strings, booleans used as numbers, NaN and both infinities.
Writers validate again before serialization, including mutated nested records.
Counts use nonnegative integers no greater than JavaScript's safe integer limit.

## Identities and reconciliation

A logical observation is the ordered tuple run/model/benchmark/allocation/sample/
trial/metric. Its ID is SHA-256 of the UTF-8 compact JSON string array of those
seven fields (no ASCII escaping). Attempt IDs are separate. Records retain
superseded attempts; a retry names an earlier, unaccepted predecessor for the same
logical observation. Exactly one accepted outcome per selected unit per direct metric
contributes to counts. Row order is retained, including study bootstrap input
order. Artifact references contain a digest or a reason that verification is
unavailable; a URI alone never asserts immutability.

The ordered selection declares allocation/sample/trial identities and row/source/
independent-unit references. Execution counts deduplicate metrics and retry
attempts. The preview represents settled snapshots, not running progress:

```
terminal = completed + failed + cancelled
requested = terminal + not_attempted + unknown
attempted = terminal
```

Unknown legacy execution is not inferred as attempted. Every selected unit has an
accepted outcome for every direct metric, including unavailable/not-attempted
records; omissions fail validation. Derived metrics reference a direct metric and
share its input coverage without inventing per-sample derived values. Each
metric's outcome counts sum to requested,
and its scored count equals accepted nonnull values. Execution `completed` means
all selected work is terminal, including known failures. Eligibility additionally
requires every unit to have completed execution and an eligible primary estimate.
All-wrong observed values remain measured zeros. All-unscored estimates are null
and ineligible. Suite eligibility and overall-estimate eligibility are separate:
a complete eligible set of benchmarks may have no declared overall aggregation.

## Status mapping

| Native state | Execution | Measurement | Value / reason |
| --- | --- | --- | --- |
| Inspect successful log, scored sample | completed | observed | Native numeric value, including zero |
| Inspect unscored grader failure | completed | grader_failed | null, original grader reason |
| Inspect sample infrastructure error | failed | infrastructure_error | null, original error class |
| Inspect cancelled sample | cancelled | cancelled | null, cancellation reason |
| Selected sample never dispatched | not_attempted | not_attempted | null, dispatch reason |
| Metric absent after execution | completed | unavailable | null, metric-unavailable reason |
| Historical execution not evidenced | unknown | legacy_unknown | null, legacy_unverified |
| Study `observed` | completed | observed | Exact original value |
| Study `model-timeout` | completed | model_timeout | Zero under the study's declared timeout policy |
| Study `infrastructure-error` | failed | infrastructure_error | null, study:infrastructure-error |
| Study `judge-parse-failure` | completed | grader_failed | null, study:judge-parse-failure |

Inspect returned-log status must be consulted separately from sample measurement:
`error` maps to failed, `cancelled` to cancelled, and `success` only maps to
completed after manifest reconciliation. Empty, partial and multiple logs require
explicit handling in #120. Unknown native statuses are unavailable/unknown,
never guessed successful. Model timeout is numeric only if the metric descriptor
declares that exact timeout value. Other unmeasured outcomes cannot carry a value.

Metric descriptors identify scorer, version, units, direction, range, independent
unit, timeout and missingness policy, and aggregation identity. Map keys must
match descriptor IDs. Primary selection is by ID, never iteration order. A
missing primary has a null estimate; an overall estimate requires an explicit
aggregation ID. Scale transforms, weights and comparator identity are #121's
reducer contract, not an implicit universal average in this schema.

## Study, data-role and judge adapters

`from_study` / `to_study` in `results.study_adapter` preserve original study,
protocol and manifest identities and status/value pairs. The caller supplies
trial, attempt and data references explicitly. Unsupported projections and retry
lineage fail instead of flattening into an old study row. Existing
`analyze_observations` is unchanged. Equivalence tests pass the same ordered rows
through both paths, covering all declared outcomes and full paired summaries with
asymmetric missingness and unequal allocations. No locked study file or original
hash is rewritten. The study sidecar version is `study-observation/1`.

Partition vocabulary version `1` defines `development`, `validation`,
`calibration`, `final_test`, `training`, and `unknown`. Python defines the enum,
exports it in JSON Schema, and TypeScript tests enforce exact agreement. Shared
calibration/export input fixtures consume these same identifiers. `unknown` is
used when role evidence is absent. A role labels evidence; it does not authorize
export, assert an untouched final test, or implement #129's enforcement ledger.

Judge records retain model/configuration digest, reversal and retry policy IDs,
and an optional calibration artifact. Null calibration means none is evidenced;
it never means calibrated. Policy strings such as `disabled` or `unknown` remain
visible. Domain qualification and its eligibility decisions remain #126's scope.

## Alternatives, consumers and rollback

Only fixing top-level status would leave metric and missingness loss. Replacing
Inspect would enlarge migration risk without defining measurement meaning.
Independent ad hoc dictionaries would keep consumers divergent. The chosen
additive contract costs more record storage and requires explicit adapters, but
keeps native evidence and scientific policies intact.

Consumers include engine, checkpoint state, CLI/matrix/parallel output,
TypeScript, recommendations, trends and studies. Legacy TypeScript ingestion
rejects versioned records before its old numeric coercions. Legacy files retain
their old reader and remain immutable. New v2 consumers must use the validated
entry point; #125 owns broader CLI/consumer migration and release cutover.

Rollback disables preview emission/use and retains all saved v2 artifacts. Do not
rewrite nulls into zero or remove reasons for old consumers, and do not restore
known false-success or midpoint grader behavior. A release/default decision waits
for consumer compatibility review; no removal date is invented here.

The independent architecture/API review identified strict JSON, shared roles,
study timeout preservation, identity collision tests, and the legacy TypeScript
null coercion. Those findings are implemented in this preview. Validation evidence
and remaining acceptance status are recorded with the #119 delivery PR.

See [declared metric aggregation](declared-metric-aggregation.md) for registry
selection, deterministic reducers, derived estimates and comparison validation.
