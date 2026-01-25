# matric-eval

Consolidated model evaluation framework for the matric ecosystem.

## Status

✅ **Released** - v0.1.0

## Purpose

Standardized benchmarking of Ollama models using:
- **Public benchmarks**: HumanEval, MBPP, GSM8K, ARC, IFEval, LiveCodeBench, DS-1000, MT-Bench
- **Custom tests**: Application-specific evaluations for matric-cli and matric-memory
- **Tool calling**: 6-scenario evaluation with correctness scoring
- **LLM-as-Judge**: Multi-turn conversation and reasoning assessment

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
# Smoke test (fast validation)
matric-eval run --tier smoke --model llama3.2:3b

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
| `run` | Run model evaluation with tier selection |
| `list-benchmarks` | List available benchmarks with descriptions |
| `list-models` | List available Ollama models |
| `recommend` | Generate model recommendations from results |
| `validate` | Check run completeness and identify gaps |

## Evaluation Tiers

| Tier | Tests per Benchmark | Duration | Use Case |
|------|---------------------|----------|----------|
| smoke | 5 | ~2 min | Quick validation |
| quick | 75 | ~20 min | Statistical sampling |
| full | all | ~2+ hours | Complete evaluation |
| custom | varies | varies | App-specific tests |

## Benchmarks

| Benchmark | Category | Tests | Description |
|-----------|----------|-------|-------------|
| HumanEval | Code Generation | 164 | Function completion |
| MBPP | Code Generation | 974 | Python problems |
| GSM8K | Math Reasoning | 1,319 | Grade school math |
| ARC | Reasoning | 1,172 | Science questions |
| IFEval | Instruction Following | 541 | Constraint checking |
| LiveCodeBench | Competitive Programming | 880 | Contest problems |
| DS-1000 | Data Science | 1,000 | Pandas/NumPy tasks |
| MT-Bench | Multi-turn | 80 | Conversation quality |
| Tool Calling | Agentic | 6 | Function invocation |

## Architecture

```
Application → matric-eval

1. DISCOVER → Query Ollama for models
2. PUBLIC   → Run standard benchmarks
3. RANK     → Filter top performers
4. CUSTOM   → Run app-specific tests
5. CONFIG   → Generate recommendations
```

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

- **Checkpoint/Resume**: Fault-tolerant evaluation with automatic recovery
- **Parallel Execution**: Concurrent model evaluation
- **Structured Logging**: JSON logs for observability
- **Model Recommendations**: Capability-based model selection
- **85% Test Coverage**: Comprehensive test suite (1106 tests)

## Related Projects

- [matric-cli](https://git.integrolabs.net/roctinam/matric-cli) - AI CLI assistant
- [matric-memory](https://git.integrolabs.net/roctinam/matric-memory) - Knowledge management

## Documentation

- [CLAUDE.md](./CLAUDE.md) - AI assistant context
- [.aiwg/](./aiwg/) - SDLC artifacts and documentation

## License

MIT
