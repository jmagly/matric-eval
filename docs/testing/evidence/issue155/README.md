# Controlled A100 preflight qualification

`controlled-preflight.json` records the actual staged Tau profile on Basilisk,
using the frozen pilot manifest and domain-grouped input files without changes.
The runner environment was the existing v3 Python 3.12.3 environment with the
separate pinned `pydantic-settings==2.12.0` support directory on PYTHONPATH; the
original environment was not modified. Source file hashes identify the tested
code overlay; this is not an assertion that the copied checkout's Git HEAD
contained those overlay bytes.

Ten checks ran in 19.98 seconds. The immutable input check, actual dependency
imports, official task loading, banking sandbox execution, and all three official
controlled-endpoint launcher repetitions passed. The three repetitions have
distinct evidence IDs, completion timestamps and native receipt hashes. No task
simulation or scoring ran.

Admission correctly failed: the actual v3 Tau checkout's changed paths do not
match the existing pinned patch contract, and both auxiliary checks intentionally
imported a nonexistent fixture dependency. The acquisition marker was asserted
absent, with zero target launch commands and one refused target attempt. This
shows independent diagnostics continue after a failure and the target boundary
remains closed. It does not qualify the v3 patch or a live auxiliary endpoint.

The separate A100 unit suite exercises 14 preflight cases plus 67 Tau regressions,
including freshness/reuse invalidation, failed receipt preservation, bounded
stdout/stderr/timeout handling, actual public CLI dispatch and input hash tampering.
Live broker transport qualification is reported separately by the actual client
profile; it must not be inferred from this deliberately failing fixture.

## Full supported admission

`supported-preflight.json` records the subsequent complete supported plan with
`/srv/matric-eval/benchmarks/tau2-qwen38-context-guard`, whose patch matches the
pinned contract. All ten checks passed in 23.67 seconds, including three separate
actual Tau controlled-endpoint repetitions and actual simulator and embedding
client checks through the public broker. The client snapshot is commit `807a5c2`;
all executed source hashes are retained. The embedder measured the configured
dimensions and both probes retained their own broker correlation. Served execution
digest binding remains unverified, and semantic calibration was not performed.

Fresh admission validation passed immediately afterward. No target model was
acquired or loaded, and no task was scored. This receipt qualifies the pre-target
admission boundary in that observed service context; target-resident qualification
and lifecycle ownership remain separate gates.

## Final dependency-bound qualification

`supported-preflight-final.json` supersedes the earlier successful receipt for
release review. It qualifies preflight source `398e156` with client source
`685f3e5` and the broker/runtime-bound simulator and embedder profiles. All ten
checks passed in 36.35 seconds, including three independent official Tau launcher
repetitions. Immediate admission revalidation also passed after rehashing the
external benchmark source/data trees, patch blob, Git state and the configured
interpreter's dependency metadata. Both live probes verified the observed broker
runtime identity and retained their own request correlation; execution-digest
binding remains explicitly unverified. No target model was loaded or task scored.

The six additional mutation regressions cover patch bytes, external source edits,
new source files, task data, runtime METADATA versions and runtime RECORD changes.
The final focused A100 suite passed 87 tests (20 preflight plus 67 Tau), with Ruff
and strict module mypy clean. The original failure fixture still demonstrates
zero target acquisitions after independent blockers; no frozen inputs or original
benchmark environments were altered.
