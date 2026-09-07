# Consumer result migration

Result representation is selected independently from terminal rendering:

```sh
matric-eval run --model MODEL --tier smoke --result-format v2 --output-format json
matric-eval read-result results/run/summary.json
matric-eval convert-result old-summary.json --output converted-summary.json
```

`legacy` remains the default result format. Version 2 retains every named metric,
nullable estimates, outcome counts, judge identities and declared comparison
eligibility. A collection carries successful result envelopes and explicit
projection failures; no missing result becomes a numeric zero. Trial evaluations
retain their separate schema and cannot implicitly become suite scores.

Python `read_consumer_result` and TypeScript `readConsumerResult` accept native
version 2 results, version 1 trials/collections/imports, and recognized historical
model, summary and matrix shapes. They reject duplicate decoded object keys,
nonfinite numbers, unknown versions and ambiguous schemas. Historical failed rows
without scores remain readable. Imported legacy payloads retain their original
text, source digest and an explicit `legacy_unverified` classification.

Conversion exclusively creates a new file. Repeating conversion to different new
paths yields the same bytes; existing destinations and aliases are refused. Keep
original files as evidence. A numeric legacy projection is available only when
all required scores, counts, status and tier are representable. Null, partial,
ineligible or richer versioned measurements fail explicitly.

```typescript
const result = await client.evaluate({
  models: ['MODEL'], resultFormat: 'v2', tier: 'smoke'
});
const imported = await client.loadResult('historical-summary.json');
```

The public TypeScript subprocess path invokes the actual CLI `run` command.
`EvalOptions` variables with dynamic result selection return a union; literal
`resultFormat: 'v2'` and default legacy calls retain narrower return types. Legacy
summaries now retain full provider-qualified model IDs and label their
qualification. Optional unavailable metadata remains null.

## Recommendations

```sh
matric-eval recommend --results-dir results/run --capability-policy policy.json
```

The policy declares version `1`, an eligible comparison SHA-256 and a
`capabilities` mapping to validated `SuiteAggregation` declarations. This first
profile requires each capability to cover the entire evaluated benchmark suite
with `require-complete` missingness. Subset/intersection ranking is not supported.
Every term identifies its metric, weight, units, direction and explicit transform.
The TypeScript report reader recomputes these reductions and checks winners and
thresholds, using a numeric comparison tolerance of `1e-12 * max(1, abs(expected))`
for cross-language floating-point sums.
A global minimum score additionally requires a shared target unit and higher-is-
better direction across capabilities.

Reports retain native sources, excluded candidates and reasons, nullable values,
and judge control identities with unverified qualification. Missing policy,
legacy sources, unknown comparison scope, incomplete metrics and ambiguous
multiple runs cannot produce recommendations. No automatic overall/balanced
ranking or numeric model-category export is provided. `--output-format
model-categories` explicitly refuses an unrepresentable conversion.

Old Python `RecommendationEngine` entry points refuse qualified ranking by
default. Historical heuristic analysis requires `legacy_exploratory=True` and
carries an unverified label. This mode does not establish comparability. New code
can call `recommend_v2` with validated sources and a declared policy.

## Immutable history

```sh
matric-eval trend-import results/run/model-result.json --database history.sqlite
matric-eval trend-series --help
```

The consumer store uses separate versioned tables, preserves original source
text and hashes, and retains every named metric. Reimporting identical bytes is
idempotent. Different bytes for the same run/model identity are refused, including
apparently harmless timestamp rewrites. Existing legacy rows are preserved;
unrecognized database schemas are refused.

Chronological selection parses timezone-aware timestamps and orders UTC instants;
invalid or naive timestamps remain visible but are excluded from a chronological
series. Missing or ineligible measurements remain explicit exclusions. Generic
result envelopes lack immutable model snapshot evidence, so the default
unchanged-model requirement excludes them. Explicit measurement-only selection
can compare the declared configuration/dataset/metric/judge scope while retaining
this limitation; it cannot claim unchanged weights. Old `TrendAnalyzer` and
`RegressionDetector` require explicit exploratory opt-in instead of silently
returning “no regression” for unverified legacy history.

## Rollout and rollback

Retain original legacy files and databases, opt into v2 on selected callers, then
move readers before changing producers elsewhere. Rollback selects legacy output
for new runs and restores an older consumer against original historical inputs;
it does not rewrite versioned evidence into synthetic numeric legacy data.
External consumer adoption and model/judge qualification require their own
validation. The fixed mock CLI fixture establishes transport and measurement
preservation only, not live-provider or external application adoption.

## Retained validation

The integrated source on base `2ac29ae4d24c154ed673ed1dd7d51c8b475820f9`
passed A100 `make ci`: 2,741 passed, 322 skipped, 81.97% coverage. TypeScript
compiled, all 72 tests passed, and `npm pack --dry-run` passed. The test count
includes the actual public TypeScript-to-CLI fixed mock evaluation. Skips remain
capability-specific exclusions; these results do not qualify live providers.

Receipts are retained under `/srv/matric-eval/results/ei-125-consumers/`:
`final-full-ci.log`, `final-full-junit.xml`, `final-ts-build.log`,
`final-ts-test.log`, `final-npm-pack.log` and
`integrated-full-source-receipt.json`. Initial failures and storage/dependency
receipts remain beside them. A final content-free matrix log correction and its
privacy regression were checked separately in `post-review-*` logs and JUnit;
`final-source-receipt.json` identifies the resulting delivery files. That focused
check does not add to or replace the full-run counts above.
