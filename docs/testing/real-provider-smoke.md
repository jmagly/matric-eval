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
| Gitea runner | Exact `teroknor`, `docker`, and `node-20` labels |

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
Gitea uses the immutable v4 artifact backend with a 14-day retention period and
fails the upload step when the diagnostic directory is absent. The runner also
prints one bounded `real-provider-smoke-diagnostic` JSON object to the step log,
so provider readiness, model pull, evaluation, and summary failures remain
actionable even when artifact storage itself is unavailable. The object excludes
provider response bodies, credentials, and captured model output.
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

The Gitea workflow intentionally targets Teroknor. Shared `ubuntu-latest` routing
previously selected runners with different service-container DNS behavior;
Teroknor is the verified CPU/Docker/Node service-container fixture. GitHub keeps
its native `ubuntu-latest` runner and published localhost service port.

For the current model-comparison program, run this fixture only on the owned
A100 checkout against an attested Ollama service, following the
[A100 policy](a100-execution.md). The command is not permission to launch a
workstation model server:

```bash
uv run python scripts/run_real_provider_smoke.py \
  --provider-url http://127.0.0.1:11434 \
  --model smollm2:135m \
  --benchmark matric_cli \
  --output artifacts/real-provider-smoke
```
