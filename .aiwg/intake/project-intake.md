# Project Intake Form

**Document Type**: Greenfield Infrastructure Project
**Generated**: 2026-01-24
**Source**: Planning documents (CLAUDE.md, PLANNING.md) + interactive session

## Metadata

- **Project name**: matric-eval - Model Evaluation Framework
- **Requestor/owner**: matric ecosystem engineering team
- **Date**: 2026-01-24
- **Stakeholders**: Engineering (matric-cli, matric-memory), DevOps/CI, Framework architects

## System Overview

**Purpose**: Consolidated model evaluation framework for the matric ecosystem. Provides standardized benchmarking of Ollama models using public benchmarks (HumanEval, MBPP, GSM8K, ARC, IFEval, etc.) and custom application-specific tests. Solves code duplication across matric-cli (TypeScript) and matric-memory (Rust) while providing best-of-breed evaluation infrastructure for all matric applications.

**Current Status**: Planning phase (greenfield project)

**Users**:
- matric-cli developers (via TypeScript bindings)
- matric-memory developers (via Rust bindings)
- DevOps/CI automation (nightly runs, smoke tests on PRs)
- Manual/ad-hoc testing (developers validating new models)
- Any matric application supporting local models (extensible to future apps)

**Tech Stack** (proposed):
- **Languages**: Python 3.11+ (core), TypeScript (bindings), Rust (bindings)
- **Framework**: Inspect AI (UK AI Safety Institute) - native Ollama support, agent evaluations
- **Package Management**: uv (modern Python dependency management)
- **Testing**: pytest (unit/integration tests)
- **Deployment**: CLI tool, installable via pip/uv, language bindings via npm/crates.io
- **Data**: JSONL format for test datasets, JSON for results/state

## Problem and Outcomes

**Problem Statement**: Evaluation code is duplicated across matric-cli (TypeScript in `source/eval/`) and matric-memory (Rust in `crates/matric-inference/`). Both implementations solve similar problems independently, leading to:
1. Repeated bug fixes (e.g., MBPP function name extraction fixed in matric-cli commit `51382e2` but not in matric-memory)
2. Inconsistent evaluation methodology across projects
3. No robust recovery from failures (recent matric-cli eval crashed at model 13/31 with EPIPE, lost all progress)
4. Manual model selection instead of data-driven config recommendations

**Target Personas**:
- Primary: Python developers building matric applications with Ollama model support
- Secondary: TypeScript/Rust developers integrating eval into existing matric-cli/matric-memory codebases
- Tertiary: DevOps engineers setting up CI pipelines for model quality gates

**Success Metrics (KPIs)**:
- **Framework validation**: Inspect AI + Ollama integration working with checkpoint/resume (blocking gate for prototype)
- **Benchmark coverage**: All 8 public benchmarks (HumanEval, MBPP, GSM8K, ARC, IFEval, LiveCodeBench, DS-1000, MTBench) running successfully
- **Resilience**: 100% recovery from interruptions (no lost progress on crashes/cancellations)
- **Performance**: Smoke tier <2 min, Quick tier <20 min, Full tier <2 hours per model
- **Adoption**: Both matric-cli and matric-memory switch to matric-eval bindings within 3 months of v1.0
- **Config generation**: Automated model-categories.json recommendations reducing manual model selection by 80%

## Current Scope and Features

**Core Features** (in-scope for v1.0):

1. **Public Benchmark Evaluation**
   - HumanEval (164 code generation problems)
   - MBPP (974 Python problems with function name extraction)
   - GSM8K (1,319 math word problems)
   - ARC (1,172 reasoning problems)
   - IFEval (541 instruction following tasks)
   - LiveCodeBench (880 competitive programming)
   - DS-1000 (1,000 data science tasks)
   - MTBench (80 multi-turn conversations)

2. **Tiered Evaluation System**
   - Smoke: 5 samples per benchmark (~2 min total)
   - Quick: 75 samples per benchmark (~20 min total)
   - Full: All problems (~2+ hours)

3. **Robust Recovery & State Management** (blocking requirement)
   - Checkpoint/resume: Save state after each model/benchmark
   - Selective re-run: Re-run specific model + benchmark combinations
   - Gap detection: Scan results directory, identify missing/incomplete results
   - Auto-recovery: Retry on transient errors (timeout, EPIPE, connection reset)
   - Graceful degradation: Skip failed model, continue, report at end
   - Idempotent runs: Re-running produces same results, skips completed

4. **Custom Test Framework**
   - JSONL-based test definitions
   - Custom scorers for app-specific metrics
   - Support for tool calling, agent scenarios, semantic similarity tests

5. **Language Bindings**
   - TypeScript npm package (subprocess wrapper for matric-cli)
   - Rust crate (subprocess wrapper for matric-memory)
   - Streaming results API

6. **Config Recommendation Engine**
   - Generate model-categories.json mapping capabilities → recommended models
   - Rank models by performance per capability
   - Filter top N performers for custom test validation

**Out-of-Scope** (explicitly excluded for v1.0, revisit in v2.0+):
- Multi-GPU distributed evaluation (start with single-machine)
- Cloud-hosted evaluation service (local/CI only for v1.0)
- Web UI for viewing results (CLI + JSON/Markdown reports sufficient initially)
- Real-time leaderboard website (generate static reports, publish manually)
- Fine-tuning or model training (evaluation only)
- Non-Ollama model providers (OpenAI, Anthropic, etc. - Ollama focus for matric ecosystem)

**Future Considerations** (post-v1.0 if project succeeds):
- lm-eval-harness integration (if Inspect AI proves inadequate)
- HELM framework support (research-grade holistic metrics)
- Distributed evaluation across multiple machines
- Evaluation result database (SQLite/PostgreSQL for historical tracking)
- Comparison reports (model A vs model B across benchmarks)
- Cost tracking (inference time, memory usage, token counts)

## Architecture (Proposed)

**Architecture Style**: Modular Python CLI with language bindings

**Chosen**: Modular monolith - **Rationale**: Single developer, clear module boundaries (tasks/solvers/scorers/config), simple deployment, easy debugging. Bindings are thin subprocess wrappers, not full microservices.

**Components** (proposed):

1. **Core Python Package** (`src/matric_eval/`)
   - **CLI** (`cli.py`): Entry point, argument parsing, orchestration
   - **Tasks** (`tasks/`): Benchmark task definitions (HumanEval, MBPP, etc.)
   - **Solvers** (`solvers/`): Custom solving strategies (code extraction, markdown handling)
   - **Scorers** (`scorers/`): Validation logic, custom metrics
   - **Config** (`config/`): Model configs, thresholds, tier definitions
   - **State** (`state.py`): Checkpoint/resume state management
   - **Recovery** (`recovery.py`): Gap detection, retry logic, error classification
   - Technology: Python 3.11+, uv package management, type hints throughout

2. **Dataset Management** (`datasets/`)
   - **Public** (`datasets/public/`): Symlinks or downloads to `/home/roctinam/data/evals/`
   - **Custom** (`datasets/custom/`): App-specific test suites in JSONL format
     - `cli/tool_calling.jsonl`, `cli/agent_scenarios.jsonl`
     - `memory/title_generation.jsonl`, `memory/semantic_similarity.jsonl`
   - Technology: JSONL files, reproducible sampling with seeds

3. **Language Bindings** (`bindings/`)
   - **TypeScript** (`bindings/typescript/`): npm package, subprocess wrapper
   - **Rust** (`bindings/rust/`): Crate, subprocess wrapper or FFI if needed
   - Technology: Subprocess execution, result streaming, type definitions

4. **Results Storage** (`results/run-{timestamp}/`)
   - Hierarchical state files (run → model → benchmark → problem)
   - Atomic writes (temp file + rename)
   - Lock files to prevent concurrent runs
   - JSON format for all state/results

**Data Models** (key entities):

1. **Run**
   - ID: timestamp-based (`run-2026-01-24T10-30-15`)
   - Tier: smoke | quick | full
   - Models: list of Ollama model names
   - Benchmarks: list of benchmark IDs
   - Seed: random seed for reproducibility
   - Status: running | completed | failed | cancelled

2. **ModelEvaluation**
   - Model: Ollama model name (e.g., `llama3.2:3b`)
   - Benchmarks: map of benchmark_id → BenchmarkResult
   - Status: pending | in_progress | completed | failed
   - Metadata: model size, quantization, capabilities

3. **BenchmarkResult**
   - Benchmark: HumanEval | MBPP | GSM8K | etc.
   - Problems: map of problem_id → ProblemResult
   - Score: aggregate score (0.0-1.0)
   - Status: pending | in_progress | completed | failed

4. **ProblemResult**
   - Problem ID: unique identifier
   - Prompt: input to model
   - Response: model output
   - Validation: pass | fail | error
   - Artifacts: extracted code, test results, error messages

**Integration Points**:
- **Ollama API**: HTTP API at `localhost:11434` (native Inspect AI support)
- **Inspect AI Framework**: Task definitions, solver pipeline, scoring
- **matric-cli**: TypeScript bindings via npm package import
- **matric-memory**: Rust bindings via Cargo dependency
- **CI/CD**: GitHub Actions or GitLab CI runners

## Scale and Performance (Target)

**Target Capacity**:
- **Initial users**: 3-5 developers (matric-cli, matric-memory teams)
- **6-month projection**: 10-20 developers across matric ecosystem
- **2-year vision**: Any matric application supporting Ollama models

**Performance Targets**:
- **Smoke tier**: <2 minutes (5 samples × 8 benchmarks = 40 problems)
- **Quick tier**: <20 minutes (75 samples × 8 benchmarks = 600 problems)
- **Full tier**: <2 hours per model (all problems, ~5,000 total)
- **Checkpoint overhead**: <1% performance impact (async state writes)
- **Resume latency**: <5 seconds to detect gaps and resume from checkpoint

**Performance Strategy**:
- **Caching**: Reuse Ollama model loads (keep model in memory between problems)
- **Batching**: Group problems by benchmark for efficient processing
- **Parallelization**: Evaluate multiple models concurrently (if resources allow)
- **Async I/O**: Non-blocking state writes, log streaming
- **Resource limits**: Timeout per problem (30s-120s based on complexity), memory limits for safe execution

## Security and Compliance (Requirements)

**Security Posture**: Baseline

**Chosen**: Baseline - **Rationale**: Internal development tool, no PII or sensitive data, running in controlled environments (local dev machines, CI). Code execution happens in Ollama sandbox.

**Data Classification**: Internal

**Identified**: Internal - **Evidence**: Evaluation results are internal development data. Models and test datasets are public. No user data, PII, or proprietary information.

**Security Controls** (required):
- **Authentication**: None (local CLI tool, CI uses existing auth)
- **Authorization**: File system permissions (results directories)
- **Data Protection**: No encryption needed (public benchmarks, internal results)
- **Secrets Management**: Ollama API endpoint configurable via environment variable
- **Code Execution**: Rely on Ollama's sandboxing for model code generation safety
- **Dependency Security**: SBOM generation (uv.lock), dependency scanning in CI

**Compliance Requirements**: None

No regulatory requirements - internal development tool.

## Team and Operations (Planned)

**Team Size**: Solo developer (1 Python expert)

**Team Skills**:
- **Python**: Expert (modern Python 3.11+, uv, type hints, async)
- **TypeScript**: Proficient (matric-cli integration)
- **Rust**: Proficient (matric-memory integration)
- **DevOps**: Familiar (CI/CD setup, Docker if needed)

**Development Velocity** (target):
- **Timeline**: 6-8 weeks to production-ready v1.0
- **Sprint length**: 1-week iterations for rapid feedback
- **Release frequency**: Continuous updates during development, semantic versioning for releases

**Process Maturity** (planned):
- **Version Control**: Git with feature branches, PR reviews (self-review for solo dev)
- **Code Review**: Self-review + CI checks (linting, type checking, tests)
- **Testing**: Target 60% coverage (pytest), integration tests for key workflows
- **CI/CD**: GitHub Actions or GitLab CI (lint, type check, test, build)
- **Documentation**: README, CLAUDE.md updates, ADRs for key decisions

**Operational Support** (planned):
- **Monitoring**: Structured logging (JSON), console output for progress
- **Logging**: Python logging module, log levels (DEBUG/INFO/ERROR)
- **Alerting**: CI failure notifications (email/Slack)
- **On-call**: None (development tool, best-effort support)

## Dependencies and Infrastructure

**Third-Party Services**:
- **Ollama**: Local Ollama server (required dependency)
- **Inspect AI**: Python framework (core dependency)
- **Public datasets**: Downloaded from HuggingFace, GitHub, or cached locally

**Infrastructure** (proposed):
- **Hosting**: Local development machine initially, can scale to dedicated eval server
- **Deployment**: Python package (pip/uv installable), language bindings published to npm/crates.io
- **Database**: File system (JSON state files), no database needed for v1.0
- **Compute**: Local CPU/GPU (Ollama handles model inference)

## Known Risks and Uncertainties

**Technical Risks**:

1. **Framework Recovery Capabilities** (HIGH PRIORITY)
   - **Risk**: Inspect AI may not support robust checkpoint/resume out of box
   - **Likelihood**: Medium (framework designed for research, not production resilience)
   - **Impact**: Blocking (checkpoint/resume is non-negotiable requirement)
   - **Mitigation**: Prototype Inspect AI checkpoint capabilities in first week. If inadequate, implement custom state management on top of framework. Be prepared to evaluate lm-eval-harness or build custom solution if needed.

2. **Ollama API Stability** (MEDIUM PRIORITY)
   - **Risk**: Ollama API may have transient failures (EPIPE, connection reset, timeouts)
   - **Likelihood**: Medium (observed in matric-cli eval, models can crash)
   - **Impact**: High (causes evaluation failures, lost progress)
   - **Mitigation**: Implement retry logic with exponential backoff. Classify errors (transient vs fatal). Auto-recovery for retryable errors, graceful degradation for fatal errors. Log all failures with context for debugging.

3. **Language Binding Complexity** (LOW-MEDIUM PRIORITY)
   - **Risk**: TypeScript/Rust subprocess bindings may be fragile or hard to maintain
   - **Likelihood**: Low (subprocess wrappers are well-understood pattern)
   - **Impact**: Medium (blocks adoption in matric-cli/memory)
   - **Mitigation**: Keep bindings thin (subprocess exec + result parsing). Provide type-safe interfaces. Test cross-language integration early. Consider FFI for Rust if subprocess overhead too high.

4. **Performance Bottlenecks** (LOW PRIORITY)
   - **Risk**: Full evaluation may exceed 2-hour target, making CI impractical
   - **Likelihood**: Medium (5,000 problems × multiple models is slow)
   - **Impact**: Medium (degrades developer experience, limits CI usage)
   - **Mitigation**: Optimize quick/smoke tiers first (most common use case). Profile slow benchmarks, parallelize where possible. Consider result caching for unchanged code. Defer full optimization until after v1.0 if needed.

**Integration Risks**:

1. **Inspect AI Ollama Compatibility**
   - **Risk**: Inspect AI's Ollama support may have bugs or limitations
   - **Impact**: Medium (could require custom model adapter)
   - **Mitigation**: Validate in prototype phase (week 1). Inspect AI is actively maintained by UK government, community support available.

2. **Dataset Availability**
   - **Risk**: Public benchmark datasets may be moved, deleted, or changed
   - **Impact**: Low (breaks reproducibility, requires maintenance)
   - **Mitigation**: Cache datasets locally in `/home/roctinam/data/evals/`. Version control dataset checksums. Document sources for re-download.

**Timeline Risks**:

1. **Scope Creep**
   - **Risk**: Adding features beyond v1.0 scope extends 6-8 week timeline
   - **Impact**: Medium (delays adoption in matric-cli/memory)
   - **Mitigation**: Strict scope adherence. All tiers equally important, but custom tests can wait until after public benchmarks working. Focus on resilience over features.

**Team Risks**:

1. **Solo Developer Bottleneck**
   - **Risk**: Single point of failure, no parallel work streams
   - **Impact**: Medium (extends timeline if blocked or unavailable)
   - **Mitigation**: Modular design allows future contributors. Document decisions in ADRs. Keep scope manageable for solo dev (6-8 weeks realistic for focused effort).

## Why This Intake Now?

**Context**: Starting greenfield infrastructure project to consolidate evaluation code across matric ecosystem. Planning phase complete (PLANNING.md), ready to begin implementation.

**Goals**:
- Validate architectural decisions (Inspect AI vs alternatives)
- Define clear scope and success criteria for v1.0
- Establish technical approach for checkpoint/resume (blocking requirement)
- Enable structured development with clear milestones
- Document trade-offs and decision rationale for future reference

**Triggers**:
- Code duplication pain points identified across matric-cli and matric-memory
- Recent eval failure (EPIPE at model 13/31) highlighted need for resilience
- Desire for data-driven model recommendations instead of manual selection
- Ecosystem readiness: Inspect AI framework mature enough for production use

## Attachments

- Solution profile: `.aiwg/intake/solution-profile.md`
- Option matrix: `.aiwg/intake/option-matrix.md`
- Planning document: `PLANNING.md` (already exists in repo)
- Session initialization: `SESSION_INIT.md` (already exists in repo)

## Next Steps

**Your intake documents are now complete and ready for the next phase!**

1. **Review** generated intake files for accuracy and completeness
2. **Validate** that resilience requirements (checkpoint/resume) are clearly prioritized
3. **Confirm** 6-8 week timeline and v1.0 scope are realistic
4. **Proceed to Inception** to create requirements and architecture artifacts:
   - Natural language: "Start Inception" or "Let's begin the Inception phase"
   - Explicit command: `/flow-concept-to-inception .`

**Note**: You do NOT need to run `/intake-start` - the `intake-wizard` command produces validated intake ready for immediate use. The Inception phase will create detailed requirements (user stories, use cases), architecture (SAD, ADRs), and test strategy artifacts.
