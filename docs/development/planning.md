# matric-eval Planning Document

## Executive Summary

This document outlines the architectural decisions and implementation plan for `matric-eval`, a consolidated model evaluation framework for the matric ecosystem.

**Key Recommendation**: Adopt Python as the core language, leveraging existing evaluation frameworks (Inspect AI or lm-eval-harness) rather than building from scratch in TypeScript.

## Research Findings

### Industry-Standard Evaluation Frameworks

| Framework | Language | Maintainer | Ollama Support | Strengths |
|-----------|----------|------------|----------------|-----------|
| **[Inspect AI](https://inspect.aisi.org.uk/)** | Python | UK AI Safety Institute | Native | Agent evals, 100+ pre-built tasks, MCP tools |
| **[lm-eval-harness](https://github.com/EleutherAI/lm-evaluation-harness)** | Python | EleutherAI | Via local-completions | Industry standard, HF Leaderboard backend |
| **[HELM](https://crfm.stanford.edu/helm/)** | Python | Stanford CRFM | Limited | Holistic metrics, research-grade |

### Why Python Over TypeScript?

1. **Ecosystem**: All major eval frameworks are Python-based
2. **Pre-built benchmarks**: 60+ tasks in lm-eval-harness, 100+ in Inspect AI
3. **Standardization**: Avoid reinventing prompt formats, validation logic, metrics
4. **Community**: Bug fixes and improvements from the broader ML community
5. **Ollama integration**: Native support in Inspect AI, tested patterns in lm-eval

### Current TypeScript Pain Points (from matric-cli)

Issues we've had to solve manually that frameworks handle:
- MBPP function name extraction (`51382e2`)
- Code extraction from markdown fences
- Safe process execution sandbox
- Validation artifact preservation
- Reproducible sampling

### Critical Requirement: Resilience & Recovery

**Problem**: Our current matric-cli eval crashed at model 13/31 with EPIPE error. Lost progress, manual restart required, no easy way to resume or re-run specific failures.

**Required Capabilities**:

| Capability | Description | Priority |
|------------|-------------|----------|
| **Checkpoint/Resume** | Save state after each model/benchmark, resume from last checkpoint | P0 |
| **Selective Re-run** | Re-run specific model + benchmark combo without full restart | P0 |
| **Gap Detection** | Scan output directory, identify missing/incomplete results | P0 |
| **Auto-Recovery** | Retry on transient errors (timeout, connection reset, EPIPE) | P1 |
| **Graceful Degradation** | Skip failed model, continue with next, report at end | P1 |
| **Idempotent Runs** | Re-running same eval produces same results, skips completed | P1 |

**State Management Design**:

```
results/run-{timestamp}/
├── meta.json                    # Run metadata, seed, config
├── state.json                   # Current progress, next model/benchmark
├── {model}/
│   ├── meta.json               # Model-level metadata
│   ├── state.json              # Which benchmarks complete
│   ├── {benchmark}/
│   │   ├── meta.json           # Benchmark metadata
│   │   ├── state.json          # Which problems complete
│   │   └── {problem_id}/       # Individual results
│   │       ├── prompt.txt
│   │       ├── response.txt
│   │       └── validation.json
│   └── summary.json            # Aggregated results (generated)
└── summary.json                # Run-level summary (generated)
```

**CLI Commands**:

```bash
# Start fresh run
matric-eval --tier quick

# Resume interrupted run
matric-eval --resume run-2026-01-24T01-15-51

# Re-run specific model
matric-eval --resume run-2026-01-24T01-15-51 --model codestral:latest

# Re-run specific benchmark for model
matric-eval --resume run-2026-01-24T01-15-51 --model codestral:latest --benchmark mbpp

# Detect and fill gaps
matric-eval --resume run-2026-01-24T01-15-51 --fill-gaps

# Validate completeness, report missing
matric-eval --validate run-2026-01-24T01-15-51
```

**Implementation Notes**:

1. **Atomic writes**: Write to temp file, rename on success (prevents partial state)
2. **Lock files**: Prevent concurrent runs on same results directory
3. **Heartbeat**: Update timestamp periodically to detect zombie runs
4. **Error classification**: Distinguish retryable (network, timeout) from fatal (bad model)
5. **Progress streaming**: Real-time status to stdout/file for monitoring

**Framework Evaluation Criteria**:

When evaluating Inspect AI vs lm-eval-harness, check:
- [ ] Does it support checkpointing natively?
- [ ] Can you resume from a specific point?
- [ ] How does it handle model crashes?
- [ ] Can you re-run individual samples?

## Recommended Architecture

### Option A: Inspect AI Foundation (Recommended)

```
matric-eval/
├── pyproject.toml              # Python project (uv/pip)
├── src/
│   └── matric_eval/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point
│       ├── tasks/              # Custom task definitions
│       │   ├── matric_cli/     # CLI-specific tests
│       │   └── matric_memory/  # Memory-specific tests
│       ├── solvers/            # Custom solving strategies
│       ├── scorers/            # Custom scoring logic
│       └── config/             # Model configs, thresholds
│
├── datasets/                   # JSONL test data
│   ├── public/                 # Public benchmarks (symlinks or downloads)
│   └── custom/                 # App-specific tests
│       ├── cli/
│       │   ├── tool_calling.jsonl
│       │   └── agent_scenarios.jsonl
│       └── memory/
│           ├── title_generation.jsonl
│           └── semantic_similarity.jsonl
│
├── bindings/                   # Language integrations
│   ├── typescript/             # npm package for matric-cli
│   │   ├── package.json
│   │   └── src/
│   │       └── index.ts        # Subprocess wrapper
│   └── rust/                   # Crate for matric-memory
│       ├── Cargo.toml
│       └── src/
│           └── lib.rs          # FFI or subprocess wrapper
│
└── docs/
    ├── adding-custom-tests.md
    ├── running-evaluations.md
    └── interpreting-results.md
```

### Why Inspect AI?

1. **Native Ollama support**: `ollama/llama3.2` model syntax works out of box
2. **Agent evaluations**: Multi-step tool use scenarios (needed for CLI)
3. **MCP tool support**: Can test tool calling directly
4. **Modern Python**: Uses `uv`, type hints, clean API
5. **UK government backing**: Active maintenance, safety-focused
6. **100+ pre-built evals**: HumanEval, MBPP, GSM8K, etc. already available

### Option B: lm-eval-harness Foundation (Alternative)

Better if:
- Need maximum benchmark coverage
- Want exact parity with HuggingFace leaderboard
- Less focus on agent/tool evaluation

```bash
# Example usage with Ollama
lm_eval --model local-completions \
    --tasks humaneval,mbpp,gsm8k \
    --model_args model=llama3.2,base_url=http://localhost:11434/v1/completions
```

## Implementation Plan

### Phase 1: Foundation (Week 1-2)

1. **Setup Python project**
   - Use `uv` for dependency management
   - Configure Inspect AI as core framework
   - Verify Ollama integration works

2. **Migrate public benchmarks**
   - Configure existing Inspect AI tasks: HumanEval, MBPP, GSM8K, ARC
   - Add missing: IFEval, LiveCodeBench, DS-1000
   - Test with sample Ollama models

3. **Dataset management**
   - Create download script for public datasets
   - Local caching strategy
   - Reproducible sampling with seeds

### Phase 2: Custom Tests (Week 2-3)

4. **matric-cli custom tests**
   - Tool calling validation
   - Agent scenario evaluation
   - Code analysis tests

5. **matric-memory custom tests**
   - Title generation
   - Semantic similarity
   - Content revision
   - Tag generation

6. **Scoring and reporting**
   - Custom scorers for app-specific metrics
   - JSON/Markdown report generation
   - Config recommendation engine

### Phase 3: Integration (Week 3-4)

7. **TypeScript bindings**
   - npm package wrapping Python subprocess
   - Stream results back to caller
   - Type definitions for results

8. **Rust bindings**
   - Crate wrapping Python subprocess
   - Async result streaming
   - Serde types for results

9. **CI/CD**
   - Smoke test on PR
   - Nightly full evaluation
   - Leaderboard generation

## Evaluation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        matric-eval                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. DISCOVER MODELS                                              │
│     └── Query Ollama for available models                       │
│     └── Filter by size (MAX_MODEL_SIZE_GB)                      │
│                                                                  │
│  2. PUBLIC BENCHMARKS (Tier-based)                              │
│     ├── smoke:  5 per benchmark  (~2 min)                       │
│     ├── quick: 75 per benchmark  (~20 min)                      │
│     └── full:  all problems      (~2+ hours)                    │
│                                                                  │
│  3. RANK & FILTER                                                │
│     └── Top N models per capability                             │
│                                                                  │
│  4. CUSTOM TESTS (app-specific)                                  │
│     ├── matric-cli: tool_calling, agent_scenarios               │
│     └── matric-memory: title, semantic, revision, tags          │
│                                                                  │
│  5. CONFIG RECOMMENDATION                                        │
│     └── Generate model-categories.json                          │
│     └── Map: capability → recommended model                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### D1: Python Core, Language Bindings for Integration

**Decision**: Core evaluation in Python, thin wrappers for TypeScript/Rust

**Rationale**:
- Leverages mature ecosystem
- Avoids duplicating complex evaluation logic
- Bindings are simple subprocess wrappers

### D2: JSONL as Universal Test Format

**Decision**: All custom tests in JSONL format

**Rationale**:
- Compatible with Inspect AI, lm-eval-harness, HELM
- Human-readable and editable
- Easy to version control
- Streaming-friendly

**Example format**:
```json
{"id": "tool-001", "prompt": "...", "expected_tools": ["read_file"], "capability": "tool-calling"}
{"id": "tool-002", "prompt": "...", "expected_tools": ["write_file", "bash"], "capability": "tool-calling"}
```

### D3: Tiered Evaluation with Early Exit

**Decision**: smoke → quick → full, with capability-based filtering

**Rationale**:
- Fast feedback for development
- Full evaluation only when needed
- Top performers get custom tests

### D4: Config Recommendation as First-Class Output

**Decision**: Evaluations produce actionable config files

**Rationale**:
- Close the loop: eval → config → better app behavior
- Reduces manual model selection
- Standardizes across apps

## Migration Path

### From matric-cli

1. Extract `source/eval/` logic into matric-eval Python tasks
2. Convert `scripts/comprehensive-model-eval.ts` to Python CLI
3. Keep `evals/` directory in matric-cli for custom test data
4. Replace eval imports with matric-eval bindings

### From matric-memory

1. Extract `crates/matric-inference/src/eval/` test definitions to JSONL
2. Replace Rust eval runner with matric-eval bindings
3. Keep test data in `evals/datasets/`

## Open Questions

1. **Inspect AI vs lm-eval-harness**: Final decision after prototyping both
2. **Dataset hosting**: Git LFS, CDN, or external mirrors?
3. **Versioning**: How to version test suites for reproducibility?
4. **Multi-GPU**: Support for distributed evaluation?

## Success Criteria

- [ ] Run HumanEval, MBPP, GSM8K against Ollama models
- [ ] Custom matric-cli tool calling tests passing
- [ ] Custom matric-memory title generation tests passing
- [ ] TypeScript bindings work from matric-cli
- [ ] Rust bindings work from matric-memory
- [ ] Config recommendation generates valid model-categories.json
- [ ] CI runs smoke tests on every PR

## References

- [Inspect AI Documentation](https://inspect.aisi.org.uk/)
- [lm-eval-harness GitHub](https://github.com/EleutherAI/lm-evaluation-harness)
- [HELM Stanford](https://crfm.stanford.edu/helm/)
- [Gitea Issue #5](https://git.integrolabs.net/roctinam/devops/issues/5) - Original project proposal
