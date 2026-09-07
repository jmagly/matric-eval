# Declared metrics and comparisons

The engine resolves a benchmark's primary metric from the registry's reviewed
catalog, or from explicit `primary_metric_id` and `metric_descriptors` arguments.
It never chooses the first scorer or metric. A missing primary stays unavailable.
The catalog describes native scalar inputs and their units, direction, bounds,
missingness policy and reducer version. Unsupported grouped, dictionary and
external scorers retain their native named estimates without a guessed primary.

Each direct metric has one accepted observation per selected sample/epoch.
Derived estimates such as stderr reference that direct metric through
`observation_metric_id`; they do not create per-sample stderr observations.
Their scored/outcome counts describe source measurement coverage, not a subgroup
denominator. Native summary denominators remain null unless a declared reducer
establishes them. `native_estimate` retains the native scalar separately from the
canonical estimate, including when unsupported inputs make the latter unavailable.

Declared scalar means are recomputed deterministically from accepted observations.
The result records the numerator, denominator and missingness method. Superseded
attempts never increase the denominator. Complete means require measured, eligible
observations; an explicit observed-only reducer can return a partial value with
ineligibility reasons. The qualified study adapter and study statistical estimators
are unchanged: paired summaries, bootstrap results, counts and source hashes remain
owned by the study protocol.

## Suite aggregation

`EvaluationEngine.run_all(..., aggregation=declaration)` accepts a
`SuiteAggregation` model. Without a declaration, `overall_score` remains null.
Every requested benchmark must have exactly one term. Each term names its primary
metric, a positive weight, and a versioned identity or affine transform specifying
the exact source units, bounds and direction. Affine transforms explicitly map
different scales into the declaration's common target units and direction.
The caller owns the scientific justification for those transforms and weights.

For example, weights 1 and 3 applied to eligible values 1 and 0 produce a numerator
of 1, denominator of 4 and estimate of 0.25. A points score of 4 on a 0–5 scale can
map to 0.8 only through an explicit affine scale of 0.2 and offset 0. Unknown
transforms, inconsistent source scales, missing primaries and nonfinite arithmetic
cannot produce eligible aggregates.

`require-complete` returns null if any requested term is unavailable or ineligible.
`exclude-unavailable` explicitly permits a weighted estimate of the remaining
terms, records the excluded scope, and always marks that partial estimate
ineligible for a full-suite comparison. It never silently renormalizes a supposedly
complete suite. Reports include requested, completed and scored benchmark counts.

## Comparison identity and checkpoint reuse

V2 envelopes and complete legacy engine reports carry a `comparability` record.
Its digest covers the exact serialized comparison payload: requested benchmark
order, protocols and selected manifests, partition roles, primary metrics and
descriptors, derived-input links, judge identity, aggregation declaration, and the
caller-supplied `comparison_configuration_sha256`. That configuration digest must
identify frozen sampling, prompts, generation/trial settings, scorer/reducer
versions and relevant environment policy. Model identity and observed scores are
excluded so the intentionally varied model can be compared under the same protocol.

The key is not a qualification certificate. Missing configuration, protocol,
manifest or partition evidence produces explicit ineligibility. In particular,
the native Inspect adapter currently leaves protocol and partition evidence
unverified; attaching a configuration hash alone cannot make it comparable.
Python `require_comparable` and TypeScript `requireComparable` validate scope and
eligibility before accepting matching identities. They reject absent, stale,
altered and incomplete comparison records.

Checkpoint reuse compares the entire versioned metric declaration and comparison
configuration identity. Removing a descriptor or changing a primary invalidates
reuse just as adding one does. Older execution-only checkpoints cannot establish
metric-policy compatibility and are rerun by the engine.

The v2 schema adds explicitly recognized optional fields for these capabilities;
old v2 records retain their shape through reader/writer round trips. Python,
JSON Schema and TypeScript readers continue to reject unknown fields and versions.
