# Local overlap diagnostics

The `diagnostic_schema_version: "1"` contract records text overlap within supplied
pairs. It does not estimate training contamination, establish model
trustworthiness, or alter benchmark scores. Both an independently solved answer
that exactly matches a reference and a low-overlap paraphrase retain
`training_exposure: "unknown"`.

```python
from matric_eval.contamination import check_overlap, write_diagnostic

report = check_overlap(
    ["The answer is forty two"],
    ["The answer is forty two"],
    n=3,
    model="example-model",
    benchmark="example-benchmark",
    raw_score=0.875,
    output_source_id="native-run-artifact/sample-output",
    reference_source_id="evaluation-dataset@resolved-revision",
)
print(write_diagnostic(report))
```

The optional `raw_score` is preserved without rescaling. Omission means no score
was supplied, not zero. Native benchmark scores and historical artifacts remain
unchanged. Diagnostic output contains text identities and measurements rather
than copies of the supplied text; content hashes are identity evidence, not a
confidentiality guarantee.

## Method and limits

`normalized-exact-and-word-ngram/1` lowercases Unicode text, collapses whitespace
with Python `str.split`, and compares normalized text for exact equality. Exact
means equality under that normalization, not necessarily byte equality. Separate
SHA-256 identities cover original UTF-8 and normalized text. Source IDs and sample
IDs state which provided records were compared.

The heuristic uses **word n-grams**, not character n-grams. Its numerator counts
output n-gram occurrences whose word tuple is present anywhere in the reference;
its denominator is the number of output n-gram occurrences. Repeated output
n-grams count repeatedly. This is a directional overlap ratio, not Jaccard
similarity or a probability of memorization. The recorded threshold only controls
`exceeds_similarity_threshold`; it has no statistical significance or scoring
meaning.

Every pair is retained, including low overlap. Empty normalized text yields
`insufficient_text`, no exact finding, and null overlap. Nonempty text shorter
than `n` can have a valid exact finding while its n-gram measurement remains null
with `insufficient_words_for_ngram_method`. A missing denominator is never
serialized as zero overlap. Reports distinguish tested, partial, insufficient,
and empty-batch coverage. No sample-size-based confidence value is generated.

`provided_output_reference_pairs` is the default scope. Callers comparing known
local training and evaluation datasets may explicitly select
`provided_train_eval_datasets` and must provide both source identities. Exact
matches then describe the supplied dataset pairs only. This API performs paired
comparisons, not an exhaustive dataset join; absence of a match does not prove
that two complete datasets are disjoint. Neither scope reveals an unavailable
foundation-model training history.

## Optional likelihood methods

Likelihood-based testing is not implemented. Every report states
`likelihood_test_status: "unsupported"` and
`likelihood_test_reason: "likelihood_method_not_implemented"`; these fields are
not a negative contamination finding.

A future extension must use a separate versioned method and validate its actual
interface and assumptions before reporting a test result. Required declarations
include access to comparable sequence/token likelihoods, tokenizer and model
identity, context/length/truncation conventions, treatment of unavailable values,
the proposed null hypothesis, and the units assumed exchangeable under that null.
Any permutation or ordering test must state why those units are exchangeable;
reordering dependent examples without justification is not a valid assumption
check. Record test settings, calibration/qualification evidence and limitations.
Absent likelihood access or unverified required assumptions must remain
unsupported/unqualified, rather than producing a clean verdict. No optional
likelihood implementation is required to use these local diagnostics.

## CLI and strict serialization

Create a JSON file containing `outputs` and `references` arrays. Optional keys
match `check_overlap` and `check_batch`: model, benchmark, raw score, sample/source
identities, scope, `n`, and threshold. Then run:

```bash
matric-eval overlap-diagnostics pairs.json --output diagnostic.json
matric-eval overlap-diagnostics diagnostic.json --artifact
matric-eval overlap-diagnostics historical-diagnostic.json --artifact --output legacy-view.json
```

The command refuses to overwrite its input artifact. `read_diagnostic` and
`write_diagnostic` reject unsupported versions, unknown current fields,
nonfinite JSON numbers, duplicate JSON keys, inconsistent ratios/statuses, and
missing method limitations. Current report readers do not accept categorical
training-exposure labels. `to_dict()` exposes the same versioned fields.

## Compatibility transition and consumers

`check_contamination` remains importable but is deprecated and now returns the
new overlap contract. `NgramDetector.check_sample` returns a diagnostic for every
pair rather than only threshold hits; `compute_overlap` returns `None` when the
method has no denominator. Consumers must migrate away from old evidence counts,
severity, contamination score, confidence, and categorical recommendations.

The historical `ContaminationReport` and `ContaminationEvidence` constructors
remain available for a deprecation period. The report warns on construction; its
`recommendation` property warns and returns `unknown_training_exposure`.
`adjusted_score(raw_score)` warns and returns the finite raw value unchanged on
both report types. The former fixed discounts are removed. A future breaking
release may remove these compatibility names; callers should migrate now to
`check_overlap`, `OverlapReport`, and the unchanged raw score.

`read_diagnostic` recognizes an unversioned historical artifact carrying old
heuristic labels or adjusted scores. It returns a `legacy-adapter/1` view with
`legacy_heuristic_unverified`, explicit exclusion reasons,
`comparison_eligible: false`, and the unchanged original artifact. If present,
`raw_score` and `historical_adjusted_score` are retained separately. It never
reconstructs an absent raw score by reversing a discount. Historical labels are
visible only inside this explicitly historical view.

`score_series_diagnostics` detects legacy adjusted-score or heuristic-label
markers recursively in an evaluation result and validates current diagnostic
attachments. Recommendation ingestion excludes the entire marked legacy series,
including its headline aggregate, and exposes exclusion reasons through
`metadata.diagnostic_reviews`. Current diagnostic methods/statuses/scopes are
also carried there and in model-category output. Raw current scores remain
unchanged. An all-excluded CLI recommendation request fails with diagnostic
reasons rather than ranking historical adjusted values.

This compatibility filter establishes only whether these known legacy markers
require separation; absence of markers is not evidence of general measurement
validity or comparability. Result-v2 strict readers already reject undeclared
legacy adjusted fields. Other consumers should apply `score_series_diagnostics`
before ranking legacy records. The `legacy-adapter/1` view is the explicit
separation path for inspection/reporting; there is no override that silently
merges it into a current recommendation series. A previously discounted value
that lost every label and its original score cannot be identified or restored
from the number alone and needs external provenance review.

## Verification scope

Fixtures cover independently solved exact answers, paraphrases, empty/short
texts, repeated word n-grams, normalized versus byte identity, unchanged raw
scores, strict serialization, legacy exclusion, recommendation metadata, and CLI
artifact handling. These tests establish software semantics and consumer guards;
they do not establish whether any foundation model saw any training example.
Executable validation runs on A100 under the workspace policy. Frozen study #114,
historical reports, and native benchmark evidence are not rewritten.
