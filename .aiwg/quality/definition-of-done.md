# Definition of Done - matric-eval

**Project**: matric-eval - Consolidated Model Evaluation Framework
**Profile**: Production (80%+ test coverage required)
**Purpose**: Comprehensive completion criteria for all work items
**Last Updated**: 2026-01-24

---

## Overview

The Definition of Done (DoD) establishes clear, objective criteria that all work items must meet before being considered complete. This ensures consistent quality across the project and prevents incomplete work from accumulating as technical debt.

**Scope**: This DoD applies to all work items including:
- User stories and features
- Bug fixes and defect resolutions
- Technical tasks and refactorings
- Documentation updates
- Architecture changes

**Mandatory vs. Conditional**: Items marked with ⚠️ are MANDATORY for all work items. Other items may be conditional based on work type.

**Quality Philosophy**: "Done" means production-ready, not just "code written". Work is not done until it's tested, reviewed, documented, and deployable.

---

## Universal Definition of Done

All work items MUST meet these criteria before being marked as "Done":

### 1. Code Complete Criteria ⚠️

- [ ] All acceptance criteria met (as defined in issue/story)
- [ ] Code implements the specified functionality correctly
- [ ] Edge cases identified and handled appropriately
- [ ] Error conditions identified and handled gracefully
- [ ] Code follows project style guidelines (PEP 8, ruff compliant)
- [ ] Type hints comprehensive and accurate (mypy strict passing)
- [ ] No linter warnings (ruff check passes)
- [ ] No commented-out code (removed or justified with TODO)
- [ ] No debug statements or print debugging (use logging)
- [ ] No hardcoded values (use constants, config, or environment variables)

**Verification**:
```bash
# All checks must pass
ruff check src/
mypy --strict src/
python -m pytest
```

### 2. Test Requirements ⚠️

- [ ] Unit tests written for all new code (minimum 80% coverage)
- [ ] Critical components have 100% test coverage (scorers, state management)
- [ ] Integration tests added for component interactions
- [ ] All tests passing locally
- [ ] All tests passing in CI
- [ ] Tests are deterministic (no flaky tests)
- [ ] Tests are fast (unit tests <1s each, integration tests <5s each)
- [ ] Test names clearly describe scenarios (test_should_X_when_Y)
- [ ] Edge cases tested (empty input, null, extreme values, malformed data)
- [ ] Error cases tested (exceptions raised as expected)

**Test Coverage Verification**:
```bash
# Coverage must meet thresholds
pytest --cov=src --cov-report=term --cov-fail-under=80
pytest --cov=src/matric_eval/scorers --cov-fail-under=100
pytest --cov=src/matric_eval/state --cov-fail-under=100
```

**Regression Test Requirement** (for bug fixes):
- [ ] Regression test added that would have caught the bug
- [ ] Test fails before fix, passes after fix
- [ ] Test added to permanent suite

### 3. Documentation Requirements ⚠️

- [ ] All public functions/classes have docstrings
- [ ] Docstrings include parameters, return types, exceptions
- [ ] Complex logic has inline comments explaining "why"
- [ ] User documentation updated (if user-facing change)
- [ ] API documentation updated (if API change)
- [ ] CHANGELOG.md updated (for notable changes)
- [ ] README.md updated (if setup/usage changed)
- [ ] Examples provided (for new features)
- [ ] Migration guide provided (if breaking change)

**Documentation Standards**:
- Docstrings follow NumPy style
- Examples in docstrings are tested (doctest or manual verification)
- Comments explain "why", not "what"
- Documentation builds successfully (if using Sphinx)

### 4. Review Approvals ⚠️

- [ ] Code self-reviewed using code-review-checklist.md
- [ ] All checklist items verified (functionality, tests, security, performance, docs)
- [ ] Self-review documented in PR description
- [ ] CI checks passing (linter, type checker, tests, coverage)
- [ ] No merge conflicts
- [ ] Branch up-to-date with main

**Solo Developer Protocol**:
- Complete entire code-review-checklist.md systematically
- Review own diff in GitHub (not just local)
- Sleep on critical changes, review again next day
- Document review completion in PR description

**Team Protocol** (if team expands):
- Peer review by at least 1 reviewer
- Critical components (scorers, state management) reviewed by 2 reviewers
- Security changes reviewed by security engineer
- All review comments addressed

### 5. Integration Verification ⚠️

- [ ] Code integrated into main branch
- [ ] Build successful in CI
- [ ] No integration conflicts
- [ ] Smoke tests passing (if applicable)
- [ ] No regression in existing functionality
- [ ] Dependencies updated (if needed)
- [ ] Configuration updated (if needed)

**Integration Checklist**:
```bash
# After merge to main, verify:
git checkout main
git pull
pytest tests/smoke/  # Smoke tests pass
pytest  # Full test suite passes
matric-eval --tier smoke  # CLI smoke test (if CLI implemented)
```

---

## Work Type Specific Criteria

### User Story / Feature

In addition to Universal DoD:

- [ ] Feature acceptance criteria met (as defined in story)
- [ ] Feature tested end-to-end (system test)
- [ ] User documentation includes usage examples
- [ ] CLI help text updated (if CLI change)
- [ ] Performance impact assessed (no significant regression)
- [ ] Security implications assessed (checklist completed)
- [ ] Backward compatibility maintained (or migration path provided)
- [ ] Feature flag configured (if phased rollout)

**Acceptance Criteria Format**:
```markdown
## Acceptance Criteria
- [ ] Given [context], when [action], then [expected result]
- [ ] Given [context], when [action], then [expected result]
```

**Example**:
```markdown
## Acceptance Criteria for "Resume Interrupted Evaluation"
- [ ] Given an interrupted evaluation run, when I run `matric-eval --resume <run-id>`, then evaluation continues from last checkpoint
- [ ] Given a completed evaluation run, when I run `matric-eval --resume <run-id>`, then no duplicate work is performed
- [ ] Given missing results in run, when I run `matric-eval --resume <run-id> --fill-gaps`, then only missing results are computed
```

### Bug Fix

In addition to Universal DoD:

- [ ] Root cause identified and documented
- [ ] Regression test added (test fails before fix, passes after)
- [ ] Similar bugs searched for (check codebase for patterns)
- [ ] Related code reviewed (potential related issues)
- [ ] Root cause analysis completed (for critical/high bugs)
- [ ] Fix verified in environment where bug occurred
- [ ] Issue linked in commit/PR
- [ ] Issue closed after verification

**Root Cause Analysis** (for critical/high severity):
- Document in `.aiwg/quality/rca/RCA-{issue-id}.md`
- Include: problem statement, timeline, root cause, fix, preventive actions
- Review and implement preventive actions

### Technical Task / Refactoring

In addition to Universal DoD:

- [ ] Behavior preserved (no functional changes)
- [ ] Tests unchanged or improved (not weakened)
- [ ] Complexity reduced (measurable improvement)
- [ ] Performance maintained or improved (benchmarked)
- [ ] Architecture decision recorded (ADR if significant)
- [ ] Migration path documented (if breaking internal APIs)
- [ ] Dependent systems notified (if external impacts)

**Refactoring Validation**:
```bash
# Before refactoring, capture baseline
pytest --cov=src --cov-report=json -o json_report_file=before.json
pytest --benchmark-save=before

# After refactoring, compare
pytest --cov=src --cov-report=json -o json_report_file=after.json
pytest --benchmark-compare=before
# Coverage should be maintained or improved
# Performance should be maintained or improved
```

### Documentation Update

In addition to Universal DoD:

- [ ] Documentation accurate (matches implementation)
- [ ] Documentation complete (all use cases covered)
- [ ] Documentation clear (understandable by target audience)
- [ ] Examples tested (manually or automated)
- [ ] Links verified (no broken links)
- [ ] Spelling/grammar checked
- [ ] Screenshots current (if applicable)
- [ ] Version documented (if versioned docs)

**Documentation Types**:
- **User Docs**: End users can complete tasks
- **API Docs**: Developers can integrate
- **Architecture Docs**: Maintainers understand design
- **Runbooks**: Operators can troubleshoot

### Performance Optimization

In addition to Universal DoD:

- [ ] Baseline performance measured (before optimization)
- [ ] Target performance defined (measurable goal)
- [ ] Actual performance measured (after optimization)
- [ ] Improvement quantified (percentage or absolute)
- [ ] Profiling data captured (identify bottlenecks)
- [ ] No correctness regression (all tests still pass)
- [ ] No maintainability regression (code still readable)
- [ ] Optimization justified (not premature)

**Performance Baselines** (matric-eval):
- Smoke tier: <2 minutes total
- Quick tier: <20 minutes total
- State checkpoint write: <100ms
- Resume overhead: <5 seconds

### Security Fix

In addition to Universal DoD:

- [ ] Vulnerability completely addressed (no bypass possible)
- [ ] Security scan passing (bandit, safety, pip-audit)
- [ ] Similar issues audited (check codebase for patterns)
- [ ] Security test added (prevent regression)
- [ ] Disclosure handled appropriately (responsible disclosure)
- [ ] Severity assessed (CVSS score if applicable)
- [ ] Fix validated by security engineer (or self if solo)
- [ ] Dependencies updated (if dependency vulnerability)

**Security Testing**:
```bash
# All security checks must pass
bandit -r src/
safety check
pip-audit
```

---

## Critical Component DoD

### Scorers (`src/matric_eval/scorers/`)

**Additional Requirements**:
- [ ] Scoring logic mathematically correct
- [ ] 100% test coverage (MANDATORY)
- [ ] Validated against reference implementation (if public benchmark)
- [ ] Deterministic (same input → same score, always)
- [ ] All edge cases tested:
  - [ ] Empty output
  - [ ] Malformed output (invalid format)
  - [ ] Correct output (should pass)
  - [ ] Incorrect output (should fail)
  - [ ] Partially correct output
  - [ ] Very long output (>10MB)
  - [ ] Special characters in output
- [ ] Performance acceptable (<100ms per score on average)

**Validation Protocol**:
1. Run on known-good examples (verify passes)
2. Run on known-bad examples (verify fails)
3. Compare to reference implementation (if available)
4. Test on edge cases (verify graceful handling)

### State Management (`src/matric_eval/state/`)

**Additional Requirements**:
- [ ] 100% test coverage (MANDATORY)
- [ ] Atomic writes (no partial state files)
- [ ] Idempotent operations (re-run produces same result)
- [ ] Lock file prevents concurrent access
- [ ] Corrupted state detected and reported
- [ ] Gap detection accurate (100% precision/recall)
- [ ] All fault injection scenarios passing:
  - [ ] Process killed during checkpoint write
  - [ ] Disk full during checkpoint write
  - [ ] Corrupted checkpoint file
  - [ ] Concurrent resume attempts
  - [ ] Missing checkpoint file
  - [ ] Partial checkpoint file
- [ ] Resume overhead <5 seconds
- [ ] No data loss in any scenario

**Fault Injection Testing**:
```bash
# Run reliability test suite
pytest tests/reliability/ -v
# All 10 reliability scenarios must pass
```

### Code Extraction (`src/matric_eval/extractors/`)

**Additional Requirements**:
- [ ] 85%+ test coverage
- [ ] Handles all markdown fence variations:
  - [ ] \`\`\`python
  - [ ] \`\`\`py
  - [ ] \`\`\` (no language tag)
  - [ ] Inline code (no fences)
- [ ] Preserves indentation
- [ ] Handles multiple code blocks
- [ ] Handles nested fences
- [ ] Removes non-code artifacts
- [ ] Performance acceptable (<10ms per extraction)

### CLI (`src/matric_eval/cli.py`)

**Additional Requirements**:
- [ ] 85%+ test coverage
- [ ] All commands documented in --help
- [ ] All flags validated (correct types, ranges)
- [ ] Flag combinations validated (mutually exclusive, required combos)
- [ ] Error messages actionable (suggest fix)
- [ ] Exit codes correct:
  - [ ] 0: Success
  - [ ] 1: User error (bad args)
  - [ ] 2: Runtime error (model not found, etc.)
  - [ ] 130: SIGINT (Ctrl+C)
- [ ] Progress output useful (not too verbose or quiet)
- [ ] Logging configured appropriately
- [ ] System test for each major command

---

## Phase-Specific DoD

### Elaboration Phase (Week 2-3)

**Prototype Quality**:
- [ ] 40%+ overall test coverage
- [ ] 80%+ state management test coverage
- [ ] Smoke tier runs in <2 minutes
- [ ] All 8 public benchmarks operational
- [ ] Checkpoint/resume works for at least 1 benchmark
- [ ] CI pipeline configured and passing

**Acceptable Technical Debt**:
- Lower coverage for non-critical components (will improve in Construction)
- Hardcoded configuration (will externalize in Construction)
- Limited error handling (will expand in Construction)
- Minimal documentation (will complete in Transition)

**Not Acceptable**:
- Broken functionality in critical paths
- No tests for checkpoint/resume
- Flaky tests
- Security vulnerabilities

### Construction Phase (Week 4-6)

**Production Quality**:
- [ ] 80%+ overall test coverage
- [ ] 100% critical component coverage (scorers, state management)
- [ ] All reliability scenarios passing (10/10)
- [ ] Benchmark validation complete (8/8 benchmarks)
- [ ] Performance thresholds met (smoke <2min, quick <20min)
- [ ] Security scan passing (0 critical/high vulnerabilities)
- [ ] User documentation complete
- [ ] API documentation complete

**No Technical Debt**:
- All known bugs fixed (or deferred with justification)
- All TODOs resolved (or tracked with issues)
- All hardcoded values externalized
- All error cases handled

### Transition Phase (Week 7)

**Deployment Ready**:
- [ ] Full tier evaluation passing
- [ ] User acceptance testing complete
- [ ] Operational runbook complete
- [ ] Deployment automation tested
- [ ] Rollback plan documented
- [ ] Monitoring configured
- [ ] Alerting configured
- [ ] Production environment validated
- [ ] Stakeholder sign-off obtained

---

## Quality Gates Checklist

### PR Merge Gate ⚠️

All PRs must meet these criteria before merge:

- [ ] All CI checks passing (linter, type checker, tests, security)
- [ ] Test coverage maintained or increased (no decrease)
- [ ] Code review checklist completed
- [ ] Self-review documented (or peer review approved)
- [ ] No merge conflicts
- [ ] Branch up-to-date with main
- [ ] All review comments addressed

**Automated Checks** (GitHub Actions):
```yaml
# .github/workflows/pr-checks.yml enforces:
- ruff check (linter)
- mypy --strict (type checker)
- pytest (tests)
- pytest-cov --fail-under=80 (coverage)
- bandit (security)
```

### Release Gate ⚠️

All releases must meet these criteria:

- [ ] All test levels passing (unit, integration, system, reliability)
- [ ] 80%+ overall test coverage
- [ ] 100% critical component coverage
- [ ] Benchmark validation complete
- [ ] Performance thresholds met
- [ ] Security scan passed (0 critical/high vulnerabilities)
- [ ] Documentation complete (user, API, architecture)
- [ ] No critical/high defects open
- [ ] CHANGELOG.md updated
- [ ] Release notes drafted
- [ ] Stakeholder approval obtained

**Sign-off Required**:
- Solo Developer (self-sign-off with documented review)
- Product Owner (if team expands)
- Security Engineer (if high-risk changes)

### Production Deployment Gate ⚠️

All production deployments must meet:

- [ ] Release gate passed
- [ ] Staging environment validated
- [ ] User acceptance testing passed
- [ ] Operational runbook tested
- [ ] Deployment automation validated
- [ ] Rollback plan tested
- [ ] Monitoring configured and tested
- [ ] Alerts configured and tested
- [ ] Production environment prepared
- [ ] Deployment window scheduled
- [ ] Stakeholder notification sent

---

## Verification Checklists

### Developer Self-Check (Before Marking Done)

Run through this checklist before marking work as done:

```bash
# 1. Code Quality
ruff check src/
mypy --strict src/

# 2. Tests
pytest -v
pytest --cov=src --cov-report=term --cov-fail-under=80

# 3. Security
bandit -r src/
safety check

# 4. Integration
git checkout main
git pull
git checkout <your-branch>
git rebase main  # Ensure up-to-date

# 5. Self-Review
# Complete code-review-checklist.md systematically
# Document review in PR description

# 6. Documentation
# Verify all docstrings complete
# Verify user docs updated (if applicable)
# Verify CHANGELOG updated (if notable change)
```

### Reviewer Verification (If Team Expands)

Peer reviewers should verify:

- [ ] Code review checklist completed
- [ ] All automated checks passing
- [ ] Tests comprehensive and meaningful
- [ ] Documentation accurate and complete
- [ ] No security concerns
- [ ] Performance acceptable
- [ ] Approve or request changes

---

## Definition of "Not Done"

Work is explicitly NOT done if:

- ❌ Tests are failing
- ❌ Coverage decreased without justification
- ❌ Linter or type checker warnings exist
- ❌ Security vulnerabilities present (critical/high)
- ❌ Code review checklist not completed
- ❌ Acceptance criteria not met
- ❌ Documentation missing or outdated
- ❌ Known bugs not fixed or tracked
- ❌ CI failing
- ❌ Merge conflicts unresolved

**Technical Debt**:
- Work with known limitations MUST have issues filed
- Issues MUST be prioritized and scheduled
- Technical debt MUST be paid down before accumulating more

---

## Exceptions and Waivers

### When to Seek Exception

Exceptions to DoD may be granted for:
- Prototyping / proof-of-concept work (clearly labeled)
- Emergency hotfixes (with follow-up issue for proper fix)
- External constraints (third-party bugs, blocked dependencies)

### Exception Process

1. Document exception request in PR/issue
2. Justify why exception needed
3. Define remediation plan (what will be done, when)
4. File follow-up issue (link to exception)
5. Obtain approval (solo developer: self-approve with documentation)
6. Track exception to closure

**Exception Template**:
```markdown
## DoD Exception Request

**Work Item**: #123
**Exception Requested**: Skip integration tests for this PR
**Justification**: Ollama service unavailable in CI environment
**Remediation Plan**: Fix CI environment by end of sprint, add tests in follow-up PR #124
**Approval**: Granted by [Name] on [Date]
```

---

## Continuous Improvement

### Retrospective Review

At end of each phase, review DoD:

- Are criteria too strict? (blocking progress)
- Are criteria too loose? (quality issues escaping)
- Are criteria clear? (no ambiguity)
- Are criteria measurable? (objective verification)

**DoD Evolution**:
- Start with essential criteria (Elaboration)
- Add criteria as needed (Construction)
- Refine based on defects (Transition)
- Stabilize for production (Maintenance)

### Metrics to Track

Monitor these metrics to validate DoD effectiveness:

| Metric | Target | Indicates DoD Is |
|--------|--------|------------------|
| Defect Escape Rate | <5% | Effective at catching bugs |
| Reopen Rate | <10% | Work truly complete |
| Technical Debt Trend | Decreasing | Paying down debt |
| Coverage Trend | Increasing | Improving quality |
| Time to Done | Stable | Criteria sustainable |

---

## Appendix A: DoD Quick Reference Card

**Print and post near workspace:**

```
╔═══════════════════════════════════════════════════════════╗
║           matric-eval DEFINITION OF DONE                  ║
╠═══════════════════════════════════════════════════════════╣
║ Code Complete:                                            ║
║  ☑ All acceptance criteria met                           ║
║  ☑ Style compliant (ruff, mypy)                          ║
║  ☑ No debug code, no hardcoded values                    ║
║                                                            ║
║ Tests:                                                     ║
║  ☑ 80%+ coverage (100% for critical)                     ║
║  ☑ All tests passing (local + CI)                        ║
║  ☑ Edge cases tested                                      ║
║  ☑ Regression test for bugs                              ║
║                                                            ║
║ Documentation:                                             ║
║  ☑ Docstrings complete                                    ║
║  ☑ User docs updated                                      ║
║  ☑ CHANGELOG updated                                      ║
║                                                            ║
║ Review:                                                    ║
║  ☑ Code review checklist completed                       ║
║  ☑ Self-review documented                                 ║
║  ☑ CI checks passing                                      ║
║                                                            ║
║ Integration:                                               ║
║  ☑ Merged to main                                         ║
║  ☑ No conflicts                                           ║
║  ☑ Smoke tests passing                                    ║
╚═══════════════════════════════════════════════════════════╝
```

---

## Appendix B: DoD by Role

### Solo Developer (Current)

**Responsibilities**:
- Complete all DoD criteria
- Self-review using checklist
- Document review completion
- Approve own PRs (with documented review)

**Simplified Workflow**:
1. Write code + tests
2. Run local checks (ruff, mypy, pytest)
3. Self-review using code-review-checklist.md
4. Document review in PR description
5. Merge after CI passes

### Team Roles (If Team Expands)

**Developer**:
- Complete code, tests, docs
- Self-review before requesting peer review
- Address review comments
- Merge after approval

**Peer Reviewer**:
- Review using code-review-checklist.md
- Verify automated checks passing
- Provide constructive feedback
- Approve or request changes

**QA Engineer**:
- Validate acceptance criteria
- Run system/integration tests
- Sign off on release readiness

**Product Owner**:
- Verify acceptance criteria
- Prioritize defects
- Approve release

---

## Appendix C: DoD Violations and Consequences

| Violation | Consequence | Remediation |
|-----------|-------------|-------------|
| Merge without tests | Revert immediately | Add tests, re-merge |
| Coverage decrease | Block merge | Add tests to restore coverage |
| Failing tests | Block merge | Fix tests |
| Security vulnerability | Block release | Fix vulnerability |
| Incomplete docs | Block release | Complete documentation |
| Unresolved review comments | Block merge | Address all comments |

**Zero Tolerance**:
- Data loss bugs (state management)
- Scoring correctness bugs
- Security vulnerabilities (critical/high)
- Test failures in main branch

**Technical Debt Limit**:
- Maximum 5 open TODOs per 1000 LOC
- Maximum 10 open bugs in backlog
- All critical/high bugs must have fix scheduled

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
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial definition of done |

---

**END OF DEFINITION OF DONE**
