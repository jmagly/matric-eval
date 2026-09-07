# Unit and deterministic contract test plan

This plan supersedes January's illustrative modules, uninstalled test tools and
unimplemented critical/mutation coverage gates. The [verification strategy](../strategy.md)
and [profile/skip disposition](../profiles.md) are authoritative for scope.

## Implemented surface

Use real source/test paths rather than the old examples `state/checkpoint.py`,
`state/recovery.py`, or a hypothetical `critical` marker:

| Area | Existing fixture anchors | Review expectation |
| --- | --- | --- |
| State and engine | `tests/unit/test_state_manager.py`, `test_engine_accounting.py`, `tests/test_checkpoint_resume.py` | Completed benchmark reuse requires supporting evidence; partial/failed work does not silently become complete. Generic checkpoints do not provide per-problem continuation. |
| Observations and adapters | `tests/unit/test_result_contract.py`, `test_result_study_adapter.py`, `test_inspect_result_adapter.py` | Preserve typed identities, nulls, reasons, sample counts and legacy study values; malformed records reject. |
| Named reductions and comparison | `tests/unit/test_result_reducers.py` and shared result fixtures | Independently calculated values; exact declared metric selection; no implicit cross-scale average; incompatible comparison scope rejects. |
| Repeated trials | `tests/unit/test_trial_results.py`, `test_trial_execution.py` | Hand-calculated disjoint/missing/retry cases, stable task alignment, explicit generation evidence and descriptive-only limitations. |
| Generated-code controller | `tests/unit/test_isolated_execution.py` | Mock Docker control calls; never execute generated code on the host. Unit tests cover policy rejection and status accounting; real isolation remains a separate profile. |
| Judge and other scorers | `tests/unit/test_llm_judge.py`, `test_judges.py` and scorer-specific files | Malformed/abstaining judgments stay unscored; parsing correctness is not live judge qualification. |
| CLI/release/consumer | `tests/test_cli.py`, `test_cli_checkpoint.py`, `test_release_contract.py`, TypeScript `src/test/` | Verify user-visible outputs/errors and actual wire boundaries within each fixture's scope. |

Some deterministic tests live outside `tests/unit/` and some tests lack the
`unit` marker. Directory selection, `-m unit`, and the full collected suite are
different selections; none should silently substitute for another gate.

## Execution and evidence

All commands below run only in the owned A100 checkout for this program:

```bash
uv sync --locked --python 3.11 --extra dev --extra study
uv run pytest tests/unit/test_result_contract.py tests/unit/test_trial_results.py \
  -ra --junitxml=/srv/matric-eval/results/<run>/focused-junit.xml
make ci
```

Replace `<run>` with a prepared evidence directory. Parent/CI validation chooses
checks appropriate to the actual change; the example focused command is not a
universal gate. `make ci` runs Ruff lint/format, the mypy baseline ratchet and
aggregate branch-enabled coverage with an 80% floor. There is no separate
per-file 100%, function, 75% branch, mutation or coverage-regression floor.
`make type-check-strict` reports all strict findings; baseline updates require
review and cannot conceal regressions.

Tests should state an independently justified expected result, exercise relevant
failure paths, and preserve evidence of the original failure before a fix/rerun.
Use real native Inspect record shapes at adapter boundaries, mock network/runtime
control only where the test is explicitly about controller behavior, and retain
shared Python/TypeScript golden fixtures. Do not derive expected values by calling
the production reducer being tested. Multiple assertions are appropriate when
they establish one complete record invariant.

Hypothesis, mutation testing, pytest-xdist and benchmark plugins are not part of
the current declared dev extra. Their old snippets were proposals. Promotion
requires reviewed dependencies, bounded fixtures, a measured baseline and an
implemented failure condition; no additional numerical threshold is adopted here.

Trace critical fixtures to the strategy's requirement table. Retain source/lock
and fixture hashes, package inventory, command exits, JUnit and skip dispositions;
a green mock or skipped case does not qualify the corresponding real capability.
