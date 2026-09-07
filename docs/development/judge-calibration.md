# Reusable judge calibration

The version-1 calibration API evaluates supplied binary grader evidence for one
declared domain, task, rubric, judge snapshot, evaluated-model snapshot and prompt
configuration. It does not run a judge or turn parser correctness into domain
qualification. PR #117's parsing, abstention and reversal behavior remains intact.

`CalibrationSet` records the sampling frame, independent unit, content identities,
rubric, human labels, annotator identities, critique/adjudication references and
access/consent ownership. It uses the result contract's `DataReference` and shared
partition roles. Purpose distinguishes rubric discovery, prompt examples,
development tuning and final assessment; it is not a competing partition schema.
Final assessment requires `final_test`. Final rows cannot be prompt examples,
and exact content duplicates across final and development purposes reject.
This exact-hash check is not a near-duplicate detector.

The reference-only `prompt_example_manifest` selects explicitly permitted prompt
examples. It never exports final rows or plaintext labels/prompts. Restricted
final rows cannot be assessed or emitted in reports. An access declaration does
not establish OS permissions or consent: the named access owner must control
the actual data and receipt files. Keep sensitive evidence in their approved
storage; the CLI does not upload it or change permissions.

## Freeze and assess

Create a `QualificationPolicy` bound to the snapshot and complete calibration-set
hashes. Supply the application-specific rationale, confidence level, required
lower bound for positive recall and coverage, upper bound for false positives
and order inconsistency, and reversal policy. There are no default qualification
percentages or universal sample-size requirements. Freeze this policy before
final assessment and retain the real frozen receipt under the access owner's
control. Timestamp validation checks declared chronology; it cannot prove that
an operator did not inspect outcomes before entering a timestamp.

`Assessment` binds that exact policy, set and snapshot. Every planned final row
appears in the report: absent rows abstain, extra or duplicate rows reject.
`parse_binary_judgment` imports exactly one JSON boolean `label`; malformed,
nonfinite, duplicate-key or ambiguous output abstains with its raw-artifact
reference. It is an import profile, not a replacement for the existing judges'
scoring scales. The positive-label meaning must be declared (for example,
"candidate violates rubric"). Never invert a positive label silently.

Forward and reversed decisions use the same candidate-relative binary meaning.
The import caller must map anonymous response positions to that meaning before
constructing the record. Both original decisions and raw references remain in
`position_outcomes`. Missing/malformed reversals and disagreement abstain; an
inconsistent order is not a tie or a successful negative label.

The report includes all six confusion outcomes (four measured classes plus
positive/negative abstentions), prevalence, positive recall, false-positive and
false-negative rates, coverage, agreement among scored items, order inconsistency
and declared slices. Positive recall is detected positives divided by *all
planned positives*: abstention cannot hide missed failure detection. False-positive
and false-negative rates also use the planned human class denominators, with
abstentions shown separately. Agreement uses only measured judgments and is
never the sole qualification criterion. Order inconsistency uses cases with two
measured order decisions; incomplete order checks also reduce overall coverage.

Each available rate includes a two-sided Wilson interval at the declared
confidence level. Empty classes have null estimates/intervals and fail any
required check. This first profile requires one row per declared independent
unit; repeated responses/labels cannot inflate its denominator. Independence and
representativeness remain assumptions reviewed by the domain owner. Intervals
are marginal, not simultaneous; slices are descriptive. A future clustered or
simultaneous qualification policy needs its own reviewed method.

## Human qualification and drift

Without a human domain-review receipt, the report remains `unqualified`, including
perfect synthetic fixtures. A `DomainReview` file must bind the exact snapshot,
set, policy and assessment hashes; identify the reviewer/domain/access owner;
and attest review of representative labels and an untouched final set. Its raw
bytes and SHA are retained in the report. Human-authored review is authenticated
by the external access owner; a hash alone does not authenticate a person.

Only human-sourced labels, verified consent/adjudication references, all declared
checks, a matching current snapshot and a matching review can yield
`qualified_by_declared_human_review`. That status states the evidence basis and
its trust boundary. Automated fixtures do not supply a real reviewer, approved
labels or an actual held-out qualification. No judge is qualified by this change.

Qualification rehashes local consent, critique, adjudication and measured raw
judge artifacts. Missing, changed or nonlocal evidence remains unverified;
supplying an asserted hash alone does not pass that check. It does not interpret
these files as an automatic substitute for the domain review.

Changing domain, rubric, prompt, model or judge snapshot invalidates reuse of
that qualification. Changing criteria creates a new policy version/hash and a
new frozen assessment; changing thresholds after seeing this assessment rejects
its hash binding. Preserve old files. Exploratory runs may use unqualified
judges but must carry that status and its reasons into downstream consumers.

## CLI

Prepare versioned calibration, policy, assessment and current snapshot JSON:

```bash
matric-eval assess-judge-calibration calibration.json policy.json assessment.json \
  --current-snapshot current-snapshot.json --output new-report.json
```

An optional `--human-review approved-review.json` supplies the domain owner's
receipt. Omission is valid exploratory assessment and remains unqualified.
`--output` creates a new file exclusively; it refuses any existing output,
including input artifacts. JSON preserves nulls and refuses nonfinite numbers.
The API lives in `matric_eval.scorers.calibration`; model `model_dump_json()`
methods emit the strict input contracts and `digest()` supplies canonical hashes.

This is reusable package infrastructure. Study #114's judge panel, seeds,
allocations, human-label artifacts and frozen protocol remain unchanged.
Reusing any study material still requires its actual consent/access and partition
permission; the existence of a file is not permission. Synthetic fixtures in
`tests/unit/test_judge_calibration.py` establish software behavior on A100, not
human or provider qualification. Keep reviewer, label collection and real
held-out evidence as separately approved work.
