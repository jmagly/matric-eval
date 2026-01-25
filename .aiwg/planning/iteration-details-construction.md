# Construction Phase - Detailed Iteration Plans

**Document Type**: Detailed Iteration Plans
**Project**: matric-eval
**Phase**: Construction (Weeks 4-7)
**Generated**: 2026-01-24

## Table of Contents

1. [Iteration 1 (Week 4): Critical Foundation](#iteration-1-week-4-critical-foundation)
2. [Iteration 2 (Week 5): Advanced Features](#iteration-2-week-5-advanced-features)
3. [Iteration 3 (Week 6): Operational Excellence](#iteration-3-week-6-operational-excellence)
4. [Iteration 4 (Week 7): Extended Features](#iteration-4-week-7-extended-features)
5. [Daily Velocity Tracking](#daily-velocity-tracking)
6. [Testing Strategy](#testing-strategy)

---

## Iteration 1 (Week 4): Critical Foundation

**Theme**: "Foundation for Evaluation Excellence"
**Total Estimated Hours**: 38 hours
**Available Hours**: 40 hours (8h/day × 5 days)
**Buffer**: 2 hours (5%)

### Issue #1: Code Execution Scoring for HumanEval/MBPP (8 hours)

**Priority**: P1
**Estimated**: 8 hours
**Test Coverage Target**: 90%

**Description**: Implement production-grade code execution scoring with Docker sandbox isolation. This replaces the simple string-matching scorers from Inception with actual Python code execution and test validation.

**Acceptance Criteria**:
- [ ] Docker sandbox configured with memory limits (512MB), timeout (5s per test), no network access
- [ ] Code extraction handles markdown fences, language tags, mixed code/text
- [ ] Test execution runs solution code + test cases, captures pass/fail
- [ ] Error handling for syntax errors, runtime errors, timeouts, memory exhaustion
- [ ] Results include execution status, stdout/stderr, test results
- [ ] Validated against matric-cli baseline with ≥95% accuracy match
- [ ] Unit tests cover all error paths and edge cases
- [ ] Integration test runs 10 HumanEval samples end-to-end

**Technical Tasks**:
1. (2h) Docker sandbox setup: Dockerfile, entrypoint script, volume mounts
2. (1.5h) Code extraction from model output: regex patterns, markdown parsing
3. (2h) Execution harness: run code + tests, timeout enforcement, result capture
4. (1h) Error handling: classify errors (syntax, runtime, timeout), retry logic
5. (1h) Integration with Inspect AI scorer API
6. (0.5h) Validation against matric-cli outputs

**Dependencies**: Docker installed, Inspect AI framework (from Inception)

**Risks**:
- Docker setup complexity on different platforms
- Code extraction false negatives (valid code rejected)
- Sandbox escape vulnerabilities

**Mitigation**: Use Docker's built-in isolation features, test with diverse code samples, security audit of entrypoint script

---

### Issue #2: Integrate inspect-evals for Public Benchmarks (6 hours)

**Priority**: P1
**Estimated**: 6 hours
**Test Coverage Target**: 85%

**Description**: Integrate inspect-evals package to leverage pre-built implementations of HumanEval, MBPP, GSM8K, and ARC-Challenge. Configure for Ollama compatibility.

**Acceptance Criteria**:
- [ ] `inspect-evals` package added to dependencies
- [ ] HumanEval, MBPP, GSM8K, ARC tasks configured and working
- [ ] Ollama model integration tested with llama3.2:3b
- [ ] Dataset loading from local cache or auto-download
- [ ] Smoke test (5 samples) completes for each benchmark in <30 seconds
- [ ] Results format matches matric-eval schema
- [ ] Unit tests for task configuration and dataset loading
- [ ] Integration test runs all 4 benchmarks

**Technical Tasks**:
1. (1h) Add inspect-evals dependency, resolve version conflicts
2. (1.5h) Configure HumanEval and MBPP with code execution scorer from #1
3. (1h) Configure GSM8K with numeric extraction and validation
4. (1h) Configure ARC-Challenge with multiple-choice scoring
5. (1h) Dataset management: local cache, download logic, versioning
6. (0.5h) Integration testing and validation

**Dependencies**: #1 (code execution scorer patterns)

**Risks**:
- inspect-evals version incompatibility with Inspect AI
- Dataset download failures or format changes
- Ollama integration issues

**Mitigation**: Pin inspect-evals version, implement dataset fallback URLs, test with multiple Ollama models

---

### Issue #3: IFEval Constraint Checking Scorer (7 hours)

**Priority**: P1
**Estimated**: 7 hours
**Test Coverage Target**: 90%

**Description**: Implement custom scorer for IFEval (Instruction Following Evaluation) that validates model outputs against constraint specifications (word count, format, keywords, structure).

**Acceptance Criteria**:
- [ ] Parses all IFEval constraint types: keywords, length, format, structure, case
- [ ] Validates model output against multiple simultaneous constraints
- [ ] Produces detailed pass/fail for each constraint
- [ ] Handles edge cases: unicode, multi-language, formatting ambiguity
- [ ] Achieves ≥90% accuracy on IFEval validation set
- [ ] Unit tests for each constraint type
- [ ] Integration test with 10 IFEval samples

**Technical Tasks**:
1. (2h) Constraint parser: extract constraint specs from IFEval format
2. (2h) Constraint validators: implement each type (keywords, length, format, etc.)
3. (1h) Composite scoring: combine multiple constraints, weighted scoring
4. (1h) Edge case handling: unicode, whitespace, capitalization
5. (0.5h) Integration with Inspect AI scorer API
6. (0.5h) Validation against IFEval reference implementation

**Dependencies**: #2 (inspect-evals integration patterns)

**Risks**:
- Constraint specification ambiguity
- Edge cases not covered in documentation
- Format parsing complexity

**Mitigation**: Study IFEval reference implementation, start with most common constraint types, iterate based on failures

---

### Issue #4: LiveCodeBench Competitive Programming Scorer (6 hours)

**Priority**: P1
**Estimated**: 6 hours
**Test Coverage Target**: 85%

**Description**: Implement scorer for LiveCodeBench competitive programming problems with time complexity validation, test case execution, and performance measurement.

**Acceptance Criteria**:
- [ ] Executes solution code against hidden test cases
- [ ] Validates correctness (all tests pass)
- [ ] Measures time complexity (actual runtime within expected bounds)
- [ ] Handles edge cases: infinite loops, memory exhaustion, incorrect output format
- [ ] Supports multiple languages (focus on Python, extensible to others)
- [ ] Unit tests for scoring logic and performance measurement
- [ ] Integration test with 5 LiveCodeBench problems

**Technical Tasks**:
1. (1.5h) Test case execution: run solution against inputs, capture outputs
2. (1.5h) Time complexity validation: measure runtime, compare to baseline
3. (1h) Error handling: timeout, memory limits, incorrect output
4. (1h) Multi-language support architecture (Python first, extensible)
5. (0.5h) Integration with code execution sandbox from #1
6. (0.5h) Validation with sample LiveCodeBench problems

**Dependencies**: #1 (code execution sandbox)

**Risks**:
- Time complexity measurement unreliable
- Language-specific runtime differences
- Hidden test case access

**Mitigation**: Use consistent execution environment, focus on Python initially, validate time measurements with known solutions

---

### Issue #5: DS-1000 Data Science Scorer (5 hours)

**Priority**: P1
**Estimated**: 5 hours
**Test Coverage Target**: 85%

**Description**: Implement scorer for DS-1000 data science problems, including environment setup with numpy/pandas/sklearn, output validation, and result comparison.

**Acceptance Criteria**:
- [ ] Python environment with data science libraries (numpy, pandas, sklearn, matplotlib)
- [ ] Executes data science code snippets with library imports
- [ ] Validates outputs: dataframes, arrays, plots, models
- [ ] Compares results against expected outputs with tolerance for floating-point
- [ ] Handles library version differences gracefully
- [ ] Unit tests for output comparison logic
- [ ] Integration test with 5 DS-1000 problems

**Technical Tasks**:
1. (1.5h) Environment setup: Docker image with data science stack
2. (1h) Code execution integration with #1 sandbox
3. (1h) Output validation: dataframe comparison, array equality, numerical tolerance
4. (1h) Library version handling: compatibility checks, fallbacks
5. (0.5h) Integration testing with sample problems

**Dependencies**: #1 (code execution patterns)

**Risks**:
- Library version incompatibilities
- Large dataset handling
- Plot/visualization validation complexity

**Mitigation**: Pin library versions in Docker, validate with small datasets first, defer plot validation to post-v1.0

---

### Issue #6: Tiered CLI with Smoke/Quick/Full Modes (6 hours)

**Priority**: P1
**Estimated**: 6 hours
**Test Coverage Target**: 90%

**Description**: Implement CLI with tier-based sampling (smoke/quick/full), model discovery from Ollama, and flexible evaluation configuration.

**Acceptance Criteria**:
- [ ] CLI supports `--tier smoke|quick|full` with different sample counts
- [ ] Model discovery queries Ollama, filters by size if configured
- [ ] Supports `--model`, `--benchmark`, `--output` flags
- [ ] Smoke tier: 5 samples/benchmark, completes in <2 minutes
- [ ] Quick tier: 75 samples/benchmark, completes in <20 minutes
- [ ] Full tier: all samples, time varies by benchmark size
- [ ] Seeded sampling for reproducibility (EVAL_SEED environment variable)
- [ ] Progress reporting during evaluation
- [ ] Unit tests for CLI argument parsing and tier configuration
- [ ] Integration test runs each tier end-to-end

**Technical Tasks**:
1. (1.5h) CLI argument parsing: argparse or click, validation
2. (1h) Tier configuration: sample counts, timeout settings, output formats
3. (1h) Model discovery: query Ollama API, filter by size, list available
4. (1h) Seeded sampling: reproducible selection of samples from full datasets
5. (1h) Progress reporting: real-time status, ETA, completion percentage
6. (0.5h) Integration with benchmarks from #2

**Dependencies**: #2 (benchmarks available), Inception CLI foundation

**Risks**:
- Ollama API changes
- Sampling bias in tier subsets
- Progress reporting performance overhead

**Mitigation**: Version-pin Ollama API expectations, validate sampling distribution, make progress reporting optional

---

### Week 4 Daily Plan

**Monday** (8 hours):
- AM: #1 Docker sandbox setup (2h)
- AM: #1 Code extraction (1.5h)
- PM: #1 Execution harness (2h)
- PM: #2 inspect-evals dependency setup (1h)
- PM: #2 HumanEval/MBPP configuration (1.5h)
- **EOD**: Code execution working, HumanEval/MBPP configured

**Tuesday** (8 hours):
- AM: #1 Error handling and integration (1.5h)
- AM: #2 GSM8K and ARC configuration (2h)
- PM: #2 Dataset management (1h)
- PM: #3 Constraint parser (2h)
- PM: #3 Constraint validators start (1.5h)
- **EOD**: All 4 inspect-evals benchmarks working, IFEval 50% complete

**Wednesday** (8 hours):
- AM: #3 Constraint validators finish (2h)
- AM: #3 Composite scoring and edge cases (1.5h)
- PM: #4 LiveCodeBench test execution (1.5h)
- PM: #4 Time complexity validation (1.5h)
- PM: #5 DS-1000 environment setup (1.5h)
- **EOD**: IFEval complete, LiveCodeBench 50% complete, DS-1000 started

**Thursday** (8 hours):
- AM: #4 Error handling and multi-language (2h)
- AM: #5 Output validation (2h)
- PM: #5 Library version handling (1.5h)
- PM: #6 CLI argument parsing (1.5h)
- PM: #6 Tier configuration (1h)
- **EOD**: All scorers complete, CLI 50% complete

**Friday** (8 hours):
- AM: #6 Model discovery and sampling (2h)
- AM: #6 Progress reporting (1h)
- AM: Integration testing all benchmarks (2h)
- PM: Bug fixes and refinements (2h)
- PM: Test coverage validation (1h)
- **EOD**: Week 4 gate review, all criteria met

**Total**: 40 hours (38 estimated + 2 buffer)

---

## Iteration 2 (Week 5): Advanced Features

**Theme**: "Custom Intelligence and Multi-Turn Evaluation"
**Total Estimated Hours**: 42 hours
**Available Hours**: 40 hours
**Buffer**: -2 hours (2.5% overflow, compensated by Week 6)

### Issue #7: Port 282 Custom Matric Tests (8 hours)

**Priority**: P2
**Estimated**: 8 hours
**Test Coverage Target**: 80%

**Description**: Migrate 282 custom tests from matric-cli and matric-memory to matric-eval JSONL format, including custom scorers for format compliance, semantic similarity, tag generation, etc.

**Acceptance Criteria**:
- [ ] All 282 tests migrated to JSONL format
- [ ] Custom scorers implemented for each test category:
  - format_compliance (55 tests): title/content format validation
  - semantic_similarity (42 tests): embedding-based similarity
  - tag_generation (30 tests): tag accuracy and relevance
  - content_revision (44 tests): revision quality assessment
  - long_context (18 tests): context window handling
  - context_generation (29 tests): context relevance
  - title_generation (64 tests): title quality metrics
- [ ] Validated against matric-cli/matric-memory baselines (±5% accuracy)
- [ ] Unit tests for each scorer category
- [ ] Integration test runs 20 samples from each category

**Technical Tasks**:
1. (2h) Data migration: convert existing tests to JSONL, validate format
2. (2h) Format compliance scorer: regex patterns, structure validation
3. (1h) Semantic similarity scorer: embedding generation, cosine similarity
4. (1h) Tag/title generation scorers: keyword matching, quality heuristics
5. (1h) Content revision scorer: diff analysis, improvement metrics
6. (1h) Integration and validation against baselines

**Dependencies**: #2 (benchmark infrastructure), Custom test data

**Risks**:
- Data format inconsistencies during migration
- Scorer accuracy divergence from original implementations
- Large dataset handling (282 tests)

**Mitigation**: Validate 10% sample first, iterate on scorers based on accuracy, batch process large datasets

---

### Issue #8: Tool Calling Evaluation (6 scenarios) (7 hours)

**Priority**: P2
**Estimated**: 7 hours
**Test Coverage Target**: 85%

**Description**: Implement tool calling evaluation with 6 scenarios testing correct tool selection, parameter validation, error handling, and multi-step reasoning.

**Acceptance Criteria**:
- [ ] 6 tool calling scenarios implemented:
  1. simple-read: Single file read operation
  2. read-modify-write: Multi-step file editing
  3. search-read-act: Complex workflow with search, read, action
  4. error-handling: Graceful failure on invalid inputs
  5. parallel-execution: Concurrent tool calls
  6. param-validation: Parameter correctness before execution
- [ ] Scorer validates tool selection accuracy (correct tools chosen)
- [ ] Scorer validates parameter correctness (valid arguments passed)
- [ ] Scorer validates execution order (sequential vs parallel as appropriate)
- [ ] Sandbox isolation for tool execution safety
- [ ] Unit tests for each scenario
- [ ] Integration test runs all 6 scenarios

**Technical Tasks**:
1. (2h) Tool scenario dataset creation: JSONL with expected tool calls
2. (2h) Tool calling scorer: validate tool selection, parameters, order
3. (1.5h) Sandbox integration for safe tool execution
4. (1h) Error handling validation: test graceful degradation
5. (0.5h) Integration with Inspect AI tool use API

**Dependencies**: #1 (sandboxing patterns), #6 (CLI foundation)

**Risks**:
- Tool calling API changes in Inspect AI
- Sandbox security for arbitrary tool execution
- Scoring ambiguity (multiple valid tool sequences)

**Mitigation**: Pin Inspect AI version, restrict tool set to safe operations, define acceptance criteria clearly

---

### Issue #9: MT-Bench Multi-Turn with LLM-as-Judge (8 hours)

**Priority**: P2
**Estimated**: 8 hours
**Test Coverage Target**: 75%

**Description**: Implement MT-Bench multi-turn conversation evaluation using LLM-as-judge for scoring response quality, coherence, and helpfulness across conversation turns.

**Acceptance Criteria**:
- [ ] 80 MT-Bench questions loaded and configured
- [ ] Multi-turn conversation state management (2+ turns per question)
- [ ] LLM-as-judge scoring using Ollama model (llama3.1:8b or better)
- [ ] Judge evaluates: helpfulness, correctness, coherence, depth, creativity
- [ ] Score variance <15% across 3 judge runs (temperature=0)
- [ ] Unit tests for conversation state and judge prompting
- [ ] Integration test runs 5 MT-Bench questions end-to-end

**Technical Tasks**:
1. (2h) MT-Bench dataset loading and conversation structure
2. (2h) Multi-turn state management: conversation history, turn tracking
3. (2h) LLM-as-judge implementation: judge prompts, score extraction
4. (1h) Score validation: variance testing, temperature tuning
5. (1h) Integration with Inspect AI model_graded_fact or custom scorer

**Dependencies**: #2 (inspect-evals integration patterns)

**Risks**:
- Judge model inconsistency (high score variance)
- Multi-turn state complexity
- Long evaluation time (2+ model calls per question)

**Mitigation**: Use temperature=0, validate judge with known-good conversations, parallelize judge calls

---

### Issue #10: 5-Dimensional Scoring Framework (6 hours)

**Priority**: P2
**Estimated**: 6 hours
**Test Coverage Target**: 85%

**Description**: Implement multi-dimensional scoring framework that evaluates models across 5 dimensions: correctness, efficiency, safety, helpfulness, reasoning. Produces composite scores and per-dimension breakdowns.

**Acceptance Criteria**:
- [ ] 5 scoring dimensions implemented:
  - Correctness (30% weight): test pass rate, accuracy
  - Efficiency (20% weight): time complexity, token usage
  - Safety (15% weight): harmful content, bias detection
  - Helpfulness (20% weight): relevance, clarity
  - Reasoning (15% weight): logical coherence, step-by-step quality
- [ ] Composite scoring: weighted average with configurable weights
- [ ] Per-dimension scores included in result metadata
- [ ] Dimension scorers integrate with existing task scorers
- [ ] Unit tests for each dimension scorer
- [ ] Integration test validates composite scoring

**Technical Tasks**:
1. (1.5h) Correctness scorer: integrate existing test-based scoring
2. (1h) Efficiency scorer: measure tokens, time, complexity
3. (1h) Safety scorer: harmful content detection, bias check
4. (1h) Helpfulness scorer: relevance metrics, clarity heuristics
5. (1h) Reasoning scorer: step detection, logical coherence
6. (0.5h) Composite scoring: weighted combination, metadata

**Dependencies**: #1-#5 (base scorers), #9 (judge patterns for subjective dimensions)

**Risks**:
- Subjective dimension scoring unreliable
- Weight tuning complexity
- Performance overhead of multiple scorers

**Mitigation**: Start with objective dimensions (correctness, efficiency), use LLM-as-judge for subjective, make weights configurable

---

### Issue #21: Port matric-memory LLM-as-Judge Templates (6 hours)

**Priority**: P2
**Estimated**: 6 hours
**Test Coverage Target**: 80%

**Description**: Port LLM-as-judge templates from matric-memory for title generation, content quality, and semantic evaluation. Integrate with matric-eval scoring framework.

**Acceptance Criteria**:
- [ ] Judge templates ported for:
  - Title generation quality (clarity, relevance, length)
  - Content revision assessment (improvement, accuracy, style)
  - Semantic similarity validation (meaning preservation)
- [ ] Templates use configurable rubrics and scoring criteria
- [ ] Validation against matric-memory judge baseline (±10% accuracy)
- [ ] Unit tests for template rendering and score extraction
- [ ] Integration test with 10 samples per template type

**Technical Tasks**:
1. (2h) Template migration: extract matric-memory templates, convert format
2. (1.5h) Rubric configuration: criteria, weights, scoring scales
3. (1h) Score extraction: parse judge responses, validate format
4. (1h) Integration with #9 judge infrastructure
5. (0.5h) Validation against matric-memory baseline

**Dependencies**: #9 (MT-Bench judge implementation)

**Risks**:
- Template format incompatibilities
- Score extraction parsing failures
- Judge model differences affecting scores

**Mitigation**: Start with simplest templates, validate extraction with diverse outputs, document judge model requirements

---

### Issue #22: Universal LLM-as-Judge with Agentic Support (7 hours)

**Priority**: P2
**Estimated**: 7 hours
**Test Coverage Target**: 75%

**Description**: Create universal LLM-as-judge scorer supporting custom rubrics, multi-step reasoning evaluation, and agentic task assessment with tool use validation.

**Acceptance Criteria**:
- [ ] Universal judge API: accepts custom rubric, question, response
- [ ] Supports multi-step reasoning evaluation (chain-of-thought assessment)
- [ ] Agentic task scoring: evaluates tool use, planning, error recovery
- [ ] Configurable judge models (different models for different tasks)
- [ ] Rubric validation: ensures criteria are well-formed
- [ ] Unit tests for rubric parsing and judge prompting
- [ ] Integration test with 3 different task types (code, reasoning, agentic)

**Technical Tasks**:
1. (2h) Universal judge API: rubric schema, prompt generation
2. (1.5h) Multi-step reasoning evaluation: step detection, coherence scoring
3. (1.5h) Agentic task assessment: tool use validation, planning quality
4. (1h) Configurable judge models: model selection, fallback logic
5. (1h) Integration with existing scorers and validation

**Dependencies**: #9 (MT-Bench), #21 (templates), #8 (tool calling patterns)

**Risks**:
- API complexity leading to confusion
- Judge prompt engineering challenges
- Evaluation time with complex rubrics

**Mitigation**: Provide clear API documentation and examples, start with simple rubrics, cache judge responses

---

### Week 5 Daily Plan

**Monday** (8 hours):
- AM: #7 Data migration (2h)
- AM: #7 Format compliance scorer (2h)
- PM: #7 Semantic similarity scorer (1h)
- PM: #8 Tool scenario dataset (2h)
- PM: #8 Tool calling scorer start (1h)
- **EOD**: Custom tests 50% migrated, tool calling started

**Tuesday** (8 hours):
- AM: #7 Tag/title scorers (2h)
- AM: #7 Content revision scorer (1h)
- PM: #8 Tool calling scorer finish (1h)
- PM: #8 Sandbox integration (1.5h)
- PM: #9 MT-Bench dataset loading (2h)
- PM: #9 Multi-turn state management start (0.5h)
- **EOD**: Custom tests complete, tool calling 70% complete

**Wednesday** (8 hours):
- AM: #8 Error handling validation (1h)
- AM: #9 Multi-turn state management finish (1.5h)
- AM: #9 LLM-as-judge implementation (2h)
- PM: #9 Score validation (1h)
- PM: #10 Correctness and efficiency scorers (2.5h)
- **EOD**: Tool calling complete, MT-Bench 70% complete, 5D scoring started

**Thursday** (8 hours):
- AM: #9 Integration testing (1h)
- AM: #10 Safety and helpfulness scorers (2h)
- PM: #10 Reasoning scorer and composite (1.5h)
- PM: #21 Template migration (2h)
- PM: #21 Rubric configuration (1.5h)
- **EOD**: MT-Bench complete, 5D scoring complete, templates 60% ported

**Friday** (8 hours):
- AM: #21 Score extraction and integration (1.5h)
- AM: #22 Universal judge API (2h)
- PM: #22 Multi-step reasoning evaluation (1.5h)
- PM: #22 Agentic task assessment (1.5h)
- PM: Integration testing and bug fixes (1.5h)
- **EOD**: Week 5 gate review, all P2 issues complete

**Total**: 40 hours (42 estimated, -2h overflow handled by prioritization)

---

## Iteration 3 (Week 6): Operational Excellence

**Theme**: "Production Resilience and Scale"
**Total Estimated Hours**: 32 hours
**Available Hours**: 40 hours
**Buffer**: 8 hours (20%)

### Issue #11: Checkpoint/Resume for Fault Tolerance (10 hours)

**Priority**: P3
**Estimated**: 10 hours
**Test Coverage Target**: 95%

**Description**: Implement comprehensive checkpoint/resume capability with gap detection, selective re-run, and zero data loss on interruption. This addresses the critical EPIPE failure scenario from matric-cli.

**Acceptance Criteria**:
- [ ] State persistence after each problem evaluation
- [ ] Resume from checkpoint with `--resume run-{id}`
- [ ] Gap detection identifies incomplete/missing results
- [ ] Selective re-run: `--model X --benchmark Y` only
- [ ] Fill gaps mode: `--fill-gaps` completes missing work
- [ ] Validation mode: `--validate` reports completeness
- [ ] Zero data loss on Ctrl+C, SIGTERM, or crash
- [ ] Lock files prevent concurrent runs on same directory
- [ ] Atomic writes (temp file + rename) for state files
- [ ] Unit tests for state management and gap detection (95% coverage)
- [ ] Fault injection tests: kill process, verify resume works
- [ ] Integration test: interrupt + resume across all benchmarks

**Technical Tasks**:
1. (3h) State management: meta.json, state.json schema, atomic writes
2. (2h) Resume logic: load state, skip completed, continue from checkpoint
3. (2h) Gap detection: scan results, identify missing/incomplete
4. (1h) Selective re-run: filter by model/benchmark, update state
5. (1h) Lock file management: prevent concurrent runs, detect zombies
6. (1h) Fault injection testing: simulate crashes, validate recovery

**Dependencies**: Inception state management foundation, #1-#5 (all benchmarks)

**Risks**:
- State corruption on abnormal termination
- Race conditions in parallel scenarios
- Lock file stale state (zombie detection)

**Mitigation**: Atomic writes with temp files, file locking with timeouts, heartbeat tracking for zombie detection

---

### Issue #12: Parallel Model Evaluation (8 hours)

**Priority**: P3
**Estimated**: 8 hours
**Test Coverage Target**: 85%

**Description**: Enable parallel evaluation of multiple models to reduce total runtime by 50%+. Implement process isolation, resource management, and result aggregation.

**Acceptance Criteria**:
- [ ] Parallel execution: `--parallel N` evaluates N models concurrently
- [ ] Process isolation: each model in separate process/container
- [ ] Resource management: CPU/memory limits per process
- [ ] Result aggregation: combine results from parallel runs
- [ ] No race conditions in state management (#11 lock files)
- [ ] Runtime reduction ≥50% for 4+ models (on 4+ core system)
- [ ] Unit tests for process management and aggregation
- [ ] Integration test: parallel evaluation of 3 models

**Technical Tasks**:
1. (2h) Process pool implementation: spawn workers, manage lifecycle
2. (2h) Work distribution: assign models to workers, load balancing
3. (1.5h) State isolation: separate state per model, lock file coordination
4. (1.5h) Result aggregation: collect results, generate summary
5. (1h) Resource limits: CPU/memory per worker, monitoring

**Dependencies**: #11 (state management), #6 (CLI)

**Risks**:
- Resource contention (CPU, memory, Ollama)
- State corruption from concurrent writes
- Deadlocks in lock file management

**Mitigation**: Limit concurrency based on system resources, file locking with timeouts, separate result directories per model

---

### Issue #13: CI/CD Pipeline with Smoke Tests (8 hours)

**Priority**: P3
**Estimated**: 8 hours
**Test Coverage Target**: 90%

**Description**: Implement CI/CD pipeline with automated smoke tests on every PR, blocking merge on failures. Tests must complete in <3 minutes.

**Acceptance Criteria**:
- [ ] GitHub Actions workflow configured (or equivalent CI)
- [ ] Smoke tests run on every PR commit
- [ ] Tests complete in <3 minutes
- [ ] PR merge blocked on test failure
- [ ] Test results published as PR comment
- [ ] Docker caching for fast setup
- [ ] Ollama model cached or mocked for CI speed
- [ ] Coverage report generated and tracked
- [ ] Unit + integration + smoke tests all passing

**Technical Tasks**:
1. (2h) CI workflow configuration: GitHub Actions YAML, triggers
2. (2h) Docker caching: layer optimization, dependency caching
3. (1.5h) Ollama setup for CI: model caching or mocking
4. (1h) Smoke test suite: fast subset of integration tests
5. (1h) Coverage reporting: generate reports, publish to PR
6. (0.5h) PR comment integration: test results and coverage summary

**Dependencies**: #6 (CLI), #1-#5 (benchmarks), Docker setup

**Risks**:
- CI runtime exceeds 3 minute target
- Ollama model download time
- Docker build time
- Flaky tests blocking PRs

**Mitigation**: Aggressive caching, consider mocking Ollama for smoke tests, parallel test execution, retry on flakes

---

### Issue #14: Comprehensive Logging and Observability (6 hours)

**Priority**: P3
**Estimated**: 6 hours
**Test Coverage Target**: 85%

**Description**: Implement structured logging with appropriate levels, real-time progress tracking, and metrics collection for observability.

**Acceptance Criteria**:
- [ ] Structured logging: JSON format, appropriate levels (DEBUG, INFO, WARN, ERROR)
- [ ] Real-time progress: current model, benchmark, problem, ETA
- [ ] Metrics collection: samples/sec, tokens/sec, success rate, error count
- [ ] Log levels configurable via CLI flag or environment variable
- [ ] Performance overhead <5% (measured with/without logging)
- [ ] Log rotation and retention policy
- [ ] Unit tests for logging utilities
- [ ] Integration test validates logs for end-to-end run

**Technical Tasks**:
1. (2h) Structured logging setup: Python logging config, JSON formatter
2. (1.5h) Progress tracking: real-time status, ETA calculation
3. (1h) Metrics collection: counters, timers, aggregation
4. (1h) Log configuration: CLI flags, environment variables, levels
5. (0.5h) Performance validation: measure overhead

**Dependencies**: #6 (CLI), #11 (state tracking)

**Risks**:
- Logging performance overhead
- Log volume management
- Sensitive data in logs

**Mitigation**: Make logging configurable, implement sampling for high-volume events, sanitize outputs

---

### Week 6 Daily Plan

**Monday** (8 hours):
- AM: #11 State management schema and atomic writes (3h)
- PM: #11 Resume logic (2h)
- PM: #11 Gap detection (2h)
- PM: Planning for Tuesday (1h)
- **EOD**: Checkpoint/resume 70% complete

**Tuesday** (8 hours):
- AM: #11 Selective re-run (1h)
- AM: #11 Lock file management (1h)
- AM: #11 Fault injection testing (1h)
- PM: #12 Process pool implementation (2h)
- PM: #12 Work distribution (2h)
- PM: Documentation (1h)
- **EOD**: Checkpoint/resume complete, parallel execution 50% complete

**Wednesday** (8 hours):
- AM: #12 State isolation (1.5h)
- AM: #12 Result aggregation (1.5h)
- PM: #12 Resource limits (1h)
- PM: #13 CI workflow configuration (2h)
- PM: #13 Docker caching (2h)
- **EOD**: Parallel execution complete, CI setup 50% complete

**Thursday** (8 hours):
- AM: #13 Ollama setup for CI (1.5h)
- AM: #13 Smoke test suite (1h)
- PM: #13 Coverage reporting (1h)
- PM: #13 PR comment integration (0.5h)
- PM: #14 Structured logging setup (2h)
- PM: #14 Progress tracking (1h)
- **EOD**: CI complete, logging 50% complete

**Friday** (8 hours):
- AM: #14 Metrics collection (1h)
- AM: #14 Log configuration (1h)
- AM: #14 Performance validation (0.5h)
- PM: Integration testing all P3 features (2h)
- PM: Bug fixes and refinements (2h)
- PM: Test coverage validation (1h)
- PM: Week 6 gate review (0.5h)
- **EOD**: All P3 issues complete, ready for Week 7

**Total**: 40 hours (32 estimated + 8 buffer for polish and integration)

---

## Iteration 4 (Week 7): Extended Features

**Theme**: "Enhanced Usability and Insights"
**Total Estimated Hours**: 25 hours (selected subset)
**Available Hours**: 40 hours
**Buffer**: 15 hours (37%)

### Issue #18: Model Recommendation Engine (10 hours)

**Priority**: P4-SELECTED
**Estimated**: 10 hours
**Test Coverage Target**: 80%

**Description**: Generate model recommendations based on evaluation results, producing config files that map capabilities to optimal models.

**Acceptance Criteria**:
- [ ] Analyzes evaluation results across all benchmarks
- [ ] Generates recommendations by capability:
  - Code generation: best HumanEval/MBPP/LiveCodeBench performers
  - Reasoning: best GSM8K/ARC performers
  - Instruction following: best IFEval performers
  - Data science: best DS-1000 performers
  - Multi-turn: best MT-Bench performers
  - Tool calling: best tool evaluation performers
- [ ] Produces model-categories.json config file
- [ ] Includes performance metrics, trade-offs, and confidence scores
- [ ] Supports custom capability definitions
- [ ] Unit tests for recommendation logic
- [ ] Integration test generates config from sample results

**Technical Tasks**:
1. (2h) Result analysis: aggregate scores by capability
2. (2h) Ranking algorithm: score normalization, capability mapping
3. (2h) Config generation: JSON schema, validation
4. (2h) Trade-off analysis: size vs performance, speed vs accuracy
5. (1h) Confidence scoring: statistical significance, sample size
6. (1h) Integration and validation

**Dependencies**: #10 (5D scoring), #1-#9 (evaluation results)

**Risks**:
- Recommendation algorithm simplistic
- Insufficient data for confident recommendations
- Config format misalignment with consumer expectations

**Mitigation**: Start with simple heuristics, document confidence levels, gather feedback from matric-cli/matric-memory teams

---

### Issue #13-EXT: Extended Reporting and Dashboards (8 hours)

**Priority**: P4-SELECTED
**Estimated**: 8 hours
**Test Coverage Target**: 75%

**Description**: Extend #14 logging/observability with comprehensive reporting: comparison tables, visualizations, trend analysis within a single run.

**Acceptance Criteria**:
- [ ] Comparison tables: model rankings across benchmarks
- [ ] Visualizations: score distributions, dimension radar charts
- [ ] Markdown report generation: summary, details, recommendations
- [ ] HTML dashboard (optional): interactive charts and filtering
- [ ] Export formats: JSON, CSV, Markdown, HTML
- [ ] Unit tests for report generation
- [ ] Integration test generates reports from sample results

**Technical Tasks**:
1. (2h) Comparison tables: aggregate results, sort by metric
2. (2h) Visualizations: matplotlib/plotly charts, dimension plots
3. (2h) Markdown report generation: template, sections, formatting
4. (1h) Export formats: JSON, CSV serialization
5. (1h) Integration and validation

**Dependencies**: #14 (logging/observability), #18 (recommendations)

**Risks**:
- Visualization library dependencies
- Report generation time overhead
- HTML dashboard scope creep

**Mitigation**: Focus on Markdown first (defer HTML to post-v1.0), use lightweight charting, time-box HTML work

---

### Issue #16-PARTIAL: TypeScript Bindings for matric-cli (7 hours)

**Priority**: P4-SELECTED
**Estimated**: 7 hours
**Test Coverage Target**: 70%

**Description**: Create TypeScript bindings enabling matric-cli to invoke matric-eval programmatically, stream results, and integrate into existing workflows.

**Acceptance Criteria**:
- [ ] npm package: `@matric/eval-bindings`
- [ ] TypeScript API: invoke evaluation, configure options
- [ ] Result streaming: real-time progress and results
- [ ] Type definitions: full TypeScript support
- [ ] Example integration code for matric-cli
- [ ] Unit tests for API wrapper
- [ ] Integration test from matric-cli repository

**Technical Tasks**:
1. (2h) npm package setup: package.json, build config, TypeScript
2. (2h) API wrapper: subprocess invocation, argument passing
3. (1.5h) Result streaming: parse JSON output, emit events
4. (1h) Type definitions: interfaces for options, results
5. (0.5h) Example integration and documentation

**Dependencies**: #6 (stable CLI), #11 (checkpoint/resume)

**Risks**:
- TypeScript/Python impedance mismatch
- Result streaming reliability
- Version compatibility between packages

**Mitigation**: Keep API simple (thin wrapper), version-lock matric-eval dependency, document breaking change policy

---

### Week 7 Daily Plan

**Monday** (8 hours):
- AM: #18 Result analysis (2h)
- AM: #18 Ranking algorithm (2h)
- PM: #18 Config generation (2h)
- PM: #18 Trade-off analysis (2h)
- **EOD**: Model recommendations 80% complete

**Tuesday** (8 hours):
- AM: #18 Confidence scoring (1h)
- AM: #18 Integration and testing (1h)
- PM: #13-EXT Comparison tables (2h)
- PM: #13-EXT Visualizations (2h)
- PM: #13-EXT Markdown reports start (2h)
- **EOD**: Recommendations complete, reporting 60% complete

**Wednesday** (8 hours):
- AM: #13-EXT Markdown reports finish (2h)
- AM: #13-EXT Export formats (1h)
- PM: #16-PARTIAL npm package setup (2h)
- PM: #16-PARTIAL API wrapper (2h)
- PM: #16-PARTIAL Result streaming (1h)
- **EOD**: Reporting complete, TypeScript bindings 70% complete

**Thursday** (8 hours):
- AM: #16-PARTIAL Result streaming finish (0.5h)
- AM: #16-PARTIAL Type definitions (1h)
- AM: #16-PARTIAL Example integration (0.5h)
- PM: Integration testing all P4 features (2h)
- PM: Documentation updates (2h)
- PM: Final bug fixes and polish (2h)
- **EOD**: All selected P4 issues complete

**Friday** (8 hours):
- AM: End-to-end testing (2h)
- AM: Performance validation (1h)
- PM: Final test coverage push (2h)
- PM: Documentation review (1h)
- PM: Construction phase retrospective (1h)
- PM: Transition phase planning (1h)
- **EOD**: Construction → Transition gate review

**Total**: 40 hours (25 estimated + 15 buffer for polish, testing, documentation)

---

## Daily Velocity Tracking

### Recommended Daily Tracking Format

Create a file `daily-status.md` or update CSV with daily actuals:

```markdown
## Week 4 - Day 1 (Monday)

**Planned**: 8 hours (#1 Docker setup, code extraction, execution harness; #2 inspect-evals setup)
**Actual**: 7.5 hours
**Completed**:
- ✅ #1 Docker sandbox setup (2h)
- ✅ #1 Code extraction (1.5h)
- ✅ #1 Execution harness (2h)
- ✅ #2 inspect-evals dependency (1h)
- ⚠️ #2 HumanEval/MBPP config (1h actual vs 1.5h estimated)

**Blockers**: None
**Notes**: Docker setup smoother than expected; HumanEval config needs more work tomorrow
**Tomorrow**: Finish #2, continue #3
```

### Velocity Metrics to Track

| Metric | Calculation | Target |
|--------|-------------|--------|
| **Story Points Velocity** | Completed issues / planned issues | ≥90% |
| **Hour Estimation Accuracy** | Actual hours / estimated hours | 0.8 - 1.2 |
| **Test Coverage Trend** | Current coverage / target coverage | ≥80% by Week 7 |
| **Bug Discovery Rate** | Bugs found / issues completed | <0.5 (less than 1 bug per 2 issues) |
| **Scope Creep** | Unplanned work / total work | <10% |

### Week-End Retrospective Template

```markdown
## Week N Retrospective

**Planned Issues**: X issues, Y hours
**Completed Issues**: X issues, Y hours
**Carry Over**: Issues carried to next week
**Test Coverage**: Current % (target %)

### What Went Well
- [Specific achievement]
- [Process that worked]

### What Could Improve
- [Challenge encountered]
- [Process gap]

### Key Decisions
- [Technical decision]
- [Scope adjustment]

### Actions for Next Week
- [Specific improvement]
- [Risk to monitor]
```

---

## Testing Strategy

### Test Coverage Targets by Component

| Component | Unit Tests | Integration Tests | Overall Target |
|-----------|------------|-------------------|----------------|
| **Scorers** | 95% | 80% | 90% |
| Code execution | 90% | 85% | 90% |
| Constraint checking | 95% | 80% | 90% |
| LLM-as-judge | 80% | 70% | 75% |
| Multi-dimensional | 85% | 75% | 80% |
| **State Management** | 95% | 90% | 95% |
| Checkpoint/resume | 95% | 95% | 95% |
| Gap detection | 90% | 85% | 90% |
| **CLI** | 85% | 80% | 85% |
| Argument parsing | 90% | N/A | 90% |
| Tier configuration | 85% | 80% | 85% |
| **Utilities** | 90% | N/A | 90% |
| Dataset loading | 90% | 70% | 85% |
| Result formatting | 95% | 75% | 90% |

### Test Types and Purposes

**Unit Tests** (90%+ coverage for critical components):
- Individual functions and classes in isolation
- Edge cases and error handling
- Fast execution (<1 second per test)
- Mock external dependencies (Ollama, Docker)

**Integration Tests** (70%+ coverage for workflows):
- End-to-end evaluation flows
- Multi-component interactions
- Real Ollama/Docker integration (where feasible)
- Slower execution (acceptable <30 seconds per test)

**Smoke Tests** (100% coverage of critical paths):
- Each CLI command
- Each benchmark tier (smoke/quick)
- Checkpoint/resume workflow
- Must complete in <3 minutes total

**Fault Injection Tests** (state management):
- Simulate crashes during evaluation
- Verify resume works with zero data loss
- Test concurrent access with locking
- Validate atomic writes

### Testing Checklist per Issue

For each issue, ensure:
- [ ] Unit tests written before implementation (TDD where applicable)
- [ ] Integration test covers end-to-end workflow
- [ ] Error paths tested (negative cases)
- [ ] Edge cases identified and tested
- [ ] Coverage meets target for that component
- [ ] Tests pass locally before PR
- [ ] CI tests pass before merge

### Test Data Management

**Public Benchmark Data**:
- Use small subsets for unit tests (5 samples)
- Use smoke tier samples for integration tests (5-10 samples)
- Full datasets only for manual validation

**Custom Test Data**:
- Create minimal fixtures for unit tests
- Use representative samples for integration tests
- Version control test data in `tests/fixtures/`

**Generated Test Data**:
- Use seeded random generation for reproducibility
- Document generation process
- Commit generated data or generation script

---

## Risk Register - Construction Phase

| ID | Risk | Impact | Prob | Week | Status | Mitigation |
|----|------|--------|------|------|--------|------------|
| C1 | Code execution sandbox vulnerabilities | HIGH | Med | 4 | Open | Docker isolation, no network, memory limits |
| C2 | LLM-as-judge variance | MED | High | 5 | Open | Temperature=0, multiple runs, validation |
| C3 | Checkpoint state corruption | HIGH | Low | 6 | Open | Atomic writes, checksums, testing |
| C4 | Parallel execution deadlocks | MED | Med | 6 | Open | File locks, process isolation |
| C5 | Test coverage below 80% | MED | Med | All | Open | Daily tracking, gate PRs |
| C6 | P4 scope creep | MED | Med | 7 | Open | Time-boxing, defer to v1.1 |
| C7 | Docker setup complexity | MED | Low | 4 | Open | Document setup, test on clean system |
| C8 | Ollama stability issues | HIGH | Med | All | Open | Retry logic, version pin, error classification |
| C9 | Custom test migration errors | MED | Med | 5 | Open | Validate 10% sample first, iterate |
| C10 | CI runtime exceeds budget | MED | Med | 6 | Open | Caching, mocking, parallel tests |

---

## Summary

This Construction phase plan delivers production-ready matric-eval through 4 focused iterations:

1. **Week 4**: Critical foundation with all public benchmarks and tiered CLI
2. **Week 5**: Advanced features including custom tests and LLM-as-judge
3. **Week 6**: Operational excellence with checkpoint/resume and CI/CD
4. **Week 7**: Selected extended features for enhanced usability

**Total Effort**: 137 estimated hours across 18-19 issues
**Available Time**: 160 hours (4 weeks × 40 hours)
**Buffer**: 23 hours (14%)

**Key Success Metrics**:
- 80%+ test coverage (Production profile requirement)
- All P1-P3 issues complete (18 issues)
- Selected P4 issues complete (2-3 issues)
- Smoke tier <2min, Quick tier <20min
- Checkpoint/resume with zero data loss
- CI/CD operational

**Gate to Transition**: Construction complete when all quality gates met, ready for end-to-end integration testing and deployment preparation.

---

**Last Updated**: 2026-01-24
**Next Review**: Daily status updates, weekly retrospectives
**Owner**: Developer
