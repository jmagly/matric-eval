# Test Strategy - matric-eval

**Project**: matric-eval - Consolidated Model Evaluation Framework
**Profile**: Production (Requires 80%+ coverage)
**Status**: Planning Phase
**Last Updated**: 2026-01-24

## Document Purpose

This document defines the comprehensive test strategy for matric-eval, establishing mandatory quality gates and coverage thresholds that MUST be met before phase transitions. Testing is a blocking requirement, not optional.

## Executive Summary

matric-eval is a mission-critical component that validates LLM performance across the matric ecosystem. Given its critical role and Production profile, the following are NON-NEGOTIABLE:

- **80% minimum code coverage** across all Python modules
- **100% coverage** for checkpoint/resume state management (critical reliability requirement)
- **100% coverage** for all custom scorers (correctness is paramount)
- **Blocking test gates** at PR merge, release, and production deployment
- **Zero tolerance** for flaky tests in critical paths

## Test Coverage Matrix (Mandatory)

| Test Level | Coverage Target | Blocking | Owner | Automation | Execution Time |
|------------|-----------------|----------|-------|------------|----------------|
| Unit | 80% lines, 75% branches | Yes - PR merge | Developer | CI-required | <5 min |
| Integration | 100% Ollama endpoints | Yes - PR merge | Test Engineer | CI-required | <15 min |
| System | 100% CLI commands | Yes - Release | QA | CI-required | <30 min |
| Benchmark Validation | 100% public benchmarks | Yes - Release | Test Engineer | CI-required | <60 min |
| Performance | Baseline established | Yes - Release | Performance Engineer | Scheduled daily | <120 min |
| Reliability | 100% checkpoint scenarios | Yes - Release | Reliability Engineer | CI-required | <20 min |
| Security | Code execution sandbox | Yes - Release | Security | Scheduled weekly | <10 min |
| Bindings | 100% TS/Rust IPC | Yes - Release | Developer | CI-required | <5 min |

## Test Levels

### 1. Unit Tests (L1)

**Scope**: Individual functions, classes, and modules in isolation.

**Coverage Requirement**: 80% line coverage, 75% branch coverage

**Critical Components** (100% coverage required):
- `/src/matric_eval/state/checkpoint.py` - Checkpoint state management
- `/src/matric_eval/state/recovery.py` - Recovery logic
- `/src/matric_eval/scorers/` - All custom scorers
- `/src/matric_eval/extractors/` - Code/response extraction
- `/src/matric_eval/validators/` - Validation logic

**Testing Approach**:
- pytest framework with pytest-cov for coverage
- Mock all external dependencies (Ollama, file I/O, network)
- Parameterized tests for edge cases
- Property-based testing for scorers (hypothesis library)

**Entry Criteria**:
- [ ] Module exists with public API
- [ ] Dependencies are mockable
- [ ] Expected behavior documented

**Exit Criteria**:
- [ ] 80% line coverage achieved (100% for critical components)
- [ ] All edge cases tested
- [ ] No hardcoded values (use fixtures)
- [ ] Fast execution (<5 seconds per module)

### 2. Integration Tests (L2)

**Scope**: Component interactions, external service integration.

**Coverage Requirement**: 100% of integration points

**Critical Integration Points**:
- Ollama API (model loading, inference, error handling)
- Inspect AI framework (task execution, scoring)
- File system (state persistence, checkpoint writes)
- CLI to core library integration

**Testing Approach**:
- Real Ollama instance (controlled model)
- Temporary file systems for state management
- Docker containers for isolated environments
- Pytest fixtures for setup/teardown

**Entry Criteria**:
- [ ] Unit tests passing for integrated components
- [ ] Test environment provisioned (Ollama, datasets)
- [ ] Test data available

**Exit Criteria**:
- [ ] All integration points tested
- [ ] Error scenarios validated (connection failures, timeouts)
- [ ] Cleanup verified (no leaked resources)
- [ ] Deterministic results (no flakiness)

### 3. System Tests (L3)

**Scope**: End-to-end CLI workflows, complete evaluation runs.

**Coverage Requirement**: 100% of CLI commands and flags

**Test Scenarios**:
- Smoke tier evaluation (5 problems per benchmark)
- Quick tier evaluation (75 problems per benchmark)
- Full tier evaluation (subset for CI)
- Resume interrupted run
- Fill gaps in incomplete run
- Validate run completeness
- Model-specific re-run
- Benchmark-specific re-run

**Testing Approach**:
- Black-box CLI testing via subprocess
- Golden file comparison for output validation
- Regression test suite for config recommendations
- Performance benchmarking (execution time)

**Entry Criteria**:
- [ ] Integration tests passing
- [ ] CLI fully implemented
- [ ] Test datasets available
- [ ] Baseline results captured

**Exit Criteria**:
- [ ] All CLI commands execute successfully
- [ ] Output format validated
- [ ] Performance within acceptable bounds
- [ ] Error messages are actionable

### 4. Benchmark Validation Tests (L4)

**Scope**: Verify public benchmark implementations match reference implementations.

**Coverage Requirement**: 100% of supported public benchmarks

**Benchmarks to Validate**:
- HumanEval (164 problems) - validate against openai/human-eval reference
- MBPP (974 problems) - validate against google-research/mbpp
- GSM8K (1,319 problems) - validate against openai/grade-school-math
- ARC (1,172 problems) - validate against allenai/ARC
- IFEval (541 problems) - validate constraint checking
- LiveCodeBench (1,055 problems, release_v6) - validate against livecodebench/code_generation
- DS-1000 (1,000 problems) - validate against xlang-ai/DS-1000
- MTBench (80 questions) - validate multi-turn handling

**Testing Approach**:
- Smoke test subset (5 problems) against known results
- Validate scoring logic matches reference
- Check prompt formatting matches reference
- Verify metric calculation (pass@k, accuracy, etc.)

**Entry Criteria**:
- [ ] Benchmark implemented in matric-eval
- [ ] Reference implementation available
- [ ] Reference results documented

**Exit Criteria**:
- [ ] Smoke test results match reference (+/- 5% for model variance)
- [ ] Scoring logic verified
- [ ] Edge cases handled (malformed output, timeouts)

### 5. Performance Tests (L5)

**Scope**: Execution time, memory usage, throughput.

**Coverage Requirement**: Baseline established for all tiers

**Performance Metrics**:
- Smoke tier: <2 minutes total
- Quick tier: <20 minutes total
- Problem throughput: >5 problems/second (mocked LLM)
- State write overhead: <100ms per checkpoint
- Memory usage: <2GB for quick tier
- Resume overhead: <5 seconds

**Testing Approach**:
- Benchmark with mocked LLM (eliminate model variance)
- Profile with py-spy or cProfile
- Memory profiling with memory_profiler
- Continuous regression tracking

**Entry Criteria**:
- [ ] System tests passing
- [ ] Profiling tools configured
- [ ] Baseline hardware specs documented

**Exit Criteria**:
- [ ] Baseline established
- [ ] No memory leaks detected
- [ ] Performance regression alerts configured
- [ ] Optimization opportunities documented

### 6. Reliability Tests (L6)

**Scope**: Checkpoint/resume, error recovery, graceful degradation.

**Coverage Requirement**: 100% of recovery scenarios

**Critical Scenarios** (MUST ALL PASS):
1. **Checkpoint after each problem** - Verify state saved
2. **Resume from partial benchmark** - Continue where left off
3. **Resume from partial model** - Skip completed benchmarks
4. **EPIPE error during inference** - Retry and continue
5. **Model crash mid-benchmark** - Skip model, continue next
6. **Disk full during checkpoint** - Fail gracefully with error
7. **Corrupted state file** - Detect and report
8. **Concurrent run prevention** - Lock file mechanism
9. **Zombie run detection** - Heartbeat timeout
10. **Gap detection** - Identify missing results

**Testing Approach**:
- Fault injection (kill processes, fill disk, corrupt files)
- Chaos engineering (random failures)
- State machine verification
- Idempotency validation (re-run produces same results)

**Entry Criteria**:
- [ ] State management implemented
- [ ] Checkpoint logic complete
- [ ] Error handling implemented

**Exit Criteria**:
- [ ] All 10 scenarios passing
- [ ] No data loss in any scenario
- [ ] Recovery time <5 seconds
- [ ] Clear error messages for unrecoverable failures

### 7. Security Tests (L7)

**Scope**: Code execution sandbox, input validation, dependency scanning.

**Coverage Requirement**: 100% of code execution paths

**Security Concerns**:
- Arbitrary code execution in generated LLM code
- Prompt injection in test prompts
- Path traversal in checkpoint directories
- Resource exhaustion (CPU, memory, disk)
- Dependency vulnerabilities

**Testing Approach**:
- Static analysis (bandit, safety)
- Sandbox escape attempts
- Resource limit enforcement
- Input fuzzing
- Dependency scanning (pip-audit)

**Entry Criteria**:
- [ ] Sandbox implementation complete
- [ ] Security tooling configured
- [ ] Threat model documented

**Exit Criteria**:
- [ ] No critical/high vulnerabilities
- [ ] Sandbox escapes blocked
- [ ] Resource limits enforced
- [ ] Input validation complete

### 8. Binding Tests (L8)

**Scope**: TypeScript and Rust bindings for language integration.

**Coverage Requirement**: 100% of binding API surface

**Test Scenarios**:
- TypeScript subprocess spawning
- Rust subprocess spawning
- JSON serialization/deserialization
- Error propagation
- Progress streaming
- Cancellation handling

**Testing Approach**:
- End-to-end tests in each language
- Mock Python backend for unit tests
- Contract testing (JSON schema validation)
- Cross-platform testing (Linux, macOS, Windows)

**Entry Criteria**:
- [ ] Bindings implemented
- [ ] Schema defined
- [ ] Error codes documented

**Exit Criteria**:
- [ ] All binding APIs tested
- [ ] Error scenarios handled
- [ ] Documentation validated
- [ ] Cross-platform verified

## Test Types

### Functional Tests

**Purpose**: Verify correct behavior according to specifications.

**Coverage**: All requirements from requirements documents.

**Traceability**: Each test MUST link to a requirement ID.

**Examples**:
- Scorer produces correct pass/fail for HumanEval problem
- CLI --resume flag continues from checkpoint
- Gap detection identifies missing results

### Non-Functional Tests

#### Performance

**Metrics**:
- Execution time per tier
- Throughput (problems/second)
- State write latency
- Resume overhead

**Thresholds**:
- Smoke: <2 min
- Quick: <20 min
- State write: <100ms
- Resume: <5s

#### Reliability

**Metrics**:
- Checkpoint success rate (100% required)
- Recovery success rate (100% required)
- Mean time to recovery (MTTR < 5s)

**Thresholds**:
- Zero data loss
- 100% idempotent operations

#### Usability

**Metrics**:
- CLI error message clarity
- Documentation completeness
- API discoverability

**Validation**:
- User testing with developers from matric-cli/matric-memory
- Error message review (actionable + clear)

#### Security

**Metrics**:
- Sandbox escape attempts blocked (100%)
- Vulnerability count (0 critical/high)
- Resource limit enforcement (100%)

**Validation**:
- Security scan passing
- Penetration testing (manual)

## Test Data Management

### Public Benchmark Data

**Location**: `/home/roctinam/data/evals/`

**Management**:
- Versioned datasets (symlinks with version tags)
- Checksums for integrity validation
- Local caching strategy
- Download automation

**Datasets**:
- humaneval (164 problems)
- mbpp (974 problems)
- gsm8k (1,319 problems)
- arc (1,172 problems)
- ifeval (541 problems)
- livecodebench (1,055 problems, release_v6)
- ds1000 (1,000 problems)
- mtbench (80 questions)

### Custom Test Data

**Location**: `/home/roctinam/dev/matric-eval/datasets/custom/`

**Format**: JSONL (one test case per line)

**Schema**:
```json
{
  "id": "test-001",
  "capability": "tool-calling",
  "prompt": "User request text",
  "expected": {
    "tools": ["read_file", "write_file"],
    "outcome": "success"
  },
  "metadata": {
    "difficulty": "medium",
    "source": "matric-cli"
  }
}
```

**Versioning**: Git-tracked, semantic versioning for major changes.

### Test Fixtures

**Location**: `/home/roctinam/dev/matric-eval/tests/fixtures/`

**Content**:
- Mock Ollama responses
- Sample checkpoint state files
- Expected validation outputs
- Configuration files

**Management**: Pytest fixtures, version controlled.

## Test Environment Requirements

### Development Environment

**Python**: 3.11+
**Package Manager**: uv
**Testing Framework**: pytest 8.0+
**Coverage Tool**: pytest-cov

**Required Services**:
- Ollama (local instance, small model for tests)
- File system (temp directories for state)

**Environment Variables**:
```bash
OLLAMA_API_BASE=http://localhost:11434
MATRIC_EVAL_TEST_MODE=true
MATRIC_EVAL_DATA_DIR=/tmp/matric-eval-test
```

### CI Environment

**Platform**: GitHub Actions / GitLab CI
**Container**: Python 3.11 slim
**Services**: Ollama (Docker container)

**Required Resources**:
- CPU: 4 cores
- Memory: 8GB
- Disk: 20GB
- Network: Access to Ollama API

**Execution**:
- PR: Unit + Integration tests
- Main: Unit + Integration + System tests
- Nightly: All test levels

### Staging Environment

**Purpose**: Pre-production validation with full dataset.

**Configuration**: Production-like hardware and data.

**Tests**: Full tier evaluation with all benchmarks.

## Quality Gates

### Phase Transition Gates

#### Inception → Elaboration

- [ ] Test strategy approved
- [ ] Coverage targets defined
- [ ] Test environment requirements documented

#### Elaboration → Construction

- [ ] Test plan approved for all levels
- [ ] CI pipeline configured
- [ ] Test data available
- [ ] Baseline coverage established (may be 0% for greenfield)

#### Construction → Transition

- [ ] 80% code coverage achieved
- [ ] 100% coverage for critical components
- [ ] All reliability scenarios passing
- [ ] Benchmark validation complete
- [ ] No critical/high defects open

#### Transition → Production

- [ ] Full tier evaluation passing
- [ ] Performance baseline validated
- [ ] Security scan passed
- [ ] Documentation complete
- [ ] Operational runbook validated

### Pull Request Merge Gate (BLOCKING)

**Required**:
- [ ] All unit tests passing
- [ ] Coverage maintained or increased (no decrease)
- [ ] Integration tests passing
- [ ] No new linter warnings
- [ ] Test added for new functionality

**Automated**:
- pytest run
- coverage report
- lint check

**Manual Review**:
- Test quality (not just coverage)
- Edge cases covered

### Release Gate (BLOCKING)

**Required**:
- [ ] All test levels passing
- [ ] Performance within thresholds
- [ ] Reliability scenarios validated
- [ ] Security scan passed
- [ ] Benchmark validation complete
- [ ] Bindings tested

**Sign-off Required**:
- Test Architect
- Security Engineer
- Product Owner

### Production Deployment Gate (BLOCKING)

**Required**:
- [ ] Staging environment validated
- [ ] Operational runbook tested
- [ ] Rollback plan documented
- [ ] Monitoring configured
- [ ] Alerts configured

**Sign-off Required**:
- Deployment Manager
- Operations Engineer

## Test Execution Strategy

### Continuous Integration (CI)

**Trigger**: Every PR commit

**Tests**:
- Unit tests (all)
- Integration tests (all)
- Lint and type checking
- Coverage report

**Time Budget**: <15 minutes

**Failure Action**: Block merge

### Continuous Deployment (CD)

**Trigger**: Merge to main

**Tests**:
- Unit + Integration + System
- Smoke tier end-to-end
- Performance regression

**Time Budget**: <30 minutes

**Failure Action**: Block deployment

### Nightly Build

**Trigger**: Scheduled (2 AM UTC)

**Tests**:
- Full test suite
- Quick tier end-to-end
- Benchmark validation
- Performance profiling
- Security scan

**Time Budget**: <2 hours

**Failure Action**: Alert team

### Release Candidate

**Trigger**: Manual (pre-release)

**Tests**:
- Full tier end-to-end
- All reliability scenarios
- Cross-platform validation
- Binding integration tests

**Time Budget**: <4 hours

**Failure Action**: Block release

## Coverage Targets (Minimum Thresholds)

| Component | Line Coverage | Branch Coverage | Mutation Score |
|-----------|---------------|-----------------|----------------|
| **Critical** |
| Checkpoint/Resume | 100% | 100% | 80% |
| Scorers | 100% | 100% | 80% |
| Validators | 100% | 95% | 75% |
| **Core** |
| CLI | 85% | 80% | N/A |
| Tasks | 80% | 75% | N/A |
| Extractors | 85% | 80% | 70% |
| **Supporting** |
| Config | 75% | 70% | N/A |
| Utils | 80% | 75% | N/A |
| Bindings | 90% | 85% | N/A |
| **Overall** | 80% | 75% | 70% |

**Mutation Testing**: Using mutmut or cosmic-ray for critical components.

## Anti-Patterns to Flag (ESCALATE)

1. **"We'll add tests later"** - Tests MUST be written with code (TDD)
2. **"Coverage is aspirational"** - Coverage is a minimum requirement
3. **"Skip flaky tests"** - Flaky tests MUST be fixed, not ignored
4. **"Manual testing is sufficient"** - Automation enables CI/CD
5. **"Integration tests are expensive"** - They prevent production bugs
6. **"100% coverage is impossible"** - It's mandatory for critical components
7. **"Coverage doesn't equal quality"** - True, but it's a minimum bar
8. **"Mocking is too complex"** - Required for unit test isolation

## Success Criteria

The Test Architect has succeeded when:

1. **Coverage Goals Met**:
   - [ ] 80% overall code coverage
   - [ ] 100% coverage for critical components
   - [ ] No coverage decrease sprint-over-sprint

2. **Quality Gates Enforced**:
   - [ ] PR merge blocked without tests
   - [ ] Release blocked without validation
   - [ ] Production deployment requires sign-off

3. **Reliability Validated**:
   - [ ] All 10 checkpoint/resume scenarios passing
   - [ ] Zero data loss in fault injection tests
   - [ ] Recovery time <5 seconds

4. **Benchmark Correctness**:
   - [ ] All 8 public benchmarks validated
   - [ ] Results match reference implementations
   - [ ] Scoring logic verified

5. **Performance Acceptable**:
   - [ ] Smoke tier <2 minutes
   - [ ] Quick tier <20 minutes
   - [ ] No memory leaks

6. **Developer Experience**:
   - [ ] Tests run fast (<15 min in CI)
   - [ ] Clear failure messages
   - [ ] Easy to write new tests

## Deliverables

This strategy produces the following deliverables:

1. **Test Strategy Document** (this document)
2. **Test Plan - Unit** (test-plan-unit.md)
3. **Test Plan - Integration** (test-plan-integration.md)
4. **Test Plan - System** (TBD)
5. **Test Plan - Reliability** (TBD)
6. **Test Coverage Reports** (automated, weekly)
7. **Quality Dashboard** (automated, real-time)

## References

| Principle | Source | Reference |
|-----------|--------|-----------|
| 80% Coverage Minimum | Google Testing Blog | [Code Coverage Goal: 80% and No Less](https://testing.googleblog.com/2010/07/code-coverage-goal-80-and-no-less.html) |
| Test Pyramid | Martin Fowler | [Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html) |
| Mutation Testing | IEEE ICST | [Mutation Testing Workshop](https://conf.researchr.org/home/icst-2024/mutation-2024) |
| Flaky Test Impact | Google | [Flaky Tests at Google](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html) |
| Test Automation | ISTQB CTAL-TAE | [Test Automation Engineering](https://istqb.org/certifications/certified-tester-advanced-level-test-automation-engineering-ctal-tae-v2-0/) |

## Appendix A: Test Traceability Matrix

Requirements will be mapped to test cases using the following format:

| Requirement ID | Test Level | Test Case | Status | Coverage |
|----------------|------------|-----------|--------|----------|
| REQ-001 | Unit | test_checkpoint_save | Pass | 100% |
| REQ-002 | Integration | test_ollama_inference | Pass | 100% |
| REQ-003 | System | test_resume_interrupted | Pass | 100% |

## Appendix B: Risk-Based Test Prioritization

High-risk areas requiring extra test coverage:

1. **Checkpoint/Resume** - Data loss risk
2. **Code Execution** - Security risk
3. **Scorers** - Correctness risk
4. **Ollama Integration** - Reliability risk
5. **State Management** - Data integrity risk

## Appendix C: Test Maintenance

**Test Code Quality Standards**:
- Tests are code - apply same quality standards
- DRY principle - use fixtures and utilities
- Clear naming - test name describes scenario
- Isolated - no dependencies between tests
- Fast - unit tests <1s, integration <5s

**Test Refactoring**:
- When code changes, update tests
- When tests are duplicated, refactor
- When tests are slow, optimize
- When tests are flaky, fix immediately

**Test Deprecation**:
- Mark obsolete tests with @pytest.mark.skip + reason
- Remove after 2 sprints if not re-enabled
- Document removal in changelog
