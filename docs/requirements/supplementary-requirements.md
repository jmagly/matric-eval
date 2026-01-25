# Supplementary Requirements (Non-Functional Requirements)

**Document ID**: REQ-SUP-001
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Planning Phase

## Document Overview

This document specifies non-functional requirements (NFRs) for matric-eval, including performance, reliability, usability, security, maintainability, and operational characteristics. These requirements apply across all use cases and define system-wide quality attributes.

## Traceability

**Traced to Gitea Issues**:
- #11: Implement checkpoint/resume for fault tolerance (Reliability)
- #12: Implement parallel model evaluation (Performance)
- #13: Add CI/CD pipeline with automated smoke tests (Operational)
- #14: Add comprehensive logging and observability (Maintainability, Operational)
- All issues contribute to overall system quality

**Traced to Business Requirements**:
- BR-003: Resource Efficiency
- BR-005: Operational Excellence

## Performance Requirements

### PERF-001: Evaluation Tier Duration

**Description**: Each evaluation tier must complete within specified time constraints to enable efficient workflows.

**Rationale**: Developers need fast feedback for iteration (smoke), reasonable turnaround for selection (quick), and comprehensive results for publication (full).

**Requirements**:

| Tier | Maximum Duration | Target Model | Measurement Context |
|------|-----------------|--------------|---------------------|
| Smoke | 5 minutes (300s) | llama3.2:3b | Single core, 16GB RAM, local Ollama |
| Quick | 30 minutes (1800s) | llama3.2:3b | Single core, 16GB RAM, local Ollama |
| Full | 4 hours (14400s) | llama3.2:3b | Parallel (4 cores), 16GB RAM, local Ollama |

**Acceptance Criteria**:
- [ ] Smoke tier completes in <300s for 90% of models <10GB
- [ ] Quick tier completes in <1800s for 90% of models <10GB
- [ ] Full tier completes in <14400s for 90% of models <10GB
- [ ] Duration logged and reported in output JSON

**Traced to**: #6 (tiered CLI), BR-003 (resource efficiency)

**Priority**: P1 - Critical

---

### PERF-002: Inference Latency Overhead

**Description**: Framework overhead must be minimal compared to raw Ollama inference.

**Rationale**: Evaluation accuracy depends on measuring true model performance, not framework inefficiency.

**Requirements**:

- **Overhead**: <10% additional latency vs. direct Ollama API calls
- **Measurement**: Compare framework-mediated inference vs. raw `curl` to Ollama API
- **Context**: Overhead includes prompt formatting, response parsing, artifact storage

**Acceptance Criteria**:
- [ ] Average latency overhead <10% across 100 sample requests
- [ ] Maximum latency overhead <20% for any single request
- [ ] Overhead breakdown logged (prompt prep, API call, parsing, storage)

**Traced to**: #1, #2 (accurate benchmarking requires minimal overhead)

**Priority**: P2 - High

---

### PERF-003: Memory Footprint

**Description**: Framework must operate within constrained memory environments.

**Rationale**: Developers run evaluations on laptops and CI/CD runners with limited RAM.

**Requirements**:

- **Framework Baseline**: <2GB for framework and dependencies (without model)
- **Evaluation State**: <8GB for full-tier checkpoint state and intermediate results
- **Total Budget**: <16GB total (framework + state + OS + buffers)

**Acceptance Criteria**:
- [ ] Peak memory usage <2GB with no evaluations running
- [ ] Peak memory usage <10GB during full-tier evaluation
- [ ] Memory leak detection: <1% growth per 1000 samples
- [ ] Memory profiling included in test suite

**Traced to**: #11 (checkpoint size), #12 (parallel execution memory)

**Priority**: P2 - High

---

### PERF-004: Parallel Execution Efficiency

**Description**: Parallel execution must achieve near-linear speedup within resource constraints.

**Rationale**: Multi-core machines should complete evaluations faster without excessive overhead.

**Requirements**:

- **Speedup**: >80% efficiency with 2-4 workers (e.g., 3.2x speedup with 4 workers)
- **Overhead**: <20% wall-time overhead vs. sequential baseline
- **Resource Sharing**: Workers share Ollama API connection, avoid port conflicts

**Acceptance Criteria**:
- [ ] 4-worker execution completes in <35% of sequential time (>2.85x speedup)
- [ ] Worker utilization >90% (minimal idle time)
- [ ] No race conditions or shared-state corruption
- [ ] Graceful degradation if Ollama rate-limits requests

**Traced to**: #12 (parallel model evaluation)

**Priority**: P2 - High

---

### PERF-005: Disk Usage Efficiency

**Description**: Checkpoint files and artifacts must fit within reasonable storage quotas.

**Rationale**: CI/CD runners and developer machines have limited disk space.

**Requirements**:

- **Checkpoint Size**: <50MB for full-tier checkpoint (3000+ samples)
- **Artifact Storage**: <5GB for full-tier results with all artifacts
- **Compression**: Optional gzip compression for artifacts (--compress flag)

**Acceptance Criteria**:
- [ ] Checkpoint file <50MB for full tier
- [ ] Total artifact storage <5GB for full tier
- [ ] Compressed artifacts <2GB for full tier
- [ ] Cleanup removes checkpoints after successful completion

**Traced to**: #11 (checkpoint/resume), #14 (logging)

**Priority**: P3 - Medium

---

### PERF-006: Throughput and Scalability

**Description**: System must handle large evaluation workloads efficiently.

**Rationale**: Full evaluations process thousands of samples, requiring sustained throughput.

**Requirements**:

- **Sample Throughput**: >10 samples/minute for code generation tasks (with llama3.2:3b)
- **Batch Efficiency**: Batch API requests where possible to reduce network overhead
- **Dataset Scaling**: Support datasets with 10,000+ samples without performance degradation

**Acceptance Criteria**:
- [ ] HumanEval (164 samples) completes in <20 minutes (>8 samples/min)
- [ ] MBPP (974 samples) completes in <2 hours (>8 samples/min)
- [ ] No performance degradation with dataset size (linear scaling)

**Traced to**: All benchmark issues (#1-#5)

**Priority**: P3 - Medium

---

## Reliability Requirements

### REL-001: Deterministic Reproducibility

**Description**: Evaluations must produce identical results on repeated runs with the same seed.

**Rationale**: Reproducibility is essential for scientific validity, debugging, and comparison.

**Requirements**:

- **Score Consistency**: Identical scores (±0.001) on repeated runs with same seed
- **Sample Selection**: Same samples selected for quick/smoke tiers with same seed
- **Random State**: Serializable random state for checkpoint/resume
- **Environmental Isolation**: Results unaffected by external factors (network, time)

**Acceptance Criteria**:
- [ ] 10 repeated runs with seed=42 produce identical scores (±0.001)
- [ ] Checkpoint/resume produces identical results to uninterrupted run
- [ ] Sample indices logged for verification
- [ ] Random state validated in test suite

**Traced to**: BR-002 (evaluation accuracy), UC001, UC002

**Priority**: P1 - Critical

---

### REL-002: Fault Tolerance

**Description**: System must gracefully handle failures and enable recovery.

**Rationale**: Long-running evaluations are susceptible to interruptions and failures.

**Requirements**:

- **Checkpoint on Interrupt**: Save state on SIGINT, SIGTERM (within 10s)
- **Resume Capability**: Resume from checkpoint with <1% data loss
- **Error Recovery**: Continue evaluation on individual sample failures
- **Resource Monitoring**: Detect resource exhaustion and checkpoint before crash

**Acceptance Criteria**:
- [ ] Ctrl+C during evaluation saves checkpoint within 10s
- [ ] Resume from checkpoint completes evaluation correctly
- [ ] Individual sample timeout/error doesn't abort entire evaluation
- [ ] Memory exhaustion triggers checkpoint, not crash
- [ ] Fault injection tests validate recovery mechanisms

**Traced to**: #11 (checkpoint/resume), UC002

**Priority**: P1 - Critical

---

### REL-003: Data Integrity

**Description**: Evaluation results must be accurate and uncorrupted.

**Rationale**: Incorrect scores lead to wrong model selection decisions.

**Requirements**:

- **Score Accuracy**: Scores match reference implementations (±0.5% for matric-cli, 100% for matric-memory)
- **Artifact Preservation**: All generated code, outputs, and metadata saved
- **Checksum Validation**: Datasets validated before use
- **Duplicate Detection**: No duplicate sample executions

**Acceptance Criteria**:
- [ ] HumanEval scores match matric-cli implementation (±0.5%)
- [ ] MBPP scores match matric-cli implementation (±0.5%)
- [ ] Custom tests match matric-memory implementation (100% agreement)
- [ ] Checkpoint merge detects and prevents duplicates
- [ ] Dataset checksums validated before and after evaluation

**Traced to**: BR-002 (evaluation accuracy), #1, #2, #7

**Priority**: P1 - Critical

---

### REL-004: Error Handling and Recovery

**Description**: System must handle errors gracefully with clear messages and recovery paths.

**Rationale**: Users need actionable guidance to resolve issues, not cryptic errors.

**Requirements**:

- **Error Coverage**: 90%+ of failure modes have clear, actionable error messages
- **Error Categorization**: Errors classified (validation, runtime, resource, configuration)
- **Exit Codes**: Distinct exit codes for failure types (0=success, 1=validation, 2=config, 3=resource, 4=checkpoint, 5=data)
- **Recovery Guidance**: Error messages include next steps

**Acceptance Criteria**:
- [ ] Ollama unavailable: "Ollama service not reachable at localhost:11434. Start with 'ollama serve'."
- [ ] Model missing: "Model 'X' not found. Pull with 'ollama pull X'."
- [ ] Dataset missing: "Dataset not found at /path. Download from <URL>."
- [ ] Disk full: "Cannot write checkpoint, disk full. Free space in /tmp/."
- [ ] No raw stack traces shown to user (logged to file)

**Traced to**: BR-005 (operational excellence), UC001 extensions

**Priority**: P2 - High

---

### REL-005: Availability and Uptime

**Description**: System must operate reliably in production CI/CD environments.

**Rationale**: Evaluation failures block development workflows and merges.

**Requirements**:

- **CI/CD Success Rate**: >95% successful smoke test runs in CI/CD
- **Transient Error Handling**: Retry on transient Ollama errors (3 attempts)
- **Graceful Degradation**: Use embedded datasets if external datasets unavailable
- **Dependency Resilience**: Validate all dependencies during initialization

**Acceptance Criteria**:
- [ ] Transient Ollama errors (503, timeout) trigger retry with exponential backoff
- [ ] Embedded minimal datasets available for smoke tier
- [ ] Missing optional dependencies log warning, not error
- [ ] CI/CD smoke tests pass >95% of time (excluding infra failures)

**Traced to**: #13 (CI/CD integration), BR-005

**Priority**: P2 - High

---

## Usability Requirements

### USE-001: Command-Line Interface Usability

**Description**: CLI must be intuitive, self-documenting, and follow conventions.

**Rationale**: Developers expect standard CLI patterns and comprehensive help.

**Requirements**:

- **Self-Documenting**: `--help` provides complete usage documentation
- **Conventions**: Follow POSIX standards (e.g., `--long-option`, `-s` short option)
- **Sensible Defaults**: Work without configuration for common cases
- **Examples**: Help text includes usage examples

**Acceptance Criteria**:
- [ ] `matric-eval --help` documents all options with examples
- [ ] Default tier (quick) and model (auto-detect or prompt) work without flags
- [ ] Short options for common flags (`-m` for model, `-t` for tier)
- [ ] Examples in help text: smoke, quick, full, resume

**Traced to**: #6 (tiered CLI)

**Priority**: P2 - High

---

### USE-002: Progress Indication and Feedback

**Description**: Users must have visibility into evaluation progress and estimated completion.

**Rationale**: Long-running evaluations need progress feedback to set expectations.

**Requirements**:

- **Progress Bar**: Real-time progress bar with percentage and ETA
- **Sample Count**: "Completed 456/3298 samples (13.8%)"
- **Time Remaining**: Estimated time based on throughput
- **Benchmark Status**: Show which benchmarks are complete, in progress, pending

**Acceptance Criteria**:
- [ ] Progress bar updates in real-time (1s refresh)
- [ ] ETA accuracy within ±20% of actual completion time
- [ ] Progress persists across checkpoint/resume
- [ ] Progress logged to file for headless/CI environments

**Traced to**: BR-003 (resource efficiency), UC001, UC002

**Priority**: P2 - High

---

### USE-003: Output Formats and Reporting

**Description**: Results must be available in multiple formats for different consumers.

**Rationale**: Humans need readable reports, machines need structured data.

**Requirements**:

- **JSON**: Machine-readable, schema-validated output (default)
- **CSV**: Flattened scores for spreadsheet analysis
- **HTML**: Interactive report with charts and visualizations
- **Markdown**: Summary table for documentation
- **Console**: Human-readable summary printed to stdout

**Acceptance Criteria**:
- [ ] JSON output validates against published schema
- [ ] CSV includes per-benchmark scores, one row per sample
- [ ] HTML report includes interactive charts (Chart.js or similar)
- [ ] Markdown summary table suitable for README
- [ ] Console summary fits on single screen

**Traced to**: UC001, #15 (future leaderboard)

**Priority**: P3 - Medium

---

### USE-004: Documentation and Examples

**Description**: Comprehensive documentation must enable self-service usage.

**Rationale**: Single-maintainer project requires low-touch support.

**Requirements**:

- **README**: Quick start with installation, basic usage, examples
- **User Guide**: Comprehensive usage documentation
- **API Documentation**: Auto-generated API docs for bindings
- **Examples**: Real-world usage examples for common scenarios
- **Troubleshooting**: FAQ and common issues with solutions

**Acceptance Criteria**:
- [ ] README has quick start (install, run smoke, interpret results)
- [ ] User guide documents all CLI options and config files
- [ ] API docs generated from docstrings (Sphinx or mkdocs)
- [ ] Examples directory with smoke, quick, full, resume, custom tests
- [ ] Troubleshooting section covers 10+ common issues

**Traced to**: BR-005 (operational excellence)

**Priority**: P2 - High

---

### USE-005: Error Messages and Diagnostics

**Description**: Error messages must be clear, actionable, and user-friendly.

**Rationale**: Cryptic errors frustrate users and increase support burden.

**Requirements**:

- **Plain Language**: No jargon, explain what went wrong
- **Root Cause**: Identify underlying issue, not just symptom
- **Actionable Steps**: Provide specific next steps to resolve
- **Context**: Include relevant details (model, benchmark, sample ID)
- **Stack Traces**: Hidden from user, logged to file for debugging

**Acceptance Criteria**:
- [ ] Error message format: "ERROR: [Problem]. [Cause]. [Action]."
- [ ] Example: "ERROR: Cannot connect to Ollama at localhost:11434. Service not running. Start with 'ollama serve'."
- [ ] No raw Python exceptions shown to user
- [ ] Stack traces logged to `~/.matric-eval/logs/errors.log`
- [ ] User testing validates error message clarity (5+ test users)

**Traced to**: REL-004 (error handling), BR-005

**Priority**: P2 - High

---

## Security Requirements

### SEC-001: Code Execution Sandboxing

**Description**: Generated code must execute in isolated sandbox to prevent security breaches.

**Rationale**: Untrusted model-generated code could contain malicious operations.

**Requirements**:

- **Network Isolation**: No network access during code execution
- **Filesystem Isolation**: Limited read/write to designated directories
- **Resource Limits**: CPU time, memory, and disk usage limits enforced
- **Process Isolation**: Separate process/container per execution

**Acceptance Criteria**:
- [ ] Network requests fail (errno=ENETUNREACH or similar)
- [ ] File writes outside sandbox directory fail (permission denied)
- [ ] CPU timeout enforced (5s smoke, 10s quick, 30s full)
- [ ] Memory limit enforced (1GB per execution)
- [ ] Docker-based sandbox available for full tier (optional)

**Traced to**: #1, #4, #5 (code execution scorers)

**Priority**: P1 - Critical

---

### SEC-002: Input Validation and Sanitization

**Description**: All user inputs must be validated to prevent injection attacks.

**Rationale**: Model names, file paths, and configuration values could contain malicious content.

**Requirements**:

- **Model Name Validation**: Alphanumeric, colon, hyphen, period only
- **Path Validation**: Prevent directory traversal (`../`, absolute paths)
- **Configuration Validation**: Schema-validated against expected types
- **Command Injection Prevention**: No shell interpolation of user inputs

**Acceptance Criteria**:
- [ ] Model name `../../etc/passwd` rejected
- [ ] File path `--output /etc/passwd` rejected
- [ ] Configuration value `$(rm -rf /)` treated as literal string
- [ ] Fuzzing tests validate input sanitization (1000+ malicious inputs)

**Traced to**: BR-005 (operational excellence)

**Priority**: P1 - Critical

---

### SEC-003: Dependency Security

**Description**: Dependencies must be vetted and regularly updated for vulnerabilities.

**Rationale**: Vulnerable dependencies introduce security risks.

**Requirements**:

- **Dependency Scanning**: Automated scanning with `pip-audit` or similar
- **Version Pinning**: Lock file with exact versions (`uv.lock`)
- **Regular Updates**: Monthly dependency updates with security patches
- **Minimal Dependencies**: Use only essential dependencies

**Acceptance Criteria**:
- [ ] `pip-audit` or `safety` runs in CI/CD, fails on high/critical vulnerabilities
- [ ] `uv.lock` committed to repository
- [ ] Dependabot or Renovate configured for automated updates
- [ ] Dependency count <50 (excluding transitive)

**Traced to**: #13 (CI/CD pipeline)

**Priority**: P2 - High

---

### SEC-004: Secrets Management

**Description**: API keys, tokens, and credentials must never be logged or committed.

**Rationale**: Leaked credentials enable unauthorized access.

**Requirements**:

- **No Hardcoded Secrets**: Secrets loaded from environment or secure storage
- **Log Redaction**: API keys and tokens redacted from logs
- **Gitignore**: `.env`, `credentials.json`, and similar files excluded
- **Checkpoint Exclusion**: Optionally exclude sensitive data from checkpoints

**Acceptance Criteria**:
- [ ] Environment variables for Ollama URL, API tokens
- [ ] Logs replace secrets with `***REDACTED***`
- [ ] `.gitignore` includes `.env*`, `*credentials*`, `*secrets*`
- [ ] Checkpoint contains no API keys or tokens (or encrypted)

**Traced to**: UC002 (checkpoint content), BR-005

**Priority**: P2 - High

---

### SEC-005: Dataset Integrity

**Description**: Benchmark datasets must be validated to prevent tampering.

**Rationale**: Corrupted or malicious datasets could produce invalid results or execute exploits.

**Requirements**:

- **Checksum Validation**: Verify dataset checksums before use
- **Source Authentication**: Download from trusted sources with HTTPS
- **Immutable Storage**: Datasets stored read-only
- **Tampering Detection**: Alert if dataset modified since initial validation

**Acceptance Criteria**:
- [ ] Dataset checksums documented and validated on load
- [ ] Datasets downloaded from official sources (HuggingFace, GitHub releases)
- [ ] File permissions set to read-only after download
- [ ] Checksum mismatch triggers error, not silent failure

**Traced to**: BR-002 (evaluation accuracy), REL-003 (data integrity)

**Priority**: P3 - Medium

---

## Maintainability Requirements

### MAINT-001: Code Quality and Style

**Description**: Codebase must follow consistent style and best practices.

**Rationale**: Consistent code is easier to maintain, review, and extend.

**Requirements**:

- **Linting**: Enforce PEP 8 with `ruff` or `flake8`
- **Formatting**: Auto-format with `black` or `ruff format`
- **Type Hints**: Type annotations for all public APIs
- **Static Analysis**: Run `mypy` for type checking

**Acceptance Criteria**:
- [ ] `ruff check` passes with zero errors
- [ ] `black --check` passes (or `ruff format`)
- [ ] `mypy` passes with strict mode
- [ ] Pre-commit hooks enforce linting and formatting

**Traced to**: BR-005 (operational excellence)

**Priority**: P2 - High

---

### MAINT-002: Test Coverage and Quality

**Description**: Comprehensive test suite ensures correctness and prevents regressions.

**Rationale**: High-quality tests enable confident refactoring and feature development.

**Requirements**:

- **Unit Test Coverage**: >80% line coverage for core modules
- **Integration Tests**: End-to-end tests for each tier (smoke, quick, full)
- **Validation Tests**: Compare scores against reference implementations
- **Performance Tests**: Verify tier duration targets
- **Fault Injection Tests**: Checkpoint/resume, resource exhaustion

**Acceptance Criteria**:
- [ ] `pytest --cov` reports >80% coverage
- [ ] Integration tests run in CI/CD on every PR
- [ ] Validation tests compare against matric-cli/matric-memory baselines
- [ ] Performance tests fail if tier durations exceeded
- [ ] Fault injection tests validate all recovery paths

**Traced to**: #13 (CI/CD), BR-002 (accuracy)

**Priority**: P1 - Critical

---

### MAINT-003: Logging and Observability

**Description**: Comprehensive logging enables troubleshooting and monitoring.

**Rationale**: Production issues require detailed logs for diagnosis.

**Requirements**:

- **Structured Logging**: JSON-formatted logs with consistent fields
- **Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL appropriately used
- **Contextual Information**: Include request IDs, sample IDs, model names
- **Log Rotation**: Automatic rotation to prevent disk exhaustion
- **Performance Metrics**: Log duration, latency, throughput

**Acceptance Criteria**:
- [ ] Logs in JSON format with timestamp, level, message, context
- [ ] Log file at `~/.matric-eval/logs/matric-eval.log`
- [ ] Log rotation at 100MB, keep last 5 files
- [ ] DEBUG logs include full prompts, completions, scores
- [ ] INFO logs include progress, benchmark completion, summary

**Traced to**: #14 (logging and observability), REL-004

**Priority**: P2 - High

---

### MAINT-004: Documentation Maintenance

**Description**: Documentation must stay current with code changes.

**Rationale**: Outdated documentation misleads users and wastes time.

**Requirements**:

- **Docstring Coverage**: 100% of public APIs documented
- **Automated Docs**: Auto-generate API docs from docstrings
- **Version Sync**: Documentation versioned with code releases
- **Changelog**: CHANGELOG.md documents all user-facing changes

**Acceptance Criteria**:
- [ ] Docstrings for all public functions, classes, modules
- [ ] API docs auto-generated with Sphinx or mkdocs
- [ ] Docs published at matric-eval.readthedocs.io (or similar)
- [ ] CHANGELOG.md follows Keep a Changelog format
- [ ] Documentation reviewed in PR process

**Traced to**: BR-005 (operational excellence)

**Priority**: P3 - Medium

---

### MAINT-005: Modularity and Extensibility

**Description**: Architecture must support extension without modification.

**Rationale**: New benchmarks and scorers should integrate cleanly.

**Requirements**:

- **Plugin Architecture**: Benchmarks and scorers loadable as plugins
- **Clear Interfaces**: Abstract base classes for tasks, solvers, scorers
- **Configuration-Driven**: New benchmarks configurable without code changes
- **Backward Compatibility**: API stability for bindings

**Acceptance Criteria**:
- [ ] Custom benchmark implementable in <100 lines of code
- [ ] Custom scorer implementable by subclassing `BaseScorer`
- [ ] Plugin registration via config file or entrypoints
- [ ] API versioning strategy documented (semantic versioning)

**Traced to**: #2 (inspect-evals integration), future benchmarks (#17)

**Priority**: P3 - Medium

---

## Operational Requirements

### OPS-001: Installation and Setup

**Description**: Installation must be simple and work across platforms.

**Rationale**: Complex installation discourages adoption.

**Requirements**:

- **Single Command Install**: `uv sync` installs all dependencies
- **Python Version**: Support Python 3.11+
- **Platform Support**: Linux (primary), macOS (secondary), Windows (best-effort)
- **No Manual Steps**: No post-install configuration required

**Acceptance Criteria**:
- [ ] `uv sync` installs on Ubuntu 24.04, macOS 14+, Windows 11
- [ ] Python 3.11, 3.12, 3.13 supported
- [ ] Default configuration works out-of-box
- [ ] Installation documented in README (<10 steps)

**Traced to**: BR-004 (ecosystem integration)

**Priority**: P2 - High

---

### OPS-002: CI/CD Integration

**Description**: Automated testing and smoke tests must run in CI/CD pipelines.

**Rationale**: Prevent regressions, ensure quality before merge.

**Requirements**:

- **Automated Tests**: All tests run on every PR
- **Smoke Tests**: Smoke tier evaluation runs on representative model
- **Performance Gates**: Fail if tier durations exceed targets
- **Code Coverage**: Fail if coverage drops below 80%

**Acceptance Criteria**:
- [ ] GitHub Actions workflow runs tests on every PR
- [ ] Smoke test evaluates llama3.2:3b (or mock model)
- [ ] Performance test fails if smoke tier >5 minutes
- [ ] Coverage report published, PR fails if <80%

**Traced to**: #13 (CI/CD pipeline)

**Priority**: P1 - Critical

---

### OPS-003: Monitoring and Alerting

**Description**: Production usage must be observable and monitorable.

**Rationale**: Detect issues before they impact users.

**Requirements**:

- **Metrics Emission**: Expose metrics for Prometheus, CloudWatch, etc.
- **Health Checks**: `/health` endpoint (if running as service)
- **Error Tracking**: Integrate with Sentry or similar (optional)
- **Usage Analytics**: Track tier usage, benchmark popularity (privacy-preserving)

**Acceptance Criteria**:
- [ ] Metrics: evaluation_duration, samples_processed, errors_total
- [ ] Metrics exportable to Prometheus (if running as service)
- [ ] Health check returns 200 if Ollama reachable
- [ ] Optional telemetry (opt-in) reports usage statistics

**Traced to**: #14 (observability), BR-005

**Priority**: P4 - Low (Future)

---

### OPS-004: Deployment and Distribution

**Description**: Software must be easily distributed and deployed.

**Rationale**: Users need standard installation methods.

**Requirements**:

- **PyPI Package**: Published to PyPI for `pip install matric-eval`
- **Versioning**: Semantic versioning (MAJOR.MINOR.PATCH)
- **Release Automation**: GitHub Actions or similar for releases
- **Docker Image** (optional): For containerized deployments

**Acceptance Criteria**:
- [ ] Package published to PyPI on tagged releases
- [ ] Version follows semver (e.g., 0.2.0, 1.0.0)
- [ ] Release notes auto-generated from CHANGELOG.md
- [ ] Docker image published to Docker Hub or GHCR (optional)

**Traced to**: BR-004 (ecosystem integration)

**Priority**: P3 - Medium

---

### OPS-005: Backup and Disaster Recovery

**Description**: Critical data must be backed up and recoverable.

**Rationale**: Loss of evaluation results or configurations is costly.

**Requirements**:

- **Checkpoint Backups**: Optionally backup checkpoints to cloud storage
- **Result Archiving**: Save results to durable storage (S3, GCS)
- **Configuration Versioning**: Version control for custom configurations
- **Data Recovery**: Documented process to recover from data loss

**Acceptance Criteria**:
- [ ] Checkpoint auto-backup to S3/GCS if configured (optional)
- [ ] Results saved to configurable output directory
- [ ] Custom configs stored in version control
- [ ] Recovery documentation covers common scenarios

**Traced to**: UC002 (checkpoint/resume), BR-005

**Priority**: P4 - Low (Future)

---

## Compatibility Requirements

### COMPAT-001: Backward Compatibility

**Description**: API changes must maintain backward compatibility within major versions.

**Rationale**: Breaking changes disrupt downstream integrations.

**Requirements**:

- **API Stability**: Public APIs stable within major version (1.x.x)
- **Deprecation Policy**: 2 minor versions notice before removal
- **Migration Guides**: Documented upgrade paths for breaking changes
- **Checkpoint Compatibility**: Read checkpoints from previous minor versions

**Acceptance Criteria**:
- [ ] No breaking API changes within 1.x.x releases
- [ ] Deprecated features marked with warnings for 2 releases
- [ ] Migration guide for 0.x to 1.0, 1.x to 2.0
- [ ] Checkpoint v1.0 readable by v1.5

**Traced to**: BR-004 (ecosystem integration), UC002

**Priority**: P3 - Medium

---

### COMPAT-002: Ollama Version Compatibility

**Description**: Support multiple Ollama versions within reason.

**Rationale**: Users may not upgrade Ollama immediately.

**Requirements**:

- **Minimum Version**: Ollama 0.1.0+
- **Recommended Version**: Latest stable release
- **API Compatibility**: Handle API differences gracefully
- **Version Detection**: Warn if Ollama version untested

**Acceptance Criteria**:
- [ ] Works with Ollama 0.1.0, 0.2.0, latest
- [ ] Detects Ollama version via API
- [ ] Warns if Ollama version <0.1.0 or unreleased
- [ ] Gracefully handles API changes between versions

**Traced to**: BR-005 (operational excellence)

**Priority**: P3 - Medium

---

### COMPAT-003: Python Version Support

**Description**: Support active Python versions per PEP 387.

**Rationale**: Balance modern features with user base compatibility.

**Requirements**:

- **Minimum Version**: Python 3.11 (Ubuntu 24.04 default)
- **Tested Versions**: 3.11, 3.12, 3.13
- **Dropped Versions**: Python <3.11 (EOL or near-EOL)

**Acceptance Criteria**:
- [ ] CI/CD tests on Python 3.11, 3.12, 3.13
- [ ] `pyproject.toml` specifies `requires-python = ">=3.11"`
- [ ] No deprecation warnings on supported versions

**Traced to**: OPS-001 (installation)

**Priority**: P2 - High

---

## Compliance and Legal Requirements

### LEGAL-001: Dataset Licensing

**Description**: All benchmark datasets must have permissive licenses.

**Rationale**: Avoid legal issues from non-commercial or restrictive licenses.

**Requirements**:

- **Allowed Licenses**: MIT, Apache 2.0, CC-BY, CC0
- **Attribution**: Proper attribution in documentation
- **License Auditing**: Quarterly review of dataset licenses
- **User Notification**: Display licenses in reports

**Acceptance Criteria**:
- [ ] All bundled datasets have permissive licenses
- [ ] LICENSE.md includes dataset attributions
- [ ] Reports include dataset license information
- [ ] Documentation lists all datasets and licenses

**Traced to**: BR-005 (operational excellence)

**Priority**: P3 - Medium

---

### LEGAL-002: Open Source Licensing

**Description**: Project must have clear open-source license.

**Rationale**: Users need clarity on usage rights.

**Requirements**:

- **License**: MIT or Apache 2.0 (to be decided)
- **License File**: LICENSE in root directory
- **Header Comments**: License header in source files (optional)
- **Dependency Compatibility**: All dependencies compatible with chosen license

**Acceptance Criteria**:
- [ ] LICENSE file in repository root
- [ ] `pyproject.toml` specifies license
- [ ] All dependencies have compatible licenses
- [ ] Third-party attributions in THIRD_PARTY_LICENSES.md

**Traced to**: BR-005 (operational excellence)

**Priority**: P2 - High

---

## Cross-Cutting Concerns

### CROSS-001: Internationalization (i18n)

**Description**: Consider internationalization for global users.

**Rationale**: Non-English users benefit from localized messages.

**Requirements**:

- **English Default**: All messages, docs, and errors in English
- **i18n Framework** (future): Support for translations (gettext)
- **Unicode Support**: Proper handling of non-ASCII characters

**Acceptance Criteria**:
- [ ] All text in English (en-US)
- [ ] No hardcoded locale assumptions (dates, numbers)
- [ ] Unicode filenames and outputs supported

**Traced to**: BR-005 (operational excellence)

**Priority**: P4 - Low (Future)

---

### CROSS-002: Accessibility

**Description**: CLI output should be accessible to users with disabilities.

**Rationale**: Inclusive design benefits all users.

**Requirements**:

- **Color Independence**: Information not conveyed by color alone
- **Screen Reader Friendly**: Structured output for screen readers
- **Keyboard-Only**: No mouse required for CLI

**Acceptance Criteria**:
- [ ] Progress bars include text percentage (not just visual)
- [ ] Color coding supplemented with symbols (✓, ✗, ⋯)
- [ ] JSON output fully accessible to screen readers

**Traced to**: USE-005 (error messages)

**Priority**: P4 - Low (Future)

---

## Requirements Traceability Matrix

| NFR ID | Category | Priority | Gitea Issues | Business Reqs | Use Cases |
|--------|----------|----------|--------------|---------------|-----------|
| PERF-001 | Performance | P1 | #6 | BR-003 | UC001 |
| PERF-002 | Performance | P2 | #1, #2 | BR-002 | UC001 |
| PERF-003 | Performance | P2 | #11, #12 | BR-003 | UC001, UC002 |
| PERF-004 | Performance | P2 | #12 | BR-003 | UC001 |
| PERF-005 | Performance | P3 | #11, #14 | BR-003 | UC002 |
| PERF-006 | Performance | P3 | #1-#5 | BR-003 | UC001 |
| REL-001 | Reliability | P1 | All | BR-002 | UC001, UC002 |
| REL-002 | Reliability | P1 | #11 | BR-005 | UC002 |
| REL-003 | Reliability | P1 | #1, #2, #7 | BR-002 | UC001 |
| REL-004 | Reliability | P2 | All | BR-005 | UC001, UC002 |
| REL-005 | Reliability | P2 | #13 | BR-005 | UC001 |
| USE-001 | Usability | P2 | #6 | BR-005 | UC001 |
| USE-002 | Usability | P2 | All | BR-003 | UC001, UC002 |
| USE-003 | Usability | P3 | All | BR-005 | UC001 |
| USE-004 | Usability | P2 | All | BR-005 | All |
| USE-005 | Usability | P2 | All | BR-005 | UC001, UC002 |
| SEC-001 | Security | P1 | #1, #4, #5 | BR-005 | UC001 |
| SEC-002 | Security | P1 | All | BR-005 | All |
| SEC-003 | Security | P2 | #13 | BR-005 | - |
| SEC-004 | Security | P2 | All | BR-005 | UC002 |
| SEC-005 | Security | P3 | All | BR-002 | UC001 |
| MAINT-001 | Maintainability | P2 | All | BR-005 | - |
| MAINT-002 | Maintainability | P1 | #13 | BR-002 | All |
| MAINT-003 | Maintainability | P2 | #14 | BR-005 | All |
| MAINT-004 | Maintainability | P3 | All | BR-005 | - |
| MAINT-005 | Maintainability | P3 | #2, #17 | BR-005 | - |
| OPS-001 | Operational | P2 | All | BR-004 | - |
| OPS-002 | Operational | P1 | #13 | BR-005 | UC001 |
| OPS-003 | Operational | P4 | #14 | BR-005 | - |
| OPS-004 | Operational | P3 | All | BR-004 | - |
| OPS-005 | Operational | P4 | #11 | BR-005 | UC002 |
| COMPAT-001 | Compatibility | P3 | All | BR-004 | UC002 |
| COMPAT-002 | Compatibility | P3 | All | BR-005 | UC001 |
| COMPAT-003 | Compatibility | P2 | All | - | - |
| LEGAL-001 | Legal | P3 | All | BR-005 | - |
| LEGAL-002 | Legal | P2 | All | BR-005 | - |

## Priority Summary

| Priority | Count | NFR IDs |
|----------|-------|---------|
| P1 - Critical | 9 | PERF-001, REL-001, REL-002, REL-003, SEC-001, SEC-002, MAINT-002, OPS-002 |
| P2 - High | 15 | PERF-002, PERF-003, PERF-004, REL-004, REL-005, USE-001, USE-002, USE-004, USE-005, SEC-003, SEC-004, MAINT-001, MAINT-003, OPS-001, COMPAT-003, LEGAL-002 |
| P3 - Medium | 10 | PERF-005, PERF-006, USE-003, SEC-005, MAINT-004, MAINT-005, OPS-004, COMPAT-001, COMPAT-002, LEGAL-001 |
| P4 - Low | 3 | OPS-003, OPS-005, CROSS-001, CROSS-002 |

## Acceptance Testing Strategy

### Performance Testing

1. **Tier Duration Tests**: Measure smoke/quick/full tier duration for llama3.2:3b
2. **Latency Overhead Tests**: Compare framework vs. raw Ollama API latency
3. **Memory Profiling**: Monitor peak memory usage during full-tier evaluation
4. **Parallel Efficiency Tests**: Measure speedup with 2, 4, 8 workers
5. **Throughput Tests**: Measure samples/minute for each benchmark

### Reliability Testing

1. **Reproducibility Tests**: 10 repeated runs with same seed, compare scores
2. **Checkpoint/Resume Tests**: Interrupt at 25%, 50%, 75%, resume and validate
3. **Fault Injection Tests**: Kill process, exhaust memory, fill disk, corrupt checkpoint
4. **Error Handling Tests**: Trigger 20+ error conditions, validate messages
5. **Data Integrity Tests**: Compare scores against matric-cli and matric-memory baselines

### Usability Testing

1. **CLI Usability Tests**: Usability testing with 5+ developers (new users)
2. **Documentation Review**: Walkthrough documentation with new users
3. **Error Message Evaluation**: Present error messages to users, assess clarity
4. **Progress Feedback Tests**: Validate ETA accuracy over 10+ evaluations

### Security Testing

1. **Sandbox Escape Tests**: Attempt network access, filesystem access, privilege escalation
2. **Input Fuzzing**: 1000+ malicious inputs (SQL injection, command injection, path traversal)
3. **Dependency Scanning**: `pip-audit` and `safety` checks in CI/CD
4. **Secrets Detection**: Scan logs and checkpoints for leaked credentials

### Operational Testing

1. **Installation Tests**: Fresh install on Ubuntu 24.04, macOS 14, Windows 11
2. **CI/CD Integration Tests**: Run smoke tests in GitHub Actions, GitLab CI
3. **Multi-Platform Tests**: Verify functionality on Linux, macOS, Windows
4. **Version Compatibility Tests**: Test with Ollama 0.1.0, 0.2.0, latest

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial supplementary requirements (NFRs) |
