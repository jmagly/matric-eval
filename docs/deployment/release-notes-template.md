# matric-eval v1.0.0 Release Notes

**Release Date**: 2026-[MONTH]-[DAY]
**Package**: matric-eval
**Version**: 1.0.0
**Type**: Major Release (Initial Stable Version)

---

## Overview

matric-eval v1.0.0 is the first stable release of the consolidated model evaluation framework for the matric ecosystem. This release delivers production-ready evaluation capabilities for Ollama models using public benchmarks and custom application-specific tests.

**Key Highlights**:
- 8 public benchmarks with production-grade scoring
- 282 custom matric tests migrated from matric-cli and matric-memory
- Checkpoint/resume for fault-tolerant long-running evaluations
- Tiered execution (smoke/quick/full) for flexible resource usage
- TypeScript bindings for matric-cli integration
- Parallel model evaluation for 50%+ runtime reduction

---

## What's New

### Public Benchmarks (8 Total)

**Code Generation**:
- **HumanEval** - 164 Python programming problems with function signatures
- **MBPP** - 974 mostly basic Python problems with function name extraction
- **LiveCodeBench** - 880 competitive programming problems with time limits
- **DS-1000** - 1,000 data science problems with NumPy/Pandas/Scikit-learn

**Reasoning & Knowledge**:
- **GSM8K** - 1,319 grade-school math word problems
- **ARC** - 1,172 reasoning problems requiring multi-step logic

**Instruction Following**:
- **IFEval** - 541 instruction-following problems with constraint checking

**Multi-Turn Conversation**:
- **MT-Bench** - 80 multi-turn conversations with LLM-as-Judge scoring

### Custom matric Tests (282 Total)

**Tool Calling Evaluation** (6 scenarios):
- Correct tool selection from multiple options
- Parameter extraction and validation
- Error handling and recovery
- Multi-step tool composition
- Contextual tool usage
- Tool result interpretation

**Agentic Evaluation**:
- Multi-turn reasoning with tool use
- Planning and execution validation
- Safety and helpfulness checks

**5-Dimensional Scoring Framework**:
- **Correctness**: Functional accuracy and test pass rate
- **Efficiency**: Runtime, token usage, resource consumption
- **Safety**: Constraint adherence, guardrail compliance
- **Helpfulness**: User intent satisfaction, clarity
- **Reasoning**: Multi-step logic, coherence

### Core Features

**Tiered Evaluation**:
- **Smoke Tier** - 5 samples per benchmark, <2 minutes, CI/CD validation
- **Quick Tier** - 75 samples per benchmark, <20 minutes, rapid iteration
- **Full Tier** - Complete datasets, hours, comprehensive assessment

**Checkpoint/Resume**:
- Automatic state persistence after each model evaluation
- Gap detection identifies incomplete work
- Selective re-run avoids duplicate computation
- Atomic writes prevent state corruption
- Fault-tolerant for long-running evaluations (e.g., 31 models over 8 hours)

**Model Discovery**:
- Automatic Ollama model listing
- Size-based filtering (MAX_MODEL_SIZE_GB)
- Capability-based ranking
- Seeded random sampling for reproducibility

**Parallel Execution**:
- Concurrent model evaluation
- 50%+ runtime reduction
- Isolated process pools
- State synchronization with file locks

**Observability**:
- Structured JSON logging
- Debug/info/warning/error levels
- Progress tracking with rich terminal output
- Error categorization (Ollama, timeout, parsing, execution)

### CLI Interface

**Primary Commands**:
```bash
# Run smoke tests (CI/CD validation)
matric-eval --tier smoke --model llama3.2:3b

# Run quick evaluation for iteration
matric-eval --tier quick --model llama3.2:3b

# Run full evaluation across all models
matric-eval --tier full

# Resume interrupted evaluation
matric-eval --resume results/quick-20260124-143022.meta.json

# Validate checkpoint integrity
matric-eval --validate results/quick-20260124-143022.meta.json

# Fill gaps in incomplete evaluation
matric-eval --fill-gaps results/quick-20260124-143022.meta.json

# Run custom tests for specific app
matric-eval --tier custom --app matric-cli

# Generate model recommendations
matric-eval --recommend --output model-categories.json
```

**Flags**:
- `--tier` - Evaluation tier (smoke/quick/full/custom)
- `--model` - Specific Ollama model (e.g., llama3.2:3b)
- `--benchmark` - Specific benchmark to run (humaneval, mbpp, etc.)
- `--resume` - Resume from checkpoint file
- `--validate` - Validate checkpoint integrity
- `--fill-gaps` - Re-run only incomplete work
- `--parallel` - Number of concurrent evaluations
- `--output` - Output file path
- `--format` - Output format (json/csv/markdown)
- `--log-level` - Logging verbosity (debug/info/warning/error)
- `--app` - Application for custom tests (matric-cli/matric-memory)
- `--recommend` - Generate model recommendation config

### Language Bindings

**TypeScript** (`@matric/eval`):
- Subprocess-based integration
- Type-safe interfaces
- JSON result parsing
- Error handling
- Example integration in matric-cli

**Rust** (Deferred to v1.1):
- Planned for matric-memory integration
- FFI or subprocess approach TBD

### Scoring Infrastructure

**Code Execution Scoring**:
- Docker sandbox isolation
- Resource limits (CPU, memory, timeout)
- Network isolation
- Safe execution of untrusted code
- Test case validation
- Artifact preservation

**LLM-as-Judge Scoring**:
- Configurable grading criteria
- Temperature=0 for consistency
- Multi-run aggregation
- Variance tracking (<15% target)
- Rubric-based assessment
- Ported templates from matric-memory

**Constraint Checking** (IFEval):
- 25+ constraint types
- Pattern matching validation
- Structural compliance checks
- Boolean logic composition

**Data Science Scoring** (DS-1000):
- Environment setup automation
- Library version management
- NumPy/Pandas/Scikit-learn tests
- Result comparison with tolerance

### Configuration Management

**Configuration File** (`.matric-eval.yaml`):
```yaml
ollama:
  url: http://localhost:11434
  timeout: 600

tiers:
  smoke:
    samples: 5
    timeout: 120
  quick:
    samples: 75
    timeout: 1200
  full:
    samples: -1  # All samples

checkpoint:
  enabled: true
  directory: ./results
  auto_save: true

logging:
  level: INFO
  format: json

parallel:
  max_workers: 4
  enabled: true
```

**Environment Variables**:
- `MATRIC_EVAL_OLLAMA_URL` - Ollama server URL
- `MATRIC_EVAL_LOG_LEVEL` - Logging verbosity
- `MATRIC_EVAL_CACHE_DIR` - Dataset cache location
- `MATRIC_EVAL_RESULTS_DIR` - Results output directory

### CI/CD Integration

**Gitea Actions Workflow**:
- Automated smoke tests on every commit
- <3 minute execution time
- Multi-platform testing (Linux, macOS, Windows)
- Coverage reporting (80%+ required)
- SBOM generation
- Security scanning with pip-audit

**Artifacts**:
- Test results JSON
- Coverage reports (HTML, XML)
- SBOM (CycloneDX format)
- Performance benchmarks

---

## Breaking Changes

**None** - This is the initial stable release, no previous public API existed.

For users migrating from internal evaluation code in matric-cli or matric-memory, see the Migration Guide section below.

---

## Migration Guide

### From matric-cli Evaluation Code

**Old Approach** (matric-cli `source/eval/`):
```typescript
// TypeScript evaluation in matric-cli
import { runEvaluation } from './eval/evaluator';

const results = await runEvaluation({
  model: 'llama3.2:3b',
  benchmarks: ['humaneval', 'mbpp'],
  samples: 75,
});
```

**New Approach** (matric-eval via bindings):
```typescript
// TypeScript using @matric/eval
import { evaluate } from '@matric/eval';

const results = await evaluate({
  tier: 'quick',
  model: 'llama3.2:3b',
  benchmarks: ['humaneval', 'mbpp'],
});
```

**Benefits**:
- Centralized evaluation logic (no code duplication)
- Checkpoint/resume support (fault tolerance)
- Consistent scoring across matric ecosystem
- Extended benchmarks (8 vs 2)
- Parallel execution support

**Migration Steps**:

1. **Install TypeScript bindings**:
```bash
npm install @matric/eval
```

2. **Update evaluation calls**:
   - Replace custom eval code with `@matric/eval` imports
   - Use `tier` instead of `samples` parameter
   - Results format is standardized JSON

3. **Update tests**:
   - matric-eval provides standardized test fixtures
   - Update test expectations for new result format

4. **Remove deprecated code**:
   - Delete `source/eval/` directory
   - Remove evaluation dependencies (if no longer needed)
   - Update documentation references

5. **Verify integration**:
```bash
npm test
# Run sample evaluation
```

**Deprecated Features** (from matric-cli eval):
- Custom MBPP function extraction (now handled by matric-eval)
- Manual checkpoint/resume logic (now automated)
- Custom code execution sandbox (now Docker-based)

**Preserved Behaviors**:
- MBPP function name extraction from test assertions
- Seeded random sampling for reproducibility
- Model size filtering
- Error categorization (Ollama, timeout, parsing)

### From matric-memory Evaluation Code

**Old Approach** (matric-memory `crates/matric-inference/src/bin/eval.rs`):
```rust
// Rust evaluation in matric-memory
use matric_inference::eval::run_evaluation;

let results = run_evaluation(EvalConfig {
    model: "llama3.2:3b".to_string(),
    tests: vec!["tool_calling", "agentic"],
    judge_model: Some("gpt-4".to_string()),
});
```

**New Approach** (matric-eval via CLI - Rust bindings in v1.1):
```bash
# CLI approach for v1.0
matric-eval --tier custom --app matric-memory --model llama3.2:3b
```

```rust
// Future Rust bindings (v1.1)
use matric_eval::evaluate;

let results = evaluate(EvalOptions {
    tier: Tier::Custom,
    app: Some("matric-memory"),
    model: "llama3.2:3b".to_string(),
})?;
```

**Migration Steps** (v1.0 - CLI approach):

1. **Install matric-eval**:
```bash
pip install matric-eval
```

2. **Update evaluation workflow**:
   - Call `matric-eval` CLI via subprocess
   - Parse JSON results in Rust
   - Migrate LLM-as-Judge templates to matric-eval format

3. **Migrate custom tests**:
   - Convert tests to JSONL format (see Custom Test Format below)
   - Place in `datasets/custom/matric-memory/` directory

4. **Update CI/CD**:
   - Replace custom eval binary with matric-eval CLI
   - Update test workflows

**Migration Steps** (v1.1 - Rust bindings):

Will be provided in v1.1 release notes when Rust bindings are available.

### Custom Test Format

**JSONL Format** (one test per line):
```jsonl
{"id": "tool-call-001", "prompt": "Search for recent papers on LLMs", "expected_tool": "search", "expected_params": {"query": "LLMs", "timeframe": "recent"}}
{"id": "agentic-002", "prompt": "Analyze data and create visualization", "expected_steps": ["load_data", "analyze", "visualize"], "max_turns": 5}
```

**Fields**:
- `id` - Unique test identifier
- `prompt` - Input prompt for model
- `expected_tool` - Expected tool name (for tool calling tests)
- `expected_params` - Expected tool parameters (for validation)
- `expected_steps` - Expected sequence of actions (for agentic tests)
- `max_turns` - Maximum conversation turns allowed
- `scoring` - Custom scoring criteria (optional)

**Placement**:
- Public benchmarks: `datasets/public/{benchmark}/` (auto-downloaded)
- Custom tests: `datasets/custom/{app}/` (user-provided)

### Configuration Migration

**matric-cli** - No configuration file previously, now optional `.matric-eval.yaml` for customization.

**matric-memory** - LLM-as-Judge prompts migrated to matric-eval templates in `src/matric_eval/templates/`.

---

## Known Issues

### Issue #1: Windows Docker Sandbox Performance

**Severity**: Low
**Impact**: Smoke tier may exceed 2-minute target on Windows with Docker Desktop
**Workaround**: Use WSL2 backend for Docker Desktop or run on Linux
**Fix Plan**: Investigate Windows-specific optimizations for v1.0.1

### Issue #2: Large Model Memory Usage

**Severity**: Medium
**Impact**: Models >32GB may cause OOM on systems with <64GB RAM
**Workaround**: Use model size filtering: `--max-model-size 32` or increase swap
**Fix Plan**: Add memory monitoring and graceful degradation for v1.1

### Issue #3: IFEval Constraint Edge Cases

**Severity**: Low
**Impact**: 2/541 IFEval tests have known parsing edge cases with complex nested constraints
**Workaround**: These tests are marked as `known_issues` in results
**Fix Plan**: Enhanced constraint parser for v1.0.1

### Issue #4: npm Package Peer Dependency Warning

**Severity**: Low
**Impact**: npm install shows peer dependency warning for Python requirement
**Workaround**: Ignore warning, ensure Python 3.11+ is installed
**Fix Plan**: Update package.json metadata for v1.0.1

---

## Deprecations

**None** - This is the initial release, no features are deprecated.

**Future Deprecations** (Planned for v2.0):
- CLI will transition to declarative configuration files (current imperative flags supported for backward compatibility)

---

## Performance

### Benchmark Execution Times

**Smoke Tier** (5 samples, single model):
- HumanEval: 12s
- MBPP: 15s
- GSM8K: 8s
- ARC: 10s
- IFEval: 18s
- LiveCodeBench: 25s
- DS-1000: 22s
- MT-Bench: 30s
- **Total**: <2 minutes

**Quick Tier** (75 samples, single model):
- HumanEval: 3.2 min
- MBPP: 4.1 min
- GSM8K: 2.5 min
- ARC: 2.8 min
- IFEval: 5.2 min
- LiveCodeBench: 6.8 min
- DS-1000: 7.1 min
- MT-Bench: 8.5 min
- **Total**: <20 minutes

**Full Tier** (all samples, 31 models):
- Sequential: ~18 hours
- Parallel (4 workers): ~9 hours (50% reduction)

### Resource Usage

**Memory**:
- Base: 500MB
- Per model evaluation: +200-500MB
- Peak (parallel 4x): 2.5GB

**Disk**:
- Datasets cache: 2GB
- Results per full tier run: 50MB
- Docker images: 1.5GB

**Network**:
- Dataset downloads (first run): 2GB
- Ollama model pulls: variable (1-32GB per model)

---

## Security

### Vulnerabilities Fixed

**None** - This is the initial release.

### Security Enhancements

**Docker Sandbox Isolation**:
- All code execution runs in isolated Docker containers
- Network disabled
- Filesystem read-only except for /tmp
- Resource limits enforced (CPU, memory, time)
- No privileged access

**Dependency Scanning**:
- All dependencies scanned with pip-audit
- No known vulnerabilities (CVSS ≥7.0)
- SBOM included for compliance tracking

**Secrets Management**:
- No credentials in code or artifacts
- API keys managed via environment variables
- Configuration files excluded from version control

---

## Dependencies

### Python Dependencies

**Core**:
- inspect-ai >= 0.3.0 - Evaluation framework
- ollama >= 0.1.0 - Ollama client
- click >= 8.1.0 - CLI interface
- pydantic >= 2.0.0 - Configuration validation

**Development**:
- pytest >= 7.4.0 - Testing framework
- pytest-cov >= 4.1.0 - Coverage reporting
- ruff >= 0.1.0 - Linting and formatting
- mypy >= 1.7.0 - Type checking

**Full dependency list**: See `pyproject.toml` or `uv.lock`

### System Dependencies

**Required**:
- Python 3.11 or higher
- Ollama server (local or remote)

**Optional**:
- Docker (for code execution scoring)
- Git (for dataset downloads)

---

## Installation

### pip/uv

```bash
# Install from PyPI
pip install matric-eval

# Verify installation
matric-eval --version

# Run smoke test
matric-eval --tier smoke --model llama3.2:3b
```

### npm (TypeScript bindings)

```bash
# Install in TypeScript project
npm install @matric/eval

# Verify installation
import { version } from '@matric/eval';
console.log(version);
```

### Development

```bash
# Clone repository
git clone https://git.integrolabs.net/roctinam/matric-eval
cd matric-eval

# Install with uv
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Run tests
pytest

# Run smoke test
matric-eval --tier smoke --model llama3.2:3b
```

---

## Upgrade Path

**From Development Versions** (pre-1.0):

No upgrade path needed - v1.0.0 is the first stable release.

**From matric-cli/matric-memory Evaluation Code**:

See Migration Guide section above for detailed steps.

---

## Roadmap

### v1.0.x Patch Releases

**Planned**:
- Bug fixes from hypercare feedback
- Performance optimizations
- Documentation improvements
- Security updates

**Timeline**: As needed (monthly or for critical issues)

### v1.1 Minor Release

**Planned Features**:
- Rust bindings for matric-memory
- Leaderboard and reporting dashboard
- Extended benchmarks (SWE-bench, GPQA)
- Contamination detection
- Historical trend analysis
- Complete TypeScript bindings (full API coverage)

**Timeline**: 6-8 weeks post-v1.0

### v2.0 Major Release

**Planned Features**:
- Multi-cloud deployment support
- Hosted evaluation service
- Web dashboard for results
- Advanced caching strategies
- Breaking API changes (if needed)

**Timeline**: 6+ months post-v1.0

---

## Contributors

**Core Team**:
- roctinam (Solo Python Developer) - Architecture, implementation, testing, documentation

**Special Thanks**:
- matric-cli team - Requirements and integration feedback
- matric-memory team - LLM-as-Judge templates and custom test requirements
- Inspect AI team (UK AI Safety Institute) - Excellent evaluation framework
- EleutherAI - lm-eval-harness inspiration

---

## Support

### Documentation

- **README.md** - Quick start and installation
- **CLAUDE.md** - AI assistant context and development guide
- **docs/** - Comprehensive user and developer guides

### Issue Tracking

- **GitHub/Gitea Issues**: https://git.integrolabs.net/roctinam/matric-eval/issues
- For bugs, feature requests, and questions

### Contact

- **Email**: dev@integrolabs.net
- **Repository**: https://git.integrolabs.net/roctinam/matric-eval

---

## License

MIT License - See LICENSE file for details.

---

## Acknowledgments

This release consolidates evaluation code previously duplicated across matric-cli and matric-memory. Special acknowledgment to the matric ecosystem for providing real-world requirements and integration constraints that shaped this framework.

The checkpoint/resume design was directly motivated by production issues encountered during matric-cli model evaluations (EPIPE error at model 13/31 after 8 hours).

---

## Changelog

### v1.0.0 (2026-[MONTH]-[DAY])

**Features** (22 issues implemented):
- Issue #1: Code execution scoring with Docker sandbox
- Issue #2: Integrate inspect-evals (HumanEval, MBPP, GSM8K, ARC)
- Issue #3: IFEval constraint checking
- Issue #4: LiveCodeBench scorer
- Issue #5: DS-1000 scorer
- Issue #6: Tiered CLI (smoke/quick/full)
- Issue #7: Custom matric tests (282 tests migrated)
- Issue #8: Tool calling evaluation (6 scenarios)
- Issue #9: MT-Bench with LLM-as-judge
- Issue #10: 5-dimensional scoring framework
- Issue #11: Checkpoint/resume with gap detection
- Issue #12: Parallel model evaluation
- Issue #13: CI/CD pipeline with smoke tests
- Issue #14: Logging and observability
- Issue #18: Model recommendation engine
- Issue #13-EXT: Extended reporting with comparisons
- Issue #16-PARTIAL: TypeScript bindings (subprocess-based)
- Issue #21: Port LLM-as-Judge templates from matric-memory
- Issue #22: Universal LLM-as-Judge with agentic support

**Deferred to v1.1**:
- Issue #15: Leaderboard and reporting dashboard
- Issue #17: Extended benchmarks (SWE-bench, GPQA)
- Issue #19: Contamination detection
- Issue #20: Historical trend analysis
- Issue #16 (complete): Full TypeScript bindings
- Rust bindings for matric-memory

**Test Coverage**: 82% (exceeds 80% Production profile requirement)

**Performance Targets Achieved**:
- Smoke tier: <2 minutes
- Quick tier: <20 minutes
- Parallel execution: 50%+ speedup

---

**Release Hash**: [GIT_COMMIT_SHA]
**Release Tag**: v1.0.0
**Release Date**: 2026-[MONTH]-[DAY]

---

**END OF RELEASE NOTES**
