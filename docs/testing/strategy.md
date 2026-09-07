# Verification strategy

Reconciled 2026-09-07 for [#130](https://git.integrolabs.net/roctinam/matric-eval/issues/130), REQ-EI-11.
This document supersedes the January planning strategy and its illustrative test
names, coverage claims, and example pipelines. It describes implemented gates
separately from acceptance work that remains open. A fixture listed here is a
source anchor, not a claim that a particular revision passed it.

All executable validation for the current model-comparison program runs on A100
under [the execution policy](a100-execution.md). Local work is source editing,
static review, and Git operations. Ordinary repository CI remains required for
merging; its evidence does not qualify an A100 measurement.

## Implemented gates and their limits

| Gate | Authoritative implementation | Evidence and meaning | Owner role |
| --- | --- | --- | --- |
| PR quality | [Gitea CI](../../.gitea/workflows/ci.yml), `quality`: `make lint`, `make format-check`, `make type-check` | Ruff checks and mypy baseline ratchet on Python 3.11. The ratchet rejects new findings; it does not assert zero existing strict findings. | Maintainer |
| PR semantics and coverage | Gitea `test`: `make test-coverage-fail`; [Makefile](../../Makefile), [coverage configuration](../../pyproject.toml) | Collected tests and aggregate coverage with `branch = true` and `fail_under = 80`. This is one combined coverage threshold, not independent 80% line/75% branch or per-module gates. Skips leave capabilities unqualified. | Test architect |
| Public-source freshness | Gitea `test`: `audit-benchmarks --live` | Retained `benchmark-freshness.json`; network freshness auditing does not run live model inference or prove scorer equivalence. | Benchmark maintainer |
| PR smoke | Gitea `smoke`: `pytest tests/unit/`, CLI help | Fixture/CLI health. The job name does not imply a live provider or every CLI option is covered. | Maintainer |
| PR build and bindings | Gitea `build`: version contract, `uv build`, wheel import, `npm ci`, TypeScript build/tests/pack dry run | Package construction and source-fixture wire checks. The wheel import occurs in the build job; clean consumers have a separate gate. | Release/platform engineer |
| Release candidate | [release.yml](../../.gitea/workflows/release.yml), [release contract](../../scripts/release_contract.py), [clean install validator](../../scripts/validate_release_candidate.py) | Version agreement, package contents, checksums, SBOMs, license/vulnerability policy, clean wheel/sdist installs and blank npm consumer checks. Publication requires the workflow's tag/token conditions. | Release engineer, #92/#93 |
| Recurring real provider | [real-provider-smoke.yml](../../.gitea/workflows/real-provider-smoke.yml), [fixture guide](real-provider-smoke.md) | Scheduled/manual credential-free Ollama CPU fixture, retained report and raw outputs; verifies transport/workflow behavior for that fixture, not a model-quality threshold. | Platform engineer |
| Isolated generated code | [runner](../../src/matric_eval/scorers/isolated_execution.py), [controlled runtime tests](../../tests/integration/test_isolated_execution_runtime.py), [profile](../development/isolated-code-execution.md) | Explicit opt-in, pinned image, effective restriction/start/cleanup evidence. Ordinary CI mock success or skipped runtime probes do not qualify the container profile. | Security engineer |
| A100 measurement | [A100 policy](a100-execution.md) and each study's frozen protocol | Exact revision, environment, fixture/task manifest, budget, GPU lease, native results and exclusions. CI coverage and provider smoke cannot substitute. | Study operator and measurement reviewer |

`make ci` implements quality plus Python coverage gates; it does not run every
Gitea job, TypeScript build, release audit, or live provider fixture. CI currently
uses `uv sync --extra ...` without `--locked`; capture the resulting lock hash
and inventory rather than claiming the command enforces an unchanged lock.
A100 validation uses `uv sync --locked` in an isolated checkout. This
reconciliation does not remove, replace, or silently strengthen CI checks.

## Disposition of earlier mandatory claims

| January claim | Current disposition / acceptance condition before promotion |
| --- | --- |
| 100% critical-component/function coverage, 75% separate branch floor, mutation floors, no coverage decrease | Not implemented gates. The aggregate 80% gate above remains mandatory. A future change needs reviewed scope, measured baseline, tools in the lock, executable failure conditions and retained evidence before adding stricter thresholds. Owner: test architect. |
| Hypothesis, mutation tools, pytest benchmark/xdist, bandit/safety as installed test stack | Not declared by the current dev extra; old command snippets were proposals. Use installed pytest/Ruff/mypy tools. Additional tools require a dependency/profile decision and real gate, not a documentation assertion. |
| Every Ollama endpoint, CLI flag, public benchmark and binding API validated | No blanket qualification. Trace named fixtures below and record missing coverage by capability. A benchmark's inventory/freshness status and a model's finite score are insufficient evidence of reference-scoring parity. |
| Checkpoint after each problem and resume inside a partial benchmark | Unsupported by the generic engine's checkpoint contract. [StateManager](../../src/matric_eval/state/manager.py) and [checkpoint guide](../development/checkpoint-resume.md) operate at benchmark completion; failed/partial benchmarks rerun. Inspect logs and trial observations are not a per-problem resumable engine. Any finer recovery needs a separately reviewed contract and crash fixtures. |
| Zero data loss in every crash, disk-full, concurrent/zombie/gap scenario; recovery under five seconds | Existing checkpoint/operational fixtures cover their stated cases only. Uncovered failure modes and timing guarantees require bounded fault fixtures, measured environment and independent expected outcomes before promotion. No general data-loss or latency guarantee follows from current tests. |
| Rust IPC and Linux/macOS/Windows bindings coverage | TypeScript is implemented; Rust remains deferred in #96. Linux package-install scope is finite below. Other operating systems and architectures are not qualified by Ubuntu jobs. |
| GitHub/GitLab as alternative authoritative CI; nightly full matrix and main-branch deployment gates | Gitea is canonical. A mirror does not establish an additional support matrix. The recurring provider smoke is implemented; arbitrary nightly performance/security/full-model pipelines and automatic production deployment are not. #109 owns live platform pipelines outside PR CI. |
| Fixed tier times, throughput/memory/latency budgets and ±5% reference-score tolerance | Historical proposals, not measured release conditions. A study/performance owner must specify fixture, runtime, estimator and justified domain tolerance before collecting evidence. There is no universal ±5% scorer-parity acceptance rule. |
| Universal sandbox-escape prevention or zero vulnerabilities | Bounded container probes establish only observed controls on the pinned runtime; Docker shares the host kernel. Release vulnerability policy reviews findings and accepted exceptions. Neither is a universal security guarantee. |
| Phase transitions require all levels, nightly dashboards, universal sign-offs | No such automated workflow is present. A future phase/deployment gate needs an owner, explicit checklist, evidence and approval record. Normal PR/CI and existing release checks still apply. |
| All tests must use TDD, one assertion, or avoid every literal | Test review requires independent expected behavior, meaningful assertions and relevant negative cases. Multiple assertions can establish one cross-record invariant. Literal hand-computed expected values are appropriate; copying the production reducer as an oracle is not. |

## Finite support and dependency profiles

[Profiles and skip dispositions](profiles.md) define the finite evidence scope:
Python 3.11 for PR semantic checks; CPython 3.11, 3.12, 3.13 and 3.14 on Linux
for the existing clean release-install gate; Python 3.11 on the attested A100
checkout for current measurement validation. `requires-python = ">=3.11"` is
package metadata, not evidence for every later Python/platform/optional extra.

The 3.11–3.14 install scope preserves the existing #93-reviewed release workflow.
The [#93 candidate record](https://git.integrolabs.net/roctinam/matric-eval/issues/93#issuecomment-102143)
reports a successful older exact-source candidate; it is historical evidence,
not proof that the current revision or every optional evaluator is qualified.
#93 still owns registry installation and release evidence. Expanding semantic,
platform or interpreter support requires that owner's profile review and fresh
exact-source checks; #130 makes no new platform-support promise.

## Critical semantic traceability

Each row identifies the invariant, an existing fixture source or an explicitly
planned fixture, execution profile, and required evidence destination. All paths
are relative to the repository; artifact names describe the required run bundle,
not files asserted to exist in this checkout. Issue links retain ownership for
work that is still under review.

| Requirement / invariant | Fixture source and independent expectation | Profile / evidence destination |
| --- | --- | --- |
| #119: versioned records preserve nulls, identities, reasons, bounds and counts | [test_result_contract.py](../../tests/unit/test_result_contract.py), [study adapter](../../tests/unit/test_result_study_adapter.py), shared [mixed.json](../../tests/fixtures/results/v2/mixed.json), TS contract tests; malformed records reject, timeout policy remains explicit, original study rows round-trip | `study-dev` and `typescript`; JUnit, shared-fixture/schema hashes, TS test log |
| #120: Inspect terminal status is independent of measurement availability | [test_engine_accounting.py](../../tests/unit/test_engine_accounting.py), [native adapter](../../tests/unit/test_inspect_result_adapter.py); all-unscored completed work stays null and completed, failed/partial logs do not become success | `study-dev`; JUnit and native fixture hashes |
| #121: named/derived metrics and declared suite aggregation | [test_result_reducers.py](../../tests/unit/test_result_reducers.py), [named-metrics.json](../../tests/fixtures/results/v2/named-metrics.json), TS tests; no implicit first metric or heterogeneous average; derived stderr has no invented sample grades; comparison scope mutations reject | `study-dev` and `typescript`; JUnit, declaration/fixture hashes, round-trip output |
| #122: aligned task trials distinguish any success from all-success | [test_trial_results.py](../../tests/unit/test_trial_results.py), [test_trial_execution.py](../../tests/unit/test_trial_execution.py), [disjoint.json](../../tests/fixtures/results/trials/disjoint.json); two disjoint successes give macro pass@2=1 and all-N=0; missing trials stay null; retries do not increase N | `study-dev` and `typescript`; JUnit, task-content/manifest/protocol hashes, trial wire fixture |
| #123: generated code cannot fall back to host execution; limits require native start and cleanup evidence | [unit controller tests](../../tests/unit/test_isolated_execution.py) plus [real runtime probes](../../tests/integration/test_isolated_execution_runtime.py); denied mounts/network, bounded resources, explicit infrastructure failures, exact container absence | `study-dev` mocks plus `isolated-python`; JUnit, effective profile/image/bootstrap hashes, raw probe log and cleanup receipts |
| #124: provenance-bound recovery | Existing [checkpoint tests](../../tests/test_checkpoint_resume.py) are baseline only. Planned additional fixtures under #124 must reject changed protocol/model/data while preserving matching completed work | `study-dev`; before/after checkpoint hashes, identity manifest and JUnit in #124 bundle |
| #125: consumers preserve versioned/unavailable results | Existing TS shared-fixture tests are baseline. Planned #125 consumer fixtures cover parsing, reporting, exports, incompatible identities and incomplete records without null-to-zero projection | `study-dev` and `typescript`; JSON/CLI golden outputs, schema/fixture hashes, JUnit/TS logs; real consumer adoption remains #94 |
| #126: judge outputs and position checks remain explicit | [test_llm_judge.py](../../tests/unit/test_llm_judge.py), [test_judges.py](../../tests/unit/test_judges.py); parsing/abstention unit results do not establish judge calibration. Planned #126 paired-position/calibration cases must retain exclusions and reverse failures | `study-dev` for fixtures; separately attested judge qualification bundle for live evidence |
| #127: inference and missingness honor independent units | Planned #127 hand-calculated/degenerate/clustered fixtures with declared uncertainty estimator and no fabricated intervals for unavailable observations | `study-dev`; protocol/fixture hashes, JUnit and calculation outputs in #127 bundle |
| #128: overlap diagnostics preserve raw scores and unknown training exposure | Implemented at source `be8e9886f6ff82c5503e6ac890d278751bd16085`: [test_contamination.py](https://git.integrolabs.net/roctinam/matric-eval/src/commit/be8e9886f6ff82c5503e6ac890d278751bd16085/tests/unit/test_contamination.py) exact/short/paraphrase cases; correct-answer overlap cannot prove contamination and raw scores remain unchanged. See [overlap diagnostics](https://git.integrolabs.net/roctinam/matric-eval/src/commit/be8e9886f6ff82c5503e6ac890d278751bd16085/docs/development/overlap-diagnostics.md). #128 was delivered in PR #138; the linked run receipt remains tied to the cited exact source | `study-dev`; [historical full-run and skip receipt](evidence/README.md), diagnostic configuration/golden outputs and JUnit in #128 bundle |
| #129: role-use history and training exports protect held-out/restricted data | Existing contract partition-role fixture is baseline only. Planned #129 mixed-role/duplicate/export fixtures reject prohibited records, preserve stable manifest hashes, and record final-test reuse as a durable role-use event | `study-dev`; input/output/lineage hashes, export or dry-run ledger, refusal reasons and reviewer role in #129 bundle |
| REQ-EI-11 / #130: verification claims match gates and profiles | Static reconciliation of this strategy, subordinate plans, pyproject, Makefile and Gitea workflows; retain changed-file review and unresolved skips | Documentation review; source/lock/profile hashes, diff and reviewer role in #130 bundle |

For each execution retain exact commit and clean-tree status, lock and installed
inventory, fixture hashes, command/exit status, JUnit with skips, initial failures,
rerun relationship and reviewer role. A100 bundles live under
`/srv/matric-eval/results/<work-item-or-run>/`; release artifacts use the release
workflow's evidence directory. Sensitive prompts/native logs stay in controlled
storage; public records use content-free identifiers and approved references.

## Ownership retained

[#92](https://git.integrolabs.net/roctinam/matric-eval/issues/92) owns publication,
[#93](https://git.integrolabs.net/roctinam/matric-eval/issues/93) clean package and
registry installs, and [#94](https://git.integrolabs.net/roctinam/matric-eval/issues/94)
actual matric-cli adoption, rollback and consumer CI.
[#95](https://git.integrolabs.net/roctinam/matric-eval/issues/95) reporting remains
deferred until #92/#91 close and two comparable production runs exist;
[#96](https://git.integrolabs.net/roctinam/matric-eval/issues/96) Rust remains deferred
until #92 and consumer contract approval; [#97](https://git.integrolabs.net/roctinam/matric-eval/issues/97)
cost accounting remains deferred until #92 or an earlier consumer budget need.
This strategy does not promote those issues or change #114's frozen study.
[#109](https://git.integrolabs.net/roctinam/matric-eval/issues/109) owns the
registry-derived agent-platform matrix and credentialed live pipelines; no live
model credentials are added to PR CI.
