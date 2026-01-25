# Construction Phase - Executive Summary

**Project**: matric-eval
**Phase**: Construction (Weeks 4-7)
**Duration**: 4 weeks (160 hours)
**Estimated Effort**: 137 hours (18-19 issues)
**Buffer**: 23 hours (14%)
**Target Test Coverage**: 82% (exceeds 80% Production requirement)

## Visual Timeline

```
Week 4: CRITICAL FOUNDATION (P1)                     38h / 40h available
├─ #1  Code execution scoring                        8h  [========] 90% coverage
├─ #2  Integrate inspect-evals                       6h  [======  ] 85% coverage
├─ #3  IFEval constraint checking                    7h  [=======] 90% coverage
├─ #4  LiveCodeBench scorer                          6h  [======  ] 85% coverage
├─ #5  DS-1000 scorer                                5h  [=====   ] 85% coverage
└─ #6  Tiered CLI                                    6h  [======  ] 90% coverage
    Gate: ✓ All benchmarks passing ✓ Coverage ≥85% ✓ Smoke tier <2min

Week 5: ADVANCED FEATURES (P2)                       42h / 40h available
├─ #7  Port 282 custom matric tests                  8h  [========] 80% coverage
├─ #8  Tool calling evaluation                       7h  [=======] 85% coverage
├─ #9  MT-Bench with LLM-as-judge                    8h  [========] 75% coverage
├─ #10 5D scoring framework                          6h  [======  ] 85% coverage
├─ #21 Port LLM-as-Judge templates                   6h  [======  ] 80% coverage
└─ #22 Universal LLM-as-Judge                        7h  [=======] 75% coverage
    Gate: ✓ Custom tests migrated ✓ Coverage ≥80% ✓ Judge variance <15%

Week 6: OPERATIONAL EXCELLENCE (P3)                  32h / 40h available
├─ #11 Checkpoint/resume                            10h  [==========] 95% coverage
├─ #12 Parallel model evaluation                     8h  [========  ] 85% coverage
├─ #13 CI/CD pipeline                                8h  [========  ] 90% coverage
└─ #14 Logging and observability                     6h  [======    ] 85% coverage
    Gate: ✓ Checkpoint works ✓ CI <3min ✓ Coverage ≥90% state mgmt

Week 7: EXTENDED FEATURES (P4 Selected)              25h / 40h available
├─ #18    Model recommendation engine               10h  [==========] 80% coverage
├─ #13EXT Extended reporting                         8h  [========  ] 75% coverage
└─ #16P   TypeScript bindings (partial)              7h  [=======   ] 70% coverage
    Deferred: #15 Leaderboard, #17 Extended benchmarks, #19 Contamination, #20 Trends
    Gate: ✓ All selected complete ✓ Coverage ≥80% overall ✓ Ready for Transition
```

## Issue Distribution

### By Priority
- **P1 (Week 4)**: 6 issues - Critical foundation, must complete
- **P2 (Week 5)**: 6 issues - Advanced features, must complete
- **P3 (Week 6)**: 4 issues - Operational excellence, must complete
- **P4 (Week 7)**: 3 selected, 4 deferred - Enhanced usability, flexible scope

### By Category
- **Benchmarks & Scoring**: 11 issues (#1-5, #7, #9-10, #21-22)
- **Infrastructure**: 4 issues (#6, #11-12, #14)
- **CI/CD & Testing**: 1 issue (#13)
- **Usability**: 3 issues (#18, #13-EXT, #16-PARTIAL)

## Effort Distribution

| Week | Issues | Estimated | Available | Buffer | Utilization |
|------|--------|-----------|-----------|--------|-------------|
| 4 | 6 | 38h | 40h | +2h (5%) | 95% |
| 5 | 6 | 42h | 40h | -2h (-5%) | 105% |
| 6 | 4 | 32h | 40h | +8h (20%) | 80% |
| 7 | 3 | 25h | 40h | +15h (37%) | 62% |
| **Total** | **19** | **137h** | **160h** | **+23h (14%)** | **86%** |

**Analysis**: Week 5 has slight overflow compensated by Week 6-7 buffer. Overall healthy 14% buffer.

## Test Coverage Breakdown

| Component | Week 4 | Week 5 | Week 6 | Week 7 | Final |
|-----------|--------|--------|--------|--------|-------|
| Scorers | 90% | 85% | - | 80% | 87% |
| State Management | - | - | 95% | - | 95% |
| CLI | 90% | - | - | 70% | 85% |
| Custom Features | - | 80% | - | 75% | 78% |
| **Overall** | **85%** | **80%** | **90%** | **75%** | **82%** |

**Validation**: Exceeds Production profile requirement of 80% overall coverage.

## Critical Dependencies

### Sequential Dependencies
1. **#1 (Code execution)** → #2, #4, #5 (all execution-based scorers)
2. **#2 (inspect-evals)** → #3, #6, #9 (benchmark infrastructure)
3. **#9 (MT-Bench judge)** → #21, #22 (judge patterns)
4. **#11 (Checkpoint/resume)** → #12 (parallel execution state)
5. **#6 (CLI)** → #13 (CI/CD automation)

### Parallel Opportunities
- Week 4: #3, #4, #5 can start concurrently after #1-#2 complete
- Week 5: #7, #8, #10 independent after Week 4 foundation
- Week 6: #13, #14 independent of #11-#12
- Week 7: All 3 issues can run in parallel

## Risk Summary

| Risk | Week | Impact | Mitigation |
|------|------|--------|------------|
| Sandbox security vulnerabilities | 4 | HIGH | Docker isolation, resource limits, testing |
| LLM-as-judge score variance | 5 | MED | Temperature=0, multiple runs, validation |
| State corruption on crash | 6 | HIGH | Atomic writes, checksums, fault injection tests |
| Parallel execution deadlocks | 6 | MED | File locks, process isolation, timeouts |
| Test coverage slips below 80% | All | MED | Daily tracking, gate PRs, dedicated test time |
| P4 scope creep extends timeline | 7 | MED | Strict time-boxing, defer to v1.1 |

## Gate Criteria Summary

### Week 4 → Week 5 Gate
- [ ] All 8 public benchmarks passing smoke tests
- [ ] Code execution scoring ≥95% accuracy vs matric-cli
- [ ] Test coverage ≥85%
- [ ] No critical bugs in CLI or state management
- [ ] Documentation updated

### Week 5 → Week 6 Gate
- [ ] Custom matric tests migrated and passing
- [ ] Tool calling evaluation works for all 6 scenarios
- [ ] MT-Bench completes 80 multi-turn evaluations
- [ ] LLM-as-Judge variance <15%
- [ ] Test coverage ≥80%

### Week 6 → Week 7 Gate
- [ ] Checkpoint/resume with zero data loss
- [ ] Parallel execution reduces runtime ≥50%
- [ ] CI/CD smoke tests <3 minutes
- [ ] Logging captures all critical events
- [ ] Test coverage ≥90% for state management
- [ ] Fault injection tests passing

### Week 7 → Transition Gate (Construction Complete)
- [ ] All selected P4 issues complete
- [ ] Overall test coverage ≥80%
- [ ] No P1/P2 critical bugs
- [ ] Documentation complete
- [ ] Performance targets met (smoke <2min, quick <20min)

## Key Deliverables

### Week 4 Deliverables
- Production-grade code execution scoring with Docker sandbox
- 8 public benchmarks operational (HumanEval, MBPP, GSM8K, ARC, IFEval, LiveCodeBench, DS-1000, MT-Bench skeleton)
- Tiered CLI with smoke/quick/full modes
- Model discovery and seeded sampling

### Week 5 Deliverables
- 282 custom matric tests migrated and operational
- Tool calling evaluation with 6 scenarios
- MT-Bench multi-turn with LLM-as-judge scoring
- 5-dimensional scoring framework (correctness, efficiency, safety, helpfulness, reasoning)
- LLM-as-judge templates from matric-memory
- Universal judge with agentic support

### Week 6 Deliverables
- Checkpoint/resume with gap detection and selective re-run
- Parallel model evaluation (50%+ runtime reduction)
- CI/CD pipeline with <3 minute smoke tests
- Comprehensive structured logging and observability

### Week 7 Deliverables
- Model recommendation engine (capability → model mapping)
- Extended reporting with comparisons and visualizations
- TypeScript bindings for matric-cli integration

## Success Metrics

### Quantitative
- **Issues Delivered**: 18-19 of 22 (82-86%)
- **Test Coverage**: 82% overall (exceeds 80% requirement)
- **P1-P3 Completion**: 16/16 (100%)
- **Performance**: Smoke <2min, Quick <20min
- **Reliability**: Zero data loss on checkpoint/resume
- **CI Speed**: <3 minutes for smoke tests

### Qualitative
- **Code Quality**: Production-grade scoring, robust error handling
- **Documentation**: User guides, API docs, troubleshooting
- **Maintainability**: Clean architecture, extensible design
- **Security**: Sandboxed execution, validated isolation

## Post-Construction (Transition Phase Preview)

**Week 8 Goals**:
1. End-to-end integration testing with matric-cli and matric-memory
2. Performance optimization and profiling
3. User acceptance testing
4. Documentation finalization
5. v1.0 release preparation

**Deferred to v1.1+**:
- #15: Leaderboard and reporting dashboard
- #17: Extended benchmarks (SWE-bench, GPQA)
- #19: Contamination detection
- #20: Historical trend analysis
- #16 (full): Complete TypeScript bindings
- Rust bindings for matric-memory

## Quick Reference

### File Locations
- **Overview**: [iteration-plan-construction.md](./iteration-plan-construction.md)
- **Detailed Plans**: [iteration-details-construction.md](./iteration-details-construction.md)
- **Week 4 CSV**: [iteration-plan-week4.csv](./iteration-plan-week4.csv)
- **Week 5 CSV**: [iteration-plan-week5.csv](./iteration-plan-week5.csv)
- **Week 6 CSV**: [iteration-plan-week6.csv](./iteration-plan-week6.csv)
- **Week 7 CSV**: [iteration-plan-week7.csv](./iteration-plan-week7.csv)
- **Planning Guide**: [README.md](./README.md)

### Daily Workflow
1. **Morning**: Check current week's detailed plan in iteration-details-construction.md
2. **During**: Track actual hours per task
3. **Evening**: Update CSV with status and actuals
4. **Weekly**: Retrospective, gate review, next week planning

### Escalation
- **Issue >50% over estimate**: Re-estimate, adjust scope or defer
- **Critical bug**: Pause features, fix immediately
- **Coverage <75%**: Stop new features, write tests
- **Gate criteria not met**: Extend iteration, do not proceed

---

**Status**: NOT STARTED
**Created**: 2026-01-24
**Owner**: Developer
**Next Action**: Complete Inception phase before starting Construction
