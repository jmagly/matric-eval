# Risk Register - matric-eval

**Project**: matric-eval - Consolidated Model Evaluation Framework
**Version**: 1.0
**Last Updated**: 2026-01-24
**Risk Owner**: Solo Python Developer

---

## Risk Scoring Matrix

| Probability | Impact | Risk Score |
|-------------|--------|------------|
| HIGH (3)    | HIGH (3) | 9 (Critical) |
| HIGH (3)    | MEDIUM (2) | 6 (High) |
| MEDIUM (2)  | HIGH (3) | 6 (High) |
| MEDIUM (2)  | MEDIUM (2) | 4 (Medium) |
| LOW (1)     | HIGH (3) | 3 (Low) |
| LOW (1)     | MEDIUM (2) | 2 (Low) |
| LOW (1)     | LOW (1) | 1 (Minimal) |

---

## Critical Risks (Score: 9)

### RISK-001: Inspect AI Lacks Native Checkpoint/Resume Support

**Category**: Technical - Framework Capability
**Status**: Identified
**Probability**: MEDIUM (2)
**Impact**: HIGH (3)
**Risk Score**: 6

**Description**: Inspect AI framework may not provide built-in checkpoint/resume capability for long-running evaluations. Recent matric-cli evaluation crashed at model 13/31 due to EPIPE error, losing all progress after hours of computation. Without checkpoint support, any failure in multi-hour evaluation runs results in complete work loss.

**Impact Analysis**:
- Complete loss of evaluation progress on crash/interruption
- Wasted compute time (potentially 8+ hours on full benchmark suite)
- Delayed model selection for downstream projects
- User frustration and adoption resistance
- Inability to handle large-scale evaluations (30+ models × 6+ benchmarks)

**Trigger Conditions**:
- Evaluation runs exceeding 2 hours
- Network interruptions to Ollama service
- System resource exhaustion (OOM, disk full)
- Process termination (SIGTERM, SIGKILL, crashes)

**Mitigation Strategies**:

1. **Validation Phase** (Sprint 1):
   - Research Inspect AI documentation for checkpoint APIs
   - Test proof-of-concept with deliberate interruption
   - Verify state serialization capabilities
   - **Decision Point**: If no native support, escalate to architecture change

2. **Custom Implementation** (if needed):
   - Design checkpoint schema: `{model_id, task_id, timestamp, results[], metadata}`
   - Implement state persistence to JSON/SQLite after each model completion
   - Add `--resume` flag to skip completed evaluations
   - Store intermediate results in `/results/{run_id}/checkpoints/`

3. **Graceful Degradation**:
   - Break evaluations into smaller batches (5-10 models per run)
   - Implement per-model result persistence
   - Add progress tracking with estimated completion time
   - Enable partial result reporting

4. **Framework Alternative**:
   - Evaluate lm-eval-harness checkpoint support as backup
   - Design abstraction layer to swap frameworks if needed

**Acceptance Criteria**:
- Evaluation can resume from interruption point with <5% duplicate work
- Checkpoint overhead <10% of total runtime
- Automatic checkpoint creation every N models (configurable)

**Owner**: Solo Python Developer
**Review Date**: Sprint 1 (Week 1)

---

## High Risks (Score: 6)

### RISK-002: Ollama + Inspect AI Integration Instability

**Category**: Technical - Integration
**Status**: Identified
**Probability**: HIGH (3)
**Impact**: MEDIUM (2)
**Risk Score**: 6

**Description**: Inspect AI's Ollama integration may be unstable, incomplete, or incompatible with local model evaluation workflows. Previous matric-cli evaluation experienced EPIPE errors suggesting connection failures between evaluation code and Ollama service.

**Impact Analysis**:
- Frequent evaluation failures requiring manual intervention
- Inconsistent benchmark results due to retry logic
- Inability to evaluate local models (forces cloud provider dependency)
- Framework replacement costs (2-3 weeks development time)

**Trigger Conditions**:
- Concurrent model requests to Ollama
- Large context windows (>8K tokens)
- Long-running inference tasks (>30s per sample)
- Ollama service restarts during evaluation

**Mitigation Strategies**:

1. **Early Integration Testing**:
   - Create smoke test calling Ollama via Inspect AI (Sprint 1, Day 1)
   - Test edge cases: timeout, context overflow, concurrent requests
   - Monitor for EPIPE, connection reset, timeout errors
   - Validate model listing and selection

2. **Resilience Patterns**:
   - Implement exponential backoff retry (3 attempts, 1s/2s/4s delays)
   - Add connection pooling/keepalive if supported
   - Detect stale connections and reconnect
   - Add health check before batch operations

3. **Fallback Options**:
   - Direct HTTP API calls to Ollama REST endpoint
   - Custom Inspect AI model provider implementation
   - Subprocess wrapper with error recovery

4. **Monitoring**:
   - Log all Ollama API calls with timing
   - Track failure rates per model
   - Alert on error rate >5%

**Acceptance Criteria**:
- Successfully evaluate 5 models × 3 benchmarks without failure
- <2% request failure rate over 1000+ inferences
- Automatic recovery from transient Ollama errors

**Owner**: Solo Python Developer
**Review Date**: Sprint 1 (Week 1)

---

### RISK-003: TypeScript/Rust Binding Complexity Overruns

**Category**: Technical - Integration
**Status**: Identified
**Probability**: MEDIUM (2)
**Impact**: HIGH (3)
**Risk Score**: 6

**Description**: Creating production-quality TypeScript (matric-cli) and Rust (matric-memory) bindings may be more complex than anticipated. Subprocess management, IPC serialization, error propagation, and streaming results introduce significant implementation overhead.

**Impact Analysis**:
- Schedule delay of 2-4 weeks if bindings take longer than planned
- Downstream projects (matric-cli, matric-memory) cannot integrate
- Solo developer context switching between Python/TypeScript/Rust
- Maintenance burden across three language codebases

**Trigger Conditions**:
- TypeScript binding development exceeds 1 week
- Rust binding development exceeds 1 week
- Streaming results require custom protocol design
- Version incompatibilities between Python/TS/Rust environments

**Mitigation Strategies**:

1. **Simplify Integration Strategy**:
   - Start with CLI-only interface (defer library bindings)
   - Use JSON output format parseable by all languages
   - Subprocess spawn with stdio communication
   - Defer streaming to v1.1

2. **Prioritize TypeScript** (matric-cli is primary consumer):
   - Ship TS binding first, Rust binding in v1.1
   - Use proven IPC libraries: `execa` (TS), `std::process` (Rust)
   - Follow existing matric-cli eval patterns

3. **Reuse Existing Code**:
   - Port matric-cli TypeScript subprocess logic
   - Copy error handling patterns from matric-memory eval.rs

4. **Prototype Early**:
   - Build minimal binding in Sprint 2
   - Test with single benchmark end-to-end
   - Validate error propagation and timeout handling

5. **Documentation**:
   - Provide integration examples for both languages
   - Document common pitfalls and workarounds

**Acceptance Criteria**:
- TypeScript binding completes evaluation from matric-cli in <5 LOC
- Rust binding compiles without warnings on stable Rust
- Bindings handle errors gracefully (no panics/crashes)

**Owner**: Solo Python Developer
**Review Date**: Sprint 2 (Week 3)

---

### RISK-004: MBPP Function Name Extraction Regression

**Category**: Technical - Data Processing
**Status**: Identified
**Probability**: MEDIUM (2)
**Impact**: HIGH (3)
**Risk Score**: 6

**Description**: MBPP benchmark requires extracting expected function names from test assertions to include in prompts. This was previously solved in matric-cli but may regress during Python reimplementation, causing MBPP evaluation failures or incorrect scoring.

**Impact Analysis**:
- Invalid MBPP results (0% pass rate due to wrong function signatures)
- Cannot compare results with matric-cli baseline
- Loss of critical Python code generation benchmark
- Rework time: 3-5 days to debug and fix

**Trigger Conditions**:
- MBPP task implementation without reviewing matric-cli solution
- Different MBPP dataset format than matric-cli used
- Test assertion parsing logic changes

**Mitigation Strategies**:

1. **Preserve Existing Logic**:
   - Extract function name regex from matric-cli `source/eval/`
   - Port TypeScript logic to Python with unit tests
   - Document edge cases (multiple functions, decorators, async)

2. **Validation Tests**:
   - Create unit tests with known MBPP samples
   - Compare extracted function names against matric-cli output
   - Test edge cases: lambda, class methods, nested functions

3. **Dataset Review**:
   - Examine `/home/roctinam/data/evals/mbpp/` structure
   - Verify test assertion format matches expectations
   - Create sample dataset fixture for testing

4. **Regression Detection**:
   - Include MBPP in smoke test suite
   - Assert >50% pass rate on known good model (baseline)
   - Alert on unexpected drop in pass rate

**Acceptance Criteria**:
- Function name extraction matches matric-cli for 100% of MBPP samples
- MBPP evaluation pass rates within 5% of matric-cli baseline
- Unit test coverage >90% for extraction logic

**Owner**: Solo Python Developer
**Review Date**: Sprint 2 (Week 3)

---

### RISK-005: Code Execution Sandbox Escape

**Category**: Security - Execution Safety
**Status**: Identified
**Probability**: LOW (1)
**Impact**: HIGH (3)
**Risk Score**: 3

**Description**: Untrusted model-generated code execution poses security risks: file system access, network requests, resource exhaustion, malicious code execution. Inadequate sandboxing could compromise host system or leak sensitive data.

**Impact Analysis**:
- Data exfiltration from evaluation host
- Denial of service via resource exhaustion
- Filesystem corruption or data loss
- Security incident requiring disclosure
- Reputation damage

**Trigger Conditions**:
- Model generates malicious code (intentional or hallucinated)
- Sandbox escape vulnerabilities in execution environment
- Missing timeout/memory limit enforcement
- Evaluation run with elevated privileges

**Mitigation Strategies**:

1. **Multi-Layer Sandboxing**:
   - Use Docker container for code execution (isolated filesystem)
   - Apply seccomp/AppArmor profiles (restrict syscalls)
   - Network isolation (no internet access)
   - Read-only filesystem mounts except `/tmp`

2. **Resource Limits**:
   - Timeout: 10 seconds per test case
   - Memory: 512MB per execution
   - CPU: 1 core, no GPU access
   - Disk: 100MB tmp space

3. **Code Analysis**:
   - AST parsing to detect suspicious patterns (exec, eval, open, import os)
   - Reject code with high-risk operations before execution
   - Log all rejected samples for review

4. **Execution Environment**:
   - Ephemeral containers (destroyed after each test)
   - No persistent state between executions
   - Randomized tmp directory names

5. **Monitoring**:
   - Log all sandbox violations
   - Alert on repeated escape attempts
   - Review logs weekly for anomalies

**Acceptance Criteria**:
- Malicious code samples cannot access filesystem outside `/tmp`
- Network requests fail/timeout
- Resource limits enforced (tested with bombs: fork, memory, CPU)
- Zero sandbox escapes in penetration testing

**Owner**: Solo Python Developer
**Review Date**: Sprint 3 (Week 5)

---

## Medium Risks (Score: 4)

### RISK-006: Large Dataset Memory Exhaustion

**Category**: Technical - Performance
**Status**: Identified
**Probability**: MEDIUM (2)
**Impact**: MEDIUM (2)
**Risk Score**: 4

**Description**: Loading large benchmark datasets into memory (MBPP: 974 samples, GSM8K: 1,319 samples, LiveCodeBench: 880 samples) may exhaust available RAM, especially when combined with model inference memory requirements.

**Impact Analysis**:
- OOM crashes during evaluation
- Swapping degrades performance (10x+ slowdown)
- Unable to run full benchmark suite
- Forced to use smaller subsets (reduced statistical validity)

**Trigger Conditions**:
- Loading multiple datasets simultaneously
- Running on low-memory systems (<16GB RAM)
- Large model context windows cached in memory
- Concurrent evaluations

**Mitigation Strategies**:

1. **Lazy Loading**:
   - Stream datasets from disk using generators
   - Load one sample at a time during evaluation
   - Use `jsonlines` library for incremental parsing

2. **Batching**:
   - Process datasets in configurable batch sizes (default: 50)
   - Explicit garbage collection between batches

3. **Memory Profiling**:
   - Measure peak memory usage in smoke tests
   - Set memory budget per evaluation tier
   - Add `--max-memory` flag for user constraints

4. **Dataset Optimization**:
   - Pre-process datasets to minimal JSON format
   - Remove unnecessary metadata fields
   - Compress large text fields

**Acceptance Criteria**:
- Full evaluation suite runs in <8GB RAM
- No swapping during normal operation
- Memory usage scales linearly with batch size

**Owner**: Solo Python Developer
**Review Date**: Sprint 2 (Week 3)

---

### RISK-007: Schedule Delay Due to Solo Developer Bottleneck

**Category**: Resource - Team Capacity
**Status**: Identified
**Probability**: MEDIUM (2)
**Impact**: MEDIUM (2)
**Risk Score**: 4

**Description**: Single developer responsible for Python core, TypeScript bindings, Rust bindings, documentation, testing, and deployment. Any sick leave, competing priorities, or underestimated tasks create immediate schedule risk.

**Impact Analysis**:
- Timeline slip from 6-8 weeks to 10-12 weeks
- Delayed integration for matric-cli and matric-memory
- Rushed implementation leading to technical debt
- Reduced testing coverage

**Trigger Conditions**:
- Developer unavailable >3 consecutive days
- Unexpected complexity in critical path tasks
- Scope creep or feature requests
- Production issues in other projects requiring attention

**Mitigation Strategies**:

1. **Scope Management**:
   - Defer Rust bindings to v1.1 if needed
   - Focus on core Python + TypeScript binding only
   - Document "must-have" vs "nice-to-have" features

2. **Time Boxing**:
   - Limit research spikes to 1 day max
   - Set 2-day limit for framework integration POC
   - Escalate if task exceeds estimate by 50%

3. **Risk Buffer**:
   - Include 20% schedule buffer in timeline
   - Reserve final week for bug fixes only

4. **Knowledge Sharing**:
   - Document decisions in PLANNING.md as you go
   - Keep CLAUDE.md updated with learnings
   - Maintain detailed commit messages for handoff

5. **External Support**:
   - Identify 1-2 team members for code review
   - Consider outsourcing documentation writing
   - Use AI assistance (Claude, Cursor) for boilerplate

**Acceptance Criteria**:
- v1.0 ships within 8 weeks (by 2026-03-21)
- Core functionality complete even if bindings delayed
- Zero P0 bugs at release

**Owner**: Solo Python Developer
**Review Date**: Weekly in standups

---

### RISK-008: Inspect AI Framework Abandonment

**Category**: External - Vendor Dependency
**Status**: Monitoring
**Probability**: LOW (1)
**Impact**: HIGH (3)
**Risk Score**: 3

**Description**: Inspect AI is maintained by UK AI Safety Institute (AISI). Government priorities may shift, funding may be cut, or maintainers may leave, leading to framework abandonment or stagnation.

**Impact Analysis**:
- No bug fixes or security patches
- Incompatibility with future Python/Ollama versions
- Forced migration to alternative framework (3-4 weeks)
- Loss of advanced features (if they exist)

**Trigger Conditions**:
- No Inspect AI releases for >6 months
- Critical bugs unaddressed for >3 months
- Maintainer announces deprecation
- Breaking changes in dependencies

**Mitigation Strategies**:

1. **Abstraction Layer**:
   - Design task/scorer interfaces independent of Inspect AI
   - Keep Inspect AI logic isolated in adapter modules
   - Document migration path to lm-eval-harness

2. **Alternative Validation**:
   - Test basic evaluation with lm-eval-harness in Sprint 1
   - Maintain compatibility with both frameworks if feasible
   - Monitor both project communities

3. **Monitoring**:
   - Watch Inspect AI GitHub for activity (monthly)
   - Subscribe to release notifications
   - Track issue resolution time

4. **Community Engagement**:
   - Report bugs to upstream maintainers
   - Contribute fixes if possible
   - Join user community for early warnings

**Acceptance Criteria**:
- Framework abstraction allows swapping with <1 week effort
- Alternative framework identified and validated
- Monitoring alerts set up

**Owner**: Solo Python Developer
**Review Date**: Monthly

---

### RISK-009: Ollama Model Size Exceeds Host Capacity

**Category**: Technical - Resource Constraints
**Status**: Identified
**Probability**: MEDIUM (2)
**Impact**: MEDIUM (2)
**Risk Score**: 4

**Description**: Some models exceed available VRAM/RAM on evaluation host. matric-cli implemented MAX_MODEL_SIZE_GB filtering, but matric-eval may attempt to load oversized models, causing OOM crashes or extremely slow CPU-only inference.

**Impact Analysis**:
- Evaluation crashes or hangs
- Extremely slow inference (hours per sample)
- System instability affecting other processes
- Incomplete evaluation results

**Trigger Conditions**:
- Evaluating models >16GB on systems with <32GB RAM
- No GPU available for large models
- Concurrent model loading

**Mitigation Strategies**:

1. **Pre-Flight Checks**:
   - Query Ollama API for model size before loading
   - Implement configurable `--max-model-size` (default: 16GB)
   - Skip models exceeding threshold with warning

2. **Resource Detection**:
   - Detect available RAM/VRAM at startup
   - Calculate safe model size limit (50% of available)
   - Warn user if requested models exceed capacity

3. **Graceful Degradation**:
   - Attempt model load with timeout (60s)
   - Unload model on failure and continue
   - Log skipped models for reporting

4. **Documentation**:
   - Document minimum system requirements
   - Provide model size recommendations per tier
   - Example: smoke (3B), quick (7B), full (up to 16GB)

**Acceptance Criteria**:
- No OOM crashes due to oversized models
- Skipped models logged with clear reasoning
- User informed of resource constraints upfront

**Owner**: Solo Python Developer
**Review Date**: Sprint 2 (Week 2)

---

### RISK-010: Inconsistent Scoring Across Benchmarks

**Category**: Technical - Quality Assurance
**Status**: Identified
**Probability**: MEDIUM (2)
**Impact**: MEDIUM (2)
**Risk Score**: 4

**Description**: Different benchmarks use different scoring methodologies (exact match, fuzzy match, AST equivalence, test execution). Inconsistent implementation leads to invalid comparisons and incorrect model rankings.

**Impact Analysis**:
- Incorrect model recommendations
- Incomparable results across benchmarks
- Loss of user trust in evaluation validity
- Need to rerun all evaluations after fixing

**Trigger Conditions**:
- Copying scorer implementations without validation
- Missing edge cases in scoring logic
- Different preprocessing between benchmarks

**Mitigation Strategies**:

1. **Scorer Validation**:
   - Compare scoring output against known baselines
   - Use reference implementations where available
   - Unit test edge cases: whitespace, comments, formatting

2. **Standardization**:
   - Document scoring methodology per benchmark
   - Implement common preprocessors (code normalization)
   - Validate against published benchmark papers

3. **Reference Data**:
   - Collect baseline results from literature
   - Test against known model performance (e.g., GPT-4 on HumanEval)
   - Assert results within expected range

4. **Review Process**:
   - Peer review scorer implementations
   - Run cross-validation with matric-cli results
   - Document scoring differences in reports

**Acceptance Criteria**:
- HumanEval scoring matches official implementation
- MBPP results within 5% of matric-cli baseline
- Documented scoring methodology for all benchmarks

**Owner**: Solo Python Developer
**Review Date**: Sprint 3 (Week 4)

---

## Low Risks (Score: 2-3)

### RISK-011: Python Version Compatibility Issues

**Category**: Technical - Environment
**Status**: Monitoring
**Probability**: LOW (1)
**Impact**: MEDIUM (2)
**Risk Score**: 2

**Description**: Requiring Python 3.11+ may exclude users on older systems. Conversely, not specifying minimum version may lead to runtime failures on Python 3.9 or earlier.

**Impact Analysis**:
- Installation failures on legacy systems
- Support burden for older Python versions
- Delayed adoption by conservative users

**Trigger Conditions**:
- Using Python 3.11+ only syntax (match/case, type hints)
- Dependencies requiring recent Python versions
- Users on Ubuntu 20.04 LTS (Python 3.8)

**Mitigation Strategies**:

1. **Version Policy**:
   - Require Python 3.11+ (document clearly)
   - Test on 3.11, 3.12, 3.13
   - Use `python_requires=">=3.11"` in pyproject.toml

2. **CI Testing**:
   - Matrix test across Python versions
   - Fail fast on incompatible syntax

3. **Documentation**:
   - Clear installation requirements
   - Provide uv installation instructions
   - Offer Docker image for legacy systems

**Acceptance Criteria**:
- Runs on Python 3.11, 3.12, 3.13 without warnings
- Installation fails gracefully on Python <3.11 with clear error

**Owner**: Solo Python Developer
**Review Date**: Sprint 1 (Week 1)

---

### RISK-012: Dataset Licensing Restrictions

**Category**: Legal - Compliance
**Status**: Monitoring
**Probability**: LOW (1)
**Impact**: MEDIUM (2)
**Risk Score**: 2

**Description**: Public benchmarks may have restrictive licenses prohibiting redistribution, commercial use, or requiring attribution. Violating terms could expose project to legal risk.

**Impact Analysis**:
- Cease and desist from dataset authors
- Removal of benchmarks from framework
- Reputation damage

**Trigger Conditions**:
- Redistributing datasets without permission
- Commercial use of non-commercial datasets
- Missing attribution requirements

**Mitigation Strategies**:

1. **License Audit**:
   - Review license for each benchmark in `/home/roctinam/data/evals/`
   - Document licenses in `datasets/README.md`
   - Flag any restrictive terms

2. **Attribution**:
   - Include citations in documentation
   - Add LICENSE file per dataset
   - Credit authors in evaluation reports

3. **Download vs Bundle**:
   - Provide download scripts instead of bundling data
   - Link to official sources
   - Document data provenance

4. **Legal Review**:
   - Consult with legal if commercial use planned
   - Obtain explicit permission for redistribution

**Acceptance Criteria**:
- All dataset licenses documented
- Attribution included in reports
- No bundled datasets with restrictive licenses

**Owner**: Solo Python Developer
**Review Date**: Sprint 1 (Week 2)

---

### RISK-013: Evaluation Result Reproducibility Failures

**Category**: Technical - Quality Assurance
**Status**: Identified
**Probability**: LOW (1)
**Impact**: MEDIUM (2)
**Risk Score**: 2

**Description**: Non-deterministic model inference, sampling randomness, or environmental differences cause evaluation results to vary between runs, preventing reproducible benchmarks.

**Impact Analysis**:
- Cannot validate results
- Invalid A/B comparisons between runs
- Loss of scientific rigor
- User distrust in evaluation quality

**Trigger Conditions**:
- Missing random seeds in sampling
- Non-zero temperature in model inference
- Concurrent evaluations affecting timing
- Different Ollama versions

**Mitigation Strategies**:

1. **Deterministic Inference**:
   - Set temperature=0 for all evaluations
   - Use fixed random seeds (configurable via `--seed`)
   - Document in evaluation config

2. **Environment Tracking**:
   - Log Python version, Inspect AI version, Ollama version
   - Record model hashes/versions
   - Include system info in results metadata

3. **Validation**:
   - Run same evaluation twice, assert <1% variance
   - Include reproducibility check in CI
   - Document sources of non-determinism

4. **Dataset Sampling**:
   - Use seeded random for subset selection (preserve from matric-cli)
   - Document sampling methodology
   - Provide full dataset option (`--no-sample`)

**Acceptance Criteria**:
- Identical results on repeated evaluation (same model, same dataset)
- All randomness seeded and documented
- Environment metadata in all result files

**Owner**: Solo Python Developer
**Review Date**: Sprint 3 (Week 5)

---

### RISK-014: Streaming Results Implementation Complexity

**Category**: Technical - Feature
**Status**: Identified
**Probability**: LOW (1)
**Impact**: LOW (1)
**Risk Score**: 1

**Description**: Real-time streaming of evaluation progress to bindings (TypeScript/Rust) may require complex IPC protocols, increasing implementation time and bug surface.

**Impact Analysis**:
- Delayed binding development
- Poor user experience (no progress feedback)
- Complex debugging of async issues

**Trigger Conditions**:
- User expectations for real-time progress
- Long-running evaluations (30+ minutes)
- TypeScript/Rust consumers requiring streaming

**Mitigation Strategies**:

1. **Defer to v1.1**:
   - Ship v1.0 with batch-only output
   - Add streaming in future release
   - Validate user demand first

2. **Simple Progress**:
   - Write progress to stderr (parseable format)
   - Update JSON file incrementally
   - Use file watching in consumers

3. **Proven Libraries**:
   - Use NDJSON (newline-delimited JSON) over stdio
   - Leverage existing IPC libraries

**Acceptance Criteria**:
- v1.0 ships without streaming (deferred)
- Progress visible in CLI output
- Consumer libraries can poll results file

**Owner**: Solo Python Developer
**Review Date**: Post-v1.0

---

### RISK-015: Docker/Container Dependency Unavailable

**Category**: Technical - Infrastructure
**Status**: Monitoring
**Probability**: LOW (1)
**Impact**: MEDIUM (2)
**Risk Score**: 2

**Description**: Code execution sandbox relies on Docker/Podman for isolation. Users without container runtime cannot run evaluations safely, limiting adoption.

**Impact Analysis**:
- Reduced user base (excludes non-Docker users)
- Security risk if fallback to unsafe execution
- Support burden for container setup

**Trigger Conditions**:
- Docker not installed or not in PATH
- Permission issues (non-root user, no docker group)
- Container runtime incompatibility (ARM vs x86)

**Mitigation Strategies**:

1. **Graceful Fallback**:
   - Detect Docker availability at startup
   - Offer degraded mode with Python `subprocess` + resource limits
   - Warn user of reduced security

2. **Alternative Runtimes**:
   - Support Podman as Docker alternative
   - Test with both runtimes

3. **Documentation**:
   - Provide Docker installation guide
   - Document security trade-offs of non-container mode
   - Include pre-built container image

4. **CI/CD**:
   - Test both Docker and non-Docker modes
   - Validate on common platforms (Ubuntu, macOS, WSL)

**Acceptance Criteria**:
- Evaluation works with Docker, Podman, or fallback mode
- Clear warnings when running without containers
- Installation docs cover container setup

**Owner**: Solo Python Developer
**Review Date**: Sprint 3 (Week 5)

---

## Risk Summary

| Risk ID | Name | Score | Status | Priority |
|---------|------|-------|--------|----------|
| RISK-001 | Inspect AI Checkpoint/Resume | 6 | Identified | P0 |
| RISK-002 | Ollama + Inspect AI Integration | 6 | Identified | P0 |
| RISK-003 | Binding Complexity Overruns | 6 | Identified | P1 |
| RISK-004 | MBPP Function Name Regression | 6 | Identified | P1 |
| RISK-005 | Sandbox Escape | 3 | Identified | P1 |
| RISK-006 | Memory Exhaustion | 4 | Identified | P2 |
| RISK-007 | Solo Developer Bottleneck | 4 | Identified | P2 |
| RISK-008 | Framework Abandonment | 3 | Monitoring | P2 |
| RISK-009 | Model Size Exceeds Capacity | 4 | Identified | P2 |
| RISK-010 | Inconsistent Scoring | 4 | Identified | P2 |
| RISK-011 | Python Version Compatibility | 2 | Monitoring | P3 |
| RISK-012 | Dataset Licensing | 2 | Monitoring | P3 |
| RISK-013 | Reproducibility Failures | 2 | Identified | P3 |
| RISK-014 | Streaming Results Complexity | 1 | Identified | P4 |
| RISK-015 | Docker Dependency | 2 | Monitoring | P3 |

---

## Next Actions

1. **Sprint 1 (Week 1)**: Validate RISK-001 and RISK-002 with POC
2. **Sprint 1 (Week 2)**: Audit dataset licenses (RISK-012)
3. **Sprint 2 (Week 3)**: Address RISK-004 during MBPP implementation
4. **Sprint 3 (Week 5)**: Security testing for RISK-005
5. **Weekly**: Review schedule risk (RISK-007) in standups
6. **Monthly**: Monitor framework activity (RISK-008)

---

## Change Log

| Date | Risk ID | Change | Author |
|------|---------|--------|--------|
| 2026-01-24 | ALL | Initial risk register created | Solo Python Developer |

