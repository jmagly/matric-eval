# matric-eval

Consolidated model evaluation framework for the matric ecosystem.

## Status

The source package version is 0.2.0. Published package availability and immutable
release evidence are recorded in
[Gitea Releases](https://git.integrolabs.net/roctinam/matric-eval/releases); see
the [supported-capability roadmap](./docs/development/roadmap.md) for release
gates and deliberately deferred work.

Registry snapshot on 2026-08-03: 39 benchmarks (24 stable, 13 gated, one
experimental, one unavailable). Generate the current inventory with
`matric-eval list-benchmarks` rather than relying on this dated count.

## Purpose

Standardized benchmarking of LLM models across multiple inference providers:
- **Public benchmarks**: Core support includes HumanEval, MBPP, GSM8K, ARC,
  IFEval, LiveCodeBench, DS-1000, MMLU, and MT-Bench; the registry also covers
  successor, agentic, security, multimodal, repository, and long-context suites
- **Custom tests**: Application-specific evaluations for matric-cli and matric-memory
- **Tool calling**: 6-scenario evaluation with correctness scoring
- **LLM-as-Judge**: Multi-turn conversation and reasoning assessment
- **Multi-provider**: Evaluate across Ollama, vLLM, llama.cpp, OpenRouter, and Chutes
- **Thinking models**: Extended reasoning support with thinking-on/off modes

`stable` describes a tested adapter and pinned protocol. It does not claim that
every benchmark has been production-run against every provider. Retained
real-provider evidence currently covers the Ollama smoke path.

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

# Validate registry metadata and pinned protocol health
matric-eval audit-benchmarks --fail-on-error

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
| `audit-benchmarks` | Audit benchmark revisions, protocols, and lifecycle state |
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

| Tier | Default selection | Use Case |
|------|-------------------|----------|
| smoke | 5 samples | Fast contract and provider checks |
| quick | 75 samples | Representative evaluation |
| full | all samples | Complete protocol execution |

Benchmark registry metadata can override these defaults. Duration depends on the
selected benchmarks, model, provider, context length, and external runner; use
retained run evidence for capacity planning.

## Benchmarks

The registry is grouped by lifecycle state:

| State | Count on 2026-08-03 | Meaning |
|---|---:|---|
| stable | 24 | Supported adapter with pinned protocol and automated tests |
| gated | 13 | Requires documented data, runner, hardware, or licensing prerequisites |
| experimental | 1 | InjecAgent research integration; compatibility may change |
| unavailable | 1 | QwenWebBench retained as an explicit no-go decision |

Core stable tasks include HumanEval, MBPP, GSM8K, ARC, IFEval,
LiveCodeBench, DS-1000, MMLU, MT-Bench, Tool Calling, matric-cli, and
matric-memory. The registry also includes the completed Wave 1-3 successor,
agentic, security, multimodal, repository, long-context, and memory work.

Run `matric-eval list-benchmarks` for names, current status, descriptions, and
sample counts. See the [protocol records](./docs/README.md#benchmark-protocols)
for pinned revisions and gate decisions.

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

The TypeScript client source version matches the Python package. Clean 0.2.0
package validation and actual matric-cli adoption are tracked by
[#93](https://git.integrolabs.net/roctinam/matric-eval/issues/93) and
[#94](https://git.integrolabs.net/roctinam/matric-eval/issues/94); source-tree
tests alone do not establish the consumer migration contract.

```bash
npm install @matric/eval-client --registry https://git.integrolabs.net/api/packages/roctinam/npm/
```

```typescript
import { createClient } from '@matric/eval-client';

const client = createClient();
const results = await client.run({ tier: 'smoke', models: ['llama3.2:3b'] });
const recommendations = await client.recommend({ resultsDir: './results' });
```

## External Datasets

Drop any git repo or directory into `datasets/` and it's auto-discovered as a benchmark:

```bash
# Clone a dataset repo
git clone https://example.com/my-eval-data.git datasets/my-eval

# Or add as submodule
git submodule add https://example.com/my-eval-data.git datasets/my-eval

# It just works
matric-eval list-benchmarks          # shows "my-eval"
matric-eval run --benchmark my-eval --tier smoke --model llama3.2:3b
```

Zero config for JSONL files with `input`/`target` fields. For more control, add a `dataset.yaml`:

```yaml
name: my-benchmark
description: Domain-specific evaluation
scorer: match
tiers: { smoke: 5, quick: 50, full: 0 }
field_mapping: { input: question, target: answer }
```

Configure dataset root: `EVAL_DATASETS_DIR=/path/to/datasets`

## Features

- **Multi-Provider**: Evaluate across Ollama, vLLM, llama.cpp, OpenRouter, Chutes
- **External Datasets**: Auto-discover datasets from git clones/submodules with zero config
- **Thinking Models**: Extended reasoning support with auto-detection
- **Checkpoint/Resume**: Fault-tolerant evaluation with automatic recovery
- **Evaluation Matrix**: YAML-based multi-provider comparison runs
- **Parallel Execution**: Concurrent model evaluation
- **Structured Logging**: JSON logs for observability
- **Model Recommendations**: Capability-based model selection
- **Authoritative CI**: Gitea Actions enforces lint, format, type, test/coverage,
  smoke, and package-build gates

Test totals are generated evidence, not a permanent feature count. On
2026-08-03, `pytest --collect-only` collected 2,307 tests; authoritative PR run
#52 completed 2,296 with 11 skips and 80.95% coverage.

## Documentation

- [docs/](./docs/README.md) - Full project documentation
- [Architecture](./docs/architecture/overview.md) - System design
- [Requirements](./docs/requirements/vision.md) - Vision and use cases
- [Testing](./docs/testing/contributing.md) - Development workflow
- [Supported-capability roadmap](./docs/development/roadmap.md) - Current support, gates, and delivery sequence
- [Operational validation](./docs/validation/operational-validation-v1.md) - Pinned scorer and reliability evidence
- [CLAUDE.md](./CLAUDE.md) - AI assistant context

## License

MIT
