# AI Agent Assignments: matric-eval v1.0

**Project**: Consolidated Model Evaluation Framework
**Timeline**: 6-8 weeks (4 phases)
**Profile**: Production
**Total Issues**: 22 (6 P1, 6 P2, 4 P3, 6 P4)

---

## Table of Contents

1. [Assignment Philosophy](#assignment-philosophy)
2. [Phase-by-Phase Assignments](#phase-by-phase-assignments)
3. [Issue-by-Issue Assignments](#issue-by-issue-assignments)
4. [Collaboration Patterns](#collaboration-patterns)
5. [Handoff Protocols](#handoff-protocols)
6. [Agent Capacity Planning](#agent-capacity-planning)

---

## Assignment Philosophy

### Guiding Principles

1. **Expertise Matching**: Assign agents based on core competencies and deliverable types
2. **Phase Alignment**: Front-load architecture/design, back-load implementation/deployment
3. **Parallel Work**: Enable concurrent workstreams where dependencies allow
4. **Quality Gates**: Code Reviewer and Test Engineer validate all implementation
5. **Human Oversight**: Lead developer remains final authority on all decisions

### Assignment Notation

- **Primary (P)**: Owns deliverable, accountable for completion
- **Secondary (S)**: Supports primary, provides expertise
- **Reviewer (R)**: Reviews and approves output
- **Informed (I)**: Kept informed of progress and decisions

---

## Phase-by-Phase Assignments

### Phase 1: Inception (Week 1)

**Goal**: Vision alignment, risk identification, architecture direction

| Agent | Role | Responsibilities | Deliverables |
|-------|------|-----------------|--------------|
| **Architecture Designer** (P) | Lead | SAD outline, technology evaluation, risk identification | SAD v0.1, ADR-001 (Inspect AI), architecture vision |
| **Requirements Analyst** (P) | Lead | Use case analysis, NFR baseline, acceptance criteria | Use cases, NFR baseline, requirements matrix |
| **API Designer** (S) | Support | CLI UX design, binding interface concepts | CLI mockups, interface strawman |
| **Lead Developer** (R) | Reviewer | Approve direction, validate feasibility | Sign-off on phase completion |

**Key Milestones**:
- Day 2: Technology stack decision (Inspect AI vs lm-eval-harness)
- Day 4: SAD v0.1 with architectural direction
- Day 5: All 22 issues have acceptance criteria
- Day 7: Inception phase gate review

**Deliverables**:
- `.aiwg/architecture/SAD.md` (outline)
- `.aiwg/architecture/decisions/ADR-001-inspect-ai.md`
- `.aiwg/requirements/use-cases.md`
- `.aiwg/requirements/nfr-baseline.md`
- `.aiwg/planning/risk-register.md` (initial)

---

### Phase 2: Elaboration (Weeks 2-3)

**Goal**: Architecture baseline, risk retirement, detailed design

| Agent | Role | Responsibilities | Deliverables |
|-------|------|-----------------|--------------|
| **Architecture Designer** (P) | Lead | Detailed SAD, component design, ADRs | SAD v1.0, 5-7 ADRs, component diagrams |
| **API Designer** (P) | Lead | CLI interface spec, Python API design, binding contracts | CLI spec, API docs, interface contracts |
| **Test Engineer** (P) | Lead | Test strategy, smoke test implementation, fixtures | Test strategy, smoke tests, pytest config |
| **DevOps Engineer** (P) | Lead | CI/CD setup, Docker sandbox, dependency management | CI/CD pipeline, Dockerfile, uv config |
| **Requirements Analyst** (S) | Support | Refine acceptance criteria, requirements traceability | Updated requirements matrix |
| **Software Implementer** (S) | Support | Proof-of-concept Inspect AI integration | PoC code (HumanEval minimal integration) |
| **Lead Developer** (R) | Reviewer | Approve ADRs, validate architecture, review PoC | Sign-off on phase completion |

**Key Milestones**:
- Week 2 Day 1: Test strategy approved
- Week 2 Day 3: CI/CD pipeline operational
- Week 2 Day 5: Smoke test passes with Ollama
- Week 3 Day 2: All ADRs approved
- Week 3 Day 4: CLI interface spec finalized
- Week 3 Day 7: Architecture baseline review (phase gate)

**Deliverables**:
- `.aiwg/architecture/SAD.md` (complete v1.0)
- `.aiwg/architecture/decisions/ADR-*.md` (5-7 ADRs)
- `.aiwg/architecture/component-design.md`
- `.aiwg/testing/test-strategy.md`
- `tests/smoke/` (pytest smoke tests)
- `.github/workflows/ci.yml` or `.gitea/workflows/ci.yml`
- `Dockerfile`
- `pyproject.toml` (complete)
- `.aiwg/api/cli-specification.md`
- `.aiwg/api/python-api.md`
- `.aiwg/api/binding-contracts.md`

---

### Phase 3: Construction (Weeks 4-7)

**Goal**: Iterative development, testing, integration

#### Week 4: P1 Issues (Core Infrastructure)

| Issue | Primary | Secondary | Reviewer | Deliverables |
|-------|---------|-----------|----------|--------------|
| Code Scoring & Validation | Software Implementer | Test Engineer | Code Reviewer | `src/matric_eval/scorers/code_scorer.py` |
| Public Benchmarks (HumanEval, MBPP) | Software Implementer | Test Engineer | Code Reviewer | `src/matric_eval/tasks/humaneval.py`, `mbpp.py` |
| CLI Core | Software Implementer | API Designer | Code Reviewer | `src/matric_eval/cli.py` |
| Model Discovery | Software Implementer | - | Code Reviewer | `src/matric_eval/discovery.py` |
| Configuration System | Software Implementer | API Designer | Code Reviewer | `src/matric_eval/config/` |
| Output Formats | Software Implementer | API Designer | Code Reviewer | `src/matric_eval/output/` |

**Support Agents**:
- **Test Engineer**: Write pytest tests for all P1 components
- **Technical Writer**: Document P1 APIs and CLI usage
- **DevOps Engineer**: Ensure CI passes for all P1 code

**Week 4 Milestones**:
- Day 2: Code scoring validates against known benchmarks
- Day 4: HumanEval integration complete and tested
- Day 7: All P1 issues merged and CI green

---

#### Week 5: P2 Issues (Advanced Features)

| Issue | Primary | Secondary | Reviewer | Deliverables |
|-------|---------|-----------|----------|--------------|
| Custom Test Support | Software Implementer | API Designer | Code Reviewer | `src/matric_eval/custom/` |
| Tool Calling Evaluation | Software Implementer | Architecture Designer | Code Reviewer | `src/matric_eval/tasks/tool_calling.py` |
| LLM-as-Judge | Software Implementer | Requirements Analyst | Code Reviewer | `src/matric_eval/scorers/llm_judge.py` |
| GSM8K & Math Benchmarks | Software Implementer | Test Engineer | Code Reviewer | `src/matric_eval/tasks/gsm8k.py` |
| Multi-Turn Evaluation | Software Implementer | Architecture Designer | Code Reviewer | `src/matric_eval/tasks/multiturn.py` |
| Model Ranking System | Software Implementer | Requirements Analyst | Code Reviewer | `src/matric_eval/ranking.py` |

**Support Agents**:
- **Test Engineer**: Integration tests for P2 features
- **Technical Writer**: Document custom test format and LLM-as-judge
- **API Designer**: Validate binding compatibility

**Week 5 Milestones**:
- Day 2: Custom test support validated with matric-cli examples
- Day 4: LLM-as-judge operational with Ollama models
- Day 7: At least 4/6 P2 issues complete

---

#### Week 6: P3 Issues (Operational Excellence)

| Issue | Primary | Secondary | Reviewer | Deliverables |
|-------|---------|-----------|----------|--------------|
| Checkpoint/Resume | Software Implementer | DevOps Engineer | Code Reviewer | `src/matric_eval/checkpoint.py` |
| CI/CD Integration | DevOps Engineer | Software Implementer | Lead Developer | `.github/workflows/`, `.gitea/workflows/` |
| Logging & Observability | Software Implementer | DevOps Engineer | Code Reviewer | `src/matric_eval/logging.py` |
| Performance Optimization | Software Implementer | Code Reviewer | Lead Developer | Performance profiling, optimizations |

**Support Agents**:
- **Test Engineer**: Validate checkpoint/resume across failures
- **Technical Writer**: Document logging configuration and observability

**Week 6 Milestones**:
- Day 2: Checkpoint/resume tested with interrupted evaluations
- Day 4: CI/CD runs full evaluation suite on PRs
- Day 7: All P3 issues complete or deferred to v1.1

---

#### Week 7: P4 Issues (Extended Features - Optional)

| Issue | Primary | Secondary | Reviewer | Status |
|-------|---------|-----------|----------|--------|
| Dashboard/Visualization | Software Implementer | Technical Writer | Code Reviewer | Optional (v1.1 candidate) |
| TypeScript Binding | API Designer | Software Implementer | Code Reviewer | Target 1/2 bindings for v1.0 |
| Rust Binding | API Designer | Software Implementer | Code Reviewer | Target 1/2 bindings for v1.0 |
| Extended Benchmarks (ARC, IFEval) | Software Implementer | Test Engineer | Code Reviewer | Stretch goal |
| Parallel Execution | Software Implementer | DevOps Engineer | Code Reviewer | Defer to v1.1 if risky |
| Report Generation | Technical Writer | Software Implementer | Code Reviewer | Basic version for v1.0 |

**Week 7 Milestones**:
- Day 2: At least 1 binding (TypeScript or Rust) operational
- Day 4: matric-cli integration validated
- Day 7: Construction phase complete, ready for transition

**Support Agents**:
- **Code Reviewer**: Final quality audit before transition
- **Test Engineer**: Integration test validation
- **Technical Writer**: Begin transition documentation

---

### Phase 4: Transition (Week 8)

**Goal**: Deployment prep, documentation, handover

| Agent | Role | Responsibilities | Deliverables |
|-------|------|-----------------|--------------|
| **DevOps Engineer** (P) | Lead | Deployment documentation, release automation, staging validation | Deployment guide, release scripts |
| **Technical Writer** (P) | Lead | User documentation, migration guides, API reference | README.md, docs/, migration guides |
| **Test Engineer** (P) | Lead | Final validation, regression testing, acceptance testing | Test reports, acceptance sign-off |
| **Code Reviewer** (S) | Support | Final code audit, security review | Security audit report, final approval |
| **Lead Developer** (R) | Reviewer | Production readiness review, v1.0 sign-off | Release approval |

**Key Milestones**:
- Day 1: Documentation freeze (all docs complete)
- Day 2: Staging deployment validated
- Day 3: matric-cli and matric-memory integration tested
- Day 4: Security audit complete
- Day 5: Release notes and changelog finalized
- Day 7: v1.0 release approved and deployed

**Deliverables**:
- `README.md` (comprehensive)
- `docs/` (user guides, API reference, architecture)
- `MIGRATION.md` (from matric-cli/matric-memory)
- `CHANGELOG.md`
- `DEPLOYMENT.md`
- Release notes
- v1.0 Git tag and release artifacts

---

## Issue-by-Issue Assignments

### Priority 1 (P1) - Week 4

| Issue | Title | Primary | Secondary | Reviewer | Phase |
|-------|-------|---------|-----------|----------|-------|
| P1-1 | Code Scoring & Validation | Software Implementer | Test Engineer | Code Reviewer | Construction |
| P1-2 | Public Benchmarks (HumanEval, MBPP) | Software Implementer | Test Engineer | Code Reviewer | Construction |
| P1-3 | CLI Core Interface | Software Implementer | API Designer | Code Reviewer | Construction |
| P1-4 | Model Discovery & Filtering | Software Implementer | - | Code Reviewer | Construction |
| P1-5 | Configuration System | Software Implementer | API Designer | Code Reviewer | Construction |
| P1-6 | Output Formats (JSON/JSONL) | Software Implementer | API Designer | Code Reviewer | Construction |

**Dependencies**:
- P1-1 blocks P1-2 (scoring needed for benchmark validation)
- P1-4 blocks P1-2 (need to discover models before evaluating)
- P1-5 blocks P1-3 (CLI reads configuration)

**Parallel Workstreams**:
- Week 4 Days 1-2: P1-4 (Model Discovery) + P1-5 (Config System)
- Week 4 Days 3-4: P1-1 (Code Scoring) + P1-6 (Output Formats)
- Week 4 Days 5-7: P1-2 (Benchmarks) + P1-3 (CLI)

---

### Priority 2 (P2) - Week 5

| Issue | Title | Primary | Secondary | Reviewer | Phase |
|-------|-------|---------|-----------|----------|-------|
| P2-1 | Custom Test Support | Software Implementer | API Designer | Code Reviewer | Construction |
| P2-2 | Tool Calling Evaluation | Software Implementer | Architecture Designer | Code Reviewer | Construction |
| P2-3 | LLM-as-Judge Scoring | Software Implementer | Requirements Analyst | Code Reviewer | Construction |
| P2-4 | GSM8K & Math Benchmarks | Software Implementer | Test Engineer | Code Reviewer | Construction |
| P2-5 | Multi-Turn Evaluation | Software Implementer | Architecture Designer | Code Reviewer | Construction |
| P2-6 | Model Ranking System | Software Implementer | Requirements Analyst | Code Reviewer | Construction |

**Dependencies**:
- P2-1 enables matric-cli/matric-memory integration (high priority)
- P2-2 depends on P2-1 (tool calling is a custom test type)
- P2-3 depends on P1-1 (extends scoring system)
- P2-6 depends on P1-2, P2-4 (needs benchmark results to rank)

**Parallel Workstreams**:
- Week 5 Days 1-2: P2-1 (Custom Tests) + P2-4 (GSM8K)
- Week 5 Days 3-4: P2-2 (Tool Calling) + P2-3 (LLM-as-Judge)
- Week 5 Days 5-7: P2-5 (Multi-Turn) + P2-6 (Ranking)

---

### Priority 3 (P3) - Week 6

| Issue | Title | Primary | Secondary | Reviewer | Phase |
|-------|-------|---------|-----------|----------|-------|
| P3-1 | Checkpoint/Resume | Software Implementer | DevOps Engineer | Code Reviewer | Construction |
| P3-2 | CI/CD Integration | DevOps Engineer | Software Implementer | Lead Developer | Construction |
| P3-3 | Logging & Observability | Software Implementer | DevOps Engineer | Code Reviewer | Construction |
| P3-4 | Performance Optimization | Software Implementer | Code Reviewer | Lead Developer | Construction |

**Dependencies**:
- P3-1 requires P1-2, P2-1 complete (checkpoint evaluation state)
- P3-2 requires P1-3 complete (CI runs CLI commands)
- P3-3 can run in parallel (independent logging framework)
- P3-4 requires profiling data from P1/P2 usage

**Parallel Workstreams**:
- Week 6 Days 1-3: P3-1 (Checkpoint) + P3-3 (Logging)
- Week 6 Days 4-5: P3-2 (CI/CD) + P3-4 (Performance)

---

### Priority 4 (P4) - Week 7 (Stretch Goals)

| Issue | Title | Primary | Secondary | Reviewer | Status |
|-------|-------|---------|-----------|----------|--------|
| P4-1 | Dashboard/Visualization | Software Implementer | Technical Writer | Code Reviewer | Defer to v1.1 |
| P4-2 | TypeScript Binding (matric-cli) | API Designer | Software Implementer | Code Reviewer | Target for v1.0 |
| P4-3 | Rust Binding (matric-memory) | API Designer | Software Implementer | Code Reviewer | Target for v1.0 |
| P4-4 | Extended Benchmarks (ARC, IFEval) | Software Implementer | Test Engineer | Code Reviewer | Stretch goal |
| P4-5 | Parallel Execution | Software Implementer | DevOps Engineer | Code Reviewer | Defer if risky |
| P4-6 | Report Generation | Technical Writer | Software Implementer | Code Reviewer | Basic version v1.0 |

**v1.0 Targets**:
- P4-2 OR P4-3 (at least one binding for integration validation)
- P4-6 (basic report generation for usability)

**v1.1 Deferrals**:
- P4-1 (dashboard - nice-to-have, not critical)
- P4-5 (parallel execution - architectural complexity, risk to timeline)

---

## Collaboration Patterns

### Pattern 1: Design-Implement-Review

**Used For**: All code deliverables

```
API Designer (Design)
    |
    v
Software Implementer (Implement)
    |
    v
Test Engineer (Test)
    |
    v
Code Reviewer (Review)
    |
    v
Lead Developer (Approve)
```

**Example**: CLI Interface (P1-3)
1. API Designer: Create CLI specification with command structure, flags, output formats
2. Software Implementer: Implement CLI using argparse/click based on spec
3. Test Engineer: Write integration tests for CLI commands
4. Code Reviewer: Review code quality, error handling, edge cases
5. Lead Developer: Final approval and merge

---

### Pattern 2: Architecture-First

**Used For**: Major architectural decisions

```
Architecture Designer (Propose ADR)
    |
    v
[Architecture Review Board]
    - Lead Developer
    - API Designer
    - Requirements Analyst
    |
    v
Architecture Designer (Finalize ADR)
    |
    v
Software Implementer (Implement per ADR)
```

**Example**: Inspect AI Integration (ADR-001)
1. Architecture Designer: Research Inspect AI vs lm-eval-harness, draft ADR-001
2. Review Board: Evaluate trade-offs (Ollama support, agent eval, maintenance)
3. Architecture Designer: Finalize ADR with decision rationale
4. Software Implementer: Implement Inspect AI integration per ADR

---

### Pattern 3: Test-Driven Development

**Used For**: Critical algorithms (scoring, validation)

```
Test Engineer (Write failing test)
    |
    v
Software Implementer (Implement to pass test)
    |
    v
Test Engineer (Validate test passes)
    |
    v
Code Reviewer (Review implementation)
```

**Example**: Code Scoring (P1-1)
1. Test Engineer: Write pytest tests for known HumanEval examples (expected pass/fail)
2. Software Implementer: Implement code extraction, sandbox execution, validation
3. Test Engineer: Validate all tests pass, add edge cases
4. Code Reviewer: Review for security (sandbox escape), performance

---

### Pattern 4: Documentation-in-Parallel

**Used For**: User-facing features

```
Software Implementer (Implement feature)
    |
    +----> Technical Writer (Document feature)
    |
    v
Code Reviewer (Review code + docs)
    |
    v
Lead Developer (Approve)
```

**Example**: Custom Test Support (P2-1)
1. Software Implementer: Implement custom test loader, JSONL format parser
2. Technical Writer (parallel): Document custom test format, examples, migration guide
3. Code Reviewer: Review code and validate documentation accuracy
4. Lead Developer: Approve for merge

---

### Pattern 5: Integration Handoff

**Used For**: Cross-component integration

```
Agent A (Complete component)
    |
    v
[Handoff Checklist]
    - Code complete and tested
    - Documentation updated
    - API contract validated
    - Integration tests pass
    |
    v
Agent B (Integrate component)
```

**Example**: CLI (P1-3) -> TypeScript Binding (P4-2)
1. Software Implementer: Complete CLI with JSON output, stable API
2. Handoff Checklist:
   - CLI commands documented in `.aiwg/api/cli-specification.md`
   - JSON output schema validated
   - Integration tests show CLI produces expected output
3. API Designer: Implement TypeScript binding using subprocess to call CLI

---

## Handoff Protocols

### Inception -> Elaboration

**Date**: End of Week 1

**From**: Architecture Designer, Requirements Analyst
**To**: API Designer, Test Engineer, DevOps Engineer

**Handoff Checklist**:
- [ ] SAD v0.1 approved by Lead Developer
- [ ] Technology stack decision (Inspect AI) documented in ADR-001
- [ ] All 22 issues have acceptance criteria in `.aiwg/requirements/`
- [ ] Risk register initialized with architectural and integration risks
- [ ] Use cases documented for primary workflows (smoke/quick/full/recommend)

**Acceptance Meeting**:
- Review SAD architectural direction with full team
- Walk through acceptance criteria for P1 issues
- Identify risks requiring retirement in Elaboration
- Assign Elaboration tasks to API Designer, Test Engineer, DevOps Engineer

**Deliverables Location**:
- `.aiwg/architecture/SAD.md` (v0.1)
- `.aiwg/architecture/decisions/ADR-001-inspect-ai.md`
- `.aiwg/requirements/use-cases.md`
- `.aiwg/requirements/nfr-baseline.md`
- `.aiwg/requirements/acceptance-criteria/` (per issue)
- `.aiwg/planning/risk-register.md`

---

### Elaboration -> Construction

**Date**: End of Week 3

**From**: Architecture Designer, API Designer, Test Engineer, DevOps Engineer
**To**: Software Implementer, Technical Writer, Code Reviewer

**Handoff Checklist**:
- [ ] SAD v1.0 complete with detailed component design
- [ ] 5-7 ADRs approved (Inspect AI, sandbox strategy, scoring approach, etc.)
- [ ] CLI specification finalized in `.aiwg/api/cli-specification.md`
- [ ] Python API contracts defined for bindings
- [ ] Smoke test suite passes with minimal Inspect AI integration
- [ ] CI/CD pipeline operational (green build on main)
- [ ] Test strategy approved with coverage targets (>80%)
- [ ] Dockerfile and pyproject.toml complete

**Acceptance Meeting**:
- Architecture review: Walk through SAD v1.0 and all ADRs
- Validate PoC: Demonstrate smoke test passing with Ollama + Inspect AI
- Review CLI spec: Ensure matric-cli/matric-memory integration clarity
- Confirm P1 issue readiness: All dependencies and acceptance criteria clear

**Deliverables Location**:
- `.aiwg/architecture/SAD.md` (v1.0)
- `.aiwg/architecture/decisions/ADR-*.md` (5-7 ADRs)
- `.aiwg/architecture/component-design.md`
- `.aiwg/api/cli-specification.md`
- `.aiwg/api/python-api.md`
- `.aiwg/api/binding-contracts.md`
- `.aiwg/testing/test-strategy.md`
- `tests/smoke/` (pytest smoke tests)
- `.github/workflows/ci.yml` or `.gitea/workflows/ci.yml`
- `Dockerfile`
- `pyproject.toml`

---

### Construction -> Transition

**Date**: End of Week 7

**From**: Software Implementer, Test Engineer, API Designer
**To**: DevOps Engineer, Technical Writer, Code Reviewer

**Handoff Checklist**:
- [ ] All P1 issues (6/6) complete and merged
- [ ] At least 4/6 P2 issues complete (Custom Tests, Tool Calling, LLM-as-Judge, GSM8K)
- [ ] At least 2/4 P3 issues complete (Checkpoint/Resume, CI/CD)
- [ ] At least 1 binding (TypeScript OR Rust) operational
- [ ] pytest test suite with >80% coverage
- [ ] Integration tests pass for matric-cli or matric-memory
- [ ] Code review approved for all merged code
- [ ] No P1 or P2 bugs remaining open

**Acceptance Meeting**:
- Demo full evaluation workflow: smoke, quick, full, recommend
- Validate matric-cli integration with TypeScript binding
- Review test coverage report and identify gaps
- Confirm documentation needs for Transition phase

**Deliverables Location**:
- `src/matric_eval/` (complete core framework)
- `tests/` (pytest suite with >80% coverage)
- `bindings/typescript/` or `bindings/rust/` (at least one binding)
- `.aiwg/testing/coverage-report.md`
- All P1/P2 issues closed in Gitea

---

### Transition -> Release

**Date**: End of Week 8

**From**: DevOps Engineer, Technical Writer, Test Engineer
**To**: Lead Developer (for release sign-off)

**Handoff Checklist**:
- [ ] README.md complete with installation, quickstart, examples
- [ ] User documentation in `docs/` (guides, API reference, architecture)
- [ ] Migration guides from matric-cli and matric-memory
- [ ] CHANGELOG.md with all v1.0 changes
- [ ] DEPLOYMENT.md with production deployment instructions
- [ ] Release notes drafted
- [ ] Staging deployment validated
- [ ] Security audit complete (no critical vulnerabilities)
- [ ] Regression testing complete (all smoke/integration tests pass)
- [ ] Performance baseline established (benchmark runtime < 5 min for smoke)

**Acceptance Meeting**:
- Final production readiness review with Lead Developer
- Walk through deployment procedure
- Review security audit findings
- Confirm post-deployment monitoring plan
- Sign off on v1.0 release

**Deliverables Location**:
- `README.md`
- `docs/` (user guides, API reference, architecture diagrams)
- `MIGRATION.md`
- `CHANGELOG.md`
- `DEPLOYMENT.md`
- `.aiwg/operations/release-notes-v1.0.md`
- `.aiwg/operations/security-audit.md`
- `.aiwg/testing/regression-test-report.md`

---

## Agent Capacity Planning

### Weekly Capacity Allocation

| Agent | Inception | Elaboration | Construction | Transition | Total Hours |
|-------|-----------|-------------|--------------|------------|-------------|
| Architecture Designer | 80% | 60% | 20% | 10% | ~80 hrs |
| Requirements Analyst | 60% | 40% | 10% | 5% | ~50 hrs |
| API Designer | 20% | 80% | 40% | 10% | ~70 hrs |
| Software Implementer | 10% | 20% | 90% | 20% | ~120 hrs |
| Test Engineer | 0% | 60% | 80% | 60% | ~100 hrs |
| DevOps Engineer | 0% | 60% | 40% | 80% | ~80 hrs |
| Technical Writer | 0% | 10% | 40% | 90% | ~60 hrs |
| Code Reviewer | 0% | 10% | 60% | 40% | ~60 hrs |

**Note**: Percentages represent focus allocation, not strict time tracking. AI agents can scale elastically based on workload.

---

### Risk Mitigation: Agent Overload

**Scenario**: Software Implementer overloaded in Week 5 (6 P2 issues)

**Mitigation**:
1. **Prioritize**: Focus on P2-1 (Custom Tests) and P2-2 (Tool Calling) first - critical for matric-cli/matric-memory
2. **Defer**: Move P2-5 (Multi-Turn) and P2-6 (Ranking) to Week 6 if needed
3. **Parallelize**: API Designer assists with P2-1 (custom test format design)
4. **Extend**: Add 2 days to Construction phase if necessary (Week 8 becomes buffer)

**Scenario**: Technical Writer can't complete docs by Transition

**Mitigation**:
1. **Early Start**: Begin API documentation in Week 6 (parallel with P3 issues)
2. **Templates**: Use documentation templates from matric-cli/matric-memory
3. **Prioritize**: Focus on README, quickstart, and migration guides (defer API reference if needed)
4. **Support**: Software Implementer provides docstring coverage to reduce writer workload

---

## Collaboration Tools & Communication

### Daily Collaboration

**Morning Sync** (via git log review):
- Review previous day's commits and PR activity
- Identify blockers or dependency issues
- Adjust daily priorities based on progress

**Continuous Collaboration** (via Claude Code session):
- Agents communicate directly in session context
- Example: Software Implementer requests API spec clarification from API Designer
- Example: Test Engineer reports test failure to Software Implementer

**End-of-Day Status** (via git commit messages):
- Commit work-in-progress with descriptive messages
- Update issue status in Gitea
- Flag blockers for next morning review

---

### Weekly Collaboration

**Monday: Phase/Week Planning**
- Review upcoming week's issues and assignments
- Confirm agent availability and capacity
- Identify dependencies and coordination needs

**Wednesday: Mid-Week Checkpoint**
- Review progress against weekly milestones
- Address blockers and escalations
- Adjust assignments if needed

**Friday: Week Close**
- Review completed work and merge PRs
- Update risk register
- Preview next week's priorities

---

### Phase Gates

**End of Each Phase: Formal Review**
- Lead Developer reviews all phase deliverables
- Handoff checklist validation
- Go/No-Go decision for next phase
- Lessons learned capture

---

## Escalation Examples

### Example 1: Technical Blocker

**Situation**: Software Implementer discovers Inspect AI doesn't support Ollama function calling in Week 5 (P2-2: Tool Calling Evaluation)

**Escalation**:
1. **L1**: Software Implementer consults Architecture Designer for alternative approach
2. **L2**: If no solution, escalate to Lead Developer with options:
   - Option A: Implement custom Ollama function calling wrapper (2-3 days effort)
   - Option B: Use lm-eval-harness for tool calling only (architectural inconsistency)
   - Option C: Defer P2-2 to v1.1 and adjust acceptance criteria
3. **L3**: If ecosystem impact (matric-cli requires tool calling), escalate to stakeholders

**Resolution**: Lead Developer decides on Option A, adjusts Week 5 timeline by 1 day

---

### Example 2: Requirements Conflict

**Situation**: Requirements Analyst identifies conflict in Week 2 - matric-cli needs streaming output, but matric-memory needs batch results

**Escalation**:
1. **L1**: Requirements Analyst consults API Designer for unified approach
2. **L2**: Escalate to Lead Developer with recommendation:
   - CLI supports both `--stream` and `--batch` modes
   - Python API provides both `evaluate_stream()` and `evaluate_batch()` methods
3. **Resolution**: Lead Developer approves, API Designer updates CLI spec

---

### Example 3: Quality Gate Failure

**Situation**: Code Reviewer blocks P1-2 (HumanEval) merge in Week 4 due to <70% test coverage

**Escalation**:
1. **L1**: Code Reviewer requests Test Engineer to add coverage
2. **L2**: If timeline at risk, escalate to Lead Developer:
   - Option A: Delay P1-2 merge by 1 day for coverage improvement
   - Option B: Accept 70% coverage with Issue filed for additional tests
3. **Resolution**: Lead Developer chooses Option A (Production profile requires >80%)

---

## Success Metrics: Agent Performance

### Individual Agent Metrics

**Architecture Designer**:
- ADRs approved without major revisions: >80%
- Architecture risks identified early (Inception): 100% of major risks
- SAD completeness score (peer review): >90%

**Software Implementer**:
- Code review approval on first submission: >70%
- Test coverage of implemented code: >80%
- Issues completed on schedule: >85%

**Test Engineer**:
- Test failure detection before merge: >95%
- Test suite runtime (smoke tests): <5 minutes
- Integration test coverage of user workflows: 100%

**DevOps Engineer**:
- CI/CD pipeline uptime: >99%
- Deployment success rate (staging): 100%
- Infrastructure-as-code coverage: 100%

**Code Reviewer**:
- Critical defects caught before merge: >90%
- Review turnaround time: <1 day
- False positive rate (unnecessary blocks): <10%

**Technical Writer**:
- Documentation completeness (peer review): >90%
- Documentation accuracy (technical validation): 100%
- Migration guide usability (matric-cli/matric-memory validation): Pass

**API Designer**:
- Breaking changes caught in design phase: 100%
- Binding interface stability (no changes after Elaboration): 100%
- CLI UX validation (matric ecosystem consistency): Pass

**Requirements Analyst**:
- Acceptance criteria clarity (developer survey): >90%
- Requirements defects (ambiguity, conflict): <5 per phase
- Traceability matrix completeness: 100%

---

### Team Collaboration Metrics

**Cross-Agent Dependencies**:
- Dependency resolution time: <2 days average
- Blocking issues escalated: <5 per phase

**Handoff Quality**:
- Handoff checklist completion: 100%
- Rework after handoff: <10% of deliverables

**Communication Effectiveness**:
- Escalations resolved at L1 (agent-to-agent): >70%
- Escalations requiring L3 (stakeholder): <5 total

---

## Appendix: Agent Role Descriptions

### Architecture Designer

**Core Competencies**:
- System design and architecture patterns
- Trade-off analysis (performance, maintainability, complexity)
- Technology evaluation and selection
- Risk identification and mitigation planning

**Deliverable Types**:
- Software Architecture Document (SAD)
- Architecture Decision Records (ADRs)
- Component diagrams and interaction flows
- Technology evaluation reports

**Collaboration Style**:
- Proactive: Identifies architectural risks early
- Consultative: Advises Software Implementer on design patterns
- Decisive: Makes architecture calls with clear rationale

---

### Requirements Analyst

**Core Competencies**:
- Use case analysis and documentation
- Non-functional requirements specification
- Requirements traceability and validation
- Stakeholder requirement translation

**Deliverable Types**:
- Use case specifications
- NFR baseline and acceptance criteria
- Requirements traceability matrix
- Stakeholder requirement analysis

**Collaboration Style**:
- Detail-oriented: Ensures clarity and completeness
- Iterative: Refines requirements based on feedback
- Validating: Confirms acceptance criteria with lead developer

---

### Software Implementer

**Core Competencies**:
- Python 3.11+ development
- Inspect AI framework integration
- Algorithm implementation (scoring, ranking)
- Code optimization and refactoring

**Deliverable Types**:
- Python source code (src/matric_eval/)
- Task, solver, and scorer implementations
- CLI and API code
- Integration code (Ollama, Inspect AI)

**Collaboration Style**:
- Pragmatic: Balances quality with timeline
- Collaborative: Requests design clarification early
- Responsive: Addresses code review feedback quickly

---

### Test Engineer

**Core Competencies**:
- pytest test design and implementation
- Integration testing and end-to-end workflows
- Test data preparation and fixtures
- Test coverage analysis and reporting

**Deliverable Types**:
- pytest test suites (unit, integration, smoke)
- Test fixtures and data
- Test coverage reports
- Test strategy documentation

**Collaboration Style**:
- Quality-focused: Ensures high test coverage
- Proactive: Writes tests before or during implementation
- Thorough: Validates edge cases and error paths

---

### API Designer

**Core Competencies**:
- CLI UX design and command structure
- API contract design and versioning
- Interface design for language bindings
- Configuration schema design

**Deliverable Types**:
- CLI specifications
- Python API documentation
- Binding interface contracts (TypeScript, Rust)
- Configuration schemas (YAML, JSON)

**Collaboration Style**:
- User-centric: Designs for developer experience
- Standards-driven: Follows matric ecosystem conventions
- Forward-thinking: Plans for extensibility and versioning

---

### DevOps Engineer

**Core Competencies**:
- CI/CD pipeline design (GitHub Actions, Gitea CI)
- Docker containerization and sandboxing
- Dependency management (uv, pyproject.toml)
- Deployment automation and infrastructure

**Deliverable Types**:
- CI/CD pipeline configurations
- Dockerfiles and container configurations
- Deployment documentation and scripts
- Release automation

**Collaboration Style**:
- Automation-first: Automates repetitive tasks
- Reliability-focused: Ensures pipeline stability
- Security-conscious: Validates sandbox integrity

---

### Technical Writer

**Core Competencies**:
- User documentation writing
- API reference documentation
- Migration guide authoring
- Inline code documentation (docstrings)

**Deliverable Types**:
- README.md and user guides
- API reference documentation
- Migration guides
- Docstring coverage for Python modules

**Collaboration Style**:
- Clarity-focused: Writes for developer audience
- Collaborative: Validates technical accuracy with implementers
- User-empathetic: Anticipates documentation needs

---

### Code Reviewer

**Core Competencies**:
- Code quality assurance
- Security vulnerability scanning
- Performance review and optimization
- Best practices enforcement (PEP 8, type hints)

**Deliverable Types**:
- Code review reports
- Quality gate pass/fail decisions
- Refactoring recommendations
- Security audit reports

**Collaboration Style**:
- Objective: Reviews against established standards
- Constructive: Provides actionable feedback
- Efficient: Prioritizes critical issues over nitpicks

---

## Appendix: Issue Reference

### Priority 1 (P1) - Core Infrastructure

1. **Code Scoring & Validation**: Implement code execution sandbox, extract code from responses, validate against test cases
2. **Public Benchmarks**: HumanEval, MBPP integration with Inspect AI, preserve MBPP function name fix
3. **CLI Core**: `matric-eval` command with --tier, --model, --app, --output flags
4. **Model Discovery**: Query Ollama API, filter by size/capabilities, cache model metadata
5. **Configuration System**: YAML/JSON config for model categories, tier definitions, custom tests
6. **Output Formats**: JSON/JSONL output with generatedCode, score, reasoning artifacts

### Priority 2 (P2) - Advanced Features

7. **Custom Test Support**: Load custom tests from JSONL, integrate with matric-cli/matric-memory
8. **Tool Calling Evaluation**: Evaluate function calling accuracy, validate tool use
9. **LLM-as-Judge**: Use Ollama models to score responses, implement judge prompts
10. **GSM8K & Math**: Math benchmark integration, numeric answer extraction
11. **Multi-Turn Evaluation**: Evaluate conversational coherence and context retention
12. **Model Ranking**: Rank models by capability, generate recommendations

### Priority 3 (P3) - Operational Excellence

13. **Checkpoint/Resume**: Save evaluation state, resume after interruption
14. **CI/CD Integration**: Automated testing on PR, smoke test validation
15. **Logging & Observability**: Structured logging, progress tracking, error reporting
16. **Performance Optimization**: Optimize benchmark runtime, memory usage

### Priority 4 (P4) - Extended Features

17. **Dashboard/Visualization**: Web UI for results (defer to v1.1)
18. **TypeScript Binding**: matric-cli integration via subprocess or native binding
19. **Rust Binding**: matric-memory integration via PyO3 or subprocess
20. **Extended Benchmarks**: ARC, IFEval, LiveCodeBench (stretch goal)
21. **Parallel Execution**: Run evaluations concurrently (defer if risky)
22. **Report Generation**: Generate Markdown/HTML reports from results

---

## Document Metadata

**Created**: 2026-01-24
**Last Updated**: 2026-01-24
**Version**: 1.0
**Owner**: Lead Developer
**Review Cycle**: Weekly during Construction, at each phase gate

**Change Log**:
- 2026-01-24: Initial agent assignments and collaboration patterns

---

## Approval

**Prepared By**: AI Agent (Project Manager Role)
**Reviewed By**: [Lead Developer - Pending]
**Approved By**: [Lead Developer - Pending]
**Approval Date**: [Pending]

**Notes**:
- This document is a living artifact - adjust agent assignments based on actual progress
- Flexibility encouraged - lead developer can reassign or rebalance workload
- All agent outputs subject to human review and approval
- Production profile requires adherence to quality gates and handoff protocols
