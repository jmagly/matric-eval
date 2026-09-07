# Nullable result consumer migration

Status: implemented bounded profile for [#125](https://git.integrolabs.net/roctinam/matric-eval/issues/125), validated on A100 after integrating #129. The predecessor #124 merged before construction. The table below records the design baseline; see [consumer migration](consumer-migration.md) for the implemented CLI/API behavior, limits and rollback.

The integrated A100 full CI run passed 2,741 tests with 322 skips and 81.97% coverage; all 72 TypeScript tests and the npm package dry-run passed. Initial transport and quality failures are retained alongside the corrected runs. A subsequent content-free matrix logging correction is covered by a separate focused check, not included in those full-run counts. Frozen study #114 and original golden artifacts remain unchanged. #94 owns actual matric-cli adoption and #95 the reporting product; neither is completed by package conformance tests.

## Current paths and gaps

| Path | Current behavior | Proposed bounded change |
| --- | --- | --- |
| `src/matric_eval/core/engine.py` | `run_all(result_format="v2")` already returns a `ResultEnvelope` when every benchmark has an observation manifest; otherwise rejects. Default legacy-shaped output can contain null overall score. | Consume this existing opt-in; never reconstruct observations from aggregate dictionaries. Retain explicit failure when no truthful v2 projection exists. |
| `src/matric_eval/cli.py` | `run` writes legacy-shaped JSON and summary; JSON output uses the rich console. `recommend` uses numeric legacy reports. | Add explicit `--result-format legacy|v2`, separate from `--output-format json|table`; serialize machine JSON with `click.echo` and strict writers. Wire every run branch consistently. |
| `src/matric_eval/results/contract.py` | Strict v2 models, nullable estimates, named metrics, judge identity; v2-only reader. | Keep authoritative validation; add a separate dual-reader module instead of weakening v2 to admit legacy. |
| `src/matric_eval/results/comparison.py` | Validates comparison payload/digest and requires eligible equal comparison identities. | Reuse this gate; a numeric estimate or matching display benchmark name does not establish comparability. |
| `bindings/typescript/src/result-contract.ts`, `trials.ts` | Standalone strict v2 and trial readers exist, disconnected from client run/recommend parsing. | Reuse these readers at subprocess ingress and preserve full envelopes/trial objects. |
| `bindings/typescript/src/client.ts`, `types.ts`, `index.ts` | `evaluate` returns numeric `EvalSummary`, rejects versioned results, coerces absent scores to zero; recommendation parser also defaults missing scores to zero. | Add explicit v2 result selection with typed overload/discriminated return, dual file reader, and nullable recommendation transport. Remove missing-score coercion from strict ingestion. |
| `src/matric_eval/recommendation.py` | `float(None)` fails; missing score defaults zero. Capability averages use whatever benchmark subset is present; results key by stripped model name. | Add validated ingestion, explicit exclusions, exact model IDs and declared comparable capability scope. Preserve source envelopes beside derived views. |
| `src/matric_eval/trends/store.py` | `score REAL NOT NULL`, one row per run/model/benchmark, `INSERT OR REPLACE`, no comparison scope. | Add separate v2 ingestion/storage with nullable named metrics and immutable source identity; leave old tables intact. |
| `src/matric_eval/trends/analyzer.py`, `regression.py` | Numeric histories mix scope; trend projection clamps to 0–1. | Select eligible comparable metric series before arithmetic; honor descriptor bounds and units rather than universal fractions. |

Surprising gaps that require explicit handling: v2 benchmark estimates can be
available while the suite overall estimate is null because no suite aggregation
was declared. This must not make individual measurements disappear. Conversely,
an available numeric value can still be ineligible. Legacy-shaped engine output
already containing null is not representable by the old numeric TypeScript API.
Result JSON and trial JSON have distinct schema discriminators; trial statistics
must not be relabeled as a suite score. Unknown explicit majors must never fall
through to legacy parsing.

The existing Python/TypeScript JSON readers also accept duplicate object keys
through their standard parsers. The migration ingress should reject duplicate
keys consistently, in addition to NaN, Infinity and finite-overflow tokens. Test
this explicitly rather than describing ordinary `JSON.parse` as sufficient.
Duplicate detection compares decoded member names: `"score"` and `"\u0073core"`
are duplicates in the same object, while separate objects may each contain `score`.

## Transport and dual readers

Propose `results/consumer.py` with `read_consumer_result`,
`read_consumer_collection`, `project_legacy`, and `convert_legacy_artifact`.
The corresponding TypeScript module exposes the same discriminated concepts.
Readers accept a known versioned result, a known versioned collection, or an
explicitly recognized historical shape. They do not accept arbitrary dictionaries
as legacy evidence.

For multiple models, use a separate collection discriminator such as
`result_collection_schema_version: "1"`, with a list of intact v2 envelopes and
explicit execution failures that could not produce an envelope. Single-model
v2 stdout is the actual `ResultEnvelope`. Collection validation cannot infer
success from list length. Do not add output-directory or summary-only fields to
the strict result envelope; put them in the collection or retain them outside
machine result stdout. A run that cannot truthfully form any requested v2
envelope fails clearly rather than falling back to legacy JSON.

Legacy input yields a distinct `legacy_unverified` import record containing the
unaltered parsed source, source artifact SHA, recognized historical shape, and
explicit unavailable metadata/reasons. It is readable historical evidence, not
a fabricated `ResultEnvelope`: old aggregates cannot reconstruct task selection,
trial/attempt lineage, metric declarations, or effective execution fingerprints.
Keep finite raw numeric scores as raw values and null as null. Do not synthesize
timestamps, provider names, missing scores, or sample outcomes. The unknown
major/schema case is an error, even if legacy-looking score fields coexist.

The old numeric client return remains a deliberate legacy projection. It is
allowed only when every required legacy scalar is finite, its semantics and
units are representable, and projection loses no required named metrics,
missingness, trial, eligibility, or comparison meaning. Otherwise raise a
structured `legacy_projection_unrepresentable` error naming unsupported fields.
This rule applies to the default numeric client even while CLI artifact output
continues to default to legacy. An absent score is unavailable, not zero; finite
ineligible values cannot pass through as qualified recommendations. If every
candidate is excluded, return explicit exclusions and a no-recommendation status,
not an empty successful ranking or synthetic zero-valued recommendation.
In practice most rich v2 records will require the v2 client. A lossy diagnostic
view may be offered separately later, but is not a successful legacy projection.

## Recommendation and trend gates

Represent ingestion independently from ranking. A candidate record retains the
full source artifact/envelope, all metrics, nullable values, coverage, execution,
eligibility reasons, comparison identity and judge identities. Reports include
excluded candidates and reasons; absence from a ranking must not erase evidence.
Legacy imports are readable in a separate historical view and excluded from
comparable ranking by default. An exploratory legacy display must explicitly say
unverified and must not be merged into a v2 comparable recommendation.

Require eligible completed benchmark scope, an eligible requested metric, and
validated compatible comparison identities before ranking peers. Do not infer
eligibility from `status == success`, a numeric score, or overlap diagnostics.
Require a declared capability metric set and aggregation policy; do not average
the intersection that happens to be present. Missing required benchmarks yields
null with reasons. The implemented first profile requires every capability declaration to cover the entire evaluated suite with require-complete missingness. Subset projection requires a future explicit policy and is conservatively refused; matching comparison identities do not authorize implicit filtering. A suite with no aggregation can
still supply eligible benchmark evidence without inventing an overall value.

The first trend storage profile should add new tables in a versioned v2 store,
leaving existing `evaluations` rows readable and unchanged. Store the canonical
source envelope once and nullable named metric rows keyed by source digest,
run/model/benchmark/metric and comparison scope. Identical imports are idempotent;
conflicting content for the same immutable identity rejects rather than replaces.
Enforce these as separate keys: source-byte digest establishes import idempotence;
a logical source identity such as `(run_id, model_id)` binds the one immutable
envelope independently of that digest. A changed digest, comparison scope or
created-at field cannot evade logical identity conflict by creating another row.
Metric rows reference that accepted source and retain benchmark/metric/scope keys.
No consumer command opens or mutates a recovery journal.

History retrieval includes unscored/ineligible points with reasons. Analysis
explicitly selects a comparable series and reports exclusions; it must not
bridge a changed metric version, dataset, protocol, judge policy or partition.
Do not average unrelated latest benchmark scores. Model snapshot identity must
also be present in longitudinal context; retaining a display model name alone
does not establish unchanged weights. Advanced inference/reporting remains #95
and #127 scope, not an opportunity to add new statistical claims here.

## Judge controls are supplied evidence

Preserve `Observation.judge` including judge ID, configuration SHA, reversal and
retry policy, and calibration artifact reference. Preserve the observation
reason and benchmark/estimate/envelope eligibility separately. A calibration URI
or hash is not a qualification decision, and reversal policy is not proof that
a particular missing judgment passed the order check.

Current `JudgeIdentity` has no embedded domain-qualification status/reasons.
Therefore surface existing contract identities/reasons faithfully and use an
explicit versioned qualification sidecar only if an actual upstream policy
supplies it. Bind that sidecar to exact result/judge/configuration/domain scope;
missing policy evidence is unverified when qualification is required. Do not
infer approval from #126 infrastructure, synthetic fixtures, artifact presence,
or a caller boolean. Any contract extension must update strict Python and
TypeScript readers together. No human calibration collection belongs in #125.

## Deterministic conversion and immutable evidence

`convert-result SOURCE --output NEW_PATH` should parse with the dual reader and
write a versioned import artifact containing source SHA, source format, preserved
payload and deterministic unavailable reasons. Conversion identity derives from
source bytes plus conversion profile version; it never derives from clock time,
random UUIDs, or the machine's absolute path. Separate a user-facing source path
from canonical identity if retaining it is useful. Conversion does not upgrade
legacy evidence to v2 comparability.

Use exclusive creation and strict canonical JSON. Refuse existing outputs,
including aliases/symlinks to inputs, and never rewrite source files. A repeated
conversion to two new paths has byte-identical canonical output. Retain source
byte hashes before/after as test evidence. Historical v1 golden files remain
byte-for-byte unchanged; no regenerated historical metric estimates.

## Acceptance fixtures and actual subprocess boundary

Hand-author expected outcomes independently of production reducers. Extend
`tests/fixtures/results/` with a consumer fixture manifest that records profile,
source hashes and expectations. Existing `v2/mixed.json`, `v2/named-metrics.json`
and `trials/disjoint.json` are source anchors; do not silently regenerate them.

| Fixture | Required assertion |
| --- | --- |
| Historical single result and multi-model summary | Readable as legacy; original bytes retained; comparability unverified. |
| v2 observed zero | Zero survives every layer as an observed value, distinct from null. |
| v2 null overall with available benchmarks | Null and reason survive; all named metrics remain accessible. |
| Grader failure, infrastructure error, not attempted, partial run | Outcomes/coverage/reasons preserved; no fabricated zero or ranked eligibility. |
| Retry history and aligned trial result | Accepted-observation semantics and trial schema retained without numeric legacy projection. |
| Same metric name but changed version/units/protocol/manifest/judge | Comparable ranking and trend join reject with explicit reasons. |
| Judge with calibration reference but no supplied qualification | Reference displayed, qualification stays unknown when required. |
| Unknown major, ambiguous wrapper, duplicate keys, NaN/Infinity/overflow | Python and TypeScript fail clearly, with no fallback or private payload echo. |
| Conversion attempted over source or existing target | Fails without changing bytes; two fresh outputs are deterministic. |
| Multiple named metrics / nullable legacy projection | Projection rejects instead of dropping metrics or filling null. |

The boundary test must spawn the installed Python CLI from the actual TypeScript
client, not mock `spawn` or replace the executable with a shell that echoes JSON.
Use a production offline conversion/read command that accepts the golden artifact
and invokes the same serializers as `run --result-format v2`. A TypeScript test
then exercises client subprocess transport and the strict result reader over its
stdout. In addition, at least one test must invoke the public TypeScript
`client.evaluate({resultFormat: "v2"})` through the actual Python `run` Click command;
converter-only TypeScript transport plus a separate Python run test is insufficient
to verify this composition. Use a test-only Python entry module registering
a fixed dataset and first-party deterministic mock provider/task; it invokes the
real Click command rather than a production hidden fixture switch. This verifies
run option wiring without live credentials, downloads or provider inference.
Keep stderr diagnostics separate from stdout and test paths containing spaces.

Proposed test owners: `tests/unit/test_consumer_results.py`,
`tests/test_cli_result_formats.py`, existing recommendation/trend test suites,
`bindings/typescript/src/test/consumer-results.test.ts`, and
`bindings/typescript/src/test/cli-boundary.test.ts`. A100 supplies executable
Python/TypeScript build, test, exit/JUnit and source/lock/fixture hash evidence.
No fixture test establishes actual matric-cli adoption or judge validity.
Hand-authored [consumer expectations](../../tests/fixtures/results/consumer/expectations.json)
bind these cases to unchanged existing source goldens and new historical/parser
inputs. They are proposed expectations, not executable validation evidence.

## Delivery, cutover and rollback

1. Review this design and freeze the collection/import/projection profiles and
   golden expectations after #124's predecessor is delivered.
2. Deliver strict dual readers, deterministic new-artifact conversion and explicit
   CLI/TypeScript v2 opt-in. Existing default remains legacy; unsafe projection
   fails clearly rather than restoring false-success behavior.
3. Deliver recommendation/trend nullable ingestion, exclusions, comparison gates,
   judge evidence preservation, and the real subprocess conformance fixture.
4. Publish a compatibility matrix and retain deprecated legacy support through
   the entire migration release. Default v2 cutover requires passing Python and
   TypeScript consumer evidence, reviewed release notes, and explicit external
   consumer rollout evidence from #94. No calendar date is inferred here.

| Reader/consumer | Legacy artifact | Result v2 | Trial v1 |
| --- | --- | --- | --- |
| Existing numeric client | Only representable historical inputs | Explicit refusal | Explicit refusal |
| New dual reader | Labeled unverified import | Strict full envelope | Separate strict trial reader |
| New comparable recommendation/trend | Preserved, excluded | Eligible matching scope only | Explicit trial metric policy required |

Rollback switches output selection/client use back to the retained migration
reader, preserving every v2 artifact and journal. It must not delete, downgrade,
rewrite, or import recovery journals into legacy checkpoints. If old readers
cannot represent a result, retain the explicit error and offer the supported
v2 reader; never reintroduce null-to-zero coercion. Legacy removal is a later
reviewed release contingent on consumer evidence, not merely elapsed time.
