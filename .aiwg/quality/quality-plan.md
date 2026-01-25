# Quality Assurance Plan - matric-eval

**Project**: matric-eval - Consolidated Model Evaluation Framework
**Profile**: Production (80%+ test coverage required)
**Status**: Planning Phase
**Last Updated**: 2026-01-24

---

## Executive Summary

This Quality Assurance Plan establishes the comprehensive quality framework for matric-eval, a mission-critical component that validates LLM performance across the matric ecosystem. Given the Production profile requirements and the critical nature of evaluation correctness, quality assurance is a blocking requirement throughout the SDLC.

**Quality Commitment**:
- Zero tolerance for defects in scoring logic (100% correctness required)
- 80% minimum test coverage overall, 100% for critical components
- All changes subject to code review before merge
- Quality gates enforced at every phase transition
- Continuous improvement through defect analysis and retrospectives

**Key Metrics**:
- Test Coverage: 80%+ overall, 100% critical paths
- Code Review: 100% of changes reviewed before merge
- Defect Density: <0.5 defects per KLOC in production
- Mean Time to Recovery: <5 seconds for checkpoint/resume
- Performance: smoke <2min, quick <20min, full <2hrs

---

## Quality Objectives

### 1. Functional Correctness

**Objective**: Ensure evaluation results are accurate and reproducible.

**Measurable Goals**:
- 100% of public benchmarks validated against reference implementations
- Score variance <5% when re-running with same seed
- Zero scoring bugs in production (defect-free scorers)
- 100% of custom tests produce deterministic results

**Success Criteria**:
- All HumanEval, MBPP, GSM8K results match reference within statistical margin
- Reproducible sampling with seeded random (EVAL_SEED)
- Code execution sandbox prevents false positives/negatives
- Format validation scorers achieve 100% precision and recall

### 2. Reliability and Resilience

**Objective**: System recovers gracefully from failures without data loss.

**Measurable Goals**:
- 100% checkpoint success rate (no data loss)
- Resume from interruption with <1% duplicate work
- Gap detection accuracy: 100% (no missed incomplete results)
- Mean Time to Recovery (MTTR): <5 seconds

**Success Criteria**:
- All 10 reliability scenarios pass (see test-strategy.md)
- Zero data loss in fault injection tests
- Atomic writes prevent corrupted state files
- Clear error messages for unrecoverable failures

### 3. Performance Efficiency

**Objective**: Evaluations complete within acceptable time bounds.

**Measurable Goals**:
- Smoke tier: <2 minutes total execution
- Quick tier: <20 minutes total execution
- Full tier: <2 hours for 8 benchmarks
- State checkpoint overhead: <100ms per write

**Success Criteria**:
- Performance baselines established and monitored
- No memory leaks (constant memory usage over time)
- Regression detection alerts configured
- Resource utilization optimized (CPU, memory, disk)

### 4. Security Assurance

**Objective**: Safe execution of untrusted LLM-generated code.

**Measurable Goals**:
- 100% sandbox escape attempts blocked
- Zero critical/high security vulnerabilities
- Resource limits enforced (timeout, memory, disk)
- Input validation prevents injection attacks

**Success Criteria**:
- Code execution isolated in Docker containers
- Security scans passing (bandit, safety, pip-audit)
- Penetration testing validates sandbox integrity
- Dependency vulnerabilities patched within 7 days

### 5. Maintainability and Documentation

**Objective**: Code is understandable, extensible, and well-documented.

**Measurable Goals**:
- 100% of public APIs documented with docstrings
- Architecture decision records (ADRs) for all major choices
- Code complexity: cyclomatic complexity <10 per function
- Documentation completeness: user docs, API docs, architecture docs

**Success Criteria**:
- New developers can run smoke tests within 30 minutes
- All modules have README explaining purpose and usage
- ADRs provide rationale for framework choices
- API documentation auto-generated from docstrings

### 6. Usability and Developer Experience

**Objective**: Tool is easy to use and provides clear feedback.

**Measurable Goals**:
- Error messages are actionable (include fix suggestions)
- CLI help text covers all use cases
- Time to first evaluation: <5 minutes after install
- API discoverability: 90%+ of common tasks documented

**Success Criteria**:
- User testing with matric-cli/matric-memory developers
- Error message review ensures clarity
- CLI follows conventions (--help, --version, etc.)
- Examples provided for all tier configurations

---

## Quality Metrics and Targets

### Code Quality Metrics

| Metric | Target | Measurement | Frequency | Owner |
|--------|--------|-------------|-----------|-------|
| Test Coverage (Overall) | 80%+ | pytest-cov | Every PR | Developer |
| Test Coverage (Critical) | 100% | pytest-cov | Every PR | Developer |
| Branch Coverage | 75%+ | pytest-cov | Every PR | Developer |
| Mutation Score | 70%+ | mutmut | Weekly | Test Architect |
| Cyclomatic Complexity | <10/function | radon | Every PR | Developer |
| Code Duplication | <3% | pylint | Every PR | Developer |
| Type Coverage | 95%+ | mypy strict | Every PR | Developer |
| Linter Warnings | 0 | ruff | Every PR | Developer |

### Defect Metrics

| Metric | Target | Measurement | Frequency | Owner |
|--------|--------|-------------|-----------|-------|
| Defect Density | <0.5/KLOC | Manual tracking | Sprint | QA Engineer |
| Critical Defects | 0 in production | Issue tracker | Daily | Product Owner |
| Mean Time to Detect (MTTD) | <1 day | Issue timestamp | Sprint | QA Engineer |
| Mean Time to Fix (MTTF) | <3 days | Issue resolution | Sprint | Developer |
| Defect Escape Rate | <5% | Production vs. Pre-prod | Release | QA Engineer |
| Reopen Rate | <10% | Issue history | Sprint | Developer |

### Performance Metrics

| Metric | Target | Measurement | Frequency | Owner |
|--------|--------|-------------|-----------|-------|
| Smoke Tier Execution | <2 min | CI timing | Every PR | Developer |
| Quick Tier Execution | <20 min | Nightly build | Daily | Performance Eng |
| Full Tier Execution | <2 hrs | Manual run | Weekly | Performance Eng |
| State Checkpoint Latency | <100ms | Profiling | Weekly | Developer |
| Memory Usage (Quick) | <2GB | Memory profiler | Weekly | Performance Eng |
| Resume Overhead | <5s | Integration tests | Every PR | Developer |

### Reliability Metrics

| Metric | Target | Measurement | Frequency | Owner |
|--------|--------|-------------|-----------|-------|
| Checkpoint Success Rate | 100% | Integration tests | Every PR | Developer |
| Recovery Success Rate | 100% | Fault injection | Weekly | Reliability Eng |
| Mean Time to Recovery | <5s | Integration tests | Every PR | Developer |
| Data Loss Events | 0 | Fault injection | Weekly | Reliability Eng |
| Idempotency Violations | 0 | Integration tests | Every PR | Developer |

### Security Metrics

| Metric | Target | Measurement | Frequency | Owner |
|--------|--------|-------------|-----------|-------|
| Critical Vulnerabilities | 0 | pip-audit, bandit | Every PR | Security |
| High Vulnerabilities | 0 | pip-audit, bandit | Every PR | Security |
| Sandbox Escape Attempts | 0 successful | Security tests | Weekly | Security |
| Resource Limit Bypasses | 0 | Security tests | Weekly | Security |
| Dependency Age | <90 days | pip list | Weekly | Developer |

---

## Review Processes

### 1. Code Review Process

**Scope**: All code changes, including tests, documentation, and configuration.

**Required Reviewers**:
- Minimum: 1 peer reviewer (solo developer: self-review with checklist)
- Critical components (scorers, state management): 2 reviewers (or extensive self-review)
- Security changes: Security engineer review (or security checklist)

**Review Checklist**:
See `code-review-checklist.md` for comprehensive review criteria.

**Review Timeline**:
- Small changes (<100 LOC): 1 business day
- Medium changes (100-500 LOC): 2 business days
- Large changes (>500 LOC): 3 business days or split into smaller PRs

**Review Outcomes**:
- **Approved**: Code can be merged
- **Approved with Comments**: Code can be merged, address comments in follow-up
- **Changes Requested**: Code must be revised before merge
- **Blocked**: Critical issues prevent merge

**Self-Review Protocol (Solo Developer)**:
1. Complete code-review-checklist.md systematically
2. Run full test suite locally
3. Review own diff line-by-line (GitHub PR view)
4. Sleep on it - review again next day for critical changes
5. Document review completion in PR description

### 2. Design Review Process

**Trigger**: New architectural decision or significant design change.

**Artifacts Required**:
- Architecture Decision Record (ADR) or design document
- Component diagram (if applicable)
- Interface contracts (API signatures)
- Test strategy for new components

**Review Criteria**:
- Alignment with existing architecture (SAD)
- Performance implications assessed
- Security considerations addressed
- Testability designed in
- Complexity justification provided

**Design Review Checklist**:
- [ ] ADR template completed with all sections
- [ ] Alternatives considered and documented
- [ ] Trade-offs clearly articulated
- [ ] Impact on existing components assessed
- [ ] Migration path defined (if breaking change)
- [ ] Test strategy outlined
- [ ] Documentation plan included

**Approval Authority**:
- Solo Developer: Self-approval with documented rationale
- Major changes: Stakeholder review (matric-cli/matric-memory teams)

### 3. Documentation Review Process

**Scope**: User documentation, API documentation, architecture docs, ADRs.

**Review Criteria**:
- **Accuracy**: Documentation matches implementation
- **Completeness**: All use cases covered
- **Clarity**: Understandable by target audience
- **Examples**: Concrete examples provided
- **Maintainability**: Easy to update as code changes

**Documentation Types**:

| Type | Audience | Review Frequency | Tools |
|------|----------|------------------|-------|
| User Docs | End users (CLI) | Every feature change | Markdown, CLI --help |
| API Docs | Developers (bindings) | Every API change | Docstrings, Sphinx |
| Architecture Docs | Maintainers | Every design change | ADRs, SAD |
| Test Docs | QA Engineers | Every test change | Test plan docs |

**Documentation Standards**:
- Use clear, concise language
- Include code examples for all APIs
- Keep examples tested (doctest or CI validation)
- Update docs in same PR as code changes
- Version documentation with releases

### 4. Requirement Review Process

**Trigger**: New feature request or requirement change.

**Review Criteria**:
- **Necessity**: Is this requirement essential?
- **Clarity**: Is the requirement unambiguous?
- **Testability**: Can we verify this requirement?
- **Feasibility**: Is this achievable with current resources?
- **Traceability**: Does it map to business goals?

**Requirement Sources**:
- matric-cli integration needs
- matric-memory integration needs
- Lessons learned from previous evaluations
- Framework capabilities (Inspect AI)
- Performance/security constraints

**Approval Process**:
1. Document requirement in `.aiwg/requirements/`
2. Link to use case or business requirement
3. Define acceptance criteria
4. Estimate effort and priority
5. Stakeholder approval (if external-facing)

---

## Quality Gates by Phase

### Inception Phase (Week 1) - COMPLETED

**Entry Criteria**:
- Project charter approved
- Initial scope defined

**Exit Criteria** (ALL MET):
- [x] Test strategy approved
- [x] Coverage targets defined (80%+ overall)
- [x] Quality metrics established
- [x] Risk register includes quality risks
- [x] Architecture direction proposed (SAD + ADRs)

**Quality Deliverables**:
- [x] Test Strategy Document
- [x] Quality Plan (this document)
- [x] Code Review Checklist
- [x] Definition of Done

**Gate Decision**: PASSED - Proceed to Elaboration

---

### Elaboration Phase (Week 2-3)

**Entry Criteria**:
- Inception gate passed
- Development environment set up
- Test infrastructure configured

**Exit Criteria** (REQUIRED FOR CONSTRUCTION):
- [ ] Test plan approved for all levels
- [ ] CI pipeline configured and running
- [ ] Baseline test coverage established (may be 0% for greenfield)
- [ ] Code review process validated (at least 1 PR reviewed)
- [ ] 40%+ overall test coverage achieved
- [ ] 80%+ coverage for state management (checkpoint/resume)
- [ ] All 8 public benchmarks operational
- [ ] Smoke tier runs in <2 minutes

**Quality Activities**:
- Set up pytest, pytest-cov, ruff, mypy, bandit
- Configure pre-commit hooks
- Implement first unit tests
- Establish code review workflow
- Create CI pipeline (GitHub Actions)
- Run first benchmark validation

**Quality Deliverables**:
- CI/CD configuration (`.github/workflows/`)
- Pre-commit hooks (`.pre-commit-config.yaml`)
- pytest configuration (`pyproject.toml`)
- First test coverage report
- Benchmark validation results

**Quality Risks**:
- Test infrastructure delays implementation
- Coverage targets unrealistic for prototype
- CI resource constraints (Ollama in container)

**Mitigation**:
- Start with simple unit tests, expand later
- Accept lower coverage in Elaboration, enforce in Construction
- Use mocked Ollama for unit tests, real instance for integration

**Gate Decision Criteria**:
- Test infrastructure functional and documented
- At least 40% coverage with upward trend
- No critical defects in checkpoint/resume
- Performance baseline established

---

### Construction Phase (Week 4-6)

**Entry Criteria**:
- Elaboration gate passed
- Architecture validated with working prototype
- Test coverage trend positive

**Exit Criteria** (REQUIRED FOR TRANSITION):
- [ ] 80% overall code coverage achieved
- [ ] 100% coverage for critical components (scorers, state management)
- [ ] All reliability scenarios passing (10/10)
- [ ] Benchmark validation complete (8/8 benchmarks)
- [ ] Performance thresholds met (smoke <2min, quick <20min)
- [ ] Security scan passed (0 critical/high vulnerabilities)
- [ ] No critical/high defects open
- [ ] Documentation complete (user docs, API docs)

**Quality Activities**:
- Write unit tests for all new code (TDD)
- Expand integration test suite
- Implement reliability tests (fault injection)
- Conduct benchmark validation
- Performance profiling and optimization
- Security testing (sandbox escape attempts)
- Documentation review and updates

**Quality Deliverables**:
- Comprehensive test suite (unit + integration + system)
- Test coverage reports (80%+ overall)
- Benchmark validation report
- Performance baseline report
- Security scan results
- Updated documentation

**Quality Risks**:
- Coverage targets not met in time
- Reliability tests reveal design flaws
- Performance optimization delays release

**Mitigation**:
- Prioritize critical component tests first
- Address reliability issues immediately (blocking)
- Accept performance regression if functionality correct (optimize in v1.1)

**Gate Decision Criteria**:
- All mandatory exit criteria met
- Test coverage trend stable or improving
- Defect backlog under control (<5 open defects)
- Stakeholders approve for transition

---

### Transition Phase (Week 7)

**Entry Criteria**:
- Construction gate passed
- All features complete and tested
- Documentation approved

**Exit Criteria** (REQUIRED FOR PRODUCTION):
- [ ] Full tier evaluation passing
- [ ] User acceptance testing complete (matric-cli/matric-memory)
- [ ] Operational runbook validated
- [ ] Deployment automation tested
- [ ] Rollback plan documented and tested
- [ ] Monitoring and alerting configured
- [ ] Production environment validated
- [ ] Sign-off from all stakeholders

**Quality Activities**:
- User acceptance testing with real use cases
- Production environment smoke tests
- Deployment rehearsal (dry run)
- Operational runbook walkthrough
- Final security review
- Performance validation in production-like environment

**Quality Deliverables**:
- User acceptance test results
- Deployment validation report
- Operational runbook
- Production readiness checklist
- Final test coverage report
- Release notes

**Quality Risks**:
- Production environment differs from development
- User acceptance testing reveals usability issues
- Performance degrades under load

**Mitigation**:
- Staging environment mirrors production
- Involve stakeholders early in UAT
- Load testing with representative datasets

**Gate Decision Criteria**:
- All mandatory exit criteria met
- Stakeholder sign-off obtained
- No critical defects in production candidate
- Deployment automation validated

---

### Production Maintenance (Ongoing)

**Quality Activities**:
- Monitor production metrics (performance, errors)
- Triage and fix defects
- Security patch management
- Dependency updates
- Continuous improvement retrospectives

**Quality Metrics**:
- Production defect rate: <0.5 defects per KLOC
- Mean Time to Detect (MTTD): <1 day
- Mean Time to Fix (MTTF): <3 days for critical, <7 days for high
- Uptime: 99.9% (excluding planned maintenance)

**Quality Gates**:
- Hotfixes require expedited review (same day)
- Security patches deployed within 7 days
- Quarterly quality review and retrospective

---

## Defect Management Process

### 1. Defect Lifecycle

```
New → Triaged → Assigned → In Progress → In Review → Resolved → Verified → Closed
  ↓                                                        ↓
Rejected                                              Reopened
```

### 2. Defect Severity Classification

| Severity | Description | Response Time | Resolution Time | Examples |
|----------|-------------|---------------|-----------------|----------|
| **Critical** | System unusable, data loss, security breach | 1 hour | 1 day | Checkpoint corruption, sandbox escape |
| **High** | Major functionality broken, workaround exists | 4 hours | 3 days | Score calculation incorrect, resume fails |
| **Medium** | Minor functionality broken, low impact | 1 day | 1 week | CLI help text wrong, slow performance |
| **Low** | Cosmetic, documentation, minor inconvenience | 1 week | 2 weeks | Typo in output, verbose logging |

### 3. Defect Priority Classification

| Priority | Description | Examples |
|----------|-------------|----------|
| **P0** | Blocks release, immediate attention | Data loss, security vulnerability |
| **P1** | Affects core functionality, must fix before release | Scoring incorrect, checkpoint broken |
| **P2** | Should fix before release, can defer if needed | Performance regression, usability issue |
| **P3** | Nice to have, can defer to next release | Minor UI issue, documentation improvement |

### 4. Defect Triage Process

**Frequency**: Daily during active development, weekly during maintenance

**Participants**: Developer, Test Architect (or solo developer self-triage)

**Process**:
1. Review all new defects
2. Verify reproducibility (attempt to reproduce)
3. Classify severity and priority
4. Assign owner
5. Set target resolution date
6. Update issue tracker

**Triage Criteria**:
- Can the defect be reproduced?
- What is the impact on users?
- What is the impact on development?
- Is there a workaround?
- What is the root cause (if known)?

### 5. Defect Resolution Process

**Steps**:
1. **Investigation**: Understand root cause
2. **Fix Development**: Implement fix with regression test
3. **Code Review**: Review fix per code-review-checklist.md
4. **Testing**: Verify fix resolves defect without side effects
5. **Documentation**: Update docs if needed
6. **Deployment**: Merge to main, deploy to production

**Regression Test Requirement**:
- Every defect fix MUST include a regression test
- Test must fail before fix, pass after fix
- Test becomes part of permanent test suite

### 6. Defect Metrics and Reporting

**Weekly Defect Report** (during Construction/Transition):
- New defects: Count by severity/priority
- Resolved defects: Count by severity/priority
- Open defects: Count by severity/priority
- Defect age: Average days open by severity
- Reopen rate: Percentage of defects reopened

**Monthly Quality Review** (during Maintenance):
- Defect density trend (defects per KLOC)
- Mean Time to Detect (MTTD) trend
- Mean Time to Fix (MTTF) trend
- Defect escape rate (production vs. pre-production)
- Root cause analysis of critical/high defects

### 7. Root Cause Analysis (RCA)

**Trigger**: All critical and high severity defects

**RCA Template**:
1. **Problem Statement**: What went wrong?
2. **Timeline**: When was it introduced? When detected?
3. **Root Cause**: Why did it happen? (5 Whys analysis)
4. **Contributing Factors**: What made it worse?
5. **Immediate Fix**: What fixed it short-term?
6. **Preventive Actions**: What prevents recurrence?
7. **Process Improvements**: What process changes are needed?

**RCA Deliverable**: Document in `.aiwg/quality/rca/RCA-{defect-id}.md`

**Follow-up**: Track preventive actions to completion

---

## Continuous Improvement

### 1. Quality Retrospectives

**Frequency**: End of each phase (Inception, Elaboration, Construction, Transition)

**Participants**: Solo Developer (or team if expanded)

**Agenda**:
1. Review quality metrics vs. targets
2. Discuss what went well (continue)
3. Discuss what went poorly (improve)
4. Identify process improvements
5. Define action items with owners and due dates

**Retrospective Template**:
```markdown
# Quality Retrospective - {Phase Name}

**Date**: YYYY-MM-DD
**Phase**: Inception/Elaboration/Construction/Transition
**Participants**: {Names}

## Metrics Review

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Test Coverage | 80% | 85% | ✓ Met |
| Defect Density | <0.5/KLOC | 0.3/KLOC | ✓ Met |
| ... | ... | ... | ... |

## What Went Well

- {Item 1}
- {Item 2}

## What Went Poorly

- {Item 1}
- {Item 2}

## Process Improvements

- {Improvement 1}: {Action} - Owner: {Name} - Due: {Date}
- {Improvement 2}: {Action} - Owner: {Name} - Due: {Date}

## Action Items

- [ ] {Action 1} - Owner: {Name} - Due: {Date}
- [ ] {Action 2} - Owner: {Name} - Due: {Date}
```

### 2. Lessons Learned

**Capture Point**: End of each phase, after major incidents

**Lessons Learned Template**:
See Appendix B in `gate-inception.md` for template

**Knowledge Sharing**:
- Document in `.aiwg/quality/lessons-learned/`
- Share with matric-cli and matric-memory teams
- Update CLAUDE.md with key insights

### 3. Process Improvement Cycle

**Cycle**: Plan → Do → Check → Act (PDCA)

**Plan**:
- Identify improvement opportunity from retrospectives or defect analysis
- Define measurable goal (e.g., reduce MTTF from 3 days to 2 days)
- Design experiment or process change

**Do**:
- Implement change on small scale (one sprint)
- Document new process
- Train participants (if needed)

**Check**:
- Measure results against goal
- Collect feedback from participants
- Compare before/after metrics

**Act**:
- If successful, standardize and scale
- If unsuccessful, iterate or abandon
- Document outcome in lessons learned

**Examples**:
- Introduce TDD to reduce defect density
- Add mutation testing to improve test quality
- Automate security scanning to reduce vulnerabilities
- Optimize CI pipeline to reduce feedback time

### 4. Benchmarking and Industry Standards

**Benchmarking Sources**:
- Google Testing Blog: Best practices from industry leader
- ISTQB standards: Test engineering certification body
- Python community: PEPs, pytest conventions, type hints

**Industry Standards**:
- PEP 8: Python code style
- PEP 484: Type hints
- pytest conventions: Test naming, fixtures, assertions
- Semantic versioning: Release numbering

**Adoption Process**:
1. Research industry best practice
2. Evaluate applicability to matric-eval
3. Pilot on small component
4. Document as standard in CLAUDE.md or ADR
5. Enforce via pre-commit hooks or CI

---

## Quality Assurance Tools

### Development Tools

| Tool | Purpose | Configuration | Enforcement |
|------|---------|---------------|-------------|
| **pytest** | Unit and integration testing | `pyproject.toml` | CI required |
| **pytest-cov** | Code coverage measurement | `.coveragerc` | CI required (80%+) |
| **ruff** | Fast Python linter | `pyproject.toml` | Pre-commit hook |
| **mypy** | Static type checking | `pyproject.toml` | CI required (strict) |
| **bandit** | Security vulnerability scanner | `.bandit` | CI required |
| **safety** | Dependency vulnerability scanner | CLI | CI required |
| **pip-audit** | Dependency audit (newer) | CLI | CI weekly |
| **mutmut** | Mutation testing | CLI | Weekly manual |
| **radon** | Code complexity metrics | CLI | CI (threshold: 10) |
| **pre-commit** | Git hook automation | `.pre-commit-config.yaml` | Developer setup |

### CI/CD Tools

| Tool | Purpose | Configuration | Trigger |
|------|---------|---------------|---------|
| **GitHub Actions** | Continuous integration | `.github/workflows/` | Every PR |
| **pytest-xdist** | Parallel test execution | pytest config | CI |
| **pytest-timeout** | Test timeout enforcement | pytest config | CI |
| **coverage-badge** | Coverage badge generation | CI script | Every merge |
| **docker** | Sandbox isolation | `Dockerfile` | Integration tests |

### Quality Monitoring

| Tool | Purpose | Configuration | Frequency |
|------|---------|---------------|-----------|
| **Coverage dashboard** | Track coverage trend | CI artifact | Every PR |
| **Defect tracker** | Issue management | GitHub Issues | Real-time |
| **Performance profiler** | Identify bottlenecks | py-spy | Weekly |
| **Memory profiler** | Detect leaks | memory_profiler | Weekly |

---

## Roles and Responsibilities

### Solo Developer Model (Current)

**Primary Role**: Python Developer
**Quality Responsibilities**:
- Write unit tests for all code (TDD)
- Self-review using code-review-checklist.md
- Run full test suite before committing
- Maintain test coverage above 80%
- Triage and fix defects
- Conduct self-retrospectives

**Support Roles** (Self-Service):
- Test Architect: Define test strategy
- Security Engineer: Run security scans
- Performance Engineer: Profile and optimize
- QA Engineer: Validate benchmarks
- Documentation Writer: Maintain docs

**Escalation**:
- If overwhelmed, defer non-critical features
- If quality targets missed, extend phase
- If critical defect found, stop new development

### Expanded Team Model (Future)

If team grows beyond solo developer:

| Role | Quality Responsibilities |
|------|--------------------------|
| **Developer** | Write tests, fix defects, self-review |
| **Peer Reviewer** | Review code, approve PRs |
| **Test Architect** | Design test strategy, maintain coverage |
| **QA Engineer** | Validate benchmarks, run system tests |
| **Security Engineer** | Security reviews, penetration testing |
| **Performance Engineer** | Profiling, optimization, baselines |
| **Product Owner** | Prioritize defects, approve quality gates |

---

## Appendix A: Quality Checklist Templates

### Pre-Commit Checklist

- [ ] All unit tests passing locally
- [ ] New code has unit tests
- [ ] Test coverage maintained or increased
- [ ] Linter (ruff) passes with no warnings
- [ ] Type checker (mypy) passes in strict mode
- [ ] Security scan (bandit) passes
- [ ] Commit message follows conventions
- [ ] Related issue linked in commit message

### Pre-PR Checklist

- [ ] All commits follow pre-commit checklist
- [ ] PR description explains changes
- [ ] Related issue linked in PR
- [ ] Tests added for new functionality
- [ ] Tests added for bug fixes (regression tests)
- [ ] Documentation updated if needed
- [ ] CHANGELOG updated (if applicable)
- [ ] Self-review completed using code-review-checklist.md

### Pre-Merge Checklist

- [ ] CI build passing (all tests green)
- [ ] Code review approved (or self-review documented)
- [ ] No merge conflicts
- [ ] Branch up-to-date with main
- [ ] Test coverage not decreased
- [ ] No new linter/type warnings
- [ ] Documentation builds successfully

### Pre-Release Checklist

- [ ] All release-blocking defects resolved
- [ ] Test coverage meets 80%+ threshold
- [ ] All reliability scenarios passing
- [ ] Benchmark validation complete
- [ ] Performance thresholds met
- [ ] Security scan passed (0 critical/high)
- [ ] Documentation complete and reviewed
- [ ] Release notes drafted
- [ ] Stakeholder approval obtained

---

## Appendix B: Quality Metrics Dashboard

**Automated Dashboard** (via CI artifacts):

```
matric-eval Quality Dashboard
=============================

Build: #42 | Date: 2026-01-24 | Branch: main | Commit: abc1234

TEST COVERAGE
  Overall:    85% ████████████████████░░░░  Target: 80%  ✓
  Critical:  100% ████████████████████████  Target: 100% ✓
  Branch:     78% ███████████████████░░░░░  Target: 75%  ✓

CODE QUALITY
  Linter:        0 warnings  ✓
  Type Checker:  0 errors    ✓
  Complexity:    8.2 avg     ✓ (threshold: 10)
  Duplication:   2.1%        ✓ (threshold: 3%)

SECURITY
  Bandit:      0 issues  ✓
  Safety:      0 vulns   ✓
  Pip-Audit:   0 vulns   ✓

PERFORMANCE
  Smoke Tier:  1m 45s  ✓ (target: <2m)
  Quick Tier:  18m 32s ✓ (target: <20m)
  State Write: 67ms    ✓ (target: <100ms)

DEFECTS
  Critical:  0 open
  High:      1 open (MATRIC-123)
  Medium:    3 open
  Low:       5 open
  Total:     9 open

TRENDS (Last 7 Days)
  Coverage:    ↑ +2%
  Defects:     ↓ -3
  Performance: → stable
```

---

## Appendix C: Quality Anti-Patterns (Escalate Immediately)

| Anti-Pattern | Why It's Bad | Response |
|--------------|--------------|----------|
| "We'll add tests later" | Tests never get written, tech debt accumulates | Require tests in same PR as code |
| "Coverage is just a number" | Indicates lack of quality commitment | Enforce 80%+ minimum |
| "Skip flaky tests" | Masks underlying issues | Fix flaky tests immediately |
| "Manual testing is enough" | Doesn't scale, not repeatable | Automate all regression tests |
| "100% coverage is impossible" | It's mandatory for critical components | Enforce for scorers, state mgmt |
| "Mocking is too hard" | Results in slow, brittle tests | Invest in test infrastructure |
| "This is a small change, no review needed" | Small changes can have big impacts | Review everything |
| "Defects can wait until after release" | Quality debt compounds | Prioritize defects by severity |

---

## Document Control

**Version**: 1.0
**Created**: 2026-01-24
**Last Updated**: 2026-01-24
**Next Review**: End of Elaboration Phase (Week 3)
**Approval Authority**: Solo Python Developer (roctinam)

**Change History**:
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial quality assurance plan |

---

**END OF QUALITY ASSURANCE PLAN**
