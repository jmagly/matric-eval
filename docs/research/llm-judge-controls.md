# LLM judge controls

LLM judgments are measurements, not ground truth. Use deterministic or official
scorers whenever they express the target construct. When model grading is necessary,
matric-eval applies the following controls.

## Shared scorer contract

- A malformed verdict or failed grader call is `Score.unscored(reason="grader_failed")`.
  It is retained in the evaluation log and excluded from aggregate metrics; it is not
  imputed as a midpoint score or tie.
- Judge calls use an explicit bounded retry count. Exhausted retries remain grader
  failures and must be reported in the denominator/accounting.
- Pairwise grading uses response-order reversal by default. The candidate is scored
  only when the A/B and B/A verdicts agree after mapping the anonymous positions back
  to response identity. A position-inconsistent verdict is unscored, not a tie.
- The original `parse_judge_score` helper retains default-value behavior for backward
  compatibility. Production scorers use strict parsing and reject absent, conflicting,
  or out-of-range verdicts.

Callers can disable pairwise reversal with `verify_position=False` for exploratory or
cost-constrained work, but those results should not be presented as position-checked.
The `max_retries` argument controls bounded retries for all shared judge scorers.

## Publication-grade studies

The Qwen3.8 study runner adds stronger controls: immutable judge snapshots, blinded
model labels, deterministic item and role ordering, two first-pass judgments, declared
disagreement thresholds, independent adjudication, append-only private journals,
human double-label calibration, and paired uncertainty reporting. Its judge outcome
bundle remains separate from model/infrastructure missingness.

The current locked Qwen3.8 plan uses different OpenAI snapshots, not a cross-vendor
panel. It therefore must not be described as a PoLL-style heterogeneous jury. Human
calibration and per-judge disagreement remain required, and a future protocol may test
cross-family panels without silently changing this preregistered study.

## Evidence basis

- Zheng et al., [Judging LLM-as-a-Judge with MT-Bench and Chatbot
  Arena](https://arxiv.org/abs/2306.05685): position swapping, reference-guided
  grading for reasoning tasks, and explicit treatment of position, verbosity, and
  self-enhancement bias.
- Verga et al., [Replacing Judges with Juries](https://arxiv.org/abs/2404.18796):
  heterogeneous model families and task-appropriate aggregation can reduce correlated
  judge bias. Panel composition is load-bearing and requires local validation.
- Zhou et al., [JETTS](https://arxiv.org/abs/2504.15253): static judge agreement does
  not establish downstream utility; same-generator comparisons reduce reliance on
  stylistic shortcuts.
- Miller, [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640): report
  uncertainty for paired differences, preserve the question or cluster as the unit of
  inference, and do not count repeated judgments as independent questions.

These controls improve measurement reliability but do not establish construct
validity. Domain-specific human calibration, adversarial examples, and representative
tasks remain necessary.
