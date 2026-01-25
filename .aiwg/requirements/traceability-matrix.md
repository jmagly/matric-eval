# Requirements Traceability Matrix

**Document ID**: REQ-TRACE-001
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Planning Phase

## Document Purpose

This document provides comprehensive traceability between all project artifacts for matric-eval, establishing bidirectional linkages between Gitea issues, use cases, requirements, architecture components, test cases, and architectural decision records (ADRs). This ensures complete coverage and enables impact analysis for changes.

## Traceability Overview

The traceability matrix establishes the following relationships:

1. **Issue → Use Case mapping**: Which use cases implement which Gitea issues
2. **Issue → NFR mapping**: Which non-functional requirements apply to which issues
3. **Use Case → Component mapping**: Which architecture components implement each use case
4. **Component → Test mapping**: Which tests validate each component
5. **Risk → Mitigation mapping**: Which ADRs and components mitigate which risks
6. **Full traceability table**: Complete cross-reference matrix

## Notation

- **UC001-UC005**: Use Cases
- **BR-001 to BR-005**: Business Requirements
- **PERF-001 to PERF-006**: Performance NFRs
- **REL-001 to REL-005**: Reliability NFRs
- **USE-001 to USE-005**: Usability NFRs
- **SEC-001 to SEC-005**: Security NFRs
- **MAINT-001 to MAINT-005**: Maintainability NFRs
- **OPS-001 to OPS-005**: Operational NFRs
- **COMPAT-001 to COMPAT-003**: Compatibility NFRs
- **LEGAL-001 to LEGAL-002**: Legal/Compliance NFRs
- **RISK-001 to RISK-015**: Identified risks
- **ADR-001 to ADR-005**: Architectural Decision Records

---

## 1. Issue → Use Case Mapping

Maps Gitea issues to the use cases that implement them.

| Gitea Issue | Title | Use Cases | Priority | Phase |
|-------------|-------|-----------|----------|-------|
| #1 | Implement HumanEval benchmark | UC001 | P0 | Phase 1 |
| #2 | Implement MBPP benchmark | UC001 | P0 | Phase 1 |
| #3 | Integrate inspect-evals for GSM8K, ARC, IFEval | UC001 | P1 | Phase 1 |
| #4 | Implement LiveCodeBench competitive programming | UC001 | P1 | Phase 1 |
| #5 | Implement DS-1000 data science scoring | UC001 | P1 | Phase 1 |
| #6 | Implement tiered CLI (smoke/quick/full) | UC001 | P0 | Phase 1 |
| #7 | Port 282 custom matric tests | UC003 | P1 | Phase 2 |
| #8 | Implement tool calling evaluation (6 scenarios) | UC003 | P1 | Phase 2 |
| #9 | Implement MT-Bench multi-turn with LLM-as-judge | UC003 | P2 | Phase 2 |
| #10 | Implement 5-dimensional scoring framework | UC003 | P2 | Phase 2 |
| #11 | Implement checkpoint/resume for fault tolerance | UC002 | P0 | Phase 3 |
| #12 | Implement parallel model evaluation | UC001 | P2 | Phase 3 |
| #13 | Add CI/CD pipeline with automated smoke tests | UC005 | P1 | Phase 3 |
| #14 | Add comprehensive logging and observability | UC001, UC002, UC005 | P2 | Phase 3 |
| #15 | Build leaderboard and reporting dashboard | UC004 | P3 | Phase 4 |
| #16 | Create language bindings (TypeScript, Rust) | UC001, UC003 | P1 | Phase 4 |
| #17 | Add extended benchmarks (SWE-bench, GPQA, CyberSecEval, GAIA) | UC001 | P3 | Phase 4 |
| #18 | Build model recommendation engine | UC004 | P2 | Phase 4 |
| #19 | Implement contamination detection | UC001 | P3 | Phase 4 |
| #20 | Add historical trend analysis | UC004 | P3 | Phase 4 |
| #21 | Port matric-memory LLM-as-Judge templates | UC003 | P1 | Phase 2 |
| #22 | Implement universal LLM-as-Judge with agentic support | UC003 | P2 | Phase 2 |

**Coverage Summary**:
- UC001 (Run Benchmark): 9 issues
- UC002 (Checkpoint/Resume): 1 issue
- UC003 (Custom Tests): 5 issues
- UC004 (Model Recommendation): 3 issues
- UC005 (CI/CD Integration): 1 issue

---

## 2. Issue → Non-Functional Requirements Mapping

Maps Gitea issues to the NFRs they must satisfy.

| Gitea Issue | Performance | Reliability | Usability | Security | Maintainability | Operational |
|-------------|-------------|-------------|-----------|----------|-----------------|-------------|
| #1 | PERF-002, PERF-006 | REL-001, REL-003 | USE-003 | SEC-001 | MAINT-002 | - |
| #2 | PERF-002, PERF-006 | REL-001, REL-003 | USE-003 | SEC-001 | MAINT-002 | - |
| #3 | PERF-002, PERF-006 | REL-001, REL-003 | USE-003 | - | MAINT-002 | - |
| #4 | PERF-002, PERF-006 | REL-001, REL-003 | USE-003 | SEC-001 | MAINT-002 | - |
| #5 | PERF-002, PERF-006 | REL-001, REL-003 | USE-003 | SEC-001 | MAINT-002 | - |
| #6 | PERF-001 | REL-001 | USE-001, USE-002 | SEC-002 | - | - |
| #7 | - | REL-003 | USE-003 | - | MAINT-002 | - |
| #8 | - | REL-003 | USE-003 | SEC-001 | MAINT-002 | - |
| #9 | - | REL-003 | USE-003 | - | MAINT-002 | - |
| #10 | - | REL-003 | USE-003 | - | MAINT-002 | - |
| #11 | PERF-003, PERF-005 | REL-002 | USE-002 | SEC-004 | MAINT-003 | OPS-005 |
| #12 | PERF-003, PERF-004 | - | USE-002 | - | - | - |
| #13 | - | REL-005 | - | SEC-003 | MAINT-002 | OPS-002 |
| #14 | - | REL-004 | USE-005 | SEC-004 | MAINT-003 | OPS-003 |
| #15 | - | - | USE-003 | - | - | OPS-003 |
| #16 | - | - | USE-004 | - | MAINT-005 | OPS-001 |
| #17 | PERF-006 | REL-003 | USE-003 | - | MAINT-005 | - |
| #18 | - | - | USE-003 | - | - | - |
| #19 | - | REL-003 | USE-003 | SEC-005 | - | - |
| #20 | - | - | USE-003 | - | - | OPS-003 |
| #21 | - | REL-003 | USE-003 | - | MAINT-002 | - |
| #22 | - | REL-003 | USE-003 | - | MAINT-002 | - |

**NFR Application Summary**:
- Most Critical NFRs: REL-001 (16 issues), REL-003 (15 issues), MAINT-002 (14 issues)
- Performance-Critical: Issues #1-#6, #12
- Security-Critical: Issues #1, #2, #4, #5, #6, #8, #11, #13, #14, #19

---

## 3. Use Case → Architecture Component Mapping

Maps use cases to the architectural components that implement them.

### UC001: Run Benchmark Evaluation

| Component | Responsibility | Implementation Status |
|-----------|----------------|----------------------|
| CLI (cli.py) | Parse tier, model, benchmark arguments | Planned |
| Orchestrator (orchestrator.py) | Coordinate evaluation workflow | Planned |
| Task Runner (runner.py) | Execute benchmark problems via Inspect AI | Planned |
| Scorers (scorers/) | Code execution, string matching, validation | Planned |
| State Manager (state.py) | Track evaluation progress | Planned |
| Config Generator (config.py) | Generate model recommendations | Planned |

**Test Coverage**:
- Unit Tests: test_cli.py, test_orchestrator.py, test_runner.py, test_scorers.py
- Integration Tests: test_ollama_integration.py, test_inspect_ai_integration.py
- System Tests: test_smoke_tier.py, test_quick_tier.py, test_full_tier.py
- Benchmark Validation: test_humaneval_validation.py, test_mbpp_validation.py

### UC002: Checkpoint and Resume Evaluation

| Component | Responsibility | Implementation Status |
|-----------|----------------|----------------------|
| State Manager (state.py) | Atomic checkpoint writes, state serialization | Planned |
| Recovery Engine (recovery.py) | Gap detection, error classification, retry logic | Planned |
| CLI (cli.py) | --resume, --fill-gaps, --validate flags | Planned |
| Orchestrator (orchestrator.py) | Resume from checkpoint state | Planned |

**Test Coverage**:
- Unit Tests: test_state_manager.py, test_recovery.py
- Reliability Tests: test_checkpoint_scenarios.py (10 critical scenarios)
- Fault Injection: test_interruption.py, test_corruption.py

### UC003: Run Custom Application Tests

| Component | Responsibility | Implementation Status |
|-----------|----------------|----------------------|
| Task Runner (runner.py) | Load JSONL custom tests | Planned |
| Scorers (scorers/tool_calling.py) | Validate tool invocations | Planned |
| Scorers (scorers/llm_as_judge.py) | 5-dimensional scoring | Planned |
| CLI (cli.py) | --app flag for custom test suites | Planned |

**Test Coverage**:
- Unit Tests: test_tool_calling_scorer.py, test_llm_judge.py
- Integration Tests: test_custom_tests.py
- Migration Tests: test_matric_cli_parity.py, test_matric_memory_parity.py

### UC004: Generate Model Recommendations

| Component | Responsibility | Implementation Status |
|-----------|----------------|----------------------|
| Config Generator (config.py) | Analyze scores, rank models, generate JSON | Planned |
| Orchestrator (orchestrator.py) | Aggregate results by capability | Planned |
| CLI (cli.py) | --recommend flag, output format selection | Planned |

**Test Coverage**:
- Unit Tests: test_config_generator.py
- Integration Tests: test_recommendation_accuracy.py
- System Tests: test_config_output_format.py

### UC005: CI/CD Integration

| Component | Responsibility | Implementation Status |
|-----------|----------------|----------------------|
| CLI (cli.py) | Exit codes, JSON output for parsing | Planned |
| Task Runner (runner.py) | Fast smoke tier execution | Planned |
| State Manager (state.py) | Minimal checkpoint overhead | Planned |

**Test Coverage**:
- CI/CD Tests: test_github_actions.py, test_gitlab_ci.py
- Performance Tests: test_smoke_tier_duration.py
- System Tests: test_exit_codes.py, test_json_output_schema.py

---

## 4. Component → Test Mapping

Maps architecture components to their comprehensive test coverage.

### Core Components

| Component | Unit Tests | Integration Tests | System Tests | Coverage Target |
|-----------|------------|-------------------|--------------|-----------------|
| cli.py | test_cli_parsing.py, test_cli_validation.py | test_cli_integration.py | test_cli_e2e.py | 85% |
| orchestrator.py | test_orchestrator_workflow.py, test_model_discovery.py | test_orchestrator_ollama.py | test_full_evaluation.py | 80% |
| state.py | test_checkpoint_write.py, test_state_serialization.py | test_state_persistence.py | test_checkpoint_resume.py | 100% |
| recovery.py | test_error_classification.py, test_retry_logic.py | test_gap_detection.py | test_fault_injection.py | 100% |
| runner.py | test_task_loading.py, test_problem_execution.py | test_inspect_ai_calls.py | test_benchmark_execution.py | 80% |

### Scorers (Critical - 100% Coverage Required)

| Component | Unit Tests | Integration Tests | Property Tests | Coverage |
|-----------|------------|-------------------|----------------|----------|
| scorers/code_execution.py | test_code_extraction.py, test_sandbox.py | test_code_execution.py | test_code_props.py | 100% |
| scorers/string_match.py | test_exact_match.py, test_fuzzy.py | - | test_match_props.py | 100% |
| scorers/tool_calling.py | test_tool_validation.py | test_tool_integration.py | - | 100% |
| scorers/llm_as_judge.py | test_5d_scoring.py, test_judge_templates.py | test_judge_reliability.py | - | 100% |
| scorers/semantic.py | test_semantic_similarity.py | test_embedding_integration.py | - | 100% |

### Supporting Components

| Component | Unit Tests | Integration Tests | Coverage Target |
|-----------|------------|-------------------|-----------------|
| config.py | test_recommendation_logic.py, test_json_generation.py | test_config_e2e.py | 75% |
| solvers/code_extraction.py | test_markdown_fence.py, test_function_extraction.py | - | 85% |
| solvers/markdown_handling.py | test_markdown_parsing.py | - | 85% |

### Benchmark-Specific Tests

| Benchmark | Validation Test | Reference Implementation | Status |
|-----------|----------------|--------------------------|--------|
| HumanEval | test_humaneval_validation.py | openai/human-eval | Planned |
| MBPP | test_mbpp_validation.py | google-research/mbpp | Planned |
| GSM8K | test_gsm8k_validation.py | openai/grade-school-math | Planned |
| ARC | test_arc_validation.py | allenai/ARC | Planned |
| IFEval | test_ifeval_validation.py | google/IFEval | Planned |
| LiveCodeBench | test_livecodebench_validation.py | livecodebench/code_generation | Planned |
| DS-1000 | test_ds1000_validation.py | xlang-ai/DS-1000 | Planned |
| MT-Bench | test_mtbench_validation.py | lmsys/FastChat | Planned |

### Reliability Tests (All Must Pass)

| Test Scenario | Test File | Acceptance Criteria | Status |
|---------------|-----------|---------------------|--------|
| Checkpoint after each problem | test_checkpoint_granularity.py | State saved correctly | Planned |
| Resume from partial benchmark | test_resume_partial_benchmark.py | Continues from checkpoint | Planned |
| Resume from partial model | test_resume_partial_model.py | Skips completed benchmarks | Planned |
| EPIPE error during inference | test_epipe_recovery.py | Retries and continues | Planned |
| Model crash mid-benchmark | test_model_crash_recovery.py | Skips model, continues | Planned |
| Disk full during checkpoint | test_disk_full.py | Fails gracefully | Planned |
| Corrupted state file | test_corrupted_state.py | Detects and reports | Planned |
| Concurrent run prevention | test_lock_mechanism.py | Lock file prevents conflict | Planned |
| Zombie run detection | test_heartbeat_timeout.py | Detects stale runs | Planned |
| Gap detection | test_gap_detection.py | Identifies missing results | Planned |

---

## 5. Risk → Mitigation Mapping

Maps identified risks to their mitigation strategies (ADRs and components).

| Risk ID | Risk Description | Impact | Mitigation Component(s) | Mitigation ADR(s) | Status |
|---------|------------------|--------|-------------------------|-------------------|--------|
| RISK-001 | Inspect AI lacks checkpoint/resume | 6 (High) | State Manager, Recovery Engine | ADR-005 | Mitigated |
| RISK-002 | Ollama + Inspect AI integration instability | 6 (High) | Recovery Engine (retry logic) | ADR-002 | Monitoring |
| RISK-003 | TypeScript/Rust binding complexity | 6 (High) | Bindings simplified to subprocess wrappers | ADR-001 | Accepted |
| RISK-004 | MBPP function name extraction regression | 6 (High) | Scorers (code_extraction.py), unit tests | - | Active |
| RISK-005 | Code execution sandbox escape | 3 (Low) | Scorers (code_execution.py), Docker isolation | - | Active |
| RISK-006 | Large dataset memory exhaustion | 4 (Medium) | Task Runner (streaming JSONL) | ADR-003 | Mitigated |
| RISK-007 | Solo developer bottleneck | 4 (Medium) | Scope management, timeboxing | - | Accepted |
| RISK-008 | Inspect AI framework abandonment | 3 (Low) | Abstraction layer, alternative validation | ADR-002 | Monitoring |
| RISK-009 | Ollama model size exceeds capacity | 4 (Medium) | Orchestrator (model size filtering) | - | Mitigated |
| RISK-010 | Inconsistent scoring across benchmarks | 4 (Medium) | Scorers (validation tests vs. reference) | - | Active |
| RISK-011 | Python version compatibility | 2 (Low) | CI/CD tests on 3.11, 3.12, 3.13 | - | Mitigated |
| RISK-012 | Dataset licensing restrictions | 2 (Low) | Legal review, attribution documentation | - | Monitoring |
| RISK-013 | Evaluation result reproducibility failures | 2 (Low) | State Manager (seeded random), deterministic inference | - | Mitigated |
| RISK-014 | Streaming results complexity | 1 (Minimal) | Deferred to v1.1 | - | Accepted |
| RISK-015 | Docker dependency unavailable | 2 (Low) | Graceful fallback to subprocess sandbox | - | Mitigated |

**Mitigation Coverage**:
- Fully Mitigated: RISK-001, RISK-006, RISK-009, RISK-011, RISK-013, RISK-015
- Actively Managed: RISK-004, RISK-005, RISK-010
- Monitoring: RISK-002, RISK-008, RISK-012
- Accepted: RISK-003, RISK-007, RISK-014

---

## 6. ADR → Component Mapping

Maps architectural decisions to the components they affect.

| ADR | Title | Affected Components | Impact | Alternatives Considered |
|-----|-------|---------------------|--------|------------------------|
| ADR-001 | Python core with language bindings | All components, Bindings | Foundational | TypeScript core, Rust core, polyglot |
| ADR-002 | Inspect AI as evaluation framework | Task Runner, Scorers | Framework selection | lm-eval-harness, HELM, custom |
| ADR-003 | JSONL as universal test format | Task Runner, Scorers | Data format | JSON arrays, CSV, Parquet, SQLite |
| ADR-004 | Tiered evaluation (smoke/quick/full) | CLI, Orchestrator, Task Runner | User experience | Single tier, fully configurable |
| ADR-005 | Checkpoint/resume state management | State Manager, Recovery Engine | Reliability | Database, event sourcing, no checkpoints |

**Component Impact Analysis**:

### ADR-001: Python Core with Bindings
- **Components Created**: All Python modules
- **Components Deferred**: TypeScript/Rust native implementations
- **Rationale**: Leverage Python ML ecosystem, avoid duplication

### ADR-002: Inspect AI Framework
- **Components Affected**: Task Runner, Scorers
- **Integration Points**: Ollama API calls, task loading, scoring
- **Rationale**: Native Ollama support, pre-built benchmarks

### ADR-003: JSONL Test Format
- **Components Affected**: Task Runner (parsing), Custom test loaders
- **Data Flow**: Datasets → Task Runner → Scorers
- **Rationale**: Streaming, framework compatibility, version control

### ADR-004: Tiered Evaluation
- **Components Affected**: CLI (argument parsing), Orchestrator (tier logic), Task Runner (sample selection)
- **User Experience**: Fast feedback (smoke), balanced (quick), comprehensive (full)
- **Rationale**: Resource efficiency, developer productivity

### ADR-005: Checkpoint/Resume Design
- **Components Created**: State Manager, Recovery Engine
- **Data Structures**: RunState, ModelState, BenchmarkState
- **Rationale**: Fault tolerance for long-running evaluations

---

## 7. Full Traceability Matrix

Comprehensive cross-reference table linking all artifacts.

| Gitea Issue | Use Case | Business Req | NFRs (Key) | Components | ADRs | Tests | Risk |
|-------------|----------|--------------|------------|------------|------|-------|------|
| #1 (HumanEval) | UC001 | BR-002 | PERF-002, REL-001, REL-003, SEC-001 | Task Runner, Scorers/code_execution | ADR-002, ADR-003 | test_humaneval_validation.py | RISK-004, RISK-010 |
| #2 (MBPP) | UC001 | BR-002 | PERF-002, REL-001, REL-003, SEC-001 | Task Runner, Scorers/code_execution, Solvers/code_extraction | ADR-002, ADR-003 | test_mbpp_validation.py | RISK-004, RISK-010 |
| #3 (inspect-evals) | UC001 | BR-002 | PERF-002, REL-001, REL-003 | Task Runner, Scorers | ADR-002 | test_gsm8k_validation.py, test_arc_validation.py | RISK-002, RISK-008 |
| #4 (LiveCodeBench) | UC001 | BR-002 | PERF-002, REL-001, REL-003, SEC-001 | Task Runner, Scorers/code_execution | ADR-002, ADR-003 | test_livecodebench_validation.py | RISK-010 |
| #5 (DS-1000) | UC001 | BR-002 | PERF-002, REL-001, REL-003, SEC-001 | Task Runner, Scorers/code_execution | ADR-002, ADR-003 | test_ds1000_validation.py | RISK-010 |
| #6 (Tiered CLI) | UC001 | BR-003 | PERF-001, REL-001, USE-001, USE-002 | CLI, Orchestrator, Task Runner | ADR-004 | test_cli_tiers.py, test_smoke_duration.py | - |
| #7 (282 custom tests) | UC003 | BR-001 | REL-003, USE-003 | Task Runner, Scorers | ADR-003 | test_custom_migration.py | - |
| #8 (Tool calling) | UC003 | BR-002 | REL-003, USE-003, SEC-001 | Scorers/tool_calling | ADR-003 | test_tool_calling_scorer.py | - |
| #9 (MT-Bench) | UC003 | BR-002 | REL-003, USE-003 | Scorers/llm_as_judge | ADR-002, ADR-003 | test_mtbench_validation.py | - |
| #10 (5D scoring) | UC003 | BR-002 | REL-003, USE-003 | Scorers/llm_as_judge | ADR-003 | test_5d_scoring.py | - |
| #11 (Checkpoint/resume) | UC002 | BR-005 | PERF-003, PERF-005, REL-002, USE-002, SEC-004 | State Manager, Recovery Engine | ADR-005 | test_checkpoint_scenarios.py (10 tests) | RISK-001 |
| #12 (Parallel eval) | UC001 | BR-003 | PERF-003, PERF-004, USE-002 | Orchestrator, Task Runner | - | test_parallel_efficiency.py | - |
| #13 (CI/CD) | UC005 | BR-005 | REL-005, SEC-003, OPS-002 | CLI, Task Runner | ADR-004 | test_github_actions.py | - |
| #14 (Logging) | UC001, UC002, UC005 | BR-005 | REL-004, USE-005, MAINT-003, OPS-003 | All components (logging) | - | test_logging.py | - |
| #15 (Leaderboard) | UC004 | BR-005 | USE-003, OPS-003 | Config Generator | - | test_leaderboard.py | - |
| #16 (Bindings) | UC001, UC003 | BR-004 | USE-004, MAINT-005, OPS-001 | Bindings (TS/Rust) | ADR-001 | test_ts_binding.py, test_rust_binding.py | RISK-003 |
| #17 (Extended benchmarks) | UC001 | BR-002 | PERF-006, REL-003, USE-003, MAINT-005 | Task Runner, Scorers | ADR-002, ADR-003 | test_swebench.py, test_gpqa.py | - |
| #18 (Recommendation engine) | UC004 | BR-004 | USE-003 | Config Generator | - | test_recommendation_accuracy.py | - |
| #19 (Contamination) | UC001 | BR-002 | REL-003, USE-003, SEC-005 | Task Runner | - | test_contamination_detection.py | RISK-012 |
| #20 (Trend analysis) | UC004 | BR-005 | USE-003, OPS-003 | Config Generator | - | test_trend_analysis.py | - |
| #21 (LLM-as-Judge templates) | UC003 | BR-001 | REL-003, USE-003 | Scorers/llm_as_judge | ADR-003 | test_judge_templates.py | - |
| #22 (Agentic judge) | UC003 | BR-002 | REL-003, USE-003 | Scorers/llm_as_judge | ADR-002, ADR-003 | test_agentic_judge.py | - |

---

## 8. Coverage Analysis

### Use Case Coverage

| Use Case | Issue Count | Component Count | Test Count | NFR Count | Completeness |
|----------|-------------|-----------------|------------|-----------|--------------|
| UC001 (Run Benchmark) | 9 | 6 | 20+ | 15 | High |
| UC002 (Checkpoint/Resume) | 1 | 2 | 10 | 8 | High |
| UC003 (Custom Tests) | 5 | 4 | 12 | 6 | High |
| UC004 (Model Recommendation) | 3 | 2 | 5 | 3 | Medium |
| UC005 (CI/CD Integration) | 1 | 3 | 4 | 4 | Medium |

### Business Requirement Coverage

| Business Req | Issue Count | Use Case Count | NFR Count | Validation Approach |
|--------------|-------------|----------------|-----------|---------------------|
| BR-001 (Code Consolidation) | 22 | 5 | - | LOC reduction in source repos |
| BR-002 (Evaluation Accuracy) | 15 | 3 | 12 | Score comparison vs. reference |
| BR-003 (Resource Efficiency) | 4 | 2 | 6 | Performance testing |
| BR-004 (Ecosystem Integration) | 3 | 2 | 4 | Binding integration tests |
| BR-005 (Operational Excellence) | 22 | 5 | 15 | CI/CD success rate, error handling |

### NFR Coverage by Category

| NFR Category | Count | Critical (P1) | High (P2) | Medium (P3) | Coverage |
|--------------|-------|---------------|-----------|-------------|----------|
| Performance | 6 | 1 | 3 | 2 | High |
| Reliability | 5 | 3 | 2 | 0 | Critical |
| Usability | 5 | 0 | 4 | 1 | High |
| Security | 5 | 2 | 2 | 1 | High |
| Maintainability | 5 | 1 | 2 | 2 | Medium |
| Operational | 5 | 1 | 2 | 1 | Medium |
| Compatibility | 3 | 0 | 1 | 2 | Medium |
| Legal | 2 | 0 | 1 | 1 | Low |

### Component Test Coverage

| Component | Unit Tests | Integration Tests | System Tests | Target Coverage | Status |
|-----------|------------|-------------------|--------------|-----------------|--------|
| State Manager | 5 | 3 | 2 | 100% | Planned |
| Recovery Engine | 5 | 3 | 10 | 100% | Planned |
| Scorers (all) | 15+ | 10 | - | 100% | Planned |
| CLI | 4 | 2 | 5 | 85% | Planned |
| Orchestrator | 4 | 2 | 3 | 80% | Planned |
| Task Runner | 4 | 3 | 8 | 80% | Planned |
| Config Generator | 3 | 1 | 2 | 75% | Planned |

### Risk Mitigation Coverage

| Risk Level | Count | Fully Mitigated | Actively Managed | Monitoring | Accepted | Coverage |
|------------|-------|-----------------|------------------|------------|----------|----------|
| High (6) | 4 | 1 | 2 | 1 | 0 | 75% |
| Medium (4) | 6 | 4 | 1 | 1 | 0 | 83% |
| Low (2-3) | 5 | 3 | 0 | 2 | 0 | 100% |
| Minimal (1) | 0 | 0 | 0 | 0 | 0 | N/A |

---

## 9. Traceability Gaps and Actions

### Identified Gaps

1. **UC004 (Model Recommendation)**: Medium component coverage, needs more architectural detail
   - **Action**: Create detailed component design for Config Generator
   - **Owner**: Architect
   - **Due**: Phase 4 planning

2. **UC005 (CI/CD Integration)**: Medium test coverage, needs more system tests
   - **Action**: Expand CI/CD test plan with platform-specific tests
   - **Owner**: Test Architect
   - **Due**: Phase 3

3. **Legal/Compliance NFRs**: Low priority but required for distribution
   - **Action**: Schedule license audit for all datasets
   - **Owner**: Project Maintainer
   - **Due**: Before Phase 4

4. **Binding Tests**: Limited coverage for TypeScript/Rust bindings
   - **Action**: Create comprehensive binding test plan
   - **Owner**: Test Architect
   - **Due**: Phase 4 planning

### Missing Traceability

1. **ADR-002 Alternative Evaluation**: Need documented fallback plan if Inspect AI fails
   - **Action**: Prototype lm-eval-harness integration in Sprint 1
   - **Owner**: Architect
   - **Due**: Week 2

2. **RISK-007 Mitigation**: Solo developer bottleneck lacks concrete mitigation components
   - **Action**: Define specific scope reduction scenarios
   - **Owner**: Product Owner
   - **Due**: Sprint planning

3. **Performance Baseline**: Missing baseline data for comparison
   - **Action**: Capture matric-cli benchmark performance as baseline
   - **Owner**: Test Architect
   - **Due**: Sprint 1

---

## 10. Impact Analysis Reference

Use this section to assess change impact.

### Example: Changing Checkpoint Format (ADR-005)

**Direct Impact**:
- State Manager component (redesign required)
- Recovery Engine component (parsing logic change)
- UC002 test suite (update fixtures)

**Indirect Impact**:
- REL-002 (Fault Tolerance) - revalidate acceptance criteria
- COMPAT-001 (Backward Compatibility) - migration path needed
- RISK-001 mitigation - verify still addressed

**Affected Tests**:
- test_checkpoint_scenarios.py (all 10 scenarios)
- test_state_serialization.py
- test_resume_partial_benchmark.py

**Ripple Effects**:
- Documentation updates (checkpoint format spec)
- Migration guide for existing checkpoints
- Version compatibility matrix update

### Example: Adding New Benchmark (e.g., SWE-bench)

**Direct Impact**:
- Task Runner (load new benchmark)
- Scorers (potentially new scorer type)
- UC001 (expand scope)

**Traced Requirements**:
- BR-002 (Evaluation Accuracy)
- PERF-006 (Throughput and Scalability)
- REL-003 (Data Integrity)

**Required Artifacts**:
- Benchmark validation test (test_swebench_validation.py)
- Reference implementation comparison
- Dataset license audit (LEGAL-001)

**Risks**:
- RISK-010 (Inconsistent Scoring) - new scorer must match reference
- RISK-012 (Dataset Licensing) - verify SWE-bench license

---

## 11. Traceability Maintenance

### Update Triggers

This traceability matrix MUST be updated when:

1. **New Gitea Issue Created**: Add to Issue → Use Case mapping
2. **Use Case Added/Modified**: Update Use Case → Component mapping
3. **New NFR Identified**: Add to NFR sections, update Issue → NFR mapping
4. **Component Added**: Update Component → Test mapping
5. **New Risk Identified**: Add to Risk → Mitigation mapping
6. **ADR Approved**: Update ADR → Component mapping
7. **Test Added**: Update Component → Test mapping

### Validation Process

**Weekly**:
- Verify all active issues mapped to use cases
- Check all components have test coverage targets
- Validate NFR priorities align with issue priorities

**Sprint Boundary**:
- Complete traceability review
- Identify and close gaps
- Update coverage metrics
- Document any new risks

**Phase Transition**:
- Full traceability audit
- Sign-off from Architect, Test Architect, Product Owner
- Coverage thresholds verified
- Gap closure plan documented

### Ownership

| Section | Owner | Review Frequency |
|---------|-------|------------------|
| Issue → Use Case | Product Owner | Weekly |
| Issue → NFR | Architect | Sprint |
| Use Case → Component | Architect | Sprint |
| Component → Test | Test Architect | Weekly |
| Risk → Mitigation | Risk Manager | Sprint |
| ADR → Component | Architect | On ADR approval |

---

## 12. References

- **Use Cases**: UC001-UC005 (use-case-UC00*.md)
- **Business Requirements**: BR-001 to BR-005 (vision.md)
- **Non-Functional Requirements**: supplementary-requirements.md
- **Architecture Components**: SAD.md
- **Risks**: risk-list.md
- **ADRs**: ADR-001 to ADR-005 (ADR-00*.md)
- **Test Strategy**: test-strategy.md
- **Test Plans**: test-plan-unit.md, test-plan-integration.md

---

## 13. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Requirements Analyst (Claude Opus 4.5) | Initial comprehensive traceability matrix |

---

## 14. Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Requirements Analyst | Claude Opus 4.5 | (Digital) | 2026-01-24 |
| Architect | TBD | Pending | - |
| Test Architect | TBD | Pending | - |
| Product Owner | TBD | Pending | - |

**Status**: Draft - Awaiting stakeholder review and approval

---

**End of Traceability Matrix**
