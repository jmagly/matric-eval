# Independent review of clustered inference design

Reviewed 2026-09-07 for [#127](https://git.integrolabs.net/roctinam/matric-eval/issues/127).
Reviewer role: independent statistical-design reviewer, performed by a separate
AI-assisted agent that did not author [the design](clustered-inference-design.md).
This is a source/derivation review, not human statistical certification, numerical
execution, empirical coverage qualification, or approval to change frozen #114.
Only this review document was written; no protocol or analysis code was changed.

**Disposition:** the design is sufficiently concrete for implementation of the
versioned protocol, paired cluster estimators, descriptive resampling, missingness
bounds, planning sensitivity and deviation accounting, using the decisions below.
It does not establish a universally valid confirmatory bootstrap interval or
clustered hypothesis test. Implementation must represent those qualification gaps
explicitly rather than invent a cluster threshold, convert percentile intervals
to p-values, or apply independent-row tests to dependent data.

## Source and derivation checks

I inspected `studies/protocol.py`, `studies/analysis.py` and the frozen
`studies/qwen38-obliteration-2026-09/protocol.yaml`. The current bootstrap samples
paired task differences; the stratified implementation averages allocation means
equally. Its existing Wilson and McNemar helpers do not provide general clustered
inference. The new method must remain opt-in and preserve historical outputs.

The distinction between equal-cluster and equal-task targets is correct. With
fixed within-task summaries, independent clusters carry either a cluster mean
D_g, or a numerator/denominator pair (S_g,M_g). Resampling the latter together and
recomputing the ratio is necessary; averaging cluster means would change the
estimand when sizes differ. Equal-probability sampling of exchangeable clusters
supports the proposed first profile. Unequal inclusion probabilities, a census
sampling target, overlapping clusters and informative nonresponse need separate
methods. A label saying “cluster” does not prove independence.

The literature supports caution about few-cluster inference and distinguishes
whole-cluster pairs bootstrap from methods designed for improved finite-sample
inference. It does not supply a universal minimum that qualifies this repository's
percentile estimator. In particular, matching the resampling unit alone does not
establish nominal coverage. See Cameron and Miller, sections VI and XI, in the
[author-hosted published paper](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015.pdf).

I independently checked these algebraic steps:

- For paired binary D in {-1,0,1}, E(D)=delta and E(D²)=q, so Var(D)=q−delta².
  The proposed p10=(q+delta)/2 and p01=(q−delta)/2 are feasible only when
  |delta|≤q≤1, with p10/p01's model-role convention explicitly fixed.
- For G independent equal-sized clusters of size m, the variance of each cluster
  sum is m sigma² + m(m−1) rho sigma². Dividing the variance of G such sums by
  (Gm)² gives sigma²[1+(m−1)rho]/(Gm). Thus rho refers to *paired differences*,
  not automatically correlation of one model's raw scores. For m>1, the
  exchangeable covariance constraint includes −1/(m−1)≤rho≤1. Binary feasibility
  may impose tighter constraints. For m=1, rho contributes nothing.
- Independent weighted stratum means yield sum_h W_h² Var(D_hg)/G_h. This is the
  equal-cluster formula; it does not supply the variance of the unequal-size
  equal-task ratio estimator.
- The half-width and critical-value-sum sample-size expressions are conventional
  known-variance normal planning approximations. They require the stated
  variance/independence assumptions and differ for one-sided versus two-sided
  testing. NIST explicitly states the known-variance premise and the different
  critical values in its [sample-size guidance](https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm).

These checks establish the algebra under the assumptions, not achieved power,
bootstrap coverage or an adequate sample size for any application.

## Decisions that make implementation unambiguous

1. **Versioned estimator scope.** Implement distinct equal-cluster and equal-task
   method identifiers. Initially use equal task weights within a cluster and
   fixed nonnegative stratum weights summing to one. Additional within-cluster
   weighting needs an explicit versioned policy, not a generic unvalidated weight
   field. Reject nonfinite values/weights, missing membership and a cluster split
   across strata. Keep excluded zero-weight strata visible, but do not require
   their clusters to satisfy a positive-weight inferential condition.

2. **Joint canonicalization.** Canonicalize deterministic task summaries before
   cluster summation; use a stable finite-number representation, a versioned
   numeric accumulation rule and a fixed metric/model-role order. A cluster's RNG
   signature must contain the *joint* sufficient-statistic vector for every
   related contrast/outcome: numerator, denominator or cluster mean, relevant
   weights and missingness-bound endpoints. Do not independently sort clusters
   for each outcome. Exclude mutable task/cluster display labels, observation
   input order, timestamps, and raw response/judge repetition counts from this
   numerical signature. Otherwise holding task summaries fixed while duplicating
   diagnostic labels could change fixed-seed draws.

3. **Stratum order also matters.** Order the stratum multiset by canonical joint
   cluster content plus its fixed weight and numerical policy, or use a
   preregistered immutable stratum identity distinct from display labels. Do not
   seed or iterate by mutable display labels. An implementation claiming arbitrary
   stratum-label invariance must choose the content-based option. Identical
   numerical records are interchangeable. Retain identity mappings separately;
   changing membership/weights is a design change and must not be hidden as
   relabeling. Sorting realized sufficient statistics is a deterministic
   permutation of the same empirical resampling distribution, not a selection
   criterion. Freeze the canonicalization rule before outcomes are analyzed.

4. **One draw schedule.** Draw G_h cluster indices with replacement per stratum
   and use that draw schedule across all model pairs and outcomes. Resampled
   copies have multiplicities, not new independent identities. Return a compact
   draw/membership receipt for fixtures so whole-cluster pairing is testable.
   Qualify exact fixed-seed reproducibility within the declared implementation/
   runtime; mathematical invariance is not a cross-version RNG guarantee.

5. **Counts and insufficient evidence.** Report requested tasks/clusters,
   observed paired tasks/clusters and repeated responses/labels separately.
   Missing cluster membership is unsupported; zero/one usable independent cluster
   in a positive-weight stratum is insufficient for a resampling-based interval.
   One task in a cluster is not the same as one cluster in a stratum. No amount
   of replicated observations repairs the latter. A constant empirical
   distribution may be reported descriptively, but must not by itself produce
   a qualified zero-width inferential interval.

6. **Qualification state.** A numeric caller-supplied minimum is not a coverage
   qualification. Any finite inferential interval needs an explicit method and
   applicability/sufficiency receipt, linked to independently reviewed coverage
   evidence for the target, weighting, cluster-size and missingness regime.
   Until such evidence is supplied, expose descriptive resampling summaries
   separately, return a null confirmatory interval with a reason, and retain
   point estimates/bounds where defined. This is a usable explicit state, not
   permission to claim that the statistical acceptance criterion has passed.

7. **Primary tests and multiplicity.** Register the complete planned family,
   sidedness and effect/margin units before analysis. Do not generate a clustered
   p-value from a percentile interval, or reuse exact McNemar unless the units
   truly are independent matched binary pairs. Unsupported primary tests remain
   null/unavailable. If some valid tests are adjusted, retain the original family
   size and unavailable slots; an internal conservative p=1 placeholder may
   reserve a slot, but must never be exposed as an observed p-value. No tests may
   disappear from the family because their outcomes are missing. Marginal
   intervals remain labeled marginal; Holm does not turn them into simultaneous
   intervals or repair invalid marginal tests.

## Missingness and target denominators

For scores bounded in [0,1], an observed source a with missing intervention gives
[-a,1−a]; an observed intervention b with missing source gives [b−1,b]; two
missing sides give [-1,1]. These are deterministic identification bounds conditional
on the declared score range. For other bounded scales, derive endpoints from
those declared bounds rather than silently normalize or reuse [0,1].

For the requested-task target, retain every requested task's denominator and
aggregate lower/upper endpoints through the same equal-task or equal-cluster
weights. An entirely unresolved cluster still contributes its target weight and
bounds. Missingness must not silently remove its stratum, reduce its weight, or
promote the complete-pair estimate to the original target. Infrastructure outcomes
remain a separate reason class; their unobserved quality value is not measured zero.

A complete-pair point estimate may be displayed as a distinct conditional
estimand with its own task/cluster counts. With unresolved target values and no
qualified missingness model, the requested-target point/interval can remain null
while its identification bounds are available. If a complete-pair bootstrap is
provided, explicitly record the changed target and any empty-cluster behavior;
never hide undefined replicate denominators by discarding inconvenient draws.

The existing #114 analyzer excludes infrastructure failures from its denominator
and reports unresolved-judge bounds over its remaining cohort. Preserve that
historical policy and label it in compatibility views. Do not retrofit the new
requested-target rule into #114, merge missingness bounds with confidence
intervals, or reinterpret the existing noninferiority decision as newly qualified.

## Independent fixtures to implement

A one-stratum example with cluster A containing one delta +1 and cluster B
containing three deltas −1 has equal-cluster estimate 0 and equal-task estimate
−1/2. For two cluster draws, the four equally likely ordered selections AA, AB,
BA, BB give equal-cluster values 1,0,0,−1 and equal-task values 1,−1/2,−1/2,−1.
This provides an enumerated oracle independent of production reducer code.
It is deliberately too small to establish inferential coverage.

For a requested two-task equal-weight target, one known delta +1 and one wholly
unresolved delta give bounds [0,1], while the conditional complete-pair mean is
1. This distinguishes the three concepts without imputing the missing task.
Add one-side-missing cases, an entirely unresolved cluster and unequal-size
clusters; apply weights to endpoints using the same target rule.

Canonicalization tests should permute rows, rename task/cluster/stratum display
labels, permute outcome input fields while retaining declared role order, and
hold task sufficient statistics fixed while repeating judge/response diagnostics.
They must preserve numeric outputs and draws while provenance identities may
change. A contrasting membership or weight mutation must change the design
identity. Include two clusters tied on one outcome but different on a second to
catch per-outcome sorting.

Other required cases are crossed membership rejection, a zero-weight singleton
stratum, a positive-weight singleton stratum, degenerate distributions,
missing/out-of-order family members, infeasible binary planning assumptions and
result-driven budget expansion. These fixtures establish semantics; subsequent
A100 simulation/coverage checks address statistical operating characteristics.

## Frozen #114 arithmetic and implementation limit

The eleven pilot allocations in the design sum to 100; the full allocations sum
to 1,200. They match the checked-in frozen protocol. The three model variants do
not triple the independent sample size for a paired contrast. The protocol's
pilot-nesting, timing-only use, 10,000 historical bootstrap replicates, Holm rule
and −3 percentage-point capability margin remain unchanged.

The displayed variance-bound normal half-width arithmetic is correct to its
stated rounding: 1.96/sqrt(n) yields 27.7, 19.6, 17.5, 16.0 and 13.9 percentage
points for n=50,100,125,150,200. For n=100, the approximate critical-value sum
2.80 gives 28 percentage points when sigma_D=1 and about 8.9 when
sigma_D=sqrt(0.1). These are conditional planning illustrations, not observed
intervals, distribution-free guarantees, or power evidence for a −0.03 margin.
The design correctly avoids treating all 1,200 heterogeneous rows as one pooled
independent estimand. This review checked the arithmetic by derivation; executable
sensitivity-grid reproduction remains an A100 deliverable.

Proceed with the bounded implementation above, retain legacy goldens, and collect
A100 command/exit/JUnit and fixture/source hashes for independent review. Remaining
confirmatory applicability, power assumptions, reviewer-approved qualification
receipts and any unsupported primary test must stay explicit. Neither this
review nor fixture success alone closes those statistical evidence requirements.
