# Contributing verification

For the current model-comparison program, execute pytest, lint, formatting,
type checks, builds and runtime fixtures only on the owned A100 checkout under
[the execution policy](a100-execution.md). Local work is editing and static diff
review. Keep the active study checkout and its dependencies unchanged.

Read the [verification strategy](strategy.md), [profiles and skips](profiles.md),
[unit plan](plans/unit.md) and [integration plan](plans/integration.md) before
claiming a capability is covered. These documents supersede the January testing
examples and unsupported numerical thresholds.

## Selecting checks

From a prepared A100 checkout with the documented cache paths:

```bash
uv sync --locked --python 3.11 --extra dev --extra study
uv run pytest tests/unit/test_result_contract.py -ra --junitxml=<evidence>/focused.xml
make ci
```

Use tests relevant to the change; `<evidence>` is a prepared run directory.
`make ci` runs Ruff lint and format checks, the mypy baseline ratchet and aggregate
branch-enabled coverage with an 80% floor. It does not run all Gitea build,
TypeScript, release or live-provider jobs. TypeScript changes additionally use
`npm ci`, `npm run build` and `npm test` from `bindings/typescript` on A100.

`make test-unit` selects `-m unit`; Gitea smoke selects the `tests/unit/` directory;
full coverage uses all collected tests. Record the exact selection. Do not replace
a required full gate with a convenient subset or count skipped tests as passes.
Strict mypy's existing findings are handled by the reviewed baseline; do not
update it to suppress newly introduced errors.

## Writing useful fixtures

Use named fixtures, explicit assumptions and independently justified expected
values. Add negative cases where they test the promised invariant, including
missing grades, partial/cancelled execution, incompatible identities and cleanup
uncertainty. Test the actual native record or subprocess boundary when that is
the claim; a mock only establishes the mocked interaction's behavior.

Keep generated code out of host subprocesses, including test examples. Unit
controller tests mock the isolation API; real probes run only through the
explicit pinned container profile. Judge fixtures test parsing/accounting;
qualification requires separately reviewed human/domain evidence.

Preserve immutable legacy goldens and add new versioned fixtures. Shared
Python/TypeScript examples should round-trip nulls, all metrics, identities and
reasons. Literal hand-calculated expectations are useful; production reducers
must not serve as their own oracle. Multiple assertions can establish one
cross-record invariant.

## Reviewing evidence

Retain exact source/lock/profile and fixture hashes, installed inventory, command
and exit, JUnit/skip records, initial failures and rerun linkage. Diagnose flaky
failures; import caching or external service variation is not a reason to call a
known failure intentional. A skip record needs its reason, affected capability,
owner role and promotion condition from the profile guide.

No per-module 100%, function-coverage, separate 75% branch, mutation or performance
floor is implemented here. New gates require a reviewed profile, bounded fixture
and executable failure condition. Test-count tables and historical pass totals
are not current qualification evidence.

#92–94 retain publication, clean installation and real-consumer ownership.
#95–97 remain deferred under their existing promotion conditions. No new live
credentials or platform pipelines belong in PR CI; #109 owns that separate work.
