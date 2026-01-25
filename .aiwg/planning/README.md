# Planning Documentation - matric-eval

**Project**: matric-eval - Consolidated Model Evaluation Framework
**Profile**: Production (6-8 weeks, 80%+ test coverage)
**Last Updated**: 2026-01-24

## Document Overview

This directory contains comprehensive SDLC planning documentation for the matric-eval project.

### Phase Plans

| Document | Phase | Duration | Status |
|----------|-------|----------|--------|
| [phase-plan-inception.md](./phase-plan-inception.md) | Inception | Week 1 | Not Started |
| phase-plan-elaboration.md | Elaboration | Weeks 2-3 | Not Created |
| [iteration-plan-construction.md](./iteration-plan-construction.md) | Construction | Weeks 4-7 | Not Started |
| phase-plan-transition.md | Transition | Week 8 | Not Created |

### Iteration Plans (Construction Phase)

| Document | Week | Focus | Issues | Est. Hours |
|----------|------|-------|--------|------------|
| [iteration-plan-week4.csv](./iteration-plan-week4.csv) | Week 4 | Critical Foundation (P1) | 6 | 38 |
| [iteration-plan-week5.csv](./iteration-plan-week5.csv) | Week 5 | Advanced Features (P2) | 6 | 42 |
| [iteration-plan-week6.csv](./iteration-plan-week6.csv) | Week 6 | Operational Excellence (P3) | 4 | 32 |
| [iteration-plan-week7.csv](./iteration-plan-week7.csv) | Week 7 | Extended Features (P4) | 2-3 | 25 |

### Detailed Planning

| Document | Purpose | Audience |
|----------|---------|----------|
| [iteration-details-construction.md](./iteration-details-construction.md) | Detailed breakdown of all 4 Construction iterations with daily plans, acceptance criteria, and testing strategy | Developer, Project Manager |

## Quick Start Guide

### For Developers

**Starting Inception Phase (Week 1)**:
1. Read [phase-plan-inception.md](./phase-plan-inception.md)
2. Follow Day 1-5 timeline
3. Complete all required deliverables (D1-D5)
4. Self-review gate criteria before proceeding to Elaboration

**Starting Construction Phase (Weeks 4-7)**:
1. Read [iteration-plan-construction.md](./iteration-plan-construction.md) for overview
2. Review [iteration-details-construction.md](./iteration-details-construction.md) for current week's detailed plan
3. Check CSV file for current week for issue tracking
4. Update CSV daily with status and actual hours
5. Perform weekly gate review before proceeding to next iteration

### For Project Managers

**Tracking Progress**:
1. Review weekly CSV files for issue status
2. Check daily velocity (actual vs estimated hours)
3. Monitor test coverage metrics
4. Update risk register as issues emerge
5. Conduct iteration retrospectives

**Gate Reviews**:
- **Inception → Elaboration**: All D1-D5 deliverables complete, checkpoint/resume proven
- **Elaboration → Construction**: All 8 benchmarks working, test coverage ≥40%
- **Week 4 → Week 5**: All P1 issues complete, test coverage ≥85%
- **Week 5 → Week 6**: All P2 issues complete, custom tests migrated
- **Week 6 → Week 7**: All P3 issues complete, checkpoint/resume operational
- **Construction → Transition**: All selected issues complete, coverage ≥80%

## Project Context

### Key Documents (Root Directory)

- [PLANNING.md](/home/roctinam/dev/matric-eval/PLANNING.md) - Overall architecture and design decisions
- [ROADMAP.md](/home/roctinam/dev/matric-eval/ROADMAP.md) - Feature roadmap and parity goals
- [CLAUDE.md](/home/roctinam/dev/matric-eval/CLAUDE.md) - Claude Code guidance

### Related Repositories

- **matric-cli**: `/home/roctinam/dev/matric-cli` - TypeScript eval code to migrate
- **matric-memory**: `/home/roctinam/dev/matric-memory` - Rust eval code to migrate

### Data Sources

- Public benchmarks: `/home/roctinam/data/evals/` (HumanEval, MBPP, GSM8K, etc.)
- Custom tests: `/home/roctinam/data/evals/matric/` (282 tests)

## Construction Phase Overview

### 4-Week Iteration Plan

**Week 4 (P1 - Critical Foundation)**:
- 8 public benchmarks operational
- Code execution scoring with sandbox
- Tiered CLI (smoke/quick/full)
- **Gate**: 85%+ test coverage, all benchmarks passing

**Week 5 (P2 - Advanced Features)**:
- 282 custom matric tests ported
- Tool calling evaluation (6 scenarios)
- MT-Bench with LLM-as-judge
- 5D scoring framework
- **Gate**: 80%+ test coverage, custom tests validated

**Week 6 (P3 - Operational Excellence)**:
- Checkpoint/resume with zero data loss
- Parallel model evaluation
- CI/CD pipeline (<3min smoke tests)
- Comprehensive logging
- **Gate**: 90%+ coverage for state management, CI operational

**Week 7 (P4 - Extended Features)**:
- Model recommendation engine
- Extended reporting
- TypeScript bindings (partial)
- **Gate**: 80%+ overall coverage, all selected features complete

### Total Delivery

**Issues**: 18-19 of 22 total (P1-P3 complete + selected P4)
**Effort**: 137 estimated hours (160 available, 14% buffer)
**Test Coverage**: 82% overall (exceeds 80% Production requirement)

**Deferred to Post-v1.0**:
- #15: Leaderboard dashboard
- #17: Extended benchmarks (SWE-bench, GPQA)
- #19: Contamination detection
- #20: Historical trend analysis

## Risk Management

### Top Construction Phase Risks

1. **Code execution sandbox security** (Week 4) - Use Docker isolation, restrict resources
2. **LLM-as-judge variance** (Week 5) - Temperature=0, multiple runs, validation
3. **Checkpoint state corruption** (Week 6) - Atomic writes, checksums, fault injection tests
4. **Parallel execution deadlocks** (Week 6) - File locks, process isolation
5. **Test coverage below 80%** (All weeks) - Daily tracking, gate PRs on coverage

### Mitigation Strategy

- **Incremental delivery**: Each week delivers working functionality
- **Prioritization**: P1-P3 must complete; P4 can be reduced if needed
- **Buffer allocation**: 14% overall buffer, concentrated in Week 6-7
- **Daily tracking**: Catch issues early, adjust scope if needed

## Testing Strategy

### Coverage Targets by Week

| Week | Unit Tests | Integration Tests | Overall | Notes |
|------|------------|-------------------|---------|-------|
| Week 4 | 90% | 70% | 85% | Focus on scorers, state management |
| Week 5 | 85% | 70% | 80% | Custom scorers, judge patterns |
| Week 6 | 95% | 80% | 90% | Critical: state management, recovery |
| Week 7 | 80% | 70% | 75% | Recommendations, bindings |
| **Final** | **87%** | **72%** | **82%** | **Exceeds 80% requirement** |

### Test Types

- **Unit Tests**: Individual functions, mocked dependencies, <1s each
- **Integration Tests**: End-to-end flows, real Ollama/Docker, <30s each
- **Smoke Tests**: Critical paths, all CLI commands, <3min total
- **Fault Injection**: State management, simulate crashes, verify recovery

## Velocity Tracking

### Recommended Daily Process

1. **Morning**: Review day's planned tasks from iteration-details-construction.md
2. **During**: Track actual hours per task
3. **Evening**: Update CSV with status and actuals
4. **Blockers**: Document and escalate same-day if critical

### Weekly Retrospective

Use template from [iteration-details-construction.md](./iteration-details-construction.md):
- What went well
- What could improve
- Key decisions
- Surprises/discoveries
- Recommendations for next week

### Metrics to Track

- **Story velocity**: Completed issues / planned issues (target ≥90%)
- **Hour accuracy**: Actual / estimated hours (target 0.8-1.2)
- **Test coverage trend**: Current / target (target ≥80% by Week 7)
- **Bug discovery rate**: Bugs found / issues completed (target <0.5)
- **Scope creep**: Unplanned work / total work (target <10%)

## Success Criteria

### Construction Phase Complete When:

**Functionality**:
- [ ] All P1 issues (6/6) complete
- [ ] All P2 issues (6/6) complete
- [ ] All P3 issues (4/4) complete
- [ ] Selected P4 issues (2-3/6) complete

**Quality**:
- [ ] Test coverage ≥80%
- [ ] No critical bugs
- [ ] Performance targets met (smoke <2min, quick <20min)
- [ ] Security validated (sandbox tested)

**Documentation**:
- [ ] User documentation complete
- [ ] Developer documentation complete
- [ ] API documentation complete
- [ ] Troubleshooting guide complete

**Operational Readiness**:
- [ ] CI/CD functional
- [ ] Logging production-ready
- [ ] Error handling comprehensive
- [ ] Observability implemented

## Next Steps

1. **If starting Inception**: Read [phase-plan-inception.md](./phase-plan-inception.md)
2. **If starting Construction Week 4**: Read [iteration-plan-construction.md](./iteration-plan-construction.md) and [iteration-details-construction.md](./iteration-details-construction.md)
3. **Daily**: Update [iteration-plan-week4.csv](./iteration-plan-week4.csv) (or current week)
4. **Weekly**: Conduct retrospective, review gate criteria
5. **Issues**: Document in risk register, escalate if blocking

## Questions?

Refer to:
- [PLANNING.md](/home/roctinam/dev/matric-eval/PLANNING.md) for architectural questions
- [ROADMAP.md](/home/roctinam/dev/matric-eval/ROADMAP.md) for feature questions
- [iteration-details-construction.md](./iteration-details-construction.md) for implementation questions
- [phase-plan-inception.md](./phase-plan-inception.md) for getting started

---

**Document Status**: Complete
**Last Review**: 2026-01-24
**Next Review**: Start of each phase
