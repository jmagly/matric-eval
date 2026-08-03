# Operational Validation v1

**Status:** PASS

This report validates the scorer and execution contracts required by roadmap Phase 6.
The raw machine-readable evidence is in
[`operational-validation-v1.json`](./operational-validation-v1.json).

## Pinned Matrix

- Matrix: `operational-parity-v1` (`sha256:03691f21320cf893a54cd8863f4e2820db534e70d548e086a4a8a1e288a82777`)
- matric-cli validator: `2ddd9d6958309bae3b890130689851ab7f5d4343`
- matric-memory evaluator: `d9deacee48101cdfc2b37c30ad5ac8591c06ffff`
- Production fixture: `smollm2:135m` on `ollama/ollama:0.32.0`
- Model digest: `9077fe9d2ae1a4a41a868836b56b8163731a8fe16621397028c2c76f838c6907`
- Seed: `42`

## Results

| Contract | Result | Evidence |
| --- | --- | --- |
| HumanEval scorer parity | PASS | 0.0 pp variance; tolerance 5.0 pp |
| MBPP scorer parity | PASS | 0.0 pp variance; tolerance 5.0 pp |
| matric-memory custom scorers | PASS | 100% agreement across 8 title/semantic cases |
| Checkpoint resume | PASS | 0 duplicate completed benchmarks; checkpoint result preserved |
| Parallel equivalence | PASS | 0 result-set differences across 12 tasks |

Measured execution durations on this validation host:

| Mode | Work | Duration |
| --- | ---: | ---: |
| Sequential | 12 units | 0.0608s |
| Parallel (4 threads) | 12 units | 0.0176s |
| Smoke tier | 5 units | 0.0254s |
| Quick tier | 20 units | 0.1017s |

Durations characterize the deterministic validation harness, not model-quality throughput. The
real-provider timing and provider/model metadata are retained by
[Gitea run #51](https://git.integrolabs.net/roctinam/matric-eval/actions/runs/51).

## Reproduce

```bash
uv run python scripts/run_operational_validation.py
uv run pytest tests/test_operational_validation.py tests/unit/test_code_execution.py
```

The command exits nonzero if any tolerance, agreement, resume, or equivalence gate fails.
