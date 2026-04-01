# CLAUDE.md


@AIWG.md

This file provides guidance to Claude Code when working with this codebase.

## Repository Purpose

Consolidated model evaluation framework for the matric ecosystem. Provides standardized benchmarking of LLM models across multiple inference providers (Ollama, vLLM, llama.cpp, OpenRouter, Chutes) using public benchmarks and custom application-specific tests.

## Project Status: Released (v0.1.0)

The project is production-ready with 80%+ test coverage and 1400+ tests passing.

## Key Context

### Why This Project Exists

We had evaluation code duplicated across projects:
- **matric-cli**: TypeScript eval in `source/eval/` with public benchmarks
- **matric-memory**: Rust eval in `crates/matric-inference/` with custom tests

Both solved similar problems independently. This consolidation:
1. Avoids fixing the same issues repeatedly
2. Standardizes evaluation methodology
3. Enables consistent model selection across the ecosystem

### Implementation

**Python core using Inspect AI framework** (UK AI Safety Institute)

Why:
- Native Ollama support (`ollama/llama3.2` syntax)
- OpenAI-compatible API support (vLLM, llama.cpp, OpenRouter, Chutes)
- 100+ pre-built evaluations
- Agent/tool calling evaluation support
- Active maintenance by UK government

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
- livecodebench/ (1,055 competitive programming, release_v6)
- ds1000/ (1,000 data science)
- mtbench/ (80 multi-turn questions)

### Key Issues Solved (Preserved from matric-cli)

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

### Stack

```
Python 3.11+
uv (package management)
Inspect AI >=0.3.203 (evaluation framework)
pytest >=9.0 (testing)
Click >=8.2 (CLI)
Rich >=14.0 (terminal output)
PyYAML (evaluation matrix configs)
```

### Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -q

# Run tests with coverage
uv run pytest tests/ --cov=src/matric_eval --cov-fail-under=80

# Run smoke tests against a model (default: Ollama)
uv run matric-eval run --tier smoke --model llama3.2:3b

# Run with a different provider
uv run matric-eval run --provider vllm --model meta-llama/Llama-3.2-3B --tier smoke
uv run matric-eval run --provider openrouter --api-key $KEY --model anthropic/claude-3.5-sonnet

# Run multi-provider matrix evaluation
uv run matric-eval run --matrix eval-matrix.yaml

# List available providers
uv run matric-eval list-providers --check-availability

# List available benchmarks
uv run matric-eval list-benchmarks

# List available Ollama models
uv run matric-eval list-models

# Generate model recommendations
uv run matric-eval recommend --results-dir ./results

# Validate run completeness
uv run matric-eval validate --results-dir ./results

# Build package
uv build

# Build TypeScript bindings
cd bindings/typescript && npm run build
```

## Architecture Overview

```
matric-eval/
├── src/matric_eval/        # Python core
│   ├── cli.py              # Click CLI (6 commands)
│   ├── config.py           # Configuration and tier definitions
│   ├── datasets.py         # Dataset loading
│   ├── logging.py          # Structured logging
│   ├── parallel.py         # Concurrent execution
│   ├── recommendation.py   # Model recommendations
│   ├── config/             # Pydantic settings
│   ├── core/               # EvaluationEngine (multi-provider)
│   ├── models/             # Model detection (thinking capabilities)
│   ├── providers/          # Provider abstraction layer
│   │   ├── base.py         # Provider protocol and types
│   │   ├── registry.py     # Provider registry
│   │   ├── matrix.py       # Evaluation matrix DSL
│   │   ├── ollama.py       # Ollama provider
│   │   ├── llamacpp.py     # llama.cpp provider
│   │   ├── vllm.py         # vLLM provider
│   │   ├── openrouter.py   # OpenRouter provider
│   │   └── chutes.py       # Chutes provider
│   ├── scorers/            # Scoring (code exec, LLM judge, multidimensional)
│   ├── state/              # Checkpoint/resume manager
│   ├── tasks/              # All benchmark tasks
│   └── utils/              # Helper utilities
├── tests/                  # pytest test suite (1400+ tests)
├── bindings/               # Language integrations
│   └── typescript/         # @matric/eval-client for matric-cli
└── .github/workflows/      # CI/CD pipeline
```

## Evaluation Flow

```
1. DISCOVER → Query provider for available models
2. PUBLIC   → Run HumanEval, MBPP, GSM8K, etc. via Inspect AI
3. RANK     → Filter top N per capability
4. CUSTOM   → Run app-specific tests on top performers
5. CONFIG   → Generate model recommendations

Provider flow:
  CLI → EvaluationEngine → Provider.format_model_id() → Inspect AI eval()
                         → Provider.get_eval_kwargs()  → (base_url, api_key, etc.)
```

## Features

- **9 Benchmarks**: HumanEval, MBPP, GSM8K, ARC, IFEval, DS-1000, LiveCodeBench, MT-Bench, Tool Calling
- **5 Providers**: Ollama, vLLM, llama.cpp, OpenRouter, Chutes
- **Thinking Models**: Auto-detect and evaluate with thinking on/off modes
- **Evaluation Matrix**: YAML-based multi-provider comparison (cartesian/explicit)
- **Tool Calling**: 6-scenario evaluation with correctness scoring
- **LLM-as-Judge**: Multi-turn conversation assessment
- **Checkpoint/Resume**: Fault-tolerant with StateManager
- **Parallel Execution**: Concurrent model evaluation
- **Model Recommendations**: Capability-based selection
- **TypeScript Bindings**: Integration for matric-cli

## Documentation

See [docs/](./docs/README.md) for comprehensive project documentation:

- [Architecture Overview](docs/architecture/overview.md) - System design
- [Vision & Requirements](docs/requirements/vision.md) - Project goals
- [Roadmap](docs/development/roadmap.md) - Implementation timeline
- [Testing Guide](docs/testing/contributing.md) - Development workflow
- [ADRs](docs/architecture/decisions/) - Architectural decisions

## References

- [Inspect AI Docs](https://inspect.aisi.org.uk/)
- [lm-eval-harness](https://github.com/EleutherAI/lm-evaluation-harness)
- [HELM Stanford](https://crfm.stanford.edu/helm/)
