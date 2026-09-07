# Integration and runtime test plan

This plan replaces January's hypothetical Compose setup, alternate CI pipelines,
universal endpoint coverage and per-problem recovery assertions. See the
[implemented gate map](../strategy.md) and [finite profiles](../profiles.md).

## Distinct integration scopes

| Scope | Current anchors | Acceptance boundary |
| --- | --- | --- |
| Deterministic component integration | `tests/test_checkpoint_resume.py`, `tests/test_cli_checkpoint.py`, `tests/unit/test_engine_accounting.py`, `scripts/run_operational_validation.py` | Native status, null/scored distinctions and benchmark checkpoint behavior follow named fixtures. A mock evaluation or operational command is not a live model run. |
| Python/TypeScript wire | Shared `tests/fixtures/results/`, TypeScript `src/test/`, Gitea build/release jobs | Exact record/null/schema/identity preservation and subprocess fixture behavior. #125 owns remaining migration conformance; #94 owns actual matric-cli adoption. Rust remains #96 deferred. |
| Clean package consumers | `scripts/validate_release_candidate.py`, Gitea release.yml | Exact wheel/sdist on Linux CPython 3.11–3.14 and blank npm tarball consumer. Provider registration is distinct from live inference. Post-publication registry installs remain #93. |
| Live Ollama transport | `tests/integration/test_ollama.py`; separate recurring real-provider-smoke workflow | Only executed named endpoints/model fixture qualify. Unavailable or unconditionally skipped cases remain unqualified; no live model credentials are required by PR CI. |
| Generated Python runtime | `tests/integration/test_isolated_execution_runtime.py` with `MATRIC_EVAL_TEST_ISOLATION=1` and explicit pinned runtime configuration | Controlled no-network/no-host-mount/resource/output/timeout/cancellation probes with native start and cleanup evidence. Read the [isolated profile](../../development/isolated-code-execution.md) before invoking. A Docker binary discovery or mock does not qualify isolation. |
| External benchmark/agent runtime | Declared per-benchmark checkout, image and canary; #109 platform inventory/pipelines | Explicit runtime identities, safe replay declaration, bounded execution, native evidence and access controls. Optional package installation alone is insufficient. |
| Model comparison | Frozen study protocol and [A100 attestation](../a100-execution.md) | Matched task manifest, prompts/scorers, budgets, environment, lease and declared estimand. Code/coverage/transport health is not measurement validity. |

## Recovery boundary

The generic engine persists completed benchmark results. Incomplete or failed
benchmarks rerun; a saved Inspect sample does not establish per-problem resume.
#124 owns a provenance-bound observation journal, idempotent commit/recovery and
safe external replay. Its fixtures must prove crash-before/after-commit,
lost acknowledgments, conflicting writers and changed-fingerprint refusal within
the declared filesystem boundary before those guarantees can be claimed.
Legacy checkpoints stay readable without invented per-sample provenance.

Existing state/operational tests do not prove every disk-full, zombie, concurrent,
model-crash or signal scenario, universal zero data loss, or recovery under five
seconds. New recovery claims need bounded fault fixtures, independent expected
outcomes and retained receipts. Never change an active study checkout to perform
fault injection.

## A100-only validation sequence

Prepare an isolated checkout and evidence directory; record source, lock,
interpreter, installed inventory and cache/storage status before dependency sync.
Run the deterministic gates, then only the selected explicit runtime profile.
Do not activate all live tests by assuming a marker implies safe configuration.
No model loading occurs without the study's lease/preflight; the bounded
`isolated-python` probe suite requires no model or GPU.

For an external runner canary, fix task IDs, runtime and resource budgets before
execution. Retain source/image/task hashes, command/exit, raw native records,
cleanup/cancellation evidence and all initial failures. A failed or skipped
canary cannot promote the full model matrix. Record every skipped/deselected
capability using the [skip disposition format](../profiles.md).

Gitea's recurring CPU Ollama smoke remains separate from PR package gates and
A100 study qualification. Additional credentialed/manual/scheduled/API platform
pipelines remain #109's responsibility; this document does not implement them.
