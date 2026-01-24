# matric-eval

Consolidated model evaluation framework for the matric ecosystem.

## Purpose

Standardized benchmarking of Ollama models using:
- **Public benchmarks**: HumanEval, MBPP, GSM8K, ARC, IFEval, LiveCodeBench, DS-1000, MT-Bench
- **Custom tests**: Application-specific evaluations for matric-cli and matric-memory

## Status

🚧 **Planning Phase** - See [PLANNING.md](./PLANNING.md) for architectural decisions.

## Quick Start

```bash
# Coming soon
matric-eval --tier smoke --model llama3.2:3b
```

## Evaluation Tiers

| Tier | Tests per Benchmark | Duration | Use Case |
|------|---------------------|----------|----------|
| smoke | 5 | ~2 min | Quick validation |
| quick | 75 | ~20 min | Statistical sampling |
| full | all | ~2+ hours | Complete evaluation |
| custom | varies | varies | App-specific tests |

## Architecture

```
Application → matric-eval

1. DISCOVER → Query Ollama for models
2. PUBLIC   → Run standard benchmarks
3. RANK     → Filter top performers
4. CUSTOM   → Run app-specific tests
5. CONFIG   → Generate recommendations
```

## Related Projects

- [matric-cli](https://git.integrolabs.net/roctinam/matric-cli) - AI CLI assistant
- [matric-memory](https://git.integrolabs.net/roctinam/matric-memory) - Knowledge management

## Documentation

- [PLANNING.md](./PLANNING.md) - Architecture and implementation plan
- [CLAUDE.md](./CLAUDE.md) - AI assistant context

## License

MIT
