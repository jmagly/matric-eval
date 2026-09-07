# Versioned clustered study analysis

The new modules implement the bounded scope approved in the
[design](./clustered-inference-design.md) and
[independent review](./clustered-inference-review.md) for #127. They provide strict
new protocol declarations, paired whole-cluster estimators, descriptive
resampling, requested-target identification bounds, planning sensitivity, and a
stopping/deviation ledger. They do not establish statistical coverage or supply
qualified clustered hypothesis tests.

`studies.protocol` and `studies.analysis` retain their historical behavior. The
frozen #114 protocol, allocations, observations and existing golden outputs are
unchanged. New analysis is opt-in through separate modules and schema versions.

## Protocol and analysis API

`ClusteredProtocol` in `matric_eval.studies.clustered_protocol` requires
`protocol_version="2"`. It declares the estimand/population, immutable sampling
frame reference, independent/task units, fixed cluster membership and stratum
weights, paired model roles, exact bounded metrics, full primary family,
practical-effect targets, planning assumptions, inference settings, missingness,
fixed budgets and outcome-access policy. Unknown fields and versions are refused.

The initial sampling profile is a superpopulation target with equal-probability,
exchangeable clusters within strata. Independence is explicitly
`declared_not_proven`. Crossed/overlapping membership, clusters split across
strata, unequal inclusion weights and census inference are unsupported. Task
weights within each cluster are equal. Population stratum weights must be
declared from a frame or as an explicitly chosen macro target.

Freeze a new protocol before outcome access using `freeze_protocol(path,
protocol)`. The helper uses exclusive creation and synchronization; it does not
overwrite a prior plan. Retain the returned canonical protocol digest outside
the mutable analysis input. These controls do not authenticate the actor or
prove that someone did not previously inspect outcomes outside the API.

```python
from matric_eval.studies.clustered_inference import TaskOutcomes, analyze_clustered
from matric_eval.studies.clustered_protocol import ClusteredProtocol

protocol = ClusteredProtocol.model_validate(protocol_document)
rows = [TaskOutcomes.model_validate(item) for item in task_summary_documents]
report = analyze_clustered(protocol, rows, source_commit=full_source_commit)
```

Each `TaskOutcomes` record contains exactly one task's already reduced paired
source/intervention values, keyed by declared hypothesis ID. Missing sides have
explicit reasons. Values must fall inside that hypothesis's declared metric
range. The producer must apply the frozen within-task rule and trial alignment;
the analyzer does not reconstruct response/judge reductions or attest their
provenance. Response trials, judge labels, infrastructure exclusions and unresolved
grades are separate diagnostic counts. Repeating those diagnostic counts cannot
increase the task or independent-cluster denominator.

## Estimator and deterministic draws

The method identifiers distinguish `paired_whole_cluster_equal_cluster/1` from
`paired_whole_cluster_equal_task/1`:

- Equal-cluster averages task means within clusters, then averages cluster means
  within each stratum.
- Equal-task divides the sum of cluster task sums by the sum of their task
  counts within each stratum. Every resample recomputes this ratio denominator.

Both combine strata with their frozen weights. Every draw resamples a whole
cluster and uses the same schedule for all model comparisons and outcomes.
Copies in a bootstrap replicate represent multiplicities, not new independent
cluster identities.

Task summaries are ordered before `math.fsum` accumulation. Cluster ordering
uses the joint sufficient-statistic vector across all declared hypotheses,
including paired/requested denominators and missingness endpoints. Stratum
ordering uses joint cluster content and fixed stratum weight. Display labels,
input order and diagnostic repetition counts do not drive RNG indexing.
The report retains a separate membership map and the draw schedule for review.
Changed membership/weights change the protocol identity; harmless relabeling can
change provenance identities while leaving numerical results and draws intact.

Fixed-seed reproducibility is within the recorded Python implementation/runtime.
An explicit `draw_schedule` is available for hand-enumerated fixtures; the report
labels it `explicit_descriptive_enumeration` and does not claim it used the
preregistered Monte Carlo seed.

## Missingness and statistical qualification

Requested-target bounds keep every requested task and its stratum/cluster weight.
For range `[L,U]`, a missing intervention paired with observed source `a` gives
`[L-a,U-a]`; a missing source paired with intervention `b` gives `[b-U,b-L]`.
Both missing gives `[L-U,U-L]`. These are identification bounds, not confidence
intervals.

Any unresolved positive-weight target leaves its requested-target point estimate
null. A complete-pair point is separately labeled conditional on observed pairs
within observed clusters, retaining the fixed stratum weights. An empty observed
positive-weight stratum makes that conditional point undefined too. The initial
version does not bootstrap the conditional target. It suppresses the requested
distribution when the original target is unresolved, so draws that happen to
omit missing clusters cannot be selectively retained.

Every confirmatory interval, marginal p-value and adjusted p-value is null in
this implementation. A protocol cannot supply an arbitrary numeric minimum and
turn it into coverage evidence: its qualification state is `unqualified`. The
report explains the absent coverage/sufficiency profile. Zero or one usable
cluster in a positive-weight stratum additionally returns `insufficient_evidence`.
A zero-weight stratum remains visible but does not impose that condition.

Complete-data resampling distributions are explicitly descriptive. A constant
distribution never becomes a qualified zero-width interval. All planned primary
family slots remain present even when their outcomes are unavailable. No p-values
are fabricated from percentile draws, and Holm is not applied to invalid or
invented marginal tests. Independent operating-characteristic qualification and
a supported test implementation remain separate work.

Reports carry analysis version 2, estimator/canonicalization/accumulation
versions, protocol and input hashes, the supplied full source commit, actual
inference-file hash and Python version. A supplied commit identifier is provenance
metadata, not an independent check of the checkout. Diagnostic missingness counts
remain separate from independent n.

## Planning and frozen #114 sensitivity

`clustered_planning` supplies `binary_paired_variance`, `design_effect`, and
`planning_sensitivity`. Paired binary variance is `q-delta²`, with feasible joint
probabilities and optional marginal-rate checks. The initial equal-size planning
profile uses `1+(m-1)rho` for paired-difference correlation in `[0,1]`; it declines
negative-correlation power gains and does not claim to solve unequal-size ratio
variance or binary correlation feasibility beyond the stated checks.

Planning uses known-variance normal approximations over every declared
variance/correlation sensitivity combination. It records sidedness, units,
assumed true difference, practical-effect target and the signed noninferiority
margin separately. Noninferiority distance is assumed difference minus null
margin, including the case of assumed difference zero. Family planning uses
`alpha/F` as a conservative Bonferroni threshold, explicitly not the eventual
Holm cutoff. The output is required cluster counts under those assumptions,
with null achieved power and no coverage qualification.

With score range width `R`, practical effects must lie in `(0,R]`, assumed
differences in `[-R,R]`, and supported noninferiority margins in `[-R,0]`.
Declared paired-difference variance cannot exceed `R²`: these inputs represent
assumed variances, so an impossible value is rejected rather than silently
reinterpreted as a conservative upper bound.

`frozen_114_sensitivity(protocol_path)` reads the frozen legacy protocol and
returns a separate allocation-limited grid for variances 1, 0.5 and 0.1. It
retains the actual source-file hash and the unchanged 100-pilot/1,200-full totals.
Its unadjusted normal half-width/detectable-effect calculations assume independent
paired tasks; they neither demonstrate the frozen -0.03 noninferiority margin
nor pool 1,200 heterogeneous tasks into one independent estimand. The function
does not write or amend the study. Artifact generation and executable arithmetic
validation run on A100.

`legacy_compatibility_view` validates the old loader and exposes explicit
`legacy_sample_independence_assumed` and historical missingness annotations in a
new view. It preserves the original document and numerical implementation.

## Stopping and deviations

`StoppingLedger` freezes a protocol document/hash in its first record, before
declared outcome access. Each `StoppingEvent` records actor, timezone-bearing
timestamp, information snapshot, accrued counts, outcome-access state, reason,
authorized action and artifact references. It binds to the previous record hash.

The local Unix file implementation uses exclusive creation, `flock` serialization,
append-only writes, flush/fsync and initial directory synchronization. It refuses
truncated chains and empty existing files instead of silently repairing them.
These are local filesystem assumptions, not distributed/NFS durability or
power-loss qualification. Actor strings and hash chains do not authenticate
reviewers or prove that an external operator omitted no events.

Outcome analysis requires a recorded enrollment closure. The fixed plan refuses
early stopping and unreported task/cluster expansion. A proposal and subsequent
decision must precede a recorded budget deviation; events cannot overwrite a
decision or undo outcome access. Corrections append references to prior events.
Any deviation state loses the original confirmatory interpretation. A textual
approval never manufactures adaptation/coverage qualification, and a changed
protocol requires a new versioned plan/log rather than reopening the old one
with different criteria. The analyzer independently rejects rows outside its
frozen manifest. These APIs do not intercept unrelated execution or file access.

An `analysis_access` event must explicitly set `outcomes_inspected=True`.
Reopening a ledger while declaring prior outcome access requires that access
already be represented by a durable access or deviation event. The constructor
cannot silently retain a pre-access history contradicted by that declaration.

## Independent fixtures and validation boundary

`tests/unit/test_clustered_inference.py` implements the independent review's
two-cluster oracle: one +1 task versus three -1 tasks gives equal-cluster 0 and
equal-task -0.5; enumerated ordered draws yield `{1,0,0,-1}` and
`{1,-0.5,-0.5,-1}` respectively. Other cases cover joint-outcome ties, relabeled
strata/clusters, repeated diagnostic counts, missing sides/whole clusters,
singleton/zero-weight strata, degenerate distributions, family retention,
paired planning, locked concurrent ledger writers and result-driven expansion.

Fixture success establishes these semantics. It does not establish empirical
coverage, actual independence, achieved power, human statistical certification,
or completion of remaining #127 qualification requirements. All executable
validation belongs on A100, with initial failures and exact command/source/fixture
identities retained alongside the independent review.
