# matric-eval

Consolidated model evaluation framework for the matric ecosystem.

## Status

v0.1.0 - Production-ready with 1400+ tests passing.

## Purpose

Standardized benchmarking of LLM models across multiple inference providers:
- **Public benchmarks**: HumanEval, MBPP, GSM8K, ARC, IFEval, LiveCodeBench, DS-1000, MMLU, MT-Bench
- **Custom tests**: Application-specific evaluations for matric-cli and matric-memory
- **Tool calling**: 6-scenario evaluation with correctness scoring
- **LLM-as-Judge**: Multi-turn conversation and reasoning assessment
- **Multi-provider**: Evaluate across Ollama, vLLM, llama.cpp, OpenRouter, and Chutes
- **Thinking models**: Extended reasoning support with thinking-on/off modes

## Installation

```bash
# From Gitea PyPI registry
pip install matric-eval --index-url https://git.integrolabs.net/api/packages/roctinam/pypi/simple/

# Or install from source
git clone https://git.integrolabs.net/roctinam/matric-eval.git
cd matric-eval
uv sync
```

## Quick Start

```bash
# Smoke test on a specific model (defaults to Ollama)
matric-eval run --tier smoke --model llama3.2:3b

# Use a different provider
matric-eval run --provider vllm --model meta-llama/Llama-3.2-3B --tier smoke
matric-eval run --provider openrouter --api-key $OPENROUTER_API_KEY --model anthropic/claude-3.5-sonnet

# Multi-provider matrix evaluation
matric-eval run --matrix eval-matrix.yaml

# List available providers and their status
matric-eval list-providers --check-availability

# List available benchmarks
matric-eval list-benchmarks

# List available Ollama models
matric-eval list-models

# Get model recommendations from results
matric-eval recommend --results-dir ./results

# Validate run completeness
matric-eval validate --results-dir ./results
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `run` | Run model evaluation with tier and provider selection |
| `list-benchmarks` | List available benchmarks with descriptions |
| `list-models` | List available Ollama models |
| `list-providers` | List available inference providers |
| `recommend` | Generate model recommendations from results |
| `validate` | Check run completeness and identify gaps |

## Inference Providers

| Provider | Type | CLI Flag | Description |
|----------|------|----------|-------------|
| Ollama | Local | `--provider ollama` | Default. Local Ollama instance |
| llama.cpp | Local | `--provider llama-cpp` | Direct GGUF model serving |
| vLLM | Local/Cloud | `--provider vllm` | High-throughput GPU inference |
| OpenRouter | Cloud | `--provider openrouter` | 100+ models via unified API |
| Chutes | Cloud | `--provider chutes` | Serverless GPU inference |

## Evaluation Tiers

| Tier | Tests per Benchmark | Duration | Use Case |
|------|---------------------|----------|----------|
| smoke | 5 | ~2 min | Quick validation |
| quick | 75 | ~20 min | Statistical sampling |
| full | all | ~2+ hours | Complete evaluation |

## Benchmarks

| Benchmark | Category | Tests | Description |
|-----------|----------|-------|-------------|
| HumanEval | Code Generation | 164 | Function completion |
| MBPP | Code Generation | 974 | Python problems |
| GSM8K | Math Reasoning | 1,319 | Grade school math |
| ARC | Reasoning | 1,172 | Science questions |
| IFEval | Instruction Following | 541 | Constraint checking |
| LiveCodeBench | Competitive Programming | 1,055 | Contest problems (release_v6) |
| DS-1000 | Data Science | 1,000 | Pandas/NumPy tasks |
| MT-Bench | Multi-turn | 80 | Conversation quality |
| Tool Calling | Agentic | 6 | Function invocation |

## Architecture

```
Application -> matric-eval

1. DISCOVER  -> Query provider for available models
2. PUBLIC    -> Run standard benchmarks via Inspect AI
3. RANK      -> Filter top performers
4. CUSTOM    -> Run app-specific tests
5. CONFIG    -> Generate recommendations

Provider Abstraction:
  CLI -> EvaluationEngine -> Provider -> Inspect AI -> Backend
                               |
                    +----------+----------+
                    |          |          |
                  Ollama    vLLM    OpenRouter  ...
```

## Evaluation Matrix

For multi-provider comparison, create a YAML matrix config:

```yaml
evaluation:
  models:
    - llama3.2:3b
    - mistral:7b
  providers:
    - ollama
    - vllm
  benchmarks:
    - humaneval
    - gsm8k
  tier: smoke
  matrix:
    mode: cartesian
  exclude:
    - model: mistral:7b
      provider: vllm
```

Then run: `matric-eval run --matrix eval-matrix.yaml`

## TypeScript Bindings

For matric-cli integration:

```bash
npm install @matric/eval-client --registry https://git.integrolabs.net/api/packages/roctinam/npm/
```

```typescript
import { createClient } from '@matric/eval-client';

const client = createClient();
const results = await client.run({ tier: 'smoke', models: ['llama3.2:3b'] });
const recommendations = await client.recommend({ resultsDir: './results' });
```

## Features

- **Multi-Provider**: Evaluate across Ollama, vLLM, llama.cpp, OpenRouter, Chutes
- **Thinking Models**: Extended reasoning support with auto-detection
- **Checkpoint/Resume**: Fault-tolerant evaluation with automatic recovery
- **Evaluation Matrix**: YAML-based multi-provider comparison runs
- **Parallel Execution**: Concurrent model evaluation
- **Structured Logging**: JSON logs for observability
- **Model Recommendations**: Capability-based model selection
- **1400+ Tests**: Comprehensive test suite with 80%+ coverage

## Documentation

- [docs/](./docs/README.md) - Full project documentation
- [Architecture](./docs/architecture/overview.md) - System design
- [Requirements](./docs/requirements/vision.md) - Vision and use cases
- [Testing](./docs/testing/contributing.md) - Development workflow
- [CLAUDE.md](./CLAUDE.md) - AI assistant context

## License

MIT
