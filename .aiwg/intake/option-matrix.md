# Option Matrix (Project Context & Intent)

**Purpose**: Capture what this project IS - its nature, audience, constraints, and intent - to determine appropriate SDLC framework application (templates, commands, agents, rigor levels).

**Generated**: 2026-01-24 (from planning docs + interactive session)

## Step 1: Project Reality

### What IS This Project?

**Project Description** (in natural language):

```
matric-eval is a consolidated model evaluation framework for the matric ecosystem. It consolidates
duplicated evaluation code from matric-cli (TypeScript) and matric-memory (Rust) into a shared Python
framework leveraging Inspect AI. The framework evaluates Ollama models against public benchmarks
(HumanEval, MBPP, GSM8K, ARC, IFEval, LiveCodeBench, DS-1000, MTBench) and custom app-specific tests.

Critical requirement: Robust checkpoint/resume recovery (100% no lost progress on failures). This is
a blocking requirement driven by recent matric-cli eval failure (EPIPE at model 13/31, lost all progress).

Timeline: 6-8 weeks to production-ready v1.0. Solo Python expert developer. Users are matric-cli/memory
developers (via TypeScript/Rust bindings), DevOps CI automation, and any future matric app supporting
Ollama models.

Success: Framework validated (Inspect AI + Ollama working with checkpoint/resume), all 8 public benchmarks
running, TypeScript/Rust bindings working, matric-cli and matric-memory adopt within 3 months.
```

### Audience & Scale

**Who uses this?** (check all from user input):
- [ ] Just me (personal project)
- [x] Small team (2-10 people, known individuals) - matric-cli, matric-memory, future app developers
- [ ] Department (10-100 people, organization-internal)
- [ ] External customers (100-10k users, paying or free)
- [ ] Large scale (10k-100k+ users, public-facing)
- [x] Other: Any matric application supporting Ollama models (extensible ecosystem)

**Audience Characteristics**:
- Technical sophistication: Technical (Python, TypeScript, Rust developers)
- User risk tolerance: Expects stability (critical infrastructure for model selection)
- Support expectations: Best-effort (internal tool, community support)

**Usage Scale** (from user or inferred):
- Active users: 3-5 developers initially, 10-20 developers in 6 months, ecosystem-wide in 2 years
- Request volume: Variable (on-demand evals, daily CI smoke tests, weekly comprehensive evals)
- Data volume: ~10GB benchmark datasets (cached locally), ~1GB results per full eval run
- Geographic distribution: Single location (local development machines, CI servers)

### Deployment & Infrastructure

**Expected Deployment Model** (inferred from user requirements):
- [ ] Static site (HTML/CSS/JS, no backend, GitHub Pages/Netlify/Vercel)
- [ ] Client-server (SPA + API backend, traditional web app)
- [ ] Full-stack application (frontend + backend + database + workers)
- [ ] Multi-system (microservices, service mesh, distributed)
- [ ] Serverless (AWS Lambda, Cloud Functions, event-driven)
- [ ] Mobile (iOS/Android native or React Native/Flutter)
- [ ] Desktop (Electron, native apps)
- [x] CLI tool (command-line utility) - Primary deployment
- [x] Hybrid (multiple deployment patterns) - CLI + language bindings (npm, Cargo)

**Where does this run?** (from user preference or defaults):
- [ ] Cloud platform (AWS, GCP, Azure, Vercel, Netlify)
- [ ] On-premise (company servers, data center)
- [ ] Hybrid (cloud + on-premise)
- [x] Local only (laptop, desktop, not deployed) - Development machines
- [x] CI/CD environment (GitHub Actions, GitLab CI) - Automated smoke tests

**Infrastructure Complexity**:
- Deployment type: CLI tool (pip/uv installable) + language bindings (npm, Cargo)
- Data persistence: File system (JSON state files, JSONL datasets)
- External dependencies: Ollama API (localhost:11434), Inspect AI framework, public datasets
- Network topology: Standalone (local execution, subprocess calls to Ollama)

### Technical Complexity

**Codebase Characteristics** (estimated):
- Size: 5k-10k LoC Python (core framework, state management, bindings)
- Languages: Python (primary), TypeScript (bindings), Rust (bindings)
- Architecture: Modular monolith (clear module boundaries, single package)
- Team familiarity: Greenfield (new project, no legacy constraints)

**Technical Risk Factors** (check all from requirements):
- [x] Performance-sensitive (latency, throughput critical) - Full eval <2 hours, smoke <2 min
- [ ] Security-sensitive (PII, payments, authentication)
- [x] Data integrity-critical (financial, medical, legal records) - State corruption must never lose progress
- [ ] High concurrency (many simultaneous users/processes)
- [x] Complex business logic (many edge cases, domain rules) - Checkpoint/resume, gap detection, error classification
- [x] Integration-heavy (many external systems, APIs) - Ollama API, Inspect AI, TypeScript/Rust subprocess
- [ ] None (straightforward technical requirements)

---

## Step 2: Constraints & Context

### Resources

**Team** (from user input):
- Size: 1 developer (solo, Python expert)
- Experience: Senior (expert Python, proficient TypeScript/Rust, familiar DevOps)
- Availability: Full-time (dedicated focus on matric-eval)

**Budget** (from user or inferred):
- Development: Unconstrained (full-time developer allocation)
- Infrastructure: Free tier (local development machines, existing CI infrastructure)
- Timeline: 6-8 weeks to production-ready v1.0

### Regulatory & Compliance

**Data Sensitivity** (check all from user input):
- [x] Public data only (no privacy concerns) - Public benchmark datasets, evaluation results internal
- [ ] User-provided content (email, profile, preferences)
- [ ] Personally Identifiable Information (PII: name, address, phone)
- [ ] Payment information (credit cards, financial accounts)
- [ ] Protected Health Information (PHI: medical records)
- [ ] Sensitive business data (trade secrets, confidential)

**Regulatory Requirements** (check all from user mention or inferred):
- [x] None (no specific regulations) - Internal development tool, public datasets
- [ ] GDPR (EU users, data privacy)
- [ ] CCPA (California users)
- [ ] HIPAA (US healthcare)
- [ ] PCI-DSS (payment card processing)
- [ ] SOX (US financial reporting)
- [ ] SOC2 (service organization controls)

**Contractual Obligations** (from user):
- [x] None (no contracts) - Internal tool, no external SLAs
- [ ] SLA commitments (uptime, response time guarantees)
- [ ] Security requirements (penetration testing, audits)
- [ ] Compliance certifications (SOC2, ISO27001)

### Technical Context

**Current State** (for new project):
- Current stage: Planning (greenfield project, architecture validated via PLANNING.md)
- Test coverage: Target 60% (Production profile)
- Documentation: Target Full SDLC (SAD, ADRs, test strategy, runbook)
- Deployment automation: CI/CD with smoke tests on PRs

---

## Step 3: Priorities & Trade-offs

### What Matters Most?

**Rank these priorities** (1 = most important, 4 = least important):

From user responses and project characteristics:
- **1** - Quality & security (build it right, avoid issues) - Checkpoint/resume blocking requirement
- **2** - Reliability & scale (handle growth, stay available) - 100% recovery success rate
- **3** - Speed to delivery (launch fast, iterate quickly) - 6-8 weeks realistic but not rushed
- **4** - Cost efficiency (minimize time/money spent) - Solo developer, free infrastructure

**Priority Weights** (must sum to 1.0, derived from ranking):

| Criterion | Weight | Rationale |
|-----------|--------|-----------|
| **Quality/security** | **0.40** | Blocking requirement for checkpoint/resume resilience. State corruption unacceptable. Production-grade implementation from day one. |
| **Reliability/scale** | **0.35** | 100% recovery success rate non-negotiable. Error handling, retry logic, graceful degradation critical. |
| **Delivery speed** | **0.15** | 6-8 weeks to v1.0 allows thorough implementation without rushing. Prioritize correctness over speed. |
| **Cost efficiency** | **0.10** | Solo developer time manageable. Free infrastructure (local dev, CI). Optimize for maintainability over cost. |
| **TOTAL** | **1.00** | Quality and reliability dominate (75% combined). Speed and cost secondary. |

### Trade-off Context

**What are you optimizing for?**
```
Robustness and resilience over speed. The entire purpose of matric-eval consolidation is to solve
checkpoint/resume failures that caused lost progress (recent EPIPE at model 13/31). A fast but fragile
implementation misses the point.

Optimize for:
- 100% recovery success rate (no lost progress ever)
- Clear error messages and recovery hints (developer experience)
- Maintainable, well-tested state management code (solo developer, future contributors)
- Production-ready from v1.0 (not MVP, not prototype - this is infrastructure)

Secondary optimizations:
- Fast smoke/quick tiers for CI feedback (<2 min, <20 min)
- Minimal binding complexity (thin subprocess wrappers, easy to maintain)
```

**What are you willing to sacrifice?**
```
- Development speed: Will take 6-8 weeks (not 2-4 weeks) to ensure production quality
- Feature scope: Custom tests can wait until public benchmarks solid. Config generation lower priority than resilience.
- Performance optimization: Full eval can be slower initially, optimize in v1.1 if needed
- Bells and whistles: No web UI, no real-time leaderboard, no distributed evaluation - focus on core CLI excellence

NOT willing to sacrifice:
- Checkpoint/resume robustness (blocking requirement)
- All evaluation tiers (smoke/quick/full - all equally important per user)
- Language bindings (TypeScript/Rust - needed for adoption)
```

**What is non-negotiable?**
```
1. Checkpoint/resume MUST work (100% recovery, no lost progress)
2. All tiers (smoke/quick/full) required from v1.0 (user specified "all tiers equally important")
3. Inspect AI validation in week 1 (blocking gate, must confirm framework adequate)
4. TypeScript and Rust bindings (adoption depends on integration with matric-cli/memory)
5. Production quality from v1.0 (not MVP/prototype - this is critical infrastructure)
```

---

## Step 4: Intent & Decision Context

### Why This Intake Now?

**What triggered this intake?** (from user or inferred):
- [x] Starting new project (need to plan approach) - Greenfield infrastructure project
- [x] Seeking SDLC structure (want organized process) - Production profile requires full SDLC rigor
- [x] Team alignment (multiple stakeholders need shared understanding) - matric-cli, matric-memory, DevOps teams
- [ ] Funding/business milestone (investor pitch, customer demo)

**What decisions need making?**
```
1. Framework choice: Inspect AI vs lm-eval-harness vs custom
   - Blocking gate: Checkpoint/resume capabilities adequate?
   - Prototype in week 1 to validate before committing

2. State management design: Full upfront vs iterate
   - User chose "Full state design upfront" (recommended)
   - Implement complete results/run-{timestamp}/ hierarchy from start

3. Migration strategy: Parallel vs phased vs greenfield
   - User chose "Greenfield first, apps switch when ready"
   - Build best-of-breed, drop old code when matric-eval proven

4. Language binding approach: Subprocess vs FFI vs HTTP
   - Start with subprocess wrappers (simplest, proven pattern)
   - Consider FFI for Rust if performance critical

5. Testing strategy: Coverage targets, CI gates
   - 60% coverage target (Production profile)
   - Focus on state management (80%) and recovery (70%)
```

**What's uncertain or controversial?**
```
1. Inspect AI checkpoint/resume capabilities (UNKNOWN until prototype)
   - Framework may not support robust state management
   - May need custom layer on top of Inspect AI
   - Prepared to evaluate lm-eval-harness if inadequate

2. Performance of full evaluation (ESTIMATE: <2 hours per model)
   - 5,000 problems × inference time = unknown until prototype
   - May exceed target, require optimization

3. TypeScript/Rust binding overhead (subprocess spawn cost)
   - Should be negligible, but untested
   - May need FFI for Rust if subprocess too slow
```

**Success criteria for this intake process**
```
1. Clear framework decision path (Inspect AI first, fallback plan if inadequate)
2. Validated scope for v1.0 (public benchmarks + tiers + bindings, defer custom tests if needed)
3. Checkpoint/resume design documented and agreed (full state hierarchy upfront)
4. Timeline realistic (6-8 weeks with quality focus, not rushed)
5. Ready to start Inception phase (requirements, architecture, test strategy)
```

---

## Step 5: Framework Application

### Relevant SDLC Components

Based on project reality (Step 1) and priorities (Step 3), which framework components are relevant?

**Templates** (check applicable):
- [x] Intake (project-intake, solution-profile, option-matrix) - **COMPLETE**
- [x] Requirements (user-stories, use-cases, NFRs) - Solo dev but complex domain, user stories for workflows
- [x] Architecture (SAD, ADRs, API contracts) - Critical decisions (framework, state design, bindings)
- [x] Test (test-strategy, test-plan, test-cases) - 60% coverage target, state/recovery focus
- [ ] Security (threat-model, security-requirements) - Baseline security, no threat modeling needed
- [x] Deployment (deployment-plan, runbook, ORR) - pip/npm/Cargo publishing, troubleshooting guide
- [ ] Governance (decision-log, CCB-minutes, RACI) - Solo dev, no formal governance

**Commands** (check applicable):
- [x] Intake commands (intake-wizard, intake-start) - **COMPLETE**
- [x] Flow commands (/flow-iteration-dual-track) - Solo dev but structured sprints beneficial
- [ ] Quality gates (/security-gate, /gate-check) - Baseline security, no formal gates
- [x] Specialized (/build-poc) - Week 1 Inspect AI prototype critical

**Agents** (check applicable):
- [x] Core SDLC agents (requirements-analyst, architect, code-reviewer, test-engineer, devops-engineer) - Production profile
- [ ] Security specialists (security-gatekeeper, security-auditor) - Baseline security, internal tool
- [ ] Operations specialists (incident-responder, reliability-engineer) - Development tool, no ops
- [ ] Enterprise specialists (legal-liaison, compliance-validator) - No compliance requirements

**Process Rigor Level** (select based on profile):
- [ ] Minimal (README, lightweight notes)
- [ ] Moderate (user stories, basic architecture, test plan)
- [x] Full (comprehensive docs, traceability, gates) - **Production profile**
- [ ] Enterprise (audit trails, compliance evidence, change control)

### Rationale for Framework Choices

**Why this subset of framework?**
```
Production profile for critical infrastructure project:

Required components:
- **Intake** (✓ COMPLETE): Establish baseline, align matric ecosystem teams
- **Requirements**: User stories for key workflows (run eval, resume, generate config)
  - Solo dev but complex domain (checkpoint/resume, error classification)
  - User stories ensure clear acceptance criteria
- **Architecture**: SAD + ADRs critical for infrastructure project
  - ADR #1: Framework choice (Inspect AI vs alternatives)
  - ADR #2: State management design (results hierarchy)
  - ADR #3: Language binding approach (subprocess vs FFI)
  - SAD: Overall system architecture, component diagram, data flow
- **Test**: 60% coverage target requires test strategy and plan
  - Focus areas: State management (80%), recovery (70%), core eval (60%)
  - Integration tests: HumanEval end-to-end with checkpoint/resume
  - CI smoke tests: Fast validation on every commit
- **Deployment**: pip/npm/Cargo publishing process, runbook for troubleshooting
  - Runbook: State corruption recovery, failed eval debugging
  - Publishing: PyPI, npm registry, crates.io

Skipped components:
- **Security templates**: Baseline security sufficient (internal tool, no PII/auth)
- **Governance**: Solo developer, no CCB or formal change control needed
- **Operations specialists**: Development tool, no 24/7 ops, no incident response
- **Enterprise templates**: No compliance, no contracts, no audit requirements

Core SDLC agents:
- Requirements Analyst: Translate user stories into technical specs
- Architect: Design state management, choose framework, binding approach
- Code Reviewer: Self-review with CI validation (linting, type checking, tests)
- Test Engineer: Ensure 60% coverage, focus on critical paths
- DevOps Engineer: CI/CD setup, publishing automation
```

**What we're skipping and why** (be explicit):
```
Skipping because internal development tool:
- Security templates (threat modeling, SAST/DAST gates) - Baseline security sufficient
- Governance templates (CCB, change control) - Solo developer, overkill
- Operations agents (incident responder, reliability engineer) - Not a service, no 24/7 ops
- Enterprise agents (legal liaison, compliance validator) - No regulatory requirements

Skipping because solo developer:
- Formal PR reviews (self-review + CI sufficient)
- RACI matrix (single owner for all components)
- Team coordination templates (no team to coordinate)

Will revisit if:
- Exposed as network service → add security templates
- Team grows >3 people → add governance, RACI
- Compliance requirements emerge → add enterprise templates
```

---

## Step 6: Evolution & Adaptation

### Expected Changes

**How might this project evolve?** (from user or inferred):
- [x] User base growth (when: 6 months, trigger: matric-cli/memory adoption complete, other apps integrate)
- [x] Feature expansion (when: 3-6 months, trigger: v1.0 successful, custom tests added, distributed eval)
- [ ] Team expansion (when: TBD, trigger: matric-eval becomes ecosystem-critical, contributors join)
- [ ] Commercial/monetization (N/A - internal tool)
- [ ] Compliance requirements (unlikely - internal tool)
- [ ] Technical pivot (when: week 1, trigger: Inspect AI checkpoint/resume inadequate)

**Adaptation Triggers** (when to revisit framework application):
```
Week 1 (Prototype phase):
- If Inspect AI checkpoint/resume inadequate → evaluate lm-eval-harness or custom framework
- Update ADR #1 with framework decision rationale

Week 4 (Mid-project checkpoint):
- If timeline slipping → reduce scope (defer custom tests to v1.1)
- If 60% coverage unrealistic → adjust to 50%, focus on state/recovery (80%/70%)

v1.0 Launch (Week 8):
- If adoption successful → add custom test framework (v1.1)
- If performance issues → optimize full tier (v1.1)
- If binding overhead high → consider FFI for Rust (v1.1)

6 Months Post-Launch:
- If team grows >3 → add governance templates, PR reviews
- If exposed as service → upgrade security to Strong, add threat modeling
- If compliance needed → upgrade to Enterprise profile
```

**Planned Framework Evolution** (from analysis):
- **Current (Inception - Week 1-2)**: Requirements, Architecture (ADR #1: framework choice)
- **Elaboration (Week 3-4)**: Architecture (SAD, ADRs #2-3), Test Strategy, Deployment Plan
- **Construction (Week 5-6)**: Implementation, Testing (60% coverage), Runbook
- **Transition (Week 7-8)**: Publishing, Integration (bindings), Migration (apps adopt)

---

## Architectural Options Analysis

### Option A: Inspect AI Foundation

**Description**: Leverage Inspect AI framework (UK AI Safety Institute) as foundation. Native Ollama support, 100+ pre-built evaluations, agent/tool evaluation capabilities. Custom state management layer on top if checkpoint/resume inadequate.

**Technology Stack**:
- **Framework**: Inspect AI (Python, uv, modern tooling)
- **State Management**: Custom layer (results/run-{timestamp}/ hierarchy)
- **Ollama Integration**: Native `ollama/llama3.2` syntax
- **Bindings**: TypeScript/Rust subprocess wrappers
- **CI/CD**: GitHub Actions, pytest, mypy, ruff

**Scoring** (0-5 scale):
| Criterion | Score | Rationale |
|-----------|------:|-----------|
| Delivery Speed | 4 | Pre-built benchmarks (HumanEval, MBPP, etc.) save weeks. Native Ollama support (no adapter needed). |
| Cost Efficiency | 5 | Free framework, local infrastructure, solo dev can maintain easily. |
| Quality/Security | 4 | Mature framework (UK government backed), but checkpoint/resume unknown (risk). Custom state layer adds complexity. |
| Reliability/Scale | 4 | Framework stable, but need to validate checkpoint/resume. Custom state management = full control over recovery. |
| **Weighted Total** | **4.15** | (4×0.15) + (5×0.10) + (4×0.40) + (4×0.35) = 4.15/5.0 |

**Trade-offs**:
- **Pros**:
  - Native Ollama support (`ollama/llama3.2` syntax works)
  - 100+ pre-built evaluations (HumanEval, MBPP, GSM8K, etc.)
  - Agent/tool evaluation support (matric-cli custom tests)
  - Active maintenance (UK AI Safety Institute)
  - Modern Python (uv, type hints, async)
  - Community support, documentation
- **Cons**:
  - Checkpoint/resume capabilities unknown (risk, must validate week 1)
  - May need custom state management layer (adds complexity)
  - Smaller ecosystem than lm-eval-harness (fewer tutorials, examples)
  - Framework abstraction may hide Ollama API details

**When to choose**: If week 1 prototype validates checkpoint/resume works or custom state layer feasible. Recommended if agent/tool evaluations important for matric-cli custom tests.

### Option B: lm-eval-harness Foundation

**Description**: Use lm-eval-harness (EleutherAI) as foundation. Industry standard, powers HuggingFace leaderboard, maximum benchmark coverage. Ollama support via local-completions adapter.

**Technology Stack**:
- **Framework**: lm-eval-harness (Python, mature ecosystem)
- **State Management**: Framework built-in (unknown capabilities)
- **Ollama Integration**: local-completions adapter (`base_url=http://localhost:11434/v1/completions`)
- **Bindings**: TypeScript/Rust subprocess wrappers
- **CI/CD**: GitHub Actions, pytest, mypy, ruff

**Scoring** (0-5 scale):
| Criterion | Score | Rationale |
|-----------|------:|-----------|
| Delivery Speed | 3 | Industry standard, but Ollama adapter requires setup. More tutorials but steeper learning curve. |
| Cost Efficiency | 5 | Free framework, local infrastructure, large community means easy troubleshooting. |
| Quality/Security | 5 | Battle-tested (HuggingFace leaderboard backend), mature codebase, extensive benchmarks. |
| Reliability/Scale | 3 | Stable framework, but checkpoint/resume unknown. May have same state management risks as Inspect AI. |
| **Weighted Total** | **3.95** | (3×0.15) + (5×0.10) + (5×0.40) + (3×0.35) = 3.95/5.0 |

**Trade-offs**:
- **Pros**:
  - Industry standard (HuggingFace leaderboard backend)
  - Maximum benchmark coverage (60+ tasks built-in)
  - Mature codebase, extensive documentation
  - Large community, many tutorials
  - Exact parity with public leaderboards (reproducibility)
- **Cons**:
  - Ollama support via adapter (not native, more setup)
  - Checkpoint/resume capabilities unknown (same risk as Inspect AI)
  - Less focus on agent/tool evaluation (research-oriented)
  - May be over-engineered for matric ecosystem needs

**When to choose**: If Inspect AI checkpoint/resume inadequate OR if exact HuggingFace leaderboard parity critical OR if agent/tool evaluations not important.

### Option C: Custom Framework (Minimal Dependencies)

**Description**: Build custom evaluation framework with minimal dependencies. Direct Ollama API calls, custom state management, JSONL-based test format. Maximum control over checkpoint/resume behavior.

**Technology Stack**:
- **Framework**: Custom Python (requests for Ollama API, asyncio for concurrency)
- **State Management**: Full custom (results/run-{timestamp}/ hierarchy, atomic writes, lock files)
- **Ollama Integration**: Direct HTTP API calls (full control)
- **Bindings**: TypeScript/Rust subprocess wrappers
- **CI/CD**: GitHub Actions, pytest, mypy, ruff

**Scoring** (0-5 scale):
| Criterion | Score | Rationale |
|-----------|------:|-----------|
| Delivery Speed | 1 | Rebuild everything from scratch (prompt handling, validation, scoring). 6-8 weeks insufficient. |
| Cost Efficiency | 2 | Solo dev time expensive (weeks to replicate what frameworks provide). Maintenance burden high. |
| Quality/Security | 3 | Full control, but high bug risk (reinventing wheel). State management complex, error-prone. |
| Reliability/Scale | 5 | **Maximum control over checkpoint/resume** (blocking requirement). Can implement exactly what we need. |
| **Weighted Total** | **3.20** | (1×0.15) + (2×0.10) + (3×0.40) + (5×0.35) = 3.20/5.0 |

**Trade-offs**:
- **Pros**:
  - **Maximum control over checkpoint/resume** (can implement exactly what we need)
  - No framework limitations or abstraction leaks
  - Direct Ollama API access (no adapter layer)
  - Minimal dependencies (easier to debug)
  - Custom state format optimized for matric use cases
- **Cons**:
  - **Reinventing the wheel** (prompt formatting, validation, scoring)
  - **6-8 week timeline insufficient** (need 12-16 weeks for custom framework)
  - High bug risk (complex state management, error classification)
  - Solo developer maintenance burden (no community support)
  - Missing pre-built benchmarks (need to implement MBPP function extraction, etc.)

**When to choose**: If both Inspect AI and lm-eval-harness checkpoint/resume inadequate AND no time pressure (12+ week timeline). **Not recommended for v1.0.**

---

## Recommendation

**Recommended Option**: **Option A: Inspect AI Foundation** (Score: 4.15/5.0)

**Rationale**:
1. **Best fit for quality/reliability priorities (75% weight)**: Mature framework with active UK government maintenance. Native Ollama support reduces integration risk. Pre-built benchmarks save development time, allowing focus on state management quality.

2. **Checkpoint/resume validation in week 1 (blocking gate)**: Prototype will reveal if Inspect AI checkpoint/resume adequate. If yes, proceed confidently. If no, custom state layer on top of Inspect AI is feasible (better than full custom framework).

3. **Agent/tool evaluation support**: matric-cli custom tests require tool calling validation. Inspect AI designed for this (MCP tool support). lm-eval-harness less suited.

4. **6-8 week timeline realistic**: Pre-built benchmarks + native Ollama support = fast start. Solo developer can focus on state management and bindings (not reimplementing benchmarks).

5. **Ecosystem fit**: Modern Python (uv, type hints, async) aligns with matric ecosystem preferences. Active maintenance means bug fixes and improvements.

**Decision Path**:
- **Week 1**: Prototype Inspect AI + Ollama integration
  - Validate checkpoint/resume capabilities (blocking gate)
  - Test HumanEval against llama3.2:3b
  - Measure performance baseline
- **If adequate**: Proceed with Option A (Inspect AI Foundation)
- **If inadequate**: Evaluate Option B (lm-eval-harness) in week 2
- **If both fail**: Custom state layer on top of Inspect AI (hybrid approach)

**Sensitivities**:
- **If Inspect AI checkpoint/resume fails** → Evaluate lm-eval-harness (week 2)
- **If timeline extends to 12+ weeks** → Could consider Option C (custom framework)
- **If agent evaluations not needed** → lm-eval-harness becomes more attractive (HF leaderboard parity)

**Implementation Plan**:
1. **Week 1**: Inspect AI prototype + checkpoint/resume validation (blocking gate)
2. **Week 2-3**: Implement state management (full hierarchy), HumanEval benchmark
3. **Week 4-5**: Add remaining benchmarks (MBPP, GSM8K, ARC, etc.), smoke/quick/full tiers
4. **Week 6-7**: TypeScript/Rust bindings, config generation, testing (60% coverage)
5. **Week 8**: Publishing (PyPI, npm, crates.io), integration, documentation

**Risks and Mitigations**:
- **Risk 1**: Inspect AI checkpoint/resume inadequate
  - **Mitigation**: Week 1 prototype validates before full commitment. Fallback to lm-eval-harness or custom state layer.
- **Risk 2**: Performance exceeds 2-hour target for full tier
  - **Mitigation**: Optimize in v1.1 if needed. Smoke/quick tiers more important for CI feedback.
- **Risk 3**: Binding complexity higher than expected
  - **Mitigation**: Start with simple subprocess wrappers. Iterate to FFI if needed in v1.1.

---

## Next Steps

1. **Review** option-matrix and confirm Inspect AI (Option A) recommendation
2. **Validate** that 6-8 week timeline realistic for Inspect AI approach
3. **Confirm** blocking gate: Week 1 prototype must validate checkpoint/resume before proceeding
4. **Begin Inception phase** using Production profile templates:
   - Create user stories for key workflows (run eval, resume, generate config)
   - Create ADR #1: Framework choice decision rationale
   - Create test strategy focusing on state management and recovery
5. **Start week 1 prototype**: `/build-poc` or direct implementation
   - Inspect AI + Ollama integration
   - Basic checkpoint/resume test
   - HumanEval on llama3.2:3b
   - Performance baseline measurement

**Command to proceed**:
```bash
/flow-concept-to-inception .
```

Or natural language: "Start Inception phase with requirements and architecture artifacts"
