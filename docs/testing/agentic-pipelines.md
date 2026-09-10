# AIWG agent-platform evaluation pipelines

## Boundary and ownership

Credentialed or long-running evaluations run through the `Agentic Evaluation
Pipeline`, never pull-request CI. The workflow has only manual, weekly, and
`repository_dispatch` entry points. Repository CI continues to validate the
package without agent-platform or live-model credentials.

The evaluation operator owns runner capacity, provider accounts, quotas, and
incident response. The matric-eval maintainers own the versioned adapter and
result contracts. Provider outages, invalid credentials, quota exhaustion, and
runner loss are infrastructure outcomes; they are not benchmark scores.

## Registry-derived coverage

The pipeline invokes the installed `aiwg help` command and parses its maintained
provider inventory. It records the AIWG version and SHA-256 of the inventory
output. There is no fallback provider list: discovery failure stops the run.

Every discovered provider gets exactly one `agentic_platform` matrix record. An
operator configuration may enable it or disposition it as `unsupported`,
`unavailable`, or `intentionally_skipped` with a machine-readable reason. A new
AIWG provider that has no configuration therefore appears as
`adapter_not_configured`; it cannot silently disappear. Direct endpoints use
separate `direct_endpoint` records even when they exercise the same benchmark and
scenario revision.

Public identifiers, revision metadata, and disposition reasons are bounded to
machine-readable forms so narrative prompts or responses cannot be smuggled into
the sanitized matrix artifact.

## Configuration

The public [example configuration](../../pipelines/agentic-evaluation.json)
contains no commands or credentials. Supply an operator-owned JSON document with
schema `matric-eval.agentic-pipeline/1`. In hosted execution, base64-encode that
document as the `MATRIC_AGENTIC_PIPELINE_CONFIG_B64` secret. Credential values are
separate workflow secrets; configuration lists only their environment-variable
names. The `aiwg.version` field is mandatory and execution fails closed when it
does not exactly match the installed CLI. The hosted workflow pins both Node.js
and AIWG; operator runner images must provide the same configured versions.

Hosted secrets use provider-scoped names such as
`MATRIC_AGENTIC_CODEX_CREDENTIAL` and
`MATRIC_AGENTIC_CLAUDE_CREDENTIAL`; OpenRouter and Chutes use
`MATRIC_DIRECT_OPENROUTER_CREDENTIAL` and
`MATRIC_DIRECT_CHUTES_CREDENTIAL`. The workflow exposes each value only to the
controller step, and the controller copies a value into a child only when that
target names it in `credentials`. Current platform names follow the same
`MATRIC_AGENTIC_<REGISTRY_ID>_CREDENTIAL` convention. Add a workflow secret
mapping when AIWG adds a provider that needs one; until then its matrix row remains
explicitly unsupported or unavailable.

An enabled platform entry has this shape:

```json
{
  "status": "enabled",
  "command": ["codex", "exec", "--json", "{prompt}"],
  "credentials": ["OPENAI_API_KEY"],
  "inherit_environment": [],
  "model": "gpt-5.2-codex",
  "model_revision": "gpt-5.2-codex-2026-08-01",
  "platform_version": "codex-cli-1.2.3",
  "dependency_revision": "runner-image-sha256:...",
  "streaming": "jsonl",
  "estimated_tokens": 2000,
  "estimated_cost_usd": 0.25,
  "result_file": "result.json"
}
```

Commands are argv arrays and never pass through a shell. Supported placeholders
are `{target}`, `{workspace}`, `{prompt}`, `{tier}`, `{scenario_id}`, and
`{benchmark_id}`. Each enabled agent platform receives a clean copy of the pinned
fixture and, by default, runs:

```text
aiwg use <framework> --provider <registry-id> --force
```

before invocation. `deploy_command` may replace that argv array when a platform
requires a qualified setup wrapper. Pin the fixture, AIWG, platform, model,
dependency, and benchmark revisions in the external operator configuration and
runner image.

Enabled targets must declare model, model revision, dependency revision, and
either platform version (agentic mode) or endpoint revision (direct mode). The
public default enumerates Ollama, vLLM, llama.cpp, OpenRouter, and Chutes as
unavailable until an operator configuration supplies an endpoint and pinned
metadata.

`streaming` is either `stdout-stderr` or `jsonl`. In both modes the child writes
continuously to mode-`0600` evidence while the controller watches the deadline
and kill switch. JSONL requires every nonblank stdout line to be a JSON object;
malformed or empty streams are typed infrastructure failures. The common result
remains the final normalized record.

For a quality outcome, the invocation may write `result_file` as:

```json
{
  "outcome": "passed",
  "reason": "scenario_complete",
  "usage": {"tokens": 1520, "cost_usd": 0.14}
}
```

A valid native `failed` outcome is classified as `agent_model_quality`. Missing
or malformed results, nonzero exits, setup failures, timeouts, and cancellation
are classified as infrastructure failures.

## Bounds, cancellation, and evidence

`limits` sets concurrency, per-attempt timeout, infrastructure-only retries, and
run-wide token and cost reservations. Estimated usage is atomically reserved for
every attempt before launch, so a target that would exceed either budget is
skipped. If an earlier attempt already failed, inability to fund its retry remains
an infrastructure failure. In-flight work is bounded by `max_concurrency`.

Create `KILL` in the configured output directory or set
`MATRIC_EVAL_KILL_SWITCH=1` to stop active process groups and skip new work. Each
attempt uses a fresh temporary workspace and process session. The child receives
only `PATH`, locale, an isolated `HOME`, the tier, explicitly named credential
variables, and explicitly allowed inherited variables. Configuration cannot
override isolation-sensitive variables such as `HOME`, `PATH`, `PYTHONPATH`, or
loader/runtime options. Fixtures containing symlinks or special files and output
directories overlapping the fixture are rejected. This is process and evidence
isolation on an operator-controlled runner, not an operating-system sandbox.

Stdout and stderr are redacted while streaming into mode-`0600` files below the
mode-`0700` private evidence directory. Configured credential and inherited values
plus common bearer/API-key forms never land in those logs. The public
`matrix-result.json` contains hashes, timing, normalized
status, failure class, revisions, limits, and coverage—not prompts, responses, or
credential values. Keep private artifacts only where platform policy permits;
the hosted workflow publishes the sanitized public result. The workflow fails if
registry coverage is incomplete or any executed target ends `failed`; explicit
`unsupported`, `unavailable`, and `intentionally_skipped` dispositions remain
successful coverage records.

## Tiers and operations

- `smoke`: one small scenario for enabled adapters; use for initial credential and
  invocation qualification.
- `conformance`: adapter setup, streaming output, cancellation, timeout, result
  parsing, and error-classification scenarios.
- `full`: the governed scenario bundle after smoke and conformance are green.

The checked-in hosted runner uses Linux, Python 3.11, Node.js 24.12.0, AIWG
2026.9.6, the locked Python dependency graph, writable temporary storage, and
network reachability to each enabled service. Custom runners must also install
every configured platform executable and provide enough private evidence space
for the bounded run. The workflow runs Mondays at 07:43 UTC; maintainers may also
start it manually or send the `matric-eval-agentic` repository-dispatch event.

On outage or invalid credentials, retain the typed result, correct the external
secret/configuration, and rerun with a fresh output directory. On quota exhaustion,
lower concurrency or budgets; do not relabel the attempt as model quality. On a
suspected secret leak, activate the kill switch, revoke the credential, restrict
artifact access, and follow the incident-response runbook before rerunning.
