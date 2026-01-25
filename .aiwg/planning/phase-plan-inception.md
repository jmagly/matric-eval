# Inception Phase Plan - matric-eval

**Document Type**: Phase Plan - Inception
**Project**: matric-eval - Consolidated Model Evaluation Framework
**Profile**: Production (6-8 weeks timeline)
**Phase Duration**: 1 week (Week 1)
**Generated**: 2026-01-24

## Phase Overview

The Inception phase establishes the foundational viability of matric-eval. This is a critical validation phase where we confirm our technical approach (Inspect AI framework), verify the P0 checkpoint/resume requirement is achievable, and establish the architectural direction for the entire project.

**Primary Goal**: Validate that Inspect AI + Ollama integration can meet our resilience requirements, particularly checkpoint/resume capability.

**Success Definition**: By end of Inception, we have working prototype demonstrating checkpoint/resume with at least one benchmark (HumanEval), clear architecture documented, and high-confidence that Production profile targets are achievable.

## Phase Objectives

### 1. Vision Alignment
- Confirm consolidation strategy addresses pain points from matric-cli and matric-memory
- Validate that Python-core with language bindings architecture meets both projects' needs
- Establish shared understanding of evaluation workflow (DISCOVER → PUBLIC → RANK → CUSTOM → CONFIG)

### 2. Risk Identification & Mitigation
- **CRITICAL BLOCKER**: Validate Inspect AI supports checkpoint/resume (or can be extended)
- Identify framework limitations that might force fallback to lm-eval-harness
- Assess Ollama integration stability and error handling patterns
- Document recovery scenarios and required state management

### 3. Architecture Direction
- Define state management structure for checkpoint/resume
- Establish results directory layout and metadata schema
- Document core abstractions (Task, Scorer, Solver, State)
- Create initial ADR for framework selection (Inspect AI vs alternatives)

### 4. Scope Refinement
- Confirm v1.0 scope boundaries (8 public benchmarks, checkpoint/resume, smoke/quick/full tiers)
- Defer custom tests and language bindings to Elaboration/Construction
- Establish clear gate criteria for moving to Elaboration phase

## Key Activities

| Activity | Owner | Duration | Deliverable | Status |
|----------|-------|----------|-------------|--------|
| **A1: Environment Setup** | Developer | 0.5 days | Working Python project with uv, mypy, ruff configured | Not Started |
| **A2: Inspect AI Prototype** | Developer | 1 day | Proof-of-concept running HumanEval on one Ollama model | Not Started |
| **A3: Checkpoint/Resume Validation** | Developer | 1.5 days | Working checkpoint/resume implementation with state persistence | Not Started |
| **A4: Error Handling Research** | Developer | 0.5 days | Catalog Ollama error modes (EPIPE, timeout, connection reset) | Not Started |
| **A5: Architecture Documentation** | Developer | 1 day | Initial SAD with state management design, directory structure | Not Started |
| **A6: ADR: Framework Selection** | Developer | 0.5 days | ADR #1 documenting Inspect AI choice and alternatives considered | Not Started |
| **A7: Risk Assessment** | Developer | 0.5 days | Documented risks with mitigation strategies | Not Started |
| **A8: Iteration Plan** | Developer | 0.5 days | Elaboration phase plan with detailed iteration breakdown | Not Started |

**Total Effort**: 6 days (with buffer fits in 1-week Inception phase)

## Deliverables Checklist

### Required Deliverables (Gate Blockers)

- [ ] **D1: Working Prototype**
  - Python project initialized with uv package management
  - HumanEval benchmark running against Ollama model (e.g., llama3.2:3b)
  - At least 5 test samples execute successfully
  - Results captured to structured output (JSON)

- [ ] **D2: Checkpoint/Resume Proof**
  - State persistence after each problem evaluation
  - Ability to interrupt run (Ctrl+C) and resume from checkpoint
  - Gap detection identifies incomplete work
  - Results directory structure (`results/run-{timestamp}/`) established

- [ ] **D3: Initial Architecture Document**
  - State management design (meta.json, state.json schema)
  - Results directory layout and file organization
  - Core evaluation workflow diagram
  - Error recovery strategy

- [ ] **D4: ADR #1 - Framework Selection**
  - Inspect AI chosen with rationale
  - Alternatives considered (lm-eval-harness, custom framework)
  - Checkpoint/resume capability validated
  - Ollama integration pattern documented

- [ ] **D5: Risk Register**
  - Top 5-10 risks identified and prioritized
  - Mitigation strategies for critical risks
  - Contingency plans (e.g., fallback to lm-eval-harness)
  - Technical dependencies documented

### Recommended Deliverables (Elaboration Input)

- [ ] **D6: Test Strategy Outline**
  - Unit test approach (pytest)
  - Integration test scope (end-to-end evaluation runs)
  - State management test scenarios (crash recovery, gap detection)
  - Coverage targets by component

- [ ] **D7: Initial Project Plan**
  - Elaboration phase iteration plan (Week 2-3)
  - Construction phase iteration plan (Week 4-6)
  - Transition phase plan (Week 7-8)
  - Key milestones and dependencies

- [ ] **D8: Technical Spike Results**
  - Inspect AI capabilities and limitations documented
  - Ollama error handling patterns cataloged
  - Performance baseline (time per problem, throughput)
  - Resource requirements (memory, disk, CPU)

## Success Criteria

The Inception phase is complete when ALL of the following criteria are met:

### Technical Validation

1. **Framework Viability**: Inspect AI successfully runs at least one public benchmark (HumanEval) against Ollama model with accurate scoring
2. **Checkpoint/Resume Works**: Demonstrated ability to interrupt and resume evaluation with zero data loss and <5 second resume latency
3. **State Management Solid**: Results directory structure supports gap detection and selective re-run scenarios
4. **Error Recovery Path**: Documented error classification and retry strategy for transient failures (EPIPE, timeout, connection reset)

### Documentation Quality

5. **Architecture Clear**: SAD provides sufficient detail for solo developer to proceed confidently into Elaboration
6. **Risks Known**: Top risks identified with mitigation strategies; no critical unknowns blocking Elaboration
7. **ADR Complete**: Framework selection decision documented with rationale and alternatives

### Scope Clarity

8. **v1.0 Boundaries Set**: Clear agreement on what's in (8 public benchmarks, checkpoint/resume, 3 tiers) and out (custom tests, bindings, multi-dimensional scoring)
9. **Iteration Plan Ready**: Elaboration phase broken into actionable iteration plans with concrete deliverables
10. **Gate Criteria Defined**: Elaboration phase success criteria established

## Timeline

**Total Duration**: 1 week (5 working days)

### Day 1-2: Foundation & Prototype
- **Monday AM**: Environment setup (Python project, uv, dependencies)
- **Monday PM**: Inspect AI integration research and initial setup
- **Tuesday AM**: HumanEval prototype implementation
- **Tuesday PM**: First successful evaluation run against Ollama model

### Day 3-4: Checkpoint/Resume Validation (P0 BLOCKER)
- **Wednesday AM**: State management design and implementation
- **Wednesday PM**: Checkpoint writing after each problem
- **Thursday AM**: Resume logic and gap detection
- **Thursday PM**: Interrupt/resume testing and validation

### Day 5: Documentation & Planning
- **Friday AM**: Architecture documentation and ADR writing
- **Friday PM**: Risk assessment, iteration planning, gate review

## Risk Management

### Critical Risks (Phase Blockers)

| Risk ID | Risk Description | Impact | Probability | Mitigation Strategy |
|---------|------------------|--------|-------------|---------------------|
| **R1** | Inspect AI does not support checkpoint/resume | CRITICAL | Medium | Prototype in first 3 days. If inadequate, evaluate lm-eval-harness or build custom state layer on top of Inspect AI |
| **R2** | Ollama integration unstable (frequent EPIPE, timeouts) | HIGH | Medium | Implement retry logic with exponential backoff. Document error patterns and auto-recovery. Consider Ollama version pinning. |
| **R3** | HumanEval scoring differs from matric-cli baseline | MEDIUM | High | Document scoring methodology. Expect some variance due to framework differences. Establish acceptable tolerance (<10%). |
| **R4** | State management complexity exceeds solo developer capacity | MEDIUM | Low | Start with simplest viable design (JSON files, no locks). Defer optimizations (atomic writes, heartbeats) to Elaboration if needed. |
| **R5** | Performance too slow for practical use (>5 min for smoke tier) | MEDIUM | Low | Profile early. If slow, investigate parallel execution or sampling optimizations in Elaboration. |

### Phase-Specific Mitigations

**Checkpoint/Resume Validation** (R1 - CRITICAL):
- **Timeline**: Must validate by Day 4 (Wednesday EOD)
- **Success Criteria**: Interrupt run mid-evaluation, resume with `--resume run-{id}`, verify no duplicate work
- **Fallback Plan**: If Inspect AI lacks native support, implement custom state wrapper. If that fails, consider lm-eval-harness or custom framework (extends timeline by 1-2 weeks).

**Ollama Stability** (R2 - HIGH):
- **Research**: Catalog error modes during prototype testing
- **Strategy**: Classify errors as retryable (network, timeout) vs fatal (bad model, syntax error)
- **Implementation**: Retry logic with max 3 attempts, exponential backoff (1s, 2s, 4s)

## Dependencies

### External Dependencies
- **Ollama**: Local Ollama instance running with at least one model installed (llama3.2:3b recommended for testing)
- **Python 3.11+**: Modern Python for type hints and async support
- **Inspect AI Framework**: Installation and compatibility validation
- **HumanEval Dataset**: Access to dataset (available in inspect-evals package)

### Internal Dependencies
- **matric-cli**: Reference implementation for evaluation workflow and scoring logic
- **matric-memory**: Future integration target for custom tests (not blocking Inception)
- **Public Datasets**: Access to `/home/roctinam/data/evals/` for benchmark data

### Knowledge Dependencies
- **Inspect AI Documentation**: Framework capabilities, API patterns, checkpoint support
- **Ollama API**: Error codes, timeout behavior, model management
- **HumanEval Specification**: Scoring methodology, test format, expected outputs

## Transition Criteria to Elaboration

The Inception phase gates to Elaboration when:

1. **All Required Deliverables Complete**: D1-D5 checked off with evidence (working code, documentation artifacts)
2. **P0 Risk Mitigated**: Checkpoint/resume demonstrated working (R1 resolved)
3. **Technical Confidence High**: No critical unknowns that would block implementation in Elaboration
4. **Architecture Approved**: Solo developer signs off on SAD and state management design
5. **Iteration Plan Ready**: Elaboration phase plan exists with concrete milestones

**Gate Review**: End of Day 5 (Friday), self-review checklist:
- Can I resume an interrupted evaluation run?
- Do I understand the state management design well enough to implement remaining benchmarks?
- Are there any showstopper risks I haven't addressed?
- Is the iteration plan for Elaboration actionable and realistic?

If any answer is "No", extend Inception by 1-2 days to resolve before proceeding.

## Elaboration Phase Preview

**Elaboration Goals** (Week 2-3):
1. Implement remaining 7 public benchmarks (MBPP, GSM8K, ARC, IFEval, DS-1000, LiveCodeBench, MT-Bench)
2. Build smoke/quick/full tier sampling with seeded reproducibility
3. Implement error recovery logic (retry, graceful degradation)
4. Achieve 40%+ test coverage on core evaluation and state management
5. Complete gap detection and selective re-run commands

**Elaboration Deliverables**:
- All 8 public benchmarks operational
- CLI with --tier, --resume, --validate, --fill-gaps commands
- Integration tests for checkpoint/resume scenarios
- Performance baseline established (smoke tier <2 min)

**Elaboration Gate Criteria**:
- Smoke tier runs successfully on 3+ models in <2 minutes
- Resume from checkpoint works across all benchmarks
- Gap detection accurately identifies incomplete work
- Test coverage reaches 40%+ with state management at 80%+

## Communication Plan

**Stakeholders** (Solo Developer Project):
- **Developer**: Primary role, accountable for all deliverables
- **matric-cli Maintainer**: Inform of progress, validate requirements
- **matric-memory Maintainer**: Inform of architecture decisions

**Status Updates**:
- **Daily**: Update task checklist in this document or project tracker
- **End of Phase**: Gate review self-assessment, document lessons learned
- **Blocker Escalation**: If R1 (checkpoint/resume) fails, document decision on fallback approach

**Artifacts Location**:
- **Code**: `/home/roctinam/dev/matric-eval/src/matric_eval/`
- **Documentation**: `/home/roctinam/dev/matric-eval/.aiwg/planning/`
- **ADRs**: `/home/roctinam/dev/matric-eval/.aiwg/adrs/`
- **Test Results**: `/home/roctinam/dev/matric-eval/results/inception-prototype/`

## Lessons Learned (Post-Phase Capture)

**To be completed at end of Inception phase:**

### What Went Well
- TBD

### What Could Improve
- TBD

### Key Decisions
- TBD

### Surprises / Discoveries
- TBD

### Recommendations for Next Phase
- TBD

## References

- [PLANNING.md](/home/roctinam/dev/matric-eval/PLANNING.md) - Overall project architecture and decisions
- [ROADMAP.md](/home/roctinam/dev/matric-eval/ROADMAP.md) - Parity goals and feature roadmap
- [Solution Profile](/home/roctinam/dev/matric-eval/.aiwg/intake/solution-profile.md) - Production profile justification
- [Inspect AI Documentation](https://inspect.aisi.org.uk/) - Framework reference
- [matric-cli Evaluation Code](/home/roctinam/dev/matric-cli/source/eval/) - Reference implementation

---

**Phase Status**: NOT STARTED
**Last Updated**: 2026-01-24
**Next Review**: End of Day 5 (Gate Review)
