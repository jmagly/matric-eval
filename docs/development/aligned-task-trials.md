# Aligned task trials

`EvaluationEngine.run_trial_benchmark` evaluates a fixed task manifest under
declared generation trials. It replaces the former benchmark-mean-positive pass
flag. A caller must declare `n`, `k`, a metric, and a versioned `PassPredicate`
(`equals` or `at_least`, with a finite threshold and metric units).

```python
from matric_eval.results.trials import PassPredicate

result = engine.run_trial_benchmark(
    "humaneval", n=4, k=2,
    predicate=PassPredicate(
        version="1", kind="equals", threshold=1.0, units="all-tests-passed"
    ),
    root_generation_seed=42,
)
```

The registry supplies reviewed scalar metric defaults. Custom tasks can pass
`metric_id` and `metric_descriptors`. A fraction of tests passed does not imply
that a task passed: the declared predicate decides. Infrastructure errors and
unscored grades remain missing observations, while wrong answers remain observed
failures. A complete task-by-trial matrix is required for a nonnull macro result.

## Different estimands

For each selected task, `n_requested` is the declared number of trials,
`n_observed` counts measured accepted outcomes, and `c` counts outcomes satisfying
the predicate. When all requested outcomes are observed:

- `pass_at_k` is `1 - C(n-c, k) / C(n, k)`: at least one success in k draws
  without replacement from the n recorded outcomes.
- `all_n_success` is the observed indicator that every one of the n trials passed.

The report macro-averages each quantity over the exact selected task set. It does
not estimate reliability as `(c/n)**k`. With task outcomes `[true, false]` and
`[false, true]`, pass@2 is 1 and all-two reliability is 0. With `[true, true]` and
`[false, false]`, both macro quantities are 0.5. For n=4, c=2, k=2, pass@2 is 5/6.
Missing task trials yield null estimates with explicit reasons, never smaller n,
clipped k, or fabricated failed answers. Observed values in failed native logs
remain visible, with execution and measurement ineligibility preserved.

All numeric utilities reject booleans/nonintegers, n<=0, c outside [0,n], k<=0,
and k>n. Empty all-success inputs and empty task aggregates raise errors. The
deprecated `run_pass_k_benchmark` spelling requires an explicit predicate and
returns this new trial contract; legacy `pass_power_k`/`pass_rate` suite fields
are removed. Migrate callers to the named per-task and macro estimates.

## Frozen selection and generation evidence

The task is loaded once, its ordered explicit sample IDs are frozen, and its
serialized sample content is hashed. Integer and string IDs stay distinct.
Every trial receives a fresh deep copy of the task and samples, one native epoch,
and a deterministic distinct 31-bit seed from the versioned hash schedule.
Native log manifests must match the frozen selection and order. Dynamic sample
sources, anonymous/duplicate IDs, and overrides of seed, epochs, shuffling,
sample IDs or limits are rejected.

Built-in loaders use the configured selection seed. To use a different selection
policy, supply an already selected `Task` and its selection seed; this API never
changes shared settings. Generation seeds do not reselect the task dataset.

Each invocation receives a fresh evaluation run ID, including repeated calls on
the same engine. Each outer `trial-i` has distinct logical observation IDs. Native epoch-1 identity
is recorded separately, and original log references, manifest hashes and retry
lineage remain intact. A superseded attempt cannot become another statistical
trial. The fixed manifest and task-content hashes describe separate evidence.

Generation evidence distinguishes the requested seed, the seed recorded in
Inspect's resolved generation configuration, and the unverified question of
whether the provider honored it. A recorded seed is not proof that an HTTP
adapter forwarded it or that an endpoint honored it. Effective temperature zero
is flagged because different seeds may still produce identical outputs; absent
temperature is explicitly unverified. Independence remains unverified and all
reported statistics are labeled descriptive-only. Model/runtime qualification,
seed-honoring experiments and inferential assumptions require separate evidence.

The standalone wire contract is `trial_schema_version: "1"`, with a JSON Schema
and strict Python/TypeScript readers. Readers recompute task counts and statistics,
reject changed metric descriptors or identities, and retain unavailable trials.
Existing frozen study protocols and statistical estimators are unchanged.
