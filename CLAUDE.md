# CLAUDE.md

This file provides guidance to Claude Code when working with this codebase.

## Repository Purpose

Consolidated model evaluation framework for the matric ecosystem. Provides standardized benchmarking of Ollama models using public benchmarks (HumanEval, MBPP, GSM8K, etc.) and custom application-specific tests.

## Project Status: Planning Phase

See `PLANNING.md` for architectural decisions and implementation plan.

## Key Context

### Why This Project Exists

We had evaluation code duplicated across projects:
- **matric-cli**: TypeScript eval in `source/eval/` with public benchmarks
- **matric-memory**: Rust eval in `crates/matric-inference/` with custom tests

Both solved similar problems independently. This consolidation will:
1. Avoid fixing the same issues repeatedly
2. Standardize evaluation methodology
3. Enable consistent model selection across the ecosystem

### Recommended Approach

**Python core using Inspect AI framework** (UK AI Safety Institute)

Why:
- Native Ollama support (`ollama/llama3.2` syntax)
- 100+ pre-built evaluations
- Agent/tool calling evaluation support
- Active maintenance by UK government

Alternative: lm-eval-harness (EleutherAI) - industry standard, powers HuggingFace leaderboard

### Related Repositories

| Repo | Path | Relevant Code |
|------|------|---------------|
| matric-cli | `/home/roctinam/dev/matric-cli` | `source/eval/`, `scripts/comprehensive-model-eval.ts` |
| matric-memory | `/home/roctinam/dev/matric-memory` | `crates/matric-inference/src/bin/eval.rs`, `evals/` |

### Public Benchmark Data

Located at `/home/roctinam/data/evals/`:
- humaneval/ (164 code generation problems)
- mbpp/ (974 Python problems)
- gsm8k/ (1,319 math problems)
- arc/ (1,172 reasoning problems)
- ifeval/ (541 instruction following)
- livecodebench/ (880 competitive programming)
- ds1000/ (1,000 data science)
- mtbench/ (80 multi-turn questions)

### Key Issues Solved in matric-cli (Preserve These)

1. **MBPP function names**: Extract from test assertions, include in prompt
2. **Code extraction**: Handle markdown fences, language tags
3. **Safe execution**: Sandbox with timeout, memory limits, no network
4. **Artifact preservation**: Include generatedCode in all validation paths
5. **Reproducible sampling**: Seeded random for consistent subsets
6. **Model size filtering**: Skip models > MAX_MODEL_SIZE_GB

## MCP Servers Available

This session has access to:
- **Gitea**: Issue tracking, repository management
- **Hound**: Code search across repositories
- **matric-memory**: Note storage and retrieval
- **IT Assets**: CMDB queries

## Development Commands

TBD - Project is in planning phase.

### Proposed Stack

```
Python 3.11+
uv (package management)
Inspect AI (evaluation framework)
pytest (testing)
```

### Proposed Commands

```bash
# Install dependencies
uv sync

# Run smoke tests against a model
matric-eval --tier smoke --model llama3.2:3b

# Run quick evaluation
matric-eval --tier quick --model llama3.2:3b

# Run full evaluation with custom tests
matric-eval --tier full --app matric-cli

# Generate config recommendations
matric-eval --recommend --output model-categories.json
```

## Architecture Overview

```
matric-eval/
├── src/matric_eval/        # Python core
│   ├── tasks/              # Benchmark task definitions
│   ├── solvers/            # Custom solving strategies
│   ├── scorers/            # Scoring and validation
│   └── config/             # Model configs
├── datasets/               # JSONL test data
│   ├── public/             # Public benchmarks
│   └── custom/             # App-specific tests
└── bindings/               # Language integrations
    ├── typescript/         # For matric-cli
    └── rust/               # For matric-memory
```

## Evaluation Flow

```
1. DISCOVER → Query Ollama for available models
2. PUBLIC   → Run HumanEval, MBPP, GSM8K, etc.
3. RANK     → Filter top N per capability
4. CUSTOM   → Run app-specific tests on top performers
5. CONFIG   → Generate model recommendations
```

## Next Steps

1. Prototype Inspect AI integration with Ollama
2. Migrate one benchmark (HumanEval) as proof of concept
3. Add one custom test suite (tool calling)
4. Create TypeScript binding for matric-cli
5. CI/CD setup with smoke tests

## References

- [Inspect AI Docs](https://inspect.aisi.org.uk/)
- [lm-eval-harness](https://github.com/EleutherAI/lm-evaluation-harness)
- [HELM Stanford](https://crfm.stanford.edu/helm/)
- [Gitea Issue #5](https://git.integrolabs.net/roctinam/devops/issues/5)
- [PLANNING.md](./PLANNING.md)
