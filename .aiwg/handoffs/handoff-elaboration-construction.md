# Handoff Checklist: Elaboration → Construction

**Project**: matric-eval
**Phase Transition**: Elaboration → Construction
**Date**: 2026-01-24
**Purpose**: Verify architectural foundation, risk mitigation, and development readiness

---

## 1. Architecture Baseline Verified

### 1.1 Architectural Decisions Documented
- [ ] **ADR-001**: Python core with language bindings (APPROVED)
- [ ] **ADR-002**: Inspect AI as evaluation framework (APPROVED)
- [ ] **ADR-003**: JSONL as universal test format (APPROVED)
- [ ] **ADR-004**: Tiered evaluation strategy (smoke/quick/full) (APPROVED)
- [ ] **ADR-005**: Checkpoint/resume resilience architecture (APPROVED)
- [ ] All ADRs reviewed by stakeholders (matric-cli team, matric-memory team)
- [ ] Architecture diagrams created and approved
  - [ ] System context diagram (matric-eval ↔ Ollama ↔ consuming apps)
  - [ ] Component diagram (tasks, solvers, scorers, bindings)
  - [ ] Data flow diagram (eval flow: discover → public → rank → custom → config)

### 1.2 Technology Stack Validated
- [ ] **Python 3.11+** confirmed available on target environments
- [ ] **uv** package manager tested and documented
- [ ] **Inspect AI** framework prototyped with Ollama integration
- [ ] **Docker** sandboxing verified for code execution
- [ ] **TypeScript bindings** approach validated (subprocess wrapper)
- [ ] **Rust bindings** approach validated (subprocess wrapper or FFI)
- [ ] Dependency licenses reviewed (no GPL/AGPL blockers)

### 1.3 Interface Contracts Defined
- [ ] **CLI interface** specification complete
  ```bash
  matric-eval --tier {smoke|quick|full}
  matric-eval --resume <run-id> [--model <model>] [--benchmark <name>]
  matric-eval --validate <run-id>
  matric-eval --recommend --output model-categories.json
  ```
- [ ] **TypeScript binding** API contract documented
- [ ] **Rust binding** API contract documented
- [ ] **Results format** schema defined (JSON structure)
- [ ] **Config recommendation** format schema defined (model-categories.json)

### 1.4 Data Architecture Approved
- [ ] Results directory structure defined and validated
  ```
  results/run-{timestamp}/
  ├── meta.json, state.json
  ├── {model}/
  │   ├── {benchmark}/
  │   │   └── {problem_id}/
  ```
- [ ] Dataset storage strategy approved (public benchmarks at `/home/roctinam/data/evals/`)
- [ ] State management design reviewed (atomic writes, lock files, heartbeat)
- [ ] Checkpoint/resume mechanism validated with prototype

---

## 2. Risk Status Confirmed

### 2.1 High-Priority Risks Mitigated
- [ ] **RISK-001**: Framework selection (Inspect AI vs lm-eval-harness)
  - **Status**: CLOSED - Inspect AI selected, prototype validated
  - **Evidence**: Working Ollama integration demonstrated
- [ ] **RISK-002**: Evaluation crash/resume (EPIPE failure in matric-cli)
  - **Status**: MITIGATED - Checkpoint architecture designed
  - **Mitigation**: State files, atomic writes, lock files, retry logic
- [ ] **RISK-003**: Code execution sandboxing
  - **Status**: MITIGATED - Docker sandbox approach validated
  - **Evidence**: Inspect AI sandbox parameter tested
- [ ] **RISK-004**: Scoring parity with matric-cli
  - **Status**: ACCEPTED - Will validate in Construction phase
  - **Plan**: Cross-validation tests scheduled in Phase 6

### 2.2 Medium-Priority Risks Tracked
- [ ] **RISK-005**: Dataset versioning and reproducibility
  - **Status**: TRACKED - JSONL format + seeded sampling planned
  - **Mitigation**: `EVAL_SEED` environment variable
- [ ] **RISK-006**: Multi-language binding maintenance burden
  - **Status**: TRACKED - Simple subprocess wrappers minimize complexity
  - **Mitigation**: Automated binding tests in CI
- [ ] **RISK-007**: Performance degradation at scale (40+ models)
  - **Status**: TRACKED - Parallel execution planned for future
  - **Mitigation**: Checkpoint/resume allows incremental runs

### 2.3 Open Risks with Contingency Plans
- [ ] **RISK-008**: Public benchmark dataset availability
  - **Contingency**: Fallback to HuggingFace datasets API if local files unavailable
- [ ] **RISK-009**: Inspect AI breaking changes
  - **Contingency**: Pin to stable version, monitor release notes
- [ ] **RISK-010**: Ollama API changes
  - **Contingency**: Inspect AI abstracts provider, minimal impact expected

---

## 3. Iteration Plan Approved

### 3.1 Phase 1: Foundation (Iteration 1-2, Week 1-2)
- [ ] Iteration plan reviewed with team
- [ ] **Deliverables**:
  - [ ] Python project setup (pyproject.toml, uv.lock)
  - [ ] 3 public benchmarks working (HumanEval, MBPP, GSM8K)
  - [ ] Smoke tier functional (5 samples per benchmark)
  - [ ] Basic CLI entry point
- [ ] **Acceptance criteria**: Smoke test runs against 1 Ollama model
- [ ] **Capacity**: 1 developer, 2 weeks
- [ ] **Dependencies**: None (greenfield)

### 3.2 Phase 2: Custom Tests (Iteration 3-4, Week 2-3)
- [ ] Iteration plan reviewed with stakeholders
- [ ] **Deliverables**:
  - [ ] matric-cli custom tests (tool calling, agent scenarios)
  - [ ] matric-memory custom tests (title, semantic, revision, tags)
  - [ ] Custom scorers implemented
  - [ ] Config recommendation engine
- [ ] **Acceptance criteria**: Custom tests score 10 models
- [ ] **Capacity**: 1 developer, 1.5 weeks
- [ ] **Dependencies**: Phase 1 complete

### 3.3 Phase 3: Integration (Iteration 5-6, Week 3-4)
- [ ] Iteration plan reviewed with consuming teams
- [ ] **Deliverables**:
  - [ ] TypeScript bindings (npm package)
  - [ ] Rust bindings (crate)
  - [ ] CI/CD pipeline (smoke tests on PR)
  - [ ] Documentation complete
- [ ] **Acceptance criteria**: matric-cli uses bindings successfully
- [ ] **Capacity**: 1 developer, 1.5 weeks
- [ ] **Dependencies**: Phase 2 complete

### 3.4 Resource Allocation Confirmed
- [ ] Developer assigned to project
- [ ] Stakeholder availability confirmed (weekly sync meetings)
- [ ] CI/CD infrastructure provisioned (GitHub Actions or Gitea CI)
- [ ] Code review bandwidth allocated

---

## 4. Test Infrastructure Ready

### 4.1 Test Strategy Defined
- [ ] **Unit tests**: pytest for Python core (tasks, scorers, solvers)
- [ ] **Integration tests**: End-to-end eval runs with Ollama
- [ ] **Binding tests**: TypeScript and Rust wrapper validation
- [ ] **Smoke tests**: Quick validation (<2 min) for CI/CD
- [ ] **Parity tests**: Cross-validation with matric-cli (Phase 6)
- [ ] Test coverage target: 80% for core evaluation logic

### 4.2 Test Environment Configured
- [ ] **Ollama instance** available for testing (local or shared)
- [ ] **Test models** identified (e.g., `llama3.2:3b` for speed)
- [ ] **Docker** available for sandboxed code execution
- [ ] **Test data** accessible at `/home/roctinam/data/evals/`
- [ ] **CI environment** supports Docker execution
- [ ] Test data fixtures created (minimal JSONL samples)

### 4.3 Test Automation Framework
- [ ] **pytest** configured with coverage reporting
- [ ] **Pre-commit hooks** setup (linting, type checking)
- [ ] **CI pipeline** skeleton created
  - [ ] Lint check (ruff, mypy)
  - [ ] Unit tests
  - [ ] Smoke tests (if Ollama available)
- [ ] **Test result reporting** mechanism defined

---

## 5. Development Environment Documented

### 5.1 Setup Documentation Complete
- [ ] **README.md** includes:
  - [ ] Prerequisites (Python 3.11+, uv, Docker, Ollama)
  - [ ] Installation steps (`uv sync`)
  - [ ] Quick start guide (run first eval)
  - [ ] Common troubleshooting
- [ ] **CONTRIBUTING.md** created:
  - [ ] Development workflow
  - [ ] Code style guide (ruff, black, mypy)
  - [ ] PR process
  - [ ] Testing requirements

### 5.2 Developer Onboarding Materials
- [ ] **Architecture overview** document (for new contributors)
- [ ] **Adding custom tests** guide (JSONL format, scorer creation)
- [ ] **Debugging guide** (inspecting state files, log verbosity)
- [ ] **Related repositories** context (matric-cli, matric-memory links)

### 5.3 Configuration Management
- [ ] **pyproject.toml** complete with all dependencies
- [ ] **uv.lock** committed to version control
- [ ] **Environment variables** documented
  - `EVAL_SEED`: Reproducible sampling seed (default: 42)
  - `OLLAMA_HOST`: Ollama server URL (default: localhost:11434)
- [ ] **Docker configuration** for sandbox execution
- [ ] **Example configs** provided (model-categories.json.example)

---

## 6. Stakeholder Sign-Off

### 6.1 Technical Review
- [ ] **System Architect**: Architecture baseline approved
- [ ] **DevOps Lead**: CI/CD approach validated
- [ ] **matric-cli team**: TypeScript bindings approach approved
- [ ] **matric-memory team**: Rust bindings approach approved

### 6.2 Risk Acceptance
- [ ] **Project Manager**: Risk register reviewed and accepted
- [ ] **Product Owner**: Open risks acknowledged (scoring parity, dataset availability)

### 6.3 Iteration Commitment
- [ ] **Development team**: Iteration plan feasible and committed
- [ ] **Stakeholders**: Review cadence agreed (weekly syncs)

---

## 7. Quality Gates

### 7.1 Documentation Completeness
- [x] PLANNING.md complete and approved
- [x] ROADMAP.md defines path to parity
- [x] CLAUDE.md provides AI assistant context
- [ ] Architecture Decision Records (ADRs) created
- [ ] API contracts documented

### 7.2 Prototype Validation
- [ ] Inspect AI + Ollama integration working
- [ ] Sample eval run successful (HumanEval on 1 model)
- [ ] Checkpoint/resume mechanism demonstrated (even if basic)

### 7.3 Team Readiness
- [ ] Developer has Inspect AI familiarity
- [ ] Access to all required systems (Ollama, Docker, test data)
- [ ] Communication channels established (Gitea issues, team chat)

---

## Handoff Criteria Met

**Construction phase may begin when**:
- All sections above marked COMPLETE
- Risk register shows HIGH risks mitigated or accepted
- Iteration 1 ready to start (plan, capacity, environment)
- Stakeholders sign off on this checklist

---

**Handoff Prepared By**: Project Manager
**Handoff Received By**: Development Team Lead
**Handoff Date**: _____________

**Signatures**:
- [ ] Project Manager: _____________
- [ ] System Architect: _____________
- [ ] Development Team Lead: _____________
- [ ] matric-cli Stakeholder: _____________
- [ ] matric-memory Stakeholder: _____________
