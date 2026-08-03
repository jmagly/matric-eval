# Requirements Traceability Matrix

**Document ID**: REQ-TRACE-002

**Status**: Living

**Last validated**: 2026-08-03

This matrix maps current supported capabilities and release requirements to
implementation, executable evidence, and tracker ownership. January 2026 use-case
documents are retained as an archived requirements baseline; their example file
names, issue numbers, and `Planning Phase` statuses are not current delivery state.

## Status Terms

- **Supported**: implemented and covered by the repository's automated contract.
- **Validated**: supported and exercised by retained operational or provider evidence.
- **Gated**: implementation exists but documented external prerequisites block normal
  completion-only execution.
- **Release gated**: implemented in source, but package/release acceptance remains open.
- **Deferred**: explicitly outside the current release until its tracker trigger is met.

## Capability Traceability

| Requirement | Status | Implementation | Executable evidence | Tracker / protocol |
|---|---|---|---|---|
| RUN-001: Run registered benchmarks by model and tier | Supported | `src/matric_eval/cli.py`, `core/engine.py`, `tasks/registry.py` | `tests/unit/test_cli.py`, `test_engine.py`, `test_tasks.py` | [Roadmap](../development/roadmap.md) |
| RUN-002: Select Ollama, llama.cpp, vLLM, OpenRouter, or Chutes | Supported | `src/matric_eval/providers/` | `tests/unit/test_providers.py`, provider registry and engine tests | Real-provider scope tracked separately by #89 |
| DATA-001: Pin benchmark data/evaluator revisions and seeded tiers | Supported | Registry metadata, `datasets.py`, `freshness.py`, `provenance.py` | Freshness, provenance, dataset, and task tests; `audit-benchmarks --fail-on-error` | [Reproducibility policy](../benchmarks/reproducibility.md) and Wave 1-3 protocols |
| SCORE-001: Execute canonical code tests for HumanEval and MBPP | Validated | `scorers/code_execution.py`, HumanEval and MBPP tasks | Code-execution/task tests and operational validation matrix | [#90](https://git.integrolabs.net/roctinam/matric-eval/issues/90) |
| SCORE-002: Preserve matric-memory title and semantic scorer contracts | Validated | `tasks/matric_memory.py` | matric-memory task tests and pinned reference matrix | [Operational Validation v1](../validation/operational-validation-v1.md) |
| CUSTOM-001: Execute matric-cli, matric-memory, and tool-calling suites | Supported | `tasks/matric_cli.py`, `matric_memory.py`, `tool_calling.py` | Corresponding unit and task tests | Registry protocols `project-v1` |
| JUDGE-001: Support MT-Bench, LLM judge, and multidimensional scores | Supported | `tasks/mtbench.py`, `scorers/llm_judge.py`, `multidimensional.py` | MT-Bench, judge, and multidimensional scorer tests | Production quality depends on configured judge/model |
| REC-001: Generate model recommendations from results | Supported | `recommendation.py`, CLI `recommend` | Recommendation and CLI tests | Input evaluation completeness remains caller-visible |
| REL-001: Persist and resume interrupted runs without repeating completed benchmarks | Validated | `state/manager.py`, CLI/engine resume path | Checkpoint, state, recovery, CLI integration, and operational validation tests | [#87](https://git.integrolabs.net/roctinam/matric-eval/issues/87) |
| REL-002: Produce equivalent result sets in sequential and threaded execution | Validated | `parallel.py`, engine orchestration | Parallel tests and 12-unit operational matrix | [#90](https://git.integrolabs.net/roctinam/matric-eval/issues/90) |
| SEC-001: Isolate code/task execution through configured sandboxes | Supported | `sandbox/`, code-execution scorer | Sandbox and code-execution tests | External runners retain their own security prerequisites |
| CI-001: Enforce repository quality and package-build gates | Validated | `.gitea/workflows/ci.yml` | Gitea PR and `main` Actions runs | [#88](https://git.integrolabs.net/roctinam/matric-eval/issues/88) |
| CI-002: Exercise a real provider on a retained schedule/manual workflow | Validated for Ollama | `.gitea/workflows/real-provider-smoke.yml`, `scripts/run_real_provider_smoke.py` | Hosted run #51 with logs, results, checkpoints, runtime and model digest | [#89](https://git.integrolabs.net/roctinam/matric-eval/issues/89) |
| PKG-001: Build installable Python and TypeScript artifacts | Release gated | `pyproject.toml`, `bindings/typescript/`, CI build job | Source builds pass; clean registry install matrix remains required | [#92](https://git.integrolabs.net/roctinam/matric-eval/issues/92), [#93](https://git.integrolabs.net/roctinam/matric-eval/issues/93) |
| ADOPT-001: Support matric-cli through the TypeScript client | Release gated | `bindings/typescript/` | Local client tests exist; consumer CI and migration/rollback remain open | [#94](https://git.integrolabs.net/roctinam/matric-eval/issues/94) |
| RUST-001: Provide a supported matric-memory Rust client | Deferred | None in the supported package contract | No acceptance evidence claimed | [#96](https://git.integrolabs.net/roctinam/matric-eval/issues/96) |

## Benchmark Protocol Traceability

The task registry is the canonical inventory. On 2026-08-03 it reported 39 entries:
24 stable, 13 gated, one experimental, and one unavailable.

| Protocol group | Registry coverage | Decision record |
|---|---|---|
| Core/project benchmarks | HumanEval, MBPP, GSM8K, ARC, IFEval, LiveCodeBench, DS-1000, MMLU, MT-Bench, matric-cli, matric-memory, Tool Calling | Task metadata and repository tests |
| Wave 1 | Agentic, repository, multimodal, document, security, and extended reasoning integrations | [Wave 1 protocols](../benchmarks/wave1-protocols.md) |
| Wave 2 | InjecAgent, EvalPlus, MMLU-Pro, MMMU-Pro, and GAIA2 successor decisions | [Wave 2 protocols](../benchmarks/wave2-protocols.md) |
| Wave 3 | RULER, BABILong, memory, long-context, episodic, InfiniteBench, and HELMET decisions | [Wave 3 protocols](../benchmarks/wave3-protocols.md) |

A `stable` registry entry means its adapter/protocol is supported and tested. It
does not assert production runs across all providers. A `gated` entry must reject
unsupported completion-only execution and direct the operator to its prerequisite
or official runner. InjecAgent remains experimental; QwenWebBench remains
unavailable.

## Current Delivery Traceability

| Issue | Requirement | Dependency / gate | State on 2026-08-03 |
|---|---|---|---|
| #87 | REL-001 | End-to-end checkpoint/resume | Closed |
| #88 | CI-001 | Authoritative Gitea CI | Closed |
| #89 | CI-002 | Retained real-provider smoke | Closed |
| #90 | SCORE-001, SCORE-002, REL-002 | Scorer and operational evidence | Closed |
| #91 | DOC-001 | Reconcile current and historical documentation | In progress |
| #92 | PKG-001, SUPPLY-001 | Depends on #87-#91; final publication waits for clean validation | Open |
| #93 | INSTALL-001 | Exact #92 candidate artifacts | Open |
| #94 | ADOPT-001 | Validated 0.2.0 TypeScript package | Open |
| #95 | REPORT-001 | Promote after #91/#92 and comparable production runs | Deferred |
| #96 | RUST-001 | Promote after #92 and consumer approval | Deferred |
| #97 | COST-001 | Promote after 0.2.0 schema release | Deferred |

Live tracker state supersedes this dated table.

## Verification

Generate current counts and validate the maintained contracts with:

```bash
uv run matric-eval list-benchmarks
uv run matric-eval audit-benchmarks --fail-on-error
make operational-validation
make lint
make format-check
make type-check
make test-coverage-fail
```

On 2026-08-03, `pytest --collect-only` collected 2,307 tests. Authoritative PR
run #52 completed 2,296 tests with 11 skips and 80.95% coverage. These dated
figures are evidence for that revision, not a permanent project count.

## Archived Requirements Baseline

UC001 through UC005, the original supplementary requirements, and the v0.1 vision
remain useful for design intent and scenario history. They are explicitly marked
archival because several examples describe proposed paths and commands that differ
from the implementation. This living matrix and the tracker control current
acceptance and support claims.
