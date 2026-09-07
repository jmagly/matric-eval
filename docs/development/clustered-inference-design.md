# Proposed clustered study inference

Status: design for [#127](https://git.integrolabs.net/roctinam/matric-eval/issues/127),
not an implemented or statistically qualified analysis. The issue requires
**separate design review before inference implementation**, followed by independent
review of the derivation and executable fixtures. This document proposes that
review surface. It changes no protocol, observation, allocation, golden fixture,
or analysis result, including frozen study #114.

Dependencies #119 and #122 provide observation and aligned-trial identities; they
do not establish statistical independence. Numerical cluster sufficiency criteria,
practical-effect targets, and confirmatory families must be reviewed for each new
design rather than inferred from benchmark names or available sample counts.

## Current behavior and compatibility

`studies/analysis.py` currently resamples individual paired sample deltas; its
stratified bootstrap resamples within allocations and equally averages allocation
means. It also supplies Wilson intervals, exact McNemar tests, Holm adjustment,
and unresolved-outcome bounds. `studies/protocol.py` requires sample pairing,
Holm correction, and timing-only pilot use, but does not declare a general
independent-unit/cluster design. Current reports have analysis schema version 1.

Keep that implementation selectable under its historical version. A new protocol
version and a separate inference/report version must opt into the design below.
Old protocols load with an explicit `legacy_sample_independence_assumed` annotation
in any new compatibility view. The annotation describes a legacy assumption; it
does not assert that existing tasks are independent. Preserve original files and
historical numerical outputs. Rollback selects the historical analysis version,
not a rewrite of observations or retroactive protocol changes.

Reuse existing numerical helpers only within their assumptions. Ordinary Wilson
and exact McNemar calculations apply to independent Bernoulli outcomes or
independent matched pairs, respectively. Repeated judges, turns or task variants
must not be passed to those helpers as independent rows. Holm correction remains
applicable to valid marginal p-values without requiring independence between
tests; it cannot repair invalid marginal tests. This proposal does not create
cluster-valid p-values by treating a percentile bootstrap interval as a test.

## Preregistered protocol surface

Every new confirmatory protocol should include the following before examining
study outcomes. Missing declarations mean `design_unqualified`, not defaults
silently inherited from the current implementation.

| Declaration | Required content |
| --- | --- |
| Estimand | Target population/frame, outcome units, comparison direction, finite-frame versus superpopulation target, and interpretation of repeated responses/judges |
| Sampling | Immutable frame/manifest identities, selection design, independent primary sampling unit, cluster membership, strata and inclusion assumptions |
| Weights | Equal-task or equal-cluster target, within-task reducer, within-cluster weights, fixed stratum/domain weights and their source |
| Pairing | Source/intervention roles, complete pairing keys, trial alignment, shared task/cluster membership, handling of unmatched observations |
| Outcomes | Exact metric/version IDs, primary and secondary status, practical-effect target or noninferiority margin in those units |
| Family | Explicit hypothesis IDs and directions, family membership, family alpha, multiplicity method, and descriptive-only contrasts |
| Inference | Method version, confidence level, replicate count, analysis seed, supported dependence structure and reviewed cluster-sufficiency rule |
| Missingness | Requested denominator, exclusions and reasons, unresolved-value bounds, assumptions for any complete-pair estimand |
| Planning | Variance/discordance and correlation assumptions, target power or interval width, sensitivity grid and operational sample constraints |
| Stopping | Fixed sample/cluster budget or separately qualified sequential design, permitted interim access, stopping rule and append-only deviation-log location |

An independent task is not interchangeable with a benchmark row. Several turns
from one conversation, variants of one underlying problem, repeated stochastic
responses, and repeated judge labels can remain dependent. Record the actual
hierarchy and identify which level is treated as independent. A cluster may
contain many tasks; response/judge repetitions remain inside their task. Unknown
membership or a cluster split across declared strata is unsupported in the first
implementation. Crossed or overlapping cluster structures require a separate
method, not an arbitrary choice of one grouping.

## Proposed paired cluster estimator

Use strata indexed by h, independent clusters within a stratum indexed by g, and
tasks within a cluster indexed by i. Freeze a within-task outcome rule first:
for example, the mean of a fixed declared number of model responses, or one
adjudicated score. Let d_hgi be the intervention outcome minus its source outcome
for that task under the same declared protocol. Responses and judge labels are
not additional independent observations. The initial method conditions on the
declared generation/judging budget; it does not claim that this budget eliminates
generation or judge uncertainty.

Let W_h be fixed nonnegative stratum weights summing to one. Two distinct targets
must have different explicit estimator identifiers:

- **Equal-cluster target:** define D_hg as the declared weighted task mean inside
  cluster g. Estimate theta = sum_h W_h (sum_g D_hg / G_h). With equal task weights
  inside each cluster, each cluster receives equal total weight regardless of size.
- **Equal-task target:** define S_hg = sum_i d_hgi and M_hg as the number of eligible
  tasks fixed by the declared target/missingness rule. Estimate
  theta = sum_h W_h (sum_g S_hg / sum_g M_hg). This ratio weights larger clusters
  more heavily, as required by that target. It must not be replaced by an average
  of cluster means.

The first profile assumes independent, exchangeable clusters sampled with equal
probability within each stratum. Unequal cluster selection probabilities,
sampling weights, finite-population corrections, informative nonresponse, or a
finite census target require a reviewed extension. Informative cluster size makes
the distinction between the two targets especially consequential. Population
stratum weights must come from the declared target frame; equal weights represent
an explicitly chosen macro target, not automatically population prevalence.

For each bootstrap replicate, draw G_h cluster indices with replacement within
each stratum. Each draw carries the entire cluster, all source/intervention pairs,
all primary outcomes, and all recorded repetitions/labels. Use the same cluster
draws across related model contrasts and outcomes. Recompute the declared
estimator, including the ratio denominator for an equal-task target. Do not
resample rows independently, split a cluster, resample model arms separately, or
turn one selected cluster into several independent clusters because it contains
many responses.

Return a percentile interval only where that method and cluster-sufficiency rule
have been qualified. Cluster-aware resampling is motivated by within-cluster
dependence, but few-cluster inference can remain unreliable; cluster resampling
alone does not solve that problem. See Cameron and Miller's
[primary methodological discussion](https://escholarship.org/uc/item/1jq5d0pq).
The proposal deliberately does not label a universal cluster count “enough.”

### Determinism and insufficient evidence

Input order and display-label changes must not change numerical estimates or
fixed-seed draws. Canonicalize the inference representation of each complete
cluster, keeping model roles and metric identities fixed. For finite Monte Carlo
reproducibility under arbitrary label renaming, order the multiset of cluster
sufficient-statistic records by canonical content rather than mutable labels.
Identical records are interchangeable. This ordering affects only RNG indexing;
it must not alter inclusion, stratum assignment, weights or a preregistered rule.
Retain a separate identity mapping for diagnostics and provenance. Changed
membership is a changed design, not a harmless label rename.

Zero clusters, one cluster in any positive-weight stratum, an unestimable target
denominator, or unresolved cluster membership yields `insufficient_evidence`
with a reason and a null inferential interval. One cluster replicated many times
must never produce a zero-width confidence interval. More generally, a count
below the preregistered, independently reviewed minimum yields the same status.
Two clusters permit a sample variance calculation but do not establish adequate
bootstrap coverage. Until a sufficiency/coverage profile is qualified, report
point estimates and descriptive resampling distributions separately from any
confirmatory claim. Never invent a finite inferential interval from a degenerate
empirical distribution alone.

A singleton cluster containing one task is valid if there are enough independent
clusters. A singleton stratum containing one cluster is the insufficient case.
Do not collapse strata after viewing outcomes to manufacture more clusters.

## Missingness, counts and families

Report requested tasks, observed paired tasks, independent clusters by stratum,
response trials, judge labels, infrastructure exclusions, unresolved grades, and
bounds separately. Repeated rows never increment independent n. Preserve
model-timeout and infrastructure-failure distinctions from the observation
contract; a missing judge outcome must not become an incorrect model answer.

For a bounded task score in [0,1], a completely unresolved paired delta lies in
[-1,1]; if one side is observed, narrow that interval using the observed side.
Aggregate these bounds with the same declared weights. The task/cluster denominator
belongs to the target, not the number of successfully graded rows. A complete-pair
estimate is conditional on observation unless a justified missingness assumption
connects it to the original target. Display that change of estimand explicitly.
Missingness bounds are not confidence intervals; retain both labels and do not
mix their endpoints into one unexplained uncertainty range.

Freeze the complete primary family, including planned comparisons with unavailable
outcomes, before examining results. Missing tests must not silently shrink the
family. Primary/secondary flags and family membership are protocol data. Apply
Holm only to a declared family of valid p-values; report unadjusted marginal
intervals as marginal unless a simultaneous-coverage procedure is separately
declared. Directional noninferiority and two-sided difference claims require
separate hypotheses and planning conventions.

## Transparent precision and power planning

The following are planning approximations with explicit assumptions, not achieved
power or a substitute for an independently reviewed clustered implementation.
Let independent paired task differences D have mean delta and variance sigma_D².
Then Var(mean D) = sigma_D²/n. A normal-approximation two-sided interval has
half-width h approximately z_(1-alpha/2) sigma_D / sqrt(n). Solving for n gives
n approximately z_(1-alpha/2)² sigma_D² / h². Applying the usual normal planning
argument to the paired differences gives

    n approximately (z_(1-alpha/2) + z_(1-beta))² sigma_D² / delta².

The critical-value sum is a conventional approximation for the desired power;
exact two-sided normal power includes both tails and should be evaluated when
precision matters. Unknown variance and small sample sizes require a different
calibration. The underlying one-sample planning formula and its known-variance
assumption are documented by
[NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm).
A one-sided noninferiority calculation substitutes z_(1-alpha) and the distance
between the assumed true difference and the null margin; it does not use the
margin's magnitude indiscriminately.

For binary paired outcomes, let q be the probability of discordance and let delta
be the intervention-minus-source success difference. Since D is -1, 0 or 1,
E[D²] = q and sigma_D² = q - delta². Thus paired precision depends on discordance,
not just the two marginal success rates. Sensitivity inputs must satisfy feasible
joint probabilities: p10 = (q + delta)/2, p01 = (q - delta)/2, q >= |delta| and
q <= 1, with any specified marginals imposing further constraints. Do not use
an independent-two-proportions formula while calling the design paired.

For equal-sized clusters with m tasks and exchangeable paired-difference
correlation rho, summing variances and covariances gives

    Var(grand mean D) = sigma_D² [1 + (m - 1) rho] / (G m).

The design effect is 1 + (m - 1) rho. It multiplies variance, not the number of
independent clusters. This derivation assumes equal sizes/common variance/common
within-cluster correlation; variable or informative sizes need the actual
cluster estimator or a specified simulation. Negative-correlation assumptions
must satisfy a valid covariance matrix and should not be used as convenient
power gains without evidence.

For equal-cluster stratum means, independence between clusters/strata gives
Var(theta) = sum_h W_h² sigma_Dh²/G_h, where sigma_Dh² is variance of cluster
summaries. Use this formula for allocation sensitivity, not the total row count.
The equal-task ratio target needs its own variance approximation or simulation;
the equal-cluster formula cannot simply be reused.

Planning output must state alpha, family size/correction, sidedness, target
power/half-width, effect units, assumed variance or discordance, clustering,
weights, missingness and finite-frame assumptions. Provide a sensitivity grid
rather than one unjustified favorable scenario. For conservative family planning,
alpha/F can approximate a Bonferroni threshold; do not claim it is the realized
Holm cutoff, which depends on the ordered family p-values. Any simulation must
publish its data-generating model, parameters, seed, replicate count, Monte Carlo
error, test rule and retained failure cases.

## Frozen #114: allocation-limited sensitivity only

The checked-in
[protocol](../../studies/qwen38-obliteration-2026-09/protocol.yaml) fixes 100 pilot
and 1,200 full samples per model, paired across three model variants. Pilots are
for timing and pipeline validation. They are nested in the full selection and may
count in full only under the frozen protocol's unchanged-protocol rule. Those
counts do not demonstrate power. This proposal neither expands them nor changes
its -3 percentage-point capability noninferiority margin, correction, comparisons,
scoring, or stopping rules.

| Allocation | Pilot | Full |
| --- | ---: | ---: |
| xstest-safe | 10 | 100 |
| xstest-unsafe | 5 | 100 |
| or-bench-hard-benign | 10 | 150 |
| strongreject-harmful | 15 | 100 |
| ifeval | 10 | 125 |
| mmlu-pro | 15 | 200 |
| livecodebench | 10 | 125 |
| mtbench | 5 | 50 |
| bfcl-v4-agentic | 5 | 100 |
| tau3-bench | 10 | 100 |
| terminal-bench-2.1 | 5 | 50 |

For a bounded paired delta in [-1,1], sigma_D² <= 1. Under independent tasks and
an unadjusted normal 95% approximation, the conservative planning half-width is
1.96/sqrt(n): approximately 27.7, 19.6, 17.5, 16.0 and 13.9 percentage points for
n = 50, 100, 125, 150 and 200 respectively. These are illustrative normal
variance-bound calculations, not guaranteed-coverage bounds or observed study
intervals. For binary outcomes near delta=0, an assumed discordance q=0.1 reduces
these values by sqrt(0.1); q=0.5 reduces them by sqrt(0.5). Neither q is known from
allocation counts. Clustering or family correction can increase uncertainty.

As a scale illustration, a two-sided unadjusted 80% normal planning calculation
uses z_0.975 + z_0.8 approximately 2.80. At n=100, its approximate detectable effect
is 2.80 sigma_D/10: 28 percentage points at sigma_D=1 and 8.9 percentage points at
sigma_D=sqrt(0.1). A one-sided noninferiority claim against -0.03 under a presumed
true delta=0 has a different planning distance and critical value; these
illustrations do not show that #114 can establish its margin. Domain macro
precision depends on its weights, allocation variances and dependence structure;
1,200 heterogeneous rows must not be substituted as independent observations of
one pooled estimand.

These calculations are algebraic sensitivity illustrations, not an executed
planning artifact. Before publication as an analysis deliverable, independently
verify the arithmetic, make the full grid reproducible on A100, and label unknown
cluster/discordance assumptions. Keep the result in a separate limitation report
linked to frozen protocol and manifest hashes; do not amend the locked study.

## Append-only stopping and deviation record

A new protocol freezes its planned cluster/task budget and analysis access policy.
Record append-only events with study/protocol hash, event ID, predecessor digest,
timestamp, actor/reviewer identity, event type, reason, available-information
snapshot, authorized action and supporting artifact references. Event types should
cover enrollment closure, analysis access, stopping evaluation, operational pause,
missingness decision, and deviation proposal/approval/rejection. Correct errors
with a superseding event; do not edit prior events.

Each stopping event records the planned boundary, actual tasks/clusters accrued,
whether outcomes were inspected, and the decision under the declared rule.
Unplanned expansion after viewing outcomes must be recorded as a deviation;
subsequent analysis loses the original confirmatory interpretation unless a
valid, independently reviewed adaptation justifies it. The implementation must
refuse silent budget expansion. This log makes deviations visible; hashes alone
do not authenticate actors or prevent an operator from omitting events, so claims
about audit completeness must match the actual access/enforcement boundary.

## Review and acceptance fixture plan

Design review must settle the supported target/weighting profile, canonicalization,
sufficiency qualification, valid primary tests, missingness estimand and stopping
boundary before numerical implementation. No statistically justified universal
cluster minimum or study-specific effect target is supplied by this document.
Independent statistical review must check the derivations and expected fixtures;
implementation authors' tests alone are insufficient.

| #127 acceptance | Proposed independent fixture |
| --- | --- |
| New protocols declare units and family; old protocols remain readable | Reject omitted units/primary family, post-freeze family edits and unknown versions; legacy round-trip with explicit assumptions and unchanged source hashes |
| Whole clusters and pairs survive resampling | Hand-enumerate a small cluster bootstrap; unequal cluster sizes distinguish equal-task/equal-cluster targets; inspect sampled membership and shared arm draws; reorder/relabel inputs with fixed seed |
| Repetitions do not inflate independent n | Duplicate responses/judge labels within fixed tasks while holding task summaries fixed; assert same cluster count and inferential result, separate repetition counts |
| Too few clusters are insufficient | One cluster with many identical rows, one positive-weight singleton stratum, zero denominator and below-qualified-minimum cases return null intervals with explicit reasons |
| Planning and stopping are transparent | Analytic paired-binary variance and equal-size design-effect fixtures, infeasible joint-probability rejection, sensitivity output, and attempted result-driven expansion with append-only deviation state |
| Historical fixtures and provenance survive | Run existing golden fixtures under historical version unchanged; new reports carry method/source commit/protocol/input-manifest hashes and record requested/observed clusters plus exclusions/bounds |

A dependence counterexample should contrast many perfectly correlated repeated
rows from one underlying task with the same number of truly independent tasks;
the first must not gain inferential n. Include missing-outcome, crossed-cluster,
stratum-weight and degenerate-distribution fixtures. Report numerical tolerance
and finite bootstrap Monte Carlo variability separately from exact invariants.

All executable validation and any active-study analysis run on A100. Retain source,
lock and fixture identities, command/exit/JUnit evidence, failures/skips, and the
independent statistical review. This design authorizes neither an inference
implementation nor a new benchmark/model run by itself.
