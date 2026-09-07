# Inspect result accounting

The engine adapts Inspect logs into version 2 observations before producing its
legacy dictionary. Execution completion, measurable performance and comparison
eligibility are separate. This integration targets Inspect AI 0.3.263 and does not
change frozen study observations, hashes, missingness policies or analysis.

## API selection and metric declarations

`EvaluationEngine.run_benchmark()` and `run_all()` accept
`result_format="v2"` as an explicit Python API opt-in. The default remains
`"legacy"`. This option selects the result contract; it is not forwarded to
Inspect and is not a new CLI output-format option.

A benchmark primary estimate requires an explicit `primary_metric_id`. Eligibility
also requires matching `metric_descriptors` with declared units, direction, value
range, scorer identity and missingness policy. Until #121 supplies registry-level
metric declarations, default engine calls leave the primary score null. Native
named estimates remain available in `observation_result.metrics` in legacy output
and `benchmarks[].metrics` in v2. A missing primary never falls back to the first
scorer or metric.

For a caller-owned task whose sample scorer is named `exact`, whose summary is
`exact/accuracy`, and whose declared policy excludes unmeasured observations:

```python
from inspect_ai import Task

from matric_eval.core import EvaluationEngine
from matric_eval.results.contract import MetricDescriptor, ResultEnvelope, write_result


def run_declared_accuracy(task: Task) -> str:
    metric = MetricDescriptor(
        metric_id="exact/accuracy",
        version="1",
        scorer_id="exact",
        value_kind="binary",
        units="fraction",
        direction="higher",
        minimum=0.0,
        maximum=1.0,
        independent_unit="task",
        missingness_policy="exclude-unmeasured/1",
        aggregation_id="accuracy/1",
        timeout_value=None,
    )
    engine = EvaluationEngine("ollama/example-model")
    result = engine.run_benchmark(
        "custom_accuracy",
        task=task,
        result_format="v2",
        primary_metric_id="exact/accuracy",
        metric_descriptors={"exact/accuracy": metric},
    )
    return write_result(ResultEnvelope.model_validate(result))
```

The descriptor must describe the actual task; declaring a descriptor does not
validate the scientific usefulness of its metric. The adapter retains Inspect's
native estimate and does not introduce a new estimator. The v2 writer rejects
nonfinite numbers and preserves legitimate nulls and reasons.

`run_all()` does not manufacture a cross-benchmark average. Its legacy
`overall_score` is null with `aggregation_reason="aggregation_undeclared"`; its
v2 `overall_estimate` is unavailable for the same reason. Declared cross-benchmark
transforms and weighting belong to #121. A suite is execution-successful only
when every requested benchmark completed; partial suites include requested,
completed and scored benchmark scope. An eligible benchmark set does not imply
that a cross-benchmark scalar exists.

## Native status and observation mapping

| Native evidence | Public treatment |
| --- | --- |
| Log `success` and complete terminal sample records | Completed benchmark execution |
| Log `error` | Failed benchmark, ineligible |
| Log `cancelled` | Cancelled benchmark, ineligible |
| Log `started`, or missing selected terminal records | Partial benchmark, ineligible |
| Correct/incorrect finite score or standard `C`/`I` label | Observed performance, including numeric zero for incorrect answers |
| `Score.unscored()` NaN with instrument-failure reason | Null measurement with its source reason |
| Sample error | Infrastructure-error observation, never an incorrect answer |
| Sample operator limit | Cancelled observation with the recorded or fallback reason |
| Other limit without a score | Unavailable measurement retaining the limit reason; no inferred model-only timeout |
| Unsupported scalar/vector/dictionary score | Unavailable measurement; native artifact retained |
| Selected ID/epoch absent from the native samples | Unknown execution and unavailable measurement |

A missing native row does not prove that execution was never attempted. The
adapter therefore does not label it `not_attempted`. An all-wrong benchmark can
be measurable and eligible. An all-unscored benchmark can be completed yet have
zero scored observations, a null primary estimate and explicit ineligibility.
Finite model-failure scores, such as an incorrect answer with a refusal reason,
remain measured outcomes; their source reason is retained through native status
and the native log reference.

The adapter uses Inspect's selected dataset IDs and epoch count, not just the
samples that returned scores. Integer and string sample IDs remain distinct.
Each ID/epoch contributes one selected unit; multiple metrics do not multiply
execution coverage. Coverage reconciles as:

```text
terminal = completed + failed + cancelled
requested = terminal + not_attempted + unknown
attempted = terminal
```

The last equation is the terminal-envelope convention: unknown execution is not
inferred to be attempted. Each metric separately records scored observations and
outcome counts. Duplicate selected IDs, duplicate terminal records, samples
outside the selected manifest and inconsistent selected counts are rejected.
When Inspect supplies `logged_samples`, inconsistent native counts are rejected.
Dynamic or other logs without a complete selected manifest cannot currently
produce a verified v2 result; they return an explicit unsupported-projection
error rather than an inferred denominator.

Inspect `error_retries` become adapter-owned `inspect-attempt-N` ordinals under
one logical observation identity. Superseded errors precede the accepted attempt
and retain linkage. These ordinals do not claim native attempt IDs or reconstruct
unavailable generated content. Retries never increase sample or statistical-trial
denominators.

## Artifacts, ambiguity and judge identity

Zero returned logs are an execution failure. Multiple returned logs are an
ambiguous benchmark execution: the legacy error result retains all collected
`log_paths` and `native_logs`, and does not silently choose the first log. A v2
request raises an explicit projection error when a verified manifest/result
cannot be constructed. Original native logs remain available for inspection;
an exception is not a fabricated empty v2 envelope.

Native references include SHA-256 when a local artifact can be hashed; otherwise
they carry an explicit unavailable-digest reason. Judge identity comes from
recorded score metadata. Its configuration digest covers only the recorded
subset available to this adapter, including explicit unknown policy values.
`recorded:unknown` reversal policy and unknown retry policy do not establish
qualification. Missing calibration remains null, and no calibration claim is
inferred from the presence of a judge ID or digest.

## Checkpoints and parallel callers

Checkpoint completion follows execution completion, independently of measurement
eligibility. A completed all-unscored benchmark may be saved and reused with its
null score and ineligibility intact. Failed, cancelled or partial benchmarks are
not reused as completed work.

Historical checkpoints without execution evidence remain readable as
`legacy_unverified`/unknown and ineligible. Their stored scores are not rewritten,
but they do not satisfy the skip condition. Fresh and checkpoint-derived model
summaries use the same accounting rules and never coerce a missing score to zero.

Parallel model evaluation maps opaque task IDs back to the original
`(model, benchmark)` tuple, preserving names such as `ollama/qwen:7b`. Sequential
and threaded callers retain the same domain result dictionaries. Callable
exceptions use failed execution, null score, zero reported samples and an
`execution_failed` eligibility reason. A generic executor's successful return
only means the callable returned; evaluation status remains in its result.

## Consumer migration

Consumers must branch on nullable scores and explicit execution/eligibility.
Do not use `score or 0`, null-coalescing numeric defaults, or successful-benchmark
subsets to create comparable overall results. The TypeScript legacy parser
rejects versioned envelopes; use its validated v2 reader for those records.
Existing native logs and study evidence remain immutable. These changes provide
truthful execution accounting; broader consumer migration and qualification
remain separate delivery gates.
