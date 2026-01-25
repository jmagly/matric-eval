# Solution Profile

**Document Type**: Greenfield Infrastructure Project Profile
**Generated**: 2026-01-24

## Profile Selection

**Profile**: Production

**Selection Logic** (automated based on inputs):
- **Prototype**: Timeline <4 weeks, no external users, experimental/learning, high uncertainty
- **MVP**: Timeline 1-3 months, initial users (internal or limited beta), proving viability
- **Production**: Timeline 3-6 months, established users, revenue-generating or critical operations ← **SELECTED**
- **Enterprise**: Compliance requirements (HIPAA/SOC2/PCI-DSS), >10k users, mission-critical, contracts/SLAs

**Chosen**: Production - **Rationale**: 6-8 week timeline to production-ready v1.0, critical infrastructure for matric ecosystem (matric-cli, matric-memory, future apps depend on it), blocking requirement for checkpoint/resume resilience requires production-grade implementation, multiple established applications will adopt immediately (not MVP/experimental).

## Profile Characteristics

### Security

**Posture**: Baseline

**Profile Defaults**:
- **Prototype/MVP**: Baseline (user auth, environment secrets, HTTPS, basic logging)
- **Production**: Strong (threat model, SAST/DAST, secrets manager, audit logs, incident response) ← **Default**
- **Enterprise**: Enterprise (full SDL, penetration testing, compliance controls, SOC2/ISO27001, IR playbooks)

**Chosen**: Baseline - **Rationale**: Override from Production default to Baseline because this is an internal development tool with no PII, no user authentication, no network exposure. Code execution is sandboxed by Ollama. Evaluation results are internal development data (public benchmarks). Strong security would be over-engineering for this use case.

**Controls Included**:
- **Authentication**: None required (local CLI tool, file system permissions)
- **Authorization**: File system permissions for results directories
- **Data Protection**: No encryption needed (public datasets, internal results, no sensitive data)
- **Secrets Management**: Environment variables for Ollama API endpoint configuration
- **Audit Logging**: None required (local tool, development use only)
- **Code Execution Safety**: Rely on Ollama's built-in sandboxing for generated code
- **Dependency Security**: SBOM generation via uv.lock, CI dependency scanning

**Gaps/Additions**:
- **Addition**: Implement subprocess timeout limits (30s-120s per problem) to prevent runaway model inference
- **Addition**: Resource limits for safe execution (memory caps if running untrusted code)
- **Gap**: No threat modeling needed for internal tool (defer until if/when exposed as service)

### Reliability

**Targets**: High reliability with focus on resilience

**Profile Defaults**:
- **Prototype**: 95% uptime, best-effort, no SLA
- **MVP**: 99% uptime, p95 latency <1s, business hours support
- **Production**: 99.9% uptime, p95 latency <500ms, 24/7 monitoring, runbooks ← **Default**
- **Enterprise**: 99.99% uptime, p95 latency <200ms, 24/7 on-call, disaster recovery

**Chosen**: Custom (Recovery-focused) - **Override**: Traditional uptime SLA not applicable (CLI tool, not service). Instead, focus on **resilience and recovery**:

- **Recovery Success Rate**: 100% (checkpoint/resume must never lose progress)
- **Resume Latency**: <5 seconds to detect gaps and continue from checkpoint
- **Smoke Tier Latency**: <2 minutes (5 samples × 8 benchmarks)
- **Quick Tier Latency**: <20 minutes (75 samples × 8 benchmarks)
- **Full Tier Latency**: <2 hours per model (~5,000 problems)
- **Checkpoint Overhead**: <1% performance impact (async state writes)
- **Error Recovery**: Auto-retry on transient errors (EPIPE, timeout, connection reset)
- **Graceful Degradation**: Skip failed models, continue evaluation, report at end

**Monitoring Strategy**:
- **Development**: Structured JSON logging, console progress output
- **CI/CD**: Test result reporting, failure notifications (email/Slack)
- **Production Use**: Log aggregation (optional, not required for v1.0)
- **State Health**: Gap detection command (`matric-eval --validate run-{id}`)

**Chosen**: Structured logging + progress streaming (console output for human monitoring, JSON logs for CI parsing)

### Testing & Quality

**Coverage Targets**: Production-level testing

**Profile Defaults**:
- **Prototype**: 0-30% (manual testing OK, fast iteration priority)
- **MVP**: 30-60% (critical paths covered, some integration tests)
- **Production**: 60-80% (comprehensive unit + integration, some e2e) ← **Default**
- **Enterprise**: 80-95% (comprehensive coverage, full e2e, performance/load testing)

**Chosen**: 60% coverage - **Rationale**: Production default. Solo developer prioritizing functional correctness over exhaustive testing. Focus test coverage on:
- **Critical path**: Checkpoint/resume state management (80%+ coverage)
- **Recovery logic**: Error classification, retry mechanisms (70%+ coverage)
- **Core evaluation**: Task runners, scorers, gap detection (60%+ coverage)
- **Language bindings**: Integration tests for TypeScript/Rust subprocess calls (50%+ coverage)
- **CLI interface**: Smoke tests for main workflows (40%+ coverage)

**Test Types**:
- **Unit**: pytest for core logic (state management, recovery, scorers)
- **Integration**: End-to-end tests for one benchmark (HumanEval + llama3.2:3b)
- **State Tests**: Checkpoint/resume scenarios (crash recovery, gap detection, selective re-run)
- **Binding Tests**: TypeScript/Rust subprocess integration (cross-language communication)
- **Performance Tests**: Smoke/Quick/Full tier timing benchmarks (regression detection)
- **CI Smoke Tests**: Fast validation on every commit (<5 min)

**Quality Gates**:
- **Pre-commit**: Linting (ruff), type checking (mypy), formatting (black)
- **CI**: All tests pass, type checking clean, 60% coverage threshold
- **Pre-release**: Manual validation of checkpoint/resume, bindings integration test
- **Documentation**: README, ADRs for major decisions, inline docstrings

### Process Rigor

**SDLC Adoption**: Production-level process for infrastructure project

**Profile Defaults**:
- **Prototype**: Minimal (README, ad-hoc, trunk-based)
- **MVP**: Moderate (user stories, basic architecture docs, feature branches, PRs for review)
- **Production**: Full (requirements docs, SAD, ADRs, test plans, runbooks, traceability) ← **Default**
- **Enterprise**: Enterprise (full artifact suite, compliance evidence, change control, audit trails)

**Chosen**: Production (Full SDLC) - **Rationale**: Infrastructure project used by multiple applications. Decisions have long-term impact. Solo developer needs structured process to avoid scope creep and maintain quality. ADRs critical for documenting framework choice, state design, recovery strategy.

**Key Artifacts** (required for Production profile):
- **Requirements**: User stories for key workflows (run evaluation, resume from checkpoint, generate config)
- **Architecture**: SAD (system architecture document), ADRs (architectural decision records)
- **Test Strategy**: Test plan covering unit/integration/performance testing approach
- **Deployment Plan**: Installation instructions, bindings publishing process
- **Runbook**: Operational procedures (troubleshooting failed evals, state corruption recovery)
- **Release Notes**: Semantic versioning, changelog, migration guides

**Tailoring Notes**:
- **Solo developer**: Self-review acceptable, PR reviews to self with CI validation
- **Lightweight governance**: No CCB or formal change control (overkill for single developer)
- **Documentation-first**: ADRs before major decisions (framework choice, state design, binding approach)
- **Pragmatic traceability**: Link user stories to tests, but no formal requirements matrix

## Improvement Roadmap

**Phase 1 (Immediate - Week 1-2): Prototype & Validation**

Critical setup for Production profile:
1. **Git + CI/CD**: Initialize repo with GitHub Actions or GitLab CI
2. **Python Project**: Set up uv, pyproject.toml, type checking (mypy)
3. **Linting & Formatting**: Configure ruff, black, pre-commit hooks
4. **Prototype**: Validate Inspect AI + Ollama integration (blocking gate)
5. **State Design**: Implement core checkpoint/resume structure (`results/run-{timestamp}/`)
6. **ADR #1**: Document framework choice (Inspect AI vs lm-eval-harness)

**Phase 2 (Short-term - Week 3-4): Core Implementation**

Build toward production-ready state:
1. **HumanEval Benchmark**: Full implementation with checkpoint/resume
2. **Recovery Logic**: Error classification, retry mechanisms, gap detection
3. **Smoke Tier**: Implement 5-sample tier for fast CI feedback
4. **Testing**: Achieve 40%+ coverage (state management, recovery, core eval)
5. **ADR #2**: Document state management design decisions
6. **Integration Test**: One end-to-end test (HumanEval on llama3.2:3b with interruption)

**Phase 3 (Medium-term - Week 5-6): Full Feature Set**

Complete v1.0 scope:
1. **All Benchmarks**: Implement all 8 public benchmarks (MBPP, GSM8K, ARC, etc.)
2. **All Tiers**: Smoke, Quick, Full evaluation modes
3. **Language Bindings**: TypeScript npm package, Rust crate (basic subprocess wrappers)
4. **Config Generation**: model-categories.json recommendation engine
5. **Testing**: Achieve 60% coverage target
6. **Documentation**: Complete README, installation guide, usage examples

**Phase 4 (Long-term - Week 7-8): Production Hardening**

Finalize for production use:
1. **Custom Tests**: Framework for app-specific tests (JSONL format, custom scorers)
2. **Performance Optimization**: Profile and optimize slow paths
3. **Error Handling**: Comprehensive error messages, recovery hints
4. **Runbook**: Operational troubleshooting guide
5. **Release**: Publish v1.0 to PyPI, npm, crates.io
6. **Migration**: Integrate into matric-cli and matric-memory

## Overrides and Customizations

**Security Overrides**:
- **Override**: Baseline security instead of Production default (Strong)
- **Rationale**: Internal tool with no PII, authentication, or network exposure. Strong security (threat modeling, SAST/DAST, audit logs) would be over-engineering. Baseline (SBOM, dependency scanning) is sufficient.
- **Revisit Trigger**: If matric-eval is exposed as network service or processes sensitive data

**Reliability Overrides**:
- **Override**: Recovery-focused metrics instead of traditional uptime SLA
- **Rationale**: CLI tool not applicable to uptime percentages. Instead, focus on resilience (100% recovery from interruptions, <5s resume latency, <1% checkpoint overhead).
- **Success Criteria**: Zero lost progress on any failure scenario (crash, cancel, network error, Ollama timeout)

**Testing Overrides**:
- **No override**: 60% coverage aligns with Production default
- **Focus**: Prioritize state management and recovery (80% coverage) over less critical components

**Process Overrides**:
- **No override**: Full SDLC (Production) appropriate for infrastructure project
- **Tailoring**: Solo developer means self-review acceptable, lightweight governance (no CCB)

## Key Decisions

**Decision #1: Profile Selection**
- **Chosen**: Production
- **Alternative Considered**: MVP (3-month timeline could fit MVP)
- **Rationale**: Blocking requirement for checkpoint/resume demands production-grade implementation. Multiple established applications (matric-cli, matric-memory) will adopt immediately, not experimental/MVP. Critical infrastructure for matric ecosystem justifies Production rigor.
- **Revisit Trigger**: If scope reduces significantly or timeline pressure increases, could drop to MVP with plan to harden in v1.1

**Decision #2: Security Posture**
- **Chosen**: Baseline (override from Production default)
- **Alternative Considered**: Strong (Production default)
- **Rationale**: Internal development tool with no PII, authentication, or sensitive data. Code execution sandboxed by Ollama. Strong security (threat modeling, SAST/DAST, audit logs) is unnecessary overhead for this use case.
- **Revisit Trigger**: If matric-eval is exposed as network service, processes user data, or requires multi-tenant isolation

**Decision #3: Test Coverage Target**
- **Chosen**: 60% (Production default)
- **Alternative Considered**: 80% (higher quality) or 40% (faster development)
- **Rationale**: Production default appropriate. Solo developer can maintain 60% with focused testing on critical paths (state management 80%, recovery 70%, core eval 60%). Higher coverage would slow development without proportional benefit.
- **Revisit Trigger**: If checkpoint/resume bugs occur frequently in production, increase to 70-80%

**Decision #4: Framework Choice**
- **Chosen**: Inspect AI (validate first, commit if checkpoint/resume adequate)
- **Alternative Considered**: lm-eval-harness (industry standard) or custom framework
- **Rationale**: Native Ollama support, agent evaluations, active UK government maintenance. Blocking gate: prototype checkpoint/resume in week 1. If inadequate, evaluate lm-eval-harness or build custom state layer.
- **Revisit Trigger**: If Inspect AI checkpoint/resume proves inadequate (ADR will document decision)

## Next Steps

1. **Review** this profile and confirm Production rigor is appropriate (not over/under-engineering)
2. **Validate** that security override (Baseline instead of Strong) is acceptable for internal tool
3. **Confirm** 60% test coverage target is realistic for solo developer in 6-8 weeks
4. **Begin Inception phase** to create detailed requirements, architecture, and test strategy:
   - Use `/flow-concept-to-inception .` to start structured SDLC process
   - Or continue with natural language: "Start Inception phase"
5. **Phase gate**: Revisit profile at Elaboration (after prototype validates Inspect AI)
