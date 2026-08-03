# Real-Provider Smoke Validation

The `Real Provider Smoke` workflow is the recurring production validation for
matric-eval. Gitea Actions is authoritative; the GitHub mirror carries the same
fixture and schedule for portability.

## Fixture

| Setting | Value |
|---|---|
| Schedule | Daily at `06:17 UTC` |
| Manual trigger | `workflow_dispatch` |
| Provider | Ollama `0.32.0` service container |
| Model | `smollm2:135m` (CPU, 271 MB) |
| Benchmark | `matric_cli`, smoke tier |
| Credentials | None required |
| Accelerator | CPU; no GPU is requested or assumed |
| Timeout | 20 minutes for the complete job |

The fixed small model validates real network transport, model acquisition,
Inspect AI inference, benchmark loading, scoring, and result persistence. It is
not a quality baseline for the model.

## Artifacts

Every run retains `artifacts/real-provider-smoke`, including:

- `smoke-report.json`: status, trigger, elapsed time, provider version, model
  digest/details, git revision, benchmark protocol, dataset revision, evaluator
  revision, and evaluation summary
- `evaluation.log`: exact command plus captured stdout and stderr
- `results/`: checkpoint state, per-benchmark output, Inspect logs, and summary

Artifact upload uses `if: always()`, so failed and gated runs retain diagnostics.
The smoke runner exits nonzero when the provider is unavailable, the model pull
fails, evaluation times out, or the summary does not contain exactly one
successful model result.

## Gating And Escalation

The Ollama fixture requires no credential and no accelerator. For a
credentialed fixture, invoke the runner with
`--required-credential-env VARIABLE_NAME`. A missing variable writes
`status: gated` and the missing variable name to `smoke-report.json`, then exits
nonzero; it must never be represented as a passing provider validation.

Investigate the first failed or gated scheduled run before retrying. Escalate
after two consecutive failures with the run URLs and retained reports attached
to an infrastructure issue. Provider outages may be rerun manually after
recovery; code or benchmark regressions require a normal pull request.

Run the same fixture locally against an existing Ollama service:

```bash
uv run python scripts/run_real_provider_smoke.py \
  --provider-url http://127.0.0.1:11434 \
  --model smollm2:135m \
  --benchmark matric_cli \
  --output artifacts/real-provider-smoke
```
