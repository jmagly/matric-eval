# Handoff Checklist: Construction → Transition

**Project**: matric-eval
**Phase Transition**: Construction → Transition
**Date**: _____________
**Purpose**: Verify feature completeness, test coverage, and production readiness

---

## 1. All Features Implemented

### 1.1 Core Evaluation Framework
- [ ] **Public benchmarks** (all working with Inspect AI):
  - [ ] HumanEval (164 problems, code execution scoring)
  - [ ] MBPP (974 problems, code execution scoring)
  - [ ] GSM8K (1,319 problems, numeric extraction scoring)
  - [ ] ARC-Challenge (2,590 problems, multiple choice)
  - [ ] IFEval (541 problems, instruction following)
  - [ ] DS-1000 (1,000 problems, data science)
  - [ ] LiveCodeBench (880 problems, competitive programming)
- [ ] **Tiered sampling** implemented:
  - [ ] Smoke tier (5-10 samples, ~2 min)
  - [ ] Quick tier (75-100 samples, ~20 min)
  - [ ] Full tier (all problems, 2+ hours)
- [ ] **Model discovery** from Ollama
- [ ] **Model filtering** by size (MAX_MODEL_SIZE_GB configurable)

### 1.2 Custom Matric Tests
- [ ] **matric-cli tests** (282 total):
  - [ ] Format compliance (55 tests)
  - [ ] Tool calling scenarios (6 scenarios)
  - [ ] Agent fixture evaluation (multi-step validation)
- [ ] **matric-memory tests** (226 total):
  - [ ] Title generation (64 tests)
  - [ ] Semantic similarity (42 tests)
  - [ ] Tag generation (30 tests)
  - [ ] Content revision (44 tests)
  - [ ] Long context (18 tests)
  - [ ] Context generation (29 tests)

### 1.3 Scoring & Reporting
- [ ] **Code execution scorer** (Docker sandbox)
- [ ] **Format validation scorer** (matric-specific rules)
- [ ] **Tool use accuracy scorer** (expected tools vs actual)
- [ ] **Multi-dimensional scorer** (5D: correctness, efficiency, safety, helpfulness, reasoning)
- [ ] **JSON report generation** (per-model, per-benchmark, aggregated)
- [ ] **Markdown summary generation** (human-readable)
- [ ] **Config recommendation engine** (model-categories.json output)

### 1.4 Resilience & Recovery
- [ ] **Checkpoint/resume** mechanism:
  - [ ] State files (meta.json, state.json) at all levels
  - [ ] Atomic writes (temp file + rename)
  - [ ] Lock files prevent concurrent runs
  - [ ] Heartbeat tracking for zombie detection
- [ ] **Selective re-run**:
  - [ ] `--resume <run-id>` flag
  - [ ] `--model <model>` filter
  - [ ] `--benchmark <name>` filter
  - [ ] `--fill-gaps` mode (detect and run missing)
- [ ] **Auto-recovery** for transient errors:
  - [ ] Retry logic for network/timeout errors
  - [ ] Graceful skip for failed models
  - [ ] Error classification (retryable vs fatal)
- [ ] **Validation command** (`--validate <run-id>`) reports completeness

### 1.5 CLI Interface
- [ ] **Main commands** implemented:
  ```bash
  matric-eval --tier {smoke|quick|full} [--model <model>]
  matric-eval --resume <run-id> [--model <model>] [--benchmark <name>]
  matric-eval --fill-gaps <run-id>
  matric-eval --validate <run-id>
  matric-eval --recommend --output model-categories.json
  ```
- [ ] **Configuration**:
  - [ ] `--config <file>` for custom tier definitions
  - [ ] Environment variables (EVAL_SEED, OLLAMA_HOST, MAX_MODEL_SIZE_GB)
  - [ ] `--verbose` flag for debug logging
- [ ] **Progress reporting**:
  - [ ] Real-time progress bar
  - [ ] Status streaming to stdout/file
  - [ ] ETA calculation

### 1.6 Language Bindings
- [ ] **TypeScript binding** (npm package):
  - [ ] Subprocess wrapper for matric-eval CLI
  - [ ] TypeScript type definitions for results
  - [ ] Stream results to caller
  - [ ] Integration test with matric-cli
- [ ] **Rust binding** (crate):
  - [ ] Subprocess wrapper or FFI
  - [ ] Serde types for results
  - [ ] Async result streaming
  - [ ] Integration test with matric-memory

---

## 2. Test Coverage Achieved

### 2.1 Unit Test Coverage
- [ ] **Overall coverage**: ≥80% for core modules
- [ ] **Tasks module** (`src/matric_eval/tasks/`):
  - [ ] Public benchmark task definitions tested
  - [ ] Custom matric task definitions tested
  - [ ] JSONL dataset loading tested
- [ ] **Scorers module** (`src/matric_eval/scorers/`):
  - [ ] Code execution scorer tested (mocked sandbox)
  - [ ] Format validation scorer tested
  - [ ] Tool use accuracy scorer tested
  - [ ] Multi-dimensional scorer tested
- [ ] **Solvers module** (`src/matric_eval/solvers/`):
  - [ ] Custom solving strategies tested
- [ ] **CLI module** (`src/matric_eval/cli.py`):
  - [ ] Argument parsing tested
  - [ ] Command routing tested
- [ ] **State management** (`src/matric_eval/state/`):
  - [ ] Checkpoint save/load tested
  - [ ] Lock file acquisition/release tested
  - [ ] Atomic write mechanism tested

### 2.2 Integration Test Coverage
- [ ] **End-to-end smoke test** (full eval run with 1 model, 3 benchmarks):
  - [ ] HumanEval smoke (5 samples)
  - [ ] MBPP smoke (5 samples)
  - [ ] GSM8K smoke (5 samples)
  - [ ] Results JSON validated
- [ ] **Checkpoint/resume test**:
  - [ ] Start eval, interrupt mid-run
  - [ ] Resume and verify completion
  - [ ] Verify idempotency (re-run produces same results)
- [ ] **Selective re-run test**:
  - [ ] Re-run specific model from completed run
  - [ ] Re-run specific benchmark from completed run
- [ ] **Gap detection test**:
  - [ ] Manually delete result files
  - [ ] Run `--fill-gaps`, verify missing results regenerated
- [ ] **Config recommendation test**:
  - [ ] Run eval, generate model-categories.json
  - [ ] Validate JSON schema

### 2.3 Parity Validation Tests
- [ ] **Cross-validation with matric-cli**:
  - [ ] Same models evaluated on both systems
  - [ ] HumanEval scores compared (<5% variance)
  - [ ] MBPP scores compared (<5% variance)
  - [ ] GSM8K scores compared (<5% variance)
  - [ ] Discrepancies documented and explained
- [ ] **Known issue preservation** (from matric-cli):
  - [ ] MBPP function name extraction working
  - [ ] Code extraction from markdown fences working
  - [ ] Artifact preservation in validation paths working

### 2.4 Binding Tests
- [ ] **TypeScript binding test**:
  - [ ] Install from npm
  - [ ] Call from TypeScript code
  - [ ] Parse returned results
  - [ ] Error handling tested
- [ ] **Rust binding test**:
  - [ ] Add crate dependency
  - [ ] Call from Rust code
  - [ ] Deserialize results
  - [ ] Error handling tested

### 2.5 Performance Tests
- [ ] **Smoke tier** completes in <2 minutes (single model)
- [ ] **Quick tier** completes in <20 minutes (single model)
- [ ] **Full tier** completes in <3 hours (single model, 7 benchmarks)
- [ ] **Memory usage** stays below 4GB during eval
- [ ] **Disk usage** reasonable (results directory <100MB per model)

---

## 3. Documentation Complete

### 3.1 User Documentation
- [ ] **README.md** includes:
  - [ ] Project overview and purpose
  - [ ] Installation instructions (uv, Docker, Ollama)
  - [ ] Quick start guide (first eval in 5 minutes)
  - [ ] CLI reference (all commands and flags)
  - [ ] Configuration options (env vars, config files)
  - [ ] Troubleshooting section
- [ ] **docs/running-evaluations.md**:
  - [ ] Tier selection guide (smoke vs quick vs full)
  - [ ] Model selection strategies
  - [ ] Interpreting results
  - [ ] Checkpoint/resume workflows
  - [ ] Performance tuning tips
- [ ] **docs/adding-custom-tests.md**:
  - [ ] JSONL format specification
  - [ ] Creating custom tasks
  - [ ] Writing custom scorers
  - [ ] Example walkthroughs

### 3.2 Developer Documentation
- [ ] **CONTRIBUTING.md**:
  - [ ] Development setup (uv sync, pre-commit)
  - [ ] Code style guide (ruff, black, mypy)
  - [ ] Testing requirements (pytest, coverage)
  - [ ] PR process and review expectations
- [ ] **docs/architecture.md**:
  - [ ] System architecture diagram
  - [ ] Component descriptions (tasks, solvers, scorers)
  - [ ] Data flow diagrams
  - [ ] State management design
- [ ] **docs/adr/** (Architecture Decision Records):
  - [ ] ADR-001: Python core decision
  - [ ] ADR-002: Inspect AI selection
  - [ ] ADR-003: JSONL format
  - [ ] ADR-004: Tiered evaluation
  - [ ] ADR-005: Checkpoint/resume design

### 3.3 Integration Documentation
- [ ] **docs/typescript-bindings.md**:
  - [ ] Installation (npm install)
  - [ ] API reference
  - [ ] Usage examples
  - [ ] Error handling
- [ ] **docs/rust-bindings.md**:
  - [ ] Installation (Cargo.toml dependency)
  - [ ] API reference
  - [ ] Usage examples
  - [ ] Error handling

### 3.4 Operational Documentation
- [ ] **docs/ci-cd-integration.md**:
  - [ ] GitHub Actions example workflow
  - [ ] Gitea CI example
  - [ ] Smoke test in PR pipeline
  - [ ] Nightly full eval setup
- [ ] **CHANGELOG.md**:
  - [ ] All versions documented (following semver)
  - [ ] Breaking changes highlighted
  - [ ] Migration guides for major versions

---

## 4. Release Artifacts Ready

### 4.1 Python Package
- [ ] **pyproject.toml** complete:
  - [ ] Version set (e.g., 0.1.0)
  - [ ] Metadata (name, description, authors, license)
  - [ ] Dependencies locked (uv.lock committed)
  - [ ] Entry points defined (`matric-eval` CLI)
- [ ] **Package build** successful:
  - [ ] `uv build` produces wheel and sdist
  - [ ] Package installable via `uv pip install`
- [ ] **PyPI publication** ready (if applicable):
  - [ ] Package name available
  - [ ] API token configured (for CI)

### 4.2 TypeScript Binding Package
- [ ] **package.json** complete:
  - [ ] Version synchronized with Python package
  - [ ] Dependencies minimal (just subprocess wrapper)
  - [ ] Type definitions included
- [ ] **npm package** build successful:
  - [ ] `npm pack` produces tarball
  - [ ] Package installable via `npm install`
- [ ] **npm publication** ready:
  - [ ] Package name available (`@matric/eval` or similar)
  - [ ] API token configured (for CI)

### 4.3 Rust Binding Crate
- [ ] **Cargo.toml** complete:
  - [ ] Version synchronized with Python package
  - [ ] Dependencies minimal
  - [ ] Documentation enabled
- [ ] **Crate build** successful:
  - [ ] `cargo build --release` succeeds
  - [ ] `cargo test` passes
- [ ] **crates.io publication** ready:
  - [ ] Crate name available (`matric-eval` or similar)
  - [ ] API token configured (for CI)

### 4.4 Distribution Artifacts
- [ ] **GitHub/Gitea release** prepared:
  - [ ] Source tarball
  - [ ] Binaries (if applicable)
  - [ ] Release notes draft
  - [ ] Checksums (SHA256)
- [ ] **Docker image** (optional, for sandbox):
  - [ ] Dockerfile validated
  - [ ] Image pushed to registry
  - [ ] Tag matches release version

---

## 5. Known Issues Documented

### 5.1 Issue Register
- [ ] **Known bugs** tracked in issue system:
  - [ ] Severity assigned (Critical, High, Medium, Low)
  - [ ] Workarounds documented (if available)
  - [ ] Target fix version set (or "future")
- [ ] **Feature limitations** documented:
  - [ ] MT-Bench not yet implemented (planned for v0.2.0)
  - [ ] Parallel model evaluation not yet implemented (planned for v0.3.0)
  - [ ] Multi-GPU support not yet implemented (planned for future)

### 5.2 Compatibility Matrix
- [ ] **Tested environments** documented:
  - [ ] Python versions (3.11, 3.12, 3.13)
  - [ ] OS platforms (Ubuntu 22.04, macOS 14, Arch Linux)
  - [ ] Ollama versions (0.1.x, 0.2.x)
  - [ ] Docker versions (24.x, 25.x)
- [ ] **Known incompatibilities** listed:
  - [ ] Python <3.11 not supported (uses modern type hints)
  - [ ] Windows support status (untested or known issues)

### 5.3 Migration Notes
- [ ] **From matric-cli** migration guide:
  - [ ] Differences in scoring methodology
  - [ ] Config file format changes
  - [ ] Result format changes
- [ ] **From matric-memory** migration guide:
  - [ ] Test data migration steps
  - [ ] API changes in bindings

---

## 6. Quality Gate Checklist

### 6.1 Functional Completeness
- [ ] All MVP features implemented (per ROADMAP.md Phase 1-3)
- [ ] All user stories from backlog completed
- [ ] No critical bugs open (P0/P1 severity)

### 6.2 Non-Functional Requirements
- [ ] **Performance**: Smoke tier <2 min, Quick tier <20 min
- [ ] **Reliability**: Checkpoint/resume tested, auto-recovery validated
- [ ] **Security**: Code execution sandboxed, no arbitrary code execution
- [ ] **Maintainability**: Code coverage ≥80%, documentation complete
- [ ] **Usability**: CLI intuitive, error messages helpful

### 6.3 Stakeholder Acceptance
- [ ] **matric-cli team** validates TypeScript bindings work
- [ ] **matric-memory team** validates Rust bindings work
- [ ] **DevOps team** validates CI/CD integration
- [ ] **Product Owner** approves feature completeness

---

## 7. Handoff Criteria Met

**Transition phase may begin when**:
- All MVP features implemented and tested
- Test coverage ≥80% achieved
- Documentation complete (user + developer + integration)
- Release artifacts built and validated
- Known issues documented with workarounds
- Stakeholders accept feature completeness

---

**Handoff Prepared By**: Development Team Lead
**Handoff Received By**: Release Manager / QA Lead
**Handoff Date**: _____________

**Signatures**:
- [ ] Development Team Lead: _____________
- [ ] QA Lead: _____________
- [ ] Release Manager: _____________
- [ ] matric-cli Stakeholder: _____________
- [ ] matric-memory Stakeholder: _____________
- [ ] Product Owner: _____________
