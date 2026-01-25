# Vision and Business Requirements

**Document ID**: REQ-VIS-001
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Planning Phase

## Executive Summary

matric-eval consolidates model evaluation capabilities from matric-cli (TypeScript) and matric-memory (Rust) into a unified Python framework. This eliminates duplicate code maintenance, standardizes evaluation methodology across the matric ecosystem, and enables consistent model selection for downstream applications. The framework will provide tiered evaluation (smoke/quick/full), support both public benchmarks and custom tests, and generate actionable model recommendations.

## Business Context

### Problem Statement

The matric ecosystem currently maintains evaluation code in multiple repositories:

- **matric-cli**: TypeScript evaluation in `source/eval/` with public benchmarks (HumanEval, MBPP, GSM8K)
- **matric-memory**: Rust evaluation in `crates/matric-inference/` with custom LLM-as-judge tests

This duplication creates:

1. **Maintenance Burden**: Bug fixes and improvements must be implemented twice
2. **Inconsistent Methodology**: Different scoring approaches lead to incomparable results
3. **Wasted Development Time**: Solving the same problems independently
4. **Configuration Drift**: Model selection criteria diverge across applications

### Solution Approach

Build a Python-based evaluation framework using Inspect AI (UK AI Safety Institute):

- Native Ollama support with `ollama/model` syntax
- 100+ pre-built benchmark evaluations
- Agent and tool calling evaluation capabilities
- Active maintenance by UK government AI Safety Institute
- Extensible architecture for custom application-specific tests

### Strategic Alignment

This project supports the matric ecosystem's goals:

- **Standardization**: Single source of truth for model evaluation
- **Quality**: Rigorous benchmarking ensures appropriate model selection
- **Efficiency**: Tiered evaluation (smoke/quick/full) optimizes resource usage
- **Interoperability**: Language bindings enable TypeScript and Rust integration

## Stakeholder Analysis

### Primary Stakeholders

| Stakeholder | Interest | Influence | Requirements Focus |
|------------|----------|-----------|-------------------|
| matric-cli Developers | High | High | TypeScript bindings, HumanEval/MBPP accuracy, artifact preservation |
| matric-memory Developers | High | High | Rust bindings, LLM-as-judge evaluation, custom test migration |
| DevOps Team | Medium | High | CI/CD integration, automated smoke tests, resource efficiency |
| End Users (matric consumers) | High | Low | Accurate model recommendations, clear performance metrics |
| Project Maintainer (roctinam) | High | High | Code consolidation, maintenance reduction, ecosystem coherence |

### Stakeholder Needs

#### matric-cli Team

- Preserve MBPP function name extraction logic
- Maintain code extraction with markdown fence handling
- Safe execution with sandboxing (timeout, memory limits, no network)
- Artifact preservation in all validation paths
- Reproducible sampling with seeded random
- Model size filtering (skip models > MAX_MODEL_SIZE_GB)

#### matric-memory Team

- Port 282 custom matric tests from `evals/` directory
- Maintain LLM-as-judge evaluation templates
- Support agentic judge with multi-turn validation
- Tool calling evaluation for 6 key scenarios
- Preserve scoring dimensions (accuracy, relevance, coherence, completeness, safety)

#### DevOps Team

- Automated smoke tests in CI/CD pipeline
- Checkpoint/resume for long-running evaluations
- Comprehensive logging and observability
- Resource-efficient parallel execution
- Clear failure modes and error reporting

#### End Users

- Fast smoke tests (<5 minutes) for sanity checking
- Quick evaluations (<30 minutes) for common use cases
- Full evaluations for comprehensive model selection
- Clear, actionable model recommendations
- Reproducible results across runs

## Success Metrics

### Technical Success Criteria

| Metric | Target | Measurement Method | Priority |
|--------|--------|-------------------|----------|
| Code Consolidation | 100% of eval code removed from matric-cli and matric-memory | LOC reduction in source repos | Critical |
| Benchmark Coverage | 8+ public benchmarks supported | Count of implemented tasks | Critical |
| Custom Test Migration | 282 matric tests successfully ported | Test execution success rate | High |
| Smoke Test Speed | <5 minutes for tier=smoke | CI/CD execution time | High |
| Quick Test Speed | <30 minutes for tier=quick | Benchmark execution time | High |
| Evaluation Accuracy | 100% match with reference implementations | Score comparison vs. original evals | Critical |
| Reproducibility | Same scores on repeated runs with same seed | Statistical variance analysis | High |
| Resource Efficiency | Parallel execution with <20% overhead | Wall time vs. sequential baseline | Medium |

### Operational Success Criteria

| Metric | Target | Measurement Method | Priority |
|--------|--------|-------------------|----------|
| CI/CD Integration | Automated smoke tests on all PRs | Pipeline execution count | Critical |
| Checkpoint Reliability | Resume from any failure with <1% data loss | Fault injection testing | High |
| Developer Adoption | matric-cli and matric-memory using bindings | Integration implementation status | Critical |
| Documentation Coverage | 100% of public APIs documented | Doc coverage tool | High |
| Error Recovery | Clear error messages for 90%+ of failures | User feedback analysis | Medium |

### Business Success Criteria

| Metric | Target | Measurement Method | Priority |
|--------|--------|-------------------|----------|
| Maintenance Time Reduction | 50% less time on eval code maintenance | Developer time tracking | High |
| Model Selection Consistency | Same model recommendations across ecosystem | Config comparison | High |
| Feature Velocity | New benchmark support in <2 days | Issue close time | Medium |
| Community Adoption | External projects using matric-eval | GitHub stars, forks | Low |

## Business Requirements

### BR-001: Code Consolidation

**Description**: Eliminate duplicate evaluation code from matric-cli and matric-memory.

**Acceptance Criteria**:
- matric-cli `source/eval/` directory removed
- matric-memory `crates/matric-inference/src/bin/eval.rs` removed
- All functionality preserved in matric-eval
- Language bindings provide equivalent capabilities

**Traced to**: Foundation for all issues

### BR-002: Evaluation Accuracy

**Description**: Match or exceed accuracy of existing evaluation implementations.

**Acceptance Criteria**:
- HumanEval scores match matric-cli implementation (±0.1%)
- MBPP scores match matric-cli implementation (±0.1%)
- Custom tests match matric-memory implementation (100% agreement)
- Reproducible results with seeded random

**Traced to**: #1, #2, #7

### BR-003: Resource Efficiency

**Description**: Provide tiered evaluation to optimize resource usage.

**Acceptance Criteria**:
- Smoke tier: <5 minutes, validates basic functionality
- Quick tier: <30 minutes, covers common use cases
- Full tier: Comprehensive evaluation with all benchmarks
- Parallel execution support for reduced wall time

**Traced to**: #6, #12

### BR-004: Ecosystem Integration

**Description**: Enable seamless integration with existing matric projects.

**Acceptance Criteria**:
- TypeScript bindings for matric-cli
- Rust bindings for matric-memory
- CLI compatible with existing workflow scripts
- JSON output format for machine consumption

**Traced to**: #16

### BR-005: Operational Excellence

**Description**: Ensure reliable operation in production environments.

**Acceptance Criteria**:
- Checkpoint/resume for fault tolerance
- Comprehensive logging for troubleshooting
- CI/CD integration with automated tests
- Clear error messages and recovery guidance

**Traced to**: #11, #13, #14

## Scope Definition

### In Scope

#### Phase 1: Core Foundation (Weeks 1-4)

- Inspect AI integration with Ollama
- HumanEval and MBPP code execution scoring
- Basic tiered CLI (smoke/quick/full)
- Integration with inspect-evals for public benchmarks
- IFEval constraint checking
- LiveCodeBench competitive programming
- DS-1000 data science scoring

**Traced to**: #1, #2, #3, #4, #5, #6

#### Phase 2: Custom Tests (Weeks 5-8)

- Port 282 custom matric tests
- Tool calling evaluation (6 scenarios)
- MT-Bench multi-turn with LLM-as-judge
- 5-dimensional scoring framework
- Port matric-memory LLM-as-Judge templates
- Universal LLM-as-Judge with agentic support

**Traced to**: #7, #8, #9, #10, #21, #22

#### Phase 3: Production Readiness (Weeks 9-12)

- Checkpoint/resume implementation
- Parallel model evaluation
- CI/CD pipeline with automated smoke tests
- Comprehensive logging and observability

**Traced to**: #11, #12, #13, #14

### Out of Scope (Future Phases)

#### Phase 4: Advanced Features

- Leaderboard and reporting dashboard
- Language bindings (TypeScript, Rust)
- Extended benchmarks (SWE-bench, GPQA, CyberSecEval, GAIA)
- Model recommendation engine
- Contamination detection
- Historical trend analysis

**Traced to**: #15, #16, #17, #18, #19, #20

#### Explicitly Excluded

- Model training or fine-tuning
- Model hosting or deployment
- Real-time inference serving
- Model architecture modifications
- Custom model development
- Commercial leaderboard hosting

### Scope Boundaries

| In Scope | Out of Scope |
|----------|--------------|
| Evaluating Ollama models | Evaluating OpenAI/Anthropic APIs |
| Code execution in sandbox | Production code deployment |
| Scoring and metrics | Model training |
| Language bindings | Full SDKs with advanced features |
| JSON configuration output | Interactive configuration UI |
| CI/CD smoke tests | Continuous model monitoring |

## Assumptions

### Technical Assumptions

1. **Ollama Availability**: Ollama server is running and accessible at localhost:11434
2. **Model Access**: Evaluated models are already pulled/available in Ollama
3. **Python Version**: Python 3.11+ is available in deployment environments
4. **Compute Resources**: Evaluation machines have sufficient RAM (16GB+) and CPU
5. **Dataset Access**: Public benchmark datasets are available at `/home/roctinam/data/evals/`
6. **Network Access**: Internet connectivity for package installation (not required for evaluation)
7. **Disk Space**: Sufficient storage for checkpoint files and evaluation logs

**Impact if Invalid**:
- Assumption 1 violation: Evaluation fails immediately
- Assumption 2 violation: Download time adds to evaluation duration
- Assumption 4 violation: Out-of-memory errors, failed evaluations
- Assumption 5 violation: Manual dataset download required

### Business Assumptions

1. **Maintenance Priority**: Reducing duplicate code maintenance is high priority
2. **Ecosystem Adoption**: matric-cli and matric-memory teams will adopt bindings
3. **Evaluation Frequency**: Smoke tests run on every PR, full evals weekly
4. **Model Lifecycle**: New models released monthly, requiring re-evaluation
5. **Resource Availability**: DevOps team can support CI/CD integration

**Impact if Invalid**:
- Assumption 2 violation: Project provides limited value, adoption fails
- Assumption 3 violation: CI/CD resource constraints, longer build times
- Assumption 5 violation: Delayed production deployment

### Organizational Assumptions

1. **Single Maintainer**: Primary development by roctinam
2. **Part-Time Effort**: Development occurs alongside other matric work
3. **Open Source**: Project remains open source, community contributions welcome
4. **Documentation Priority**: Self-service documentation is critical
5. **Backward Compatibility**: Existing eval scripts continue to work during migration

## Constraints

### Technical Constraints

1. **Ollama Models Only**: No support for API-based models (cost/latency constraints)
2. **Single Machine**: No distributed evaluation across multiple nodes (initial version)
3. **Python Ecosystem**: Must integrate with Inspect AI framework
4. **Sandbox Security**: Code execution must be isolated (no network, limited resources)
5. **Dataset Licensing**: Only use publicly available, permissively licensed benchmarks
6. **Backward Compatibility**: Preserve exact scoring logic from matric-cli/matric-memory

### Operational Constraints

1. **CI/CD Time Budget**: Smoke tests must complete within GitHub Actions free tier limits
2. **Disk Space**: Checkpoints and logs must fit within reasonable storage quotas
3. **Memory Footprint**: Must run on developer laptops (16GB RAM)
4. **Installation Complexity**: Single `uv sync` command for setup
5. **Python Version**: Support Python 3.11+ (Ubuntu 24.04 default)

### Business Constraints

1. **Budget**: Zero-cost infrastructure (use existing Ollama deployments)
2. **Timeline**: Phase 1 completion within 4 weeks
3. **Resource**: Single developer, part-time effort
4. **Dependencies**: Cannot modify Inspect AI framework, only extend it
5. **Migration Timeline**: matric-cli/matric-memory must migrate within 3 months

## Risk Analysis

| Risk | Probability | Impact | Mitigation Strategy | Owner |
|------|------------|--------|---------------------|-------|
| Inspect AI lacks critical feature | Medium | High | Prototype key scenarios first, fallback to lm-eval-harness | Development |
| Scoring accuracy drift during migration | Medium | Critical | Validation suite comparing old vs. new scores | Quality |
| Checkpoint/resume complexity exceeds estimate | High | Medium | Iterative implementation, start with simple state | Development |
| Adoption resistance from matric teams | Low | Critical | Early stakeholder engagement, demonstrate value | Product |
| Dataset licensing issues | Low | Medium | Audit all datasets, maintain attribution | Legal/Compliance |
| Ollama API changes break integration | Low | High | Pin Ollama version, monitor release notes | DevOps |
| Resource exhaustion in CI/CD | Medium | Medium | Implement resource limits, optimize smoke tests | DevOps |
| LLM-as-judge reliability issues | High | Medium | Multiple judge models, statistical validation | Quality |
| Custom test migration introduces bugs | Medium | High | Side-by-side comparison, gradual cutover | Development |
| Performance degradation vs. native implementations | Low | Medium | Benchmark against baselines, optimize critical paths | Development |

## Dependencies

### Internal Dependencies

1. **matric-cli**: Requires TypeScript bindings (Phase 4)
2. **matric-memory**: Requires Rust bindings (Phase 4)
3. **Ollama**: Must be running and accessible
4. **Dataset Repository**: Public benchmarks at `/home/roctinam/data/evals/`

### External Dependencies

1. **Inspect AI**: Core evaluation framework
2. **inspect-evals**: Pre-built benchmark implementations
3. **Python 3.11+**: Runtime environment
4. **uv**: Package and project management
5. **pytest**: Testing framework
6. **Docker** (optional): For enhanced sandboxing

### Critical Path

```
Inspect AI Integration (Week 1)
    ↓
HumanEval Migration (Week 2)
    ↓
Public Benchmarks via inspect-evals (Week 3)
    ↓
Tiered CLI (Week 4)
    ↓
Custom Test Migration (Weeks 5-8)
    ↓
Production Hardening (Weeks 9-12)
    ↓
Ecosystem Integration (Phase 4)
```

## Open Questions

### Technical Questions

1. **Inspect AI Maturity**: Can inspect-evals handle all required benchmarks, or do we need custom implementations?
2. **Sandbox Approach**: Docker-based sandboxing vs. Python subprocess isolation?
3. **Checkpoint Format**: JSON, Pickle, SQLite, or custom binary format?
4. **Parallel Execution**: Process pool, thread pool, or async/await?
5. **LLM-as-Judge Model Selection**: Which judge models provide best reliability?

### Business Questions

1. **Migration Timeline**: Should we enforce a hard cutover date for matric-cli/matric-memory?
2. **Community Support**: Do we accept external contributions during Phase 1?
3. **Versioning Strategy**: Semantic versioning with 0.x or jump to 1.0?
4. **Release Cadence**: Weekly releases during development or milestone-based?

### Operational Questions

1. **CI/CD Strategy**: GitHub Actions, GitLab CI, or self-hosted runners?
2. **Monitoring**: Application-level metrics or just CI/CD pass/fail?
3. **Documentation Hosting**: ReadTheDocs, GitHub Pages, or project wiki?
4. **Issue Tracking**: Gitea only, or also GitHub Issues for community?

## Next Steps

### Immediate Actions (Week 1)

1. **Prototype Validation**: Implement minimal Inspect AI + Ollama integration
2. **HumanEval PoC**: Migrate one benchmark to prove scoring accuracy
3. **Architecture Review**: Finalize directory structure and module boundaries
4. **Stakeholder Briefing**: Present plan to matric-cli and matric-memory teams

### Short Term (Weeks 2-4)

1. **Core Implementation**: Complete Phase 1 deliverables (#1-#6)
2. **Testing Infrastructure**: Establish pytest framework and CI/CD
3. **Documentation**: Write API docs and user guides
4. **Early Validation**: Run smoke tests in matric-cli CI/CD

### Medium Term (Weeks 5-12)

1. **Custom Tests**: Complete Phase 2 deliverables (#7-#10, #21-#22)
2. **Production Hardening**: Complete Phase 3 deliverables (#11-#14)
3. **Migration Planning**: Coordinate cutover with downstream teams
4. **Community Preparation**: Polish docs for external users

## References

- **Inspect AI Documentation**: https://inspect.aisi.org.uk/
- **lm-eval-harness**: https://github.com/EleutherAI/lm-evaluation-harness
- **HELM Benchmark**: https://crfm.stanford.edu/helm/
- **Gitea Project**: https://git.integrolabs.net/roctinam/matric-eval
- **Planning Document**: /home/roctinam/dev/matric-eval/PLANNING.md
- **Claude Instructions**: /home/roctinam/dev/matric-eval/CLAUDE.md

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial vision and business requirements |
