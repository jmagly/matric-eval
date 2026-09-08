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
