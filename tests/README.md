# matric-eval test suite

Use the [verification strategy](../docs/testing/strategy.md),
[contributor guide](../docs/testing/contributing.md), and
[profile/skip dispositions](../docs/testing/profiles.md) for the current gates.
For this model-comparison program, every executable command runs on the owned
A100 checkout under [the execution policy](../docs/testing/a100-execution.md).
Local work is editing and static review; do not start a workstation model server.

## Finding and selecting tests

Shared fixtures are in `conftest.py`, factories in `factories.py`, deterministic
and native-adapter cases in `unit/`, runtime probes in `integration/`, and CLI,
checkpoint, release and other component tests also live at this directory's root.
Shared Python/TypeScript wire examples live under `fixtures/results/`.

On A100, choose a relevant focused test first; retain its command, exact source,
profile and JUnit evidence. `make test-unit` selects the `unit` marker while
Gitea smoke selects `tests/unit/` by directory; these are different subsets.
`make ci` runs Ruff lint/format, the mypy baseline ratchet and the full collected
Python suite with an aggregate branch-enabled 80% coverage floor. There are no
independent function, critical-component 100%, mutation or 75% branch gates.
TypeScript and release checks are separate Gitea jobs.

Registered pytest markers are declared in `pyproject.toml`; strict marker/config
validation applies. A skipped runtime/data test does not establish capability.
Preserve node IDs and skip reasons with owner and promotion condition; supplying
a service does not activate an unconditional skip decorator.

## Adding fixtures

Assert independently justified expected behavior and relevant failures. Preserve
legacy golden data; add versioned examples for changed contracts. Use real native
record shapes at adapter boundaries and explicitly scoped mocks for controller
unit tests. Do not call production reducers to generate their own expected result.

Generated code executes only through the configured isolated runner, including
runtime tests. Mocked Docker tests do not qualify actual isolation; real probes
require the documented opt-in profile. A judge's parsing tests likewise do not
prove calibration or live-model validity.

See the [unit plan](../docs/testing/plans/unit.md) and
[integration plan](../docs/testing/plans/integration.md) for traceable fixture
anchors and the limits of checkpoint, provider, package and measurement evidence.
