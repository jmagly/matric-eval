# Construction Phase Gate Checklist

## Gate Metadata

| Attribute | Value |
|-----------|-------|
| **Gate Name** | Construction Phase Completion |
| **Scheduled Date** | 2026-02-28 (End of Week 7) |
| **Phase** | Construction |
| **Next Phase** | Transition |
| **Status** | PENDING |
| **Gate Facilitator** | Project Manager |
| **Required Approvers** | System Architect, Test Architect, Configuration Manager |
| **Review Meeting** | Week 7 Friday - Construction Gate Review |

## Purpose

Verify that matric-eval has successfully implemented the planned feature set with acceptable quality, performance, and documentation to proceed to the Transition phase for deployment and knowledge transfer.

## Gate Criteria Summary

- [ ] **Feature Completeness**: All P1/P2 issues complete (16/22 issues)
- [ ] **Quality Metrics**: Test coverage ≥80%, no HIGH/CRITICAL defects
- [ ] **Performance**: Smoke <2min, Quick <20min validated
- [ ] **Integration**: Ollama, Inspect AI, dataset access proven
- [ ] **Documentation**: User guides, API docs, deployment guide complete
- [ ] **Release Readiness**: Deployment pipeline functional, rollback tested
- [ ] **Transition Prep**: Handover materials ready

---

## 1. Feature Completion Matrix

### Week 4 - P1 Core Implementation (Issues #1-6)

| Issue | Title | Acceptance Criteria | Status | Notes |
|-------|-------|---------------------|--------|-------|
| #1 | Setup Python project structure | - [ ] `uv` initialized<br>- [ ] pyproject.toml configured<br>- [ ] src/matric_eval/ created<br>- [ ] CI smoke test passes | ⏳ PENDING | |
| #2 | Integrate Inspect AI framework | - [ ] Ollama model provider works<br>- [ ] Sample eval runs successfully<br>- [ ] Logging configured | ⏳ PENDING | |
| #3 | Implement HumanEval benchmark | - [ ] 164 problems loaded<br>- [ ] Code extraction handles markdown<br>- [ ] Pass@1/5/10 metrics calculated<br>- [ ] Results match matric-cli baseline | ⏳ PENDING | |
| #4 | Implement MBPP benchmark | - [ ] Function name extraction working<br>- [ ] 974 problems loaded<br>- [ ] Test assertions validated<br>- [ ] Artifact preservation verified | ⏳ PENDING | |
| #5 | Implement GSM8K benchmark | - [ ] 1,319 problems loaded<br>- [ ] Numeric answer extraction<br>- [ ] CoT evaluation supported | ⏳ PENDING | |
| #6 | Create CLI interface | - [ ] `matric-eval --tier smoke` works<br>- [ ] Model selection/filtering<br>- [ ] Output formats (JSON/CSV)<br>- [ ] Progress indicators | ⏳ PENDING | |

**P1 Gate**: 6/6 issues complete, smoke test runs end-to-end

### Week 5 - P2 Extended Features (Issues #7-10, #21-22)

| Issue | Title | Acceptance Criteria | Status | Notes |
|-------|-------|---------------------|--------|-------|
| #7 | Add ARC benchmark | - [ ] 1,172 problems loaded<br>- [ ] Multiple choice scoring<br>- [ ] Challenge/Easy split supported | ⏳ PENDING | |
| #8 | Add IFEval benchmark | - [ ] 541 prompts loaded<br>- [ ] Instruction adherence scoring<br>- [ ] Strict/Loose metrics | ⏳ PENDING | |
| #9 | Implement safe execution sandbox | - [ ] Timeout enforcement (30s default)<br>- [ ] Memory limits (512MB)<br>- [ ] Network isolation<br>- [ ] No arbitrary file access | ⏳ PENDING | |
| #10 | Add custom test framework | - [ ] JSONL dataset format defined<br>- [ ] Custom scorers supported<br>- [ ] App-specific test loading | ⏳ PENDING | |
| #21 | Implement tool calling evaluation | - [ ] Function definition format<br>- [ ] Execution validation<br>- [ ] Multi-step tool sequences | ⏳ PENDING | |
| #22 | Implement LLM-as-judge scoring | - [ ] Judge model configuration<br>- [ ] Prompt templates<br>- [ ] Score normalization | ⏳ PENDING | |

**P2 Gate**: 6/6 issues complete, custom test suite runs successfully

### Week 6 - P3 Reliability & Performance (Issues #11-14)

| Issue | Title | Acceptance Criteria | Status | Notes |
|-------|-------|---------------------|--------|-------|
| #11 | Add checkpoint/resume support | - [ ] Progress saved to disk<br>- [ ] `--resume` flag works<br>- [ ] Partial results recoverable | ⏳ PENDING | |
| #12 | Implement parallel execution | - [ ] `--parallel N` flag<br>- [ ] Thread-safe result collection<br>- [ ] Resource limits respected | ⏳ PENDING | |
| #13 | Create CI/CD pipeline | - [ ] GitHub Actions/Gitea workflow<br>- [ ] Automated smoke tests<br>- [ ] Release artifact publishing | ⏳ PENDING | |
| #14 | Add performance monitoring | - [ ] Execution time tracking<br>- [ ] Token usage metrics<br>- [ ] Cost estimation | ⏳ PENDING | |

**P3 Gate**: 4/4 issues complete, CI pipeline green

### Week 7 - P4 Integration & Polish (Selected Issues)

| Issue | Title | Acceptance Criteria | Status | Notes |
|-------|-------|---------------------|--------|-------|
| #15 | Generate model recommendations | - [ ] Categorization logic (tier-based)<br>- [ ] JSON config output<br>- [ ] Capability mapping | ⏳ PENDING | Optional |
| #16 | Create TypeScript bindings | - [ ] NPM package structure<br>- [ ] Subprocess invocation<br>- [ ] Type definitions | ⏳ PENDING | Optional |
| #17 | Add result visualization | - [ ] HTML report generation<br>- [ ] Comparison tables<br>- [ ] Charts/graphs | ⏳ PENDING | Optional |
| #18 | Implement result caching | - [ ] Cache key generation<br>- [ ] TTL configuration<br>- [ ] Cache invalidation | ⏳ PENDING | Optional |
| #19 | Add batch evaluation mode | - [ ] Multi-model execution<br>- [ ] Comparison reports<br>- [ ] Aggregated metrics | ⏳ PENDING | Optional |
| #20 | Create Rust bindings | - [ ] Crate structure<br>- [ ] FFI/subprocess interface<br>- [ ] Type safety | ⏳ PENDING | Optional |

**P4 Gate**: At least 2/6 issues complete based on priority

### Feature Completion Summary

- **Required (P1/P2)**: 12/12 issues complete
- **Highly Desired (P3)**: 4/4 issues complete
- **Optional (P4)**: ≥2/6 issues complete
- **Total**: ≥18/22 issues (82% minimum)

---

## 2. Quality Metrics Requirements

### 2.1 Test Coverage

| Component | Target | Measurement | Status |
|-----------|--------|-------------|--------|
| **Overall Coverage** | ≥80% | `pytest --cov=matric_eval` | ⏳ PENDING |
| **Critical Paths** | 100% | Code execution, scoring, sandboxing | ⏳ PENDING |
| **Benchmark Tasks** | ≥90% | HumanEval, MBPP, GSM8K, ARC, IFEval | ⏳ PENDING |
| **CLI Interface** | ≥75% | Argument parsing, error handling | ⏳ PENDING |
| **Custom Framework** | ≥85% | Dataset loading, custom scorers | ⏳ PENDING |

**Gate Criterion**: Overall ≥80% AND Critical Paths = 100%

### 2.2 Test Types

- [ ] **Unit Tests**: All core functions (tasks, scorers, solvers)
- [ ] **Integration Tests**: Ollama connectivity, dataset loading, end-to-end eval
- [ ] **Smoke Tests**: Single problem from each benchmark (<2 minutes total)
- [ ] **Performance Tests**: Quick tier baseline (<20 minutes)
- [ ] **Security Tests**: Sandbox escape attempts, resource exhaustion
- [ ] **Regression Tests**: Preserve matric-cli/matric-memory parity

### 2.3 Defect Tracking

| Severity | Target | Current | Status |
|----------|--------|---------|--------|
| **CRITICAL** | 0 open | TBD | ⏳ PENDING |
| **HIGH** | 0 open | TBD | ⏳ PENDING |
| **MEDIUM** | ≤3 open, triaged with mitigation | TBD | ⏳ PENDING |
| **LOW** | Documented in backlog | TBD | ⏳ PENDING |

**Gate Criterion**: No CRITICAL/HIGH defects; MEDIUM defects have workarounds documented

### 2.4 Code Quality

- [ ] **Linting**: `ruff check` passes with no errors
- [ ] **Type Checking**: `mypy` passes (strict mode)
- [ ] **Formatting**: `ruff format` applied consistently
- [ ] **Complexity**: No functions >50 lines (exceptions documented)
- [ ] **Documentation**: All public APIs have docstrings
- [ ] **Security Scan**: `bandit` or `safety` passes with no HIGH findings

---

## 3. Performance Validation

### 3.1 Performance Thresholds

| Tier | Target Duration | Problem Count | Models Tested | Status |
|------|----------------|---------------|---------------|--------|
| **Smoke** | <2 minutes | 1 per benchmark (5 total) | llama3.2:3b | ⏳ PENDING |
| **Quick** | <20 minutes | ~50 total | llama3.2:3b | ⏳ PENDING |
| **Full** | <4 hours | All datasets | Top 3 models | ⏳ PENDING |

**Gate Criterion**: Smoke and Quick tiers meet targets on reference hardware

### 3.2 Resource Constraints

- [ ] **Memory**: Peak usage <4GB for Quick tier
- [ ] **Disk**: Results <100MB per full evaluation
- [ ] **Network**: Graceful degradation if Ollama unreachable
- [ ] **CPU**: Parallel execution scales linearly up to 4 cores

### 3.3 Baseline Validation

- [ ] **HumanEval**: Results match matric-cli within 5% for llama3.2:3b
- [ ] **MBPP**: Function name extraction 100% accurate on sample
- [ ] **GSM8K**: Numeric extraction handles decimals, percentages, fractions
- [ ] **Reproducibility**: Seeded runs produce identical results

---

## 4. Integration Validation Checklist

### 4.1 External Dependencies

- [ ] **Ollama Integration**
  - [ ] Model discovery via `/api/tags`
  - [ ] Generation via `/api/generate` with streaming
  - [ ] Size filtering (skip models >12GB by default)
  - [ ] Error handling (model not found, OOM, timeout)

- [ ] **Inspect AI Framework**
  - [ ] Task definition syntax validated
  - [ ] Solver chain execution verified
  - [ ] Scorer integration tested
  - [ ] Logging and metrics collection working

- [ ] **Dataset Access**
  - [ ] Reads from `/home/roctinam/data/evals/` successfully
  - [ ] Handles missing datasets gracefully
  - [ ] Custom dataset path override supported

### 4.2 Cross-Repository Compatibility

- [ ] **matric-cli Migration Path**
  - [ ] Can read existing eval results for comparison
  - [ ] Produces compatible JSON output format
  - [ ] Preserves artifact structure (generatedCode, etc.)

- [ ] **matric-memory Integration**
  - [ ] Custom test format matches Rust expectations
  - [ ] Can consume recommendations JSON
  - [ ] Tool calling evaluation aligns with matric-memory use cases

### 4.3 Platform Support

- [ ] **Linux**: Primary development/CI environment (Ubuntu 22.04+)
- [ ] **macOS**: Developer workstations (Python 3.11+ via Homebrew)
- [ ] **Docker**: Containerized execution tested
- [ ] **Python Versions**: 3.11, 3.12 validated

---

## 5. Documentation Requirements

### 5.1 User Documentation

- [ ] **README.md**: Overview, quick start, installation
- [ ] **docs/user-guide.md**: Complete CLI reference
  - [ ] All flags and options documented
  - [ ] Tier selection guidance
  - [ ] Model filtering examples
  - [ ] Output format specifications
- [ ] **docs/benchmarks.md**: Benchmark descriptions
  - [ ] Dataset sources and licenses
  - [ ] Scoring methodologies
  - [ ] Interpretation guidance
- [ ] **docs/custom-tests.md**: Custom test creation guide
  - [ ] JSONL format specification
  - [ ] Scorer interface
  - [ ] Integration examples

### 5.2 Developer Documentation

- [ ] **ARCHITECTURE.md**: System design, data flow, extension points
- [ ] **CONTRIBUTING.md**: Setup, testing, PR guidelines
- [ ] **API Reference**: Auto-generated from docstrings (Sphinx/MkDocs)
- [ ] **docs/development.md**: Local development workflow
  - [ ] Dataset setup instructions
  - [ ] Ollama configuration
  - [ ] Testing strategies

### 5.3 Operational Documentation

- [ ] **docs/deployment.md**: Installation and configuration
  - [ ] System requirements
  - [ ] Dependency installation (`uv sync`)
  - [ ] Environment variables
  - [ ] First-run validation
- [ ] **docs/troubleshooting.md**: Common issues and solutions
  - [ ] Ollama connection failures
  - [ ] Dataset not found errors
  - [ ] Sandbox timeout handling
  - [ ] Memory/disk issues
- [ ] **CHANGELOG.md**: Release notes for v0.1.0

### 5.4 Project Documentation

- [ ] **PLANNING.md**: Maintained and current
- [ ] **ROADMAP.md**: Updated with actuals
- [ ] **.aiwg/ Documentation**: All SDLC artifacts complete
  - [ ] Configuration management plan
  - [ ] Test plan
  - [ ] Deployment plan
  - [ ] Gate checklists

---

## 6. Release Readiness Criteria

### 6.1 Build & Packaging

- [ ] **PyPI Package**: Built with `uv build`, installable via `pip install matric-eval`
- [ ] **Version**: Semver applied (v0.1.0)
- [ ] **Dependencies**: Pinned in `uv.lock`, ranges in `pyproject.toml`
- [ ] **Entry Points**: `matric-eval` CLI command registered
- [ ] **Metadata**: License, authors, repository URL, keywords

### 6.2 Deployment Pipeline

- [ ] **CI/CD Workflow**: Automated build/test/publish on tag push
- [ ] **Smoke Tests**: Run on every commit (2min timeout)
- [ ] **Quick Tests**: Run on PR merge (20min timeout)
- [ ] **Release Artifacts**: Wheel and sdist published to PyPI or Gitea package registry
- [ ] **Docker Image**: Optional containerized version built and tagged

### 6.3 Rollback & Recovery

- [ ] **Rollback Plan**: Previous version (matric-cli/matric-memory evals) remain functional
- [ ] **Data Migration**: No breaking changes to result formats
- [ ] **Config Compatibility**: Backwards compatibility verified
- [ ] **Failure Modes**: Graceful degradation documented

### 6.4 Security & Compliance

- [ ] **Dependency Scan**: No known HIGH/CRITICAL vulnerabilities
- [ ] **Code Scan**: `bandit` security linter passes
- [ ] **Secrets Management**: No hardcoded credentials, uses environment variables
- [ ] **License Compliance**: All dependencies reviewed (MIT/Apache-2.0 compatible)

---

## 7. Transition Phase Preparation

### 7.1 Handover Materials

- [ ] **User Training Materials**: Quick start guide, video walkthrough (optional)
- [ ] **Administrator Guide**: Installation, configuration, monitoring
- [ ] **Support Runbook**: Common issues, escalation paths
- [ ] **Knowledge Transfer Session**: Scheduled for Week 8

### 7.2 Production Readiness

- [ ] **Production Environment**: Defined (developer workstations, CI runners)
- [ ] **Monitoring**: Logging strategy defined (file-based, structured logs)
- [ ] **Backup Strategy**: Result archival process documented
- [ ] **Support Model**: GitHub Issues/Gitea for bug reports

### 7.3 Post-Deployment Validation Plan

- [ ] **Smoke Test Plan**: Run on first production use
- [ ] **User Acceptance Test**: Key stakeholders validate workflows
- [ ] **Performance Baseline**: Capture initial metrics for comparison
- [ ] **Feedback Mechanism**: Issue templates, feedback form

---

## 8. Gate Decision Criteria

### GO Decision Requirements (ALL must be met)

1. **Feature Completeness**: P1/P2 issues (12/12) complete + P3 (4/4) complete
2. **Quality**: Test coverage ≥80%, no CRITICAL/HIGH defects
3. **Performance**: Smoke <2min, Quick <20min validated
4. **Documentation**: User guide, deployment guide, API reference complete
5. **Integration**: Ollama, Inspect AI, dataset access proven
6. **Release**: CI/CD pipeline functional, v0.1.0 package built

### CONDITIONAL GO Requirements

If any criterion missed, document:
- **Gap Description**: What is incomplete?
- **Risk Assessment**: Impact on Transition phase
- **Mitigation Plan**: How will gap be closed?
- **Acceptance**: Approver sign-off on mitigation

### NO GO Triggers (Any ONE blocks gate)

1. **Critical Defect**: Unresolved HIGH/CRITICAL bug
2. **Core Feature Missing**: P1 issue incomplete (issues #1-6)
3. **Integration Failure**: Cannot connect to Ollama or load datasets
4. **Performance Miss**: Smoke tier >5 minutes (>2x target)
5. **Security Issue**: Unmitigated sandbox escape or vulnerability

---

## 9. Approval Sign-Off

| Role | Name | Decision | Date | Signature | Comments |
|------|------|----------|------|-----------|----------|
| **Project Manager** | | ⏳ PENDING | | | |
| **System Architect** | | ⏳ PENDING | | | |
| **Test Architect** | | ⏳ PENDING | | | |
| **Configuration Manager** | | ⏳ PENDING | | | |

---

## 10. Status Tracking

### Current Status: PENDING

**Target Date**: 2026-02-28
**Last Updated**: 2026-01-24
**Updated By**: Project Manager (Claude Code)

### Weekly Progress Checkpoints

| Week | Date | Focus | Completion % | Risks |
|------|------|-------|--------------|-------|
| Week 4 | 2026-02-07 | P1 issues #1-6 | TBD | Initial integration risks |
| Week 5 | 2026-02-14 | P2 issues #7-10, #21-22 | TBD | Custom test complexity |
| Week 6 | 2026-02-21 | P3 issues #11-14 | TBD | CI/CD infrastructure |
| Week 7 | 2026-02-28 | P4 polish, gate prep | TBD | Documentation completeness |

### Known Risks

1. **Inspect AI Learning Curve**: Mitigation - Prototype in Week 4
2. **Dataset Access Issues**: Mitigation - Validate paths in issue #1
3. **Sandbox Security**: Mitigation - Dedicated security testing in issue #9
4. **Performance Regression**: Mitigation - Baseline validation in Week 5

---

## Next Steps After Gate Approval

1. **Transition Phase Launch**: Week 8 begins
2. **Production Deployment**: Install on CI runners, developer workstations
3. **User Onboarding**: Training sessions, documentation distribution
4. **Monitoring**: Collect usage metrics, gather feedback
5. **Support**: Monitor Gitea issues, respond to bug reports
6. **Retrospective**: Schedule lessons learned session (Week 9)

---

## References

- **PLANNING.md**: Architecture and technology decisions
- **ROADMAP.md**: Timeline and milestones
- **.aiwg/plans/test-plan.md**: Quality assurance strategy
- **.aiwg/plans/deployment-plan.md**: Release and installation procedures
- **.aiwg/gates/gate-elaboration.md**: Previous gate checklist
- **Gitea Issues**: [roctinam/devops#5](https://git.integrolabs.net/roctinam/devops/issues/5)

---

**Document Control**
Version: 1.0
Created: 2026-01-24
Last Modified: 2026-01-24
Owner: Project Manager
Classification: Internal
