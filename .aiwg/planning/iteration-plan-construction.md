# Construction Phase Plan - matric-eval

**Document Type**: Phase Plan - Construction
**Project**: matric-eval - Consolidated Model Evaluation Framework
**Profile**: Production (80%+ test coverage required)
**Phase Duration**: 4 weeks (Weeks 4-7)
**Generated**: 2026-01-24

## Phase Overview

The Construction phase delivers production-ready evaluation capabilities. This is the main implementation phase where we build all 8 public benchmarks, custom matric tests, advanced features, and operational excellence capabilities to achieve a robust, fault-tolerant evaluation framework.

**Primary Goal**: Implement complete evaluation pipeline with 80%+ test coverage, checkpoint/resume, tiered execution, and comprehensive scoring.

**Success Definition**: By end of Construction, we have production-quality codebase supporting smoke/quick/full tiers across 8+ benchmarks, custom matric tests, tool calling evaluation, and comprehensive CI/CD pipeline.

## Construction Strategy

### Incremental Value Delivery

Each iteration delivers working, testable functionality:
- **Week 4 (P1)**: Critical foundation - public benchmarks, tiered CLI, core scoring
- **Week 5 (P2)**: Advanced features - custom tests, tool calling, LLM-as-judge
- **Week 6 (P3)**: Operational excellence - resilience, parallelization, CI/CD
- **Week 7 (P4)**: Extended features - subset selection based on velocity

### Risk Mitigation Through Prioritization

P1 issues establish the MVP functionality. If timeline pressures emerge, P4 issues can be deferred to post-v1.0 releases while maintaining a production-ready system.

### Test Coverage Strategy

- **Unit Tests**: 90%+ coverage for scorers, state management, utilities
- **Integration Tests**: 70%+ coverage for end-to-end evaluation flows
- **Smoke Tests**: 100% of CLI commands and major workflows
- **Overall Target**: 80%+ per Production profile requirements

## Iteration Breakdown

### Iteration 1 (Week 4): Critical Foundation - P1 Issues

**Theme**: "Foundation for Evaluation Excellence"

**Duration**: 5 days (40 hours)

**Issues**: 6 issues totaling ~38 estimated hours

**Objectives**:
1. Implement production-grade code execution scoring with sandboxing
2. Integrate inspect-evals for HumanEval, MBPP, GSM8K, ARC
3. Build custom scorers for IFEval, LiveCodeBench, DS-1000
4. Deliver tiered CLI (smoke/quick/full) with model discovery
5. Achieve 85%+ test coverage on all P1 deliverables

**Acceptance Criteria**:
- All 8 public benchmarks execute successfully against Ollama models
- Smoke tier completes in <2 minutes with 5 samples per benchmark
- Quick tier completes in <20 minutes with 75 samples per benchmark
- Code execution scoring works with Docker sandbox isolation
- IFEval constraint checking validates all instruction-following scenarios
- LiveCodeBench handles competitive programming problems with time limits
- DS-1000 evaluates data science code with environment setup
- CLI supports --tier, --model, --benchmark, --output flags
- Test coverage ≥85% for all P1 code

**Risk Areas**:
- Docker sandbox setup complexity
- IFEval constraint parsing accuracy
- LiveCodeBench runtime environment dependencies
- DS-1000 library compatibility issues

**Mitigation**: Start with simpler benchmarks (HumanEval, MBPP), defer complex scorers to mid-iteration once patterns established.

---

### Iteration 2 (Week 5): Advanced Features - P2 Issues

**Theme**: "Custom Intelligence and Multi-Turn Evaluation"

**Duration**: 5 days (40 hours)

**Issues**: 6 issues totaling ~42 estimated hours

**Objectives**:
1. Port 282 custom matric tests from matric-cli and matric-memory
2. Implement tool calling evaluation with 6 scenarios
3. Build MT-Bench multi-turn evaluation with LLM-as-judge
4. Create 5-dimensional scoring framework
5. Port matric-memory LLM-as-Judge templates
6. Develop universal LLM-as-Judge with agentic support

**Acceptance Criteria**:
- All 282 matric custom tests operational with appropriate scorers
- Tool calling evaluation validates correct tool selection and parameters
- MT-Bench runs 80 multi-turn conversations with judge scoring
- 5D scoring captures correctness, efficiency, safety, helpfulness, reasoning
- LLM-as-Judge templates support configurable grading criteria
- Agentic evaluation handles multi-step reasoning and tool use
- Test coverage ≥80% for all P2 code
- Custom scorers validated against matric-cli/matric-memory baselines

**Risk Areas**:
- Custom test data migration and format consistency
- LLM-as-Judge reliability and scoring variance
- Multi-turn state management complexity
- Tool calling sandbox security

**Mitigation**: Validate custom test format with 10% sample first, iterate on scorers before full migration.

---

### Iteration 3 (Week 6): Operational Excellence - P3 Issues

**Theme**: "Production Resilience and Scale"

**Duration**: 5 days (40 hours)

**Issues**: 4 issues totaling ~32 estimated hours

**Objectives**:
1. Implement checkpoint/resume with gap detection
2. Enable parallel model evaluation for throughput
3. Build CI/CD pipeline with smoke tests on every PR
4. Create comprehensive logging and observability

**Acceptance Criteria**:
- Checkpoint/resume works across all benchmarks with zero data loss
- Gap detection identifies incomplete work and enables selective re-run
- Parallel evaluation reduces total runtime by 50%+ for multi-model runs
- CI/CD runs smoke tests in <3 minutes, blocks PRs on failure
- Logging captures all evaluation events with structured metadata
- Observability dashboard shows real-time progress and metrics
- Test coverage ≥90% for state management and recovery logic
- Fault injection tests validate resilience scenarios

**Risk Areas**:
- Parallel execution race conditions
- Checkpoint state consistency across interruptions
- CI/CD resource constraints (Docker, Ollama)
- Logging performance overhead

**Mitigation**: Implement file locking for state writes, use CI caching for dependencies, make logging configurable.

---

### Iteration 4 (Week 7): Extended Features - P4 Selected Subset

**Theme**: "Enhanced Usability and Insights"

**Duration**: 5 days (40 hours)

**Issues**: 2-3 selected from 6 available P4 issues (~25 estimated hours)

**Selection Criteria**: Choose based on velocity from Weeks 4-6 and stakeholder priority

**Recommended Subset**:
1. **#18: Model recommendation engine** (10h) - Highest ROI for end users
2. **#13 partial: Extended reporting** (8h) - Completion of P3 observability work
3. **#16 partial: TypeScript bindings** (7h) - Enable matric-cli integration

**Deferred to Post-v1.0**:
- #15: Leaderboard dashboard (nice-to-have, not critical for v1.0)
- #17: SWE-bench/GPQA (extended benchmarks, can add incrementally)
- #19: Contamination detection (research-grade feature, not MVP)
- #20: Historical trend analysis (requires multiple evaluation runs over time)

**Acceptance Criteria** (for selected issues):
- Model recommendation engine generates config based on evaluation results
- Extended reporting includes comparison tables and trend visualizations
- TypeScript bindings enable matric-cli to invoke evaluations programmatically
- Test coverage ≥75% for all P4 code
- Documentation updated with usage examples

**Risk Areas**:
- Recommendation algorithm accuracy
- Bindings API stability
- Scope creep if trying to do too much

**Mitigation**: Time-box each P4 issue to estimated hours, cut scope if exceeding.

---

## Cumulative Metrics

### Estimated Effort by Iteration

| Iteration | Week | Issues | Est. Hours | Available Hours | Buffer |
|-----------|------|--------|------------|-----------------|--------|
| 1 | Week 4 | 6 (P1) | 38 | 40 | 2h (5%) |
| 2 | Week 5 | 6 (P2) | 42 | 40 | -2h (overflow) |
| 3 | Week 6 | 4 (P3) | 32 | 40 | 8h (20%) |
| 4 | Week 7 | 2-3 (P4) | 25 | 40 | 15h (37%) |
| **Total** | **4 weeks** | **18-19** | **137** | **160** | **23h (14%)** |

**Velocity Assumption**: 8 hours productive work per day, 5 days per week = 40 hours per iteration.

**Buffer Strategy**: Week 2 has slight overflow (-2h) but compensated by Week 3 (+8h) and Week 4 (+15h). Overall 14% buffer is healthy for Production profile.

### Test Coverage Progression

| Iteration | Unit Tests | Integration Tests | Overall Target |
|-----------|------------|-------------------|----------------|
| 1 | 90% | 70% | 85% |
| 2 | 85% | 70% | 80% |
| 3 | 95% | 80% | 90% |
| 4 | 80% | 70% | 75% |
| **Final** | **87%** | **72%** | **82%** |

**Validation**: Exceeds Production profile requirement of 80%+ overall coverage.

### Feature Completeness by Iteration

| Feature Category | Week 4 | Week 5 | Week 6 | Week 7 |
|------------------|--------|--------|--------|--------|
| Public Benchmarks | 100% | 100% | 100% | 100% |
| Custom Tests | 0% | 100% | 100% | 100% |
| Tool Calling | 0% | 100% | 100% | 100% |
| LLM-as-Judge | 0% | 100% | 100% | 100% |
| Checkpoint/Resume | Partial | Partial | 100% | 100% |
| Parallel Execution | 0% | 0% | 100% | 100% |
| CI/CD | 0% | 0% | 100% | 100% |
| Recommendations | 0% | 0% | 0% | 100% |
| Bindings | 0% | 0% | 0% | Partial |

## Risk Management

### Construction Phase Risks

| Risk ID | Description | Impact | Probability | Iteration | Mitigation |
|---------|-------------|--------|-------------|-----------|------------|
| **C1** | Code execution sandbox security vulnerabilities | HIGH | Medium | Week 4 | Use Docker isolation, restrict network, memory limits, timeout enforcement |
| **C2** | LLM-as-Judge scoring variance/unreliability | MEDIUM | High | Week 5 | Use multiple judges, temperature=0, validation against human baselines |
| **C3** | Checkpoint state corruption on crash | HIGH | Low | Week 6 | Atomic writes, temp files, validation checksums |
| **C4** | Parallel execution deadlocks/race conditions | MEDIUM | Medium | Week 6 | File locks, process isolation, atomic operations |
| **C5** | Test coverage slips below 80% | MEDIUM | Medium | All | Daily coverage reports, gate PR merges on coverage threshold |
| **C6** | P4 scope creep extends timeline | MEDIUM | Medium | Week 7 | Strict time-boxing, defer non-essential features to v1.1 |

### Contingency Plans

**If Week 5 overruns by >4 hours**:
- Defer #22 (Universal LLM-as-Judge) to P4
- Simplify 5D scoring to 3D initially
- Reduce custom test port to 200/282 (prioritize most important)

**If test coverage falls below 80% by Week 6**:
- Dedicate Week 7 Day 1-2 to test writing
- Defer P4 features to post-v1.0
- Focus on state management and scorer coverage (highest risk areas)

**If CI/CD setup blocked by infrastructure**:
- Document manual testing procedures
- Defer full CI to Transition phase
- Ensure local smoke tests work reliably

## Dependencies

### External Dependencies
- **Inspect AI Framework**: Core evaluation engine, must remain stable
- **Ollama**: Model serving, must handle concurrent requests for parallel execution
- **Docker**: Sandbox isolation for code execution
- **Public Datasets**: HumanEval, MBPP, GSM8K, etc. availability
- **Judge Models**: Ollama models for LLM-as-judge scoring (llama3.1:8b+)

### Inter-Iteration Dependencies
- **Week 4 → Week 5**: Public benchmark infrastructure must work before custom tests
- **Week 5 → Week 6**: LLM-as-judge patterns established before CI automation
- **Week 6 → Week 7**: Checkpoint/resume must be solid before recommendations
- **Week 4 → Week 7**: Core CLI must be stable before bindings

### Critical Path
1. Code execution scoring (Week 4) → Tool calling evaluation (Week 5)
2. Tiered CLI (Week 4) → Parallel execution (Week 6) → CI/CD (Week 6)
3. Core scorers (Week 4) → 5D scoring (Week 5) → Recommendations (Week 7)
4. State management (Week 4) → Checkpoint/resume (Week 6) → Gap detection (Week 6)

## Quality Gates

### Iteration Gate Criteria

Each iteration must meet these criteria before proceeding:

**Week 4 Gate**:
- [ ] All 8 public benchmarks passing smoke tests
- [ ] Code execution scoring validated with ≥95% accuracy vs matric-cli
- [ ] Test coverage ≥85%
- [ ] No critical bugs in CLI or state management
- [ ] Documentation updated for all new features

**Week 5 Gate**:
- [ ] Custom matric tests migrated and passing
- [ ] Tool calling evaluation works for all 6 scenarios
- [ ] MT-Bench completes 80 multi-turn evaluations
- [ ] LLM-as-Judge variance <15% across multiple runs
- [ ] Test coverage ≥80%

**Week 6 Gate**:
- [ ] Checkpoint/resume demonstrated with zero data loss
- [ ] Parallel execution reduces runtime by ≥50%
- [ ] CI/CD runs smoke tests in <3 minutes
- [ ] Logging captures all critical events
- [ ] Test coverage ≥90% for state management
- [ ] Fault injection tests passing

**Week 7 Gate** (Construction → Transition):
- [ ] All selected P4 issues complete
- [ ] Overall test coverage ≥80%
- [ ] No P1/P2 critical bugs remaining
- [ ] Documentation complete for all features
- [ ] Performance meets targets (smoke <2min, quick <20min)

## Communication Plan

### Status Updates
- **Daily**: Update CSV iteration plans with status
- **Weekly**: Iteration retrospective, update risk register
- **End of Phase**: Construction completion report, lessons learned

### Deliverables Review
- **Code Reviews**: Self-review all PRs before merge
- **Test Reviews**: Validate coverage reports weekly
- **Documentation Reviews**: Update docs with each feature

### Escalation Path
- **Issue exceeds estimate by >50%**: Re-estimate, adjust scope or defer
- **Critical bug discovered**: Pause feature work, fix immediately
- **Test coverage falls below 75%**: Stop new features, write tests

## Success Criteria

The Construction phase is complete when ALL of the following criteria are met:

### Functionality
1. **All P1 issues (6/6) complete**: Public benchmarks operational with production-grade scoring
2. **All P2 issues (6/6) complete**: Custom tests, tool calling, LLM-as-judge working
3. **All P3 issues (4/4) complete**: Checkpoint/resume, parallelization, CI/CD operational
4. **Selected P4 issues (2-3/6) complete**: Recommendations and/or bindings delivered

### Quality
5. **Test Coverage ≥80%**: Overall codebase meets Production profile requirement
6. **No Critical Bugs**: All P1/P2 issues validated and stable
7. **Performance Targets Met**: Smoke <2min, Quick <20min, Full <4hrs for 10 models
8. **Security Validated**: Code execution sandbox tested, no privilege escalation

### Documentation
9. **User Documentation**: CLI usage, configuration, interpretation guides
10. **Developer Documentation**: Architecture, scorer development, extension patterns
11. **API Documentation**: All public APIs documented with examples
12. **Troubleshooting Guide**: Common issues and solutions

### Operational Readiness
13. **CI/CD Functional**: Automated testing on every PR
14. **Logging Production-Ready**: Structured logs with appropriate levels
15. **Error Handling Comprehensive**: Graceful degradation, retry logic, clear error messages
16. **Observability**: Progress tracking, metrics collection, result visualization

## Transition Phase Preview

**Transition Goals** (Week 8):
1. End-to-end testing with real matric-cli and matric-memory integration
2. Performance optimization and benchmarking
3. User acceptance testing with stakeholders
4. Documentation finalization and examples
5. Deployment preparation and release planning

**Transition Deliverables**:
- Integration test suite passing for matric-cli and matric-memory
- Performance benchmarks documented
- User guide and tutorial videos
- v1.0 release candidate tagged
- Migration guide from matric-cli eval code

**Transition Gate Criteria**:
- End-to-end tests passing with zero failures
- Performance within 10% of targets
- Documentation reviewed and approved
- No critical or high-priority bugs
- Stakeholder sign-off

## Lessons Learned Process

At the end of each iteration, capture:

### What Went Well
- Specific achievements that exceeded expectations
- Techniques or approaches that worked particularly well
- Areas where estimates were accurate

### What Could Improve
- Challenges encountered and how they were resolved
- Areas where estimates were significantly off
- Process improvements for next iteration

### Key Decisions
- Major technical decisions made
- Scope changes or priority adjustments
- Architecture or design changes

### Surprises / Discoveries
- Unexpected issues or complications
- Positive surprises or easier-than-expected work
- New insights about the domain or framework

### Recommendations for Next Iteration
- Specific adjustments to process or approach
- Risk areas to monitor closely
- Opportunities to leverage

## References

- [PLANNING.md](/home/roctinam/dev/matric-eval/PLANNING.md) - Overall architecture
- [ROADMAP.md](/home/roctinam/dev/matric-eval/ROADMAP.md) - Feature roadmap
- [Phase Plan: Inception](/home/roctinam/dev/matric-eval/.aiwg/planning/phase-plan-inception.md)
- [Phase Plan: Elaboration](/home/roctinam/dev/matric-eval/.aiwg/planning/phase-plan-elaboration.md)
- [Iteration Plan: Week 4](/home/roctinam/dev/matric-eval/.aiwg/planning/iteration-plan-week4.csv)
- [Iteration Plan: Week 5](/home/roctinam/dev/matric-eval/.aiwg/planning/iteration-plan-week5.csv)
- [Iteration Plan: Week 6](/home/roctinam/dev/matric-eval/.aiwg/planning/iteration-plan-week6.csv)
- [Iteration Plan: Week 7](/home/roctinam/dev/matric-eval/.aiwg/planning/iteration-plan-week7.csv)

---

**Phase Status**: NOT STARTED
**Last Updated**: 2026-01-24
**Next Review**: End of Week 4 (Iteration 1 Gate Review)
