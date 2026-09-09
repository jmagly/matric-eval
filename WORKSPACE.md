# WORKSPACE.md
<!-- aiwg-managed -->
<!-- Generated structure by AIWG; operator content is protected by markers. -->

<!-- AIWG:workspace-context:start -->

## AIWG Context Graph

This file is the canonical provider-neutral home for project and operator context.
Provider startup files are generated adapters: they direct the harness here first,
then to AIWG.md for framework discovery and routing.

### Precedence

1. Provider, system, and organization instructions retain their native authority.
2. Root WORKSPACE.md supplies shared project/operator context.
3. AIWG.md supplies generated framework/discovery context.
4. Narrower linked files and provider-native subtree instructions govern their declared scope.

### Ownership

- Edit project-neutral notes only inside the protected Project Context section below.
- Keep detailed policies, runbooks, hooks, and quickrefs in linked files.
- Keep provider-only directives in `.aiwg/context/providers/`.
- Never store secrets, tokens, credentials, or machine-local sensitive values here.

### Linked Context

- [AIWG framework context](./AIWG.md)
- [AIWG project configuration](.aiwg/aiwg.config)
- [Project-local quickref](.aiwg/quickref.json) (when configured)

<!-- AIWG:workspace-context:end -->

<!-- AIWG:workspace-operator:start -->

## Project Context

matric-eval is a Python 3.11+ model evaluation framework built on Inspect AI.
The CLI, provider adapters, benchmark registry, checkpoint recovery, study
workflows, and TypeScript subprocess bindings are implemented in this repository.

### Development commands

Run commands from the repository root:

```bash
uv sync --locked --extra dev --extra study
uv run matric-eval --help
uv run matric-eval list-benchmarks
uv run matric-eval list-providers
make test-unit
make ci
uv build
```

`make ci` runs Ruff lint/format checks, the mypy baseline ratchet, and tests with
an 80% coverage floor. `make type-check-strict` displays all strict mypy findings;
`make type-check-update` is reserved for reviewed baseline reductions. Provider
smoke tests require the services and opt-ins described in the
[real-provider smoke guide](docs/testing/real-provider-smoke.md).

### Code and documentation map

- [Package metadata](pyproject.toml), [locked dependencies](uv.lock), and
  [development targets](Makefile) define installation and validation.
- [CLI](src/matric_eval/cli.py) defines commands and options;
  [settings](src/matric_eval/config/settings.py) and
  [config compatibility exports](src/matric_eval/config/__init__.py) define active
  configuration behavior. The adjacent `src/matric_eval/config.py` is legacy.
- [Benchmark registry](src/matric_eval/tasks/registry.py),
  [tasks](src/matric_eval/tasks/), and [scorers](src/matric_eval/scorers/) define
  benchmark availability and evaluation behavior.
- [Providers](src/matric_eval/providers/) implement inference backends;
  [core](src/matric_eval/core/) and [state](src/matric_eval/state/) implement
  execution and recovery; [studies](src/matric_eval/studies/) implements study
  protocol and manifest workflows.
- [TypeScript bindings](bindings/typescript/) call the Python CLI.
- [README](README.md), [documentation index](docs/README.md), and
  [contributing guide](CONTRIBUTING.md) are the starting points for users and
  contributors. [Planning](docs/development/planning.md) and
  [roadmap](docs/development/roadmap.md) contain historical design and planned work;
  verify current behavior against source and tests.

### Repository delivery

The canonical repository and engineering tracker are
[Integro Labs Gitea](https://git.integrolabs.net/roctinam/matric-eval) (`origin`).
The `github` remote is a public mirror. Follow the delivery policy in
[AIWG configuration](.aiwg/aiwg.config): changes require a pull request to `main`,
green CI, and no force pushes. CalVer `YYYY.M.PATCH` versions are synchronized by `make version-bump` and checked
by `make version-check`. The validated [release workflow](.gitea/workflows/release.yml)
attaches Gitea release downloads; the equivalent
[GitHub workflow](.github/workflows/release.yml) attaches GitHub release downloads
when the checked tag is pushed to the mirror. Python and npm registry publishing
are disabled.
See [the release guide](docs/development/releasing.md).

<!-- AIWG:workspace-operator:end -->
