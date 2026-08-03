# matric-eval Delivery Plan

**Status**: Active 0.2.0 release planning

**Last reconciled**: 2026-08-03

This is the current delivery plan. The original week-based construction plans
under `.aiwg/planning/` are archived project history; their issue numbers,
estimates, and completion states must not be used for current scheduling.

## Delivery Sources Of Truth

1. [Gitea issues](https://git.integrolabs.net/roctinam/matric-eval/issues) own scope, dependencies, and acceptance criteria.
2. [Gitea milestones](https://git.integrolabs.net/roctinam/matric-eval/milestones) own release grouping and open/closed state.
3. The [supported-capability roadmap](roadmap.md) summarizes current product status.
4. `matric-eval list-benchmarks` and `matric-eval audit-benchmarks` generate the benchmark inventory and protocol health.
5. Gitea Actions is authoritative for integration and release evidence.

## Current Position

The Reliability & CI Hardening milestone closed on 2026-08-03 with issues #87
through #90 complete. The repository is now in the Release 0.2 & Ecosystem
Adoption milestone. Version 0.1.0 remains the latest released package until #92
completes all release gates.

## Ordered Work

| Stage | Tracker item | State | Required outcome |
|---|---|---|---|
| Documentation baseline | [#91](https://git.integrolabs.net/roctinam/matric-eval/issues/91) | In progress | Public docs, planning, traceability, protocols, and historical records agree with current evidence |
| Release candidate | [#92](https://git.integrolabs.net/roctinam/matric-eval/issues/92) | Blocked until #91 | Consistent 0.2.0 versions, changelog/release notes, wheel, sdist, TypeScript package, SBOM, license report, and vulnerability audit |
| Clean validation | [#93](https://git.integrolabs.net/roctinam/matric-eval/issues/93) | Coordinates with #92 | Install and exercise candidate artifacts in every supported clean environment; attach hashes and results before final publication |
| Ecosystem adoption | [#94](https://git.integrolabs.net/roctinam/matric-eval/issues/94) | Blocked by package candidate | Validate the TypeScript client in matric-cli, including streaming, cancellation, errors, migration, and rollback |

Release preparation and clean validation are iterative: #92 produces immutable
candidate artifacts, #93 validates those exact hashes, and #92 publishes the tag
and final release only after that evidence passes. #94 validates the supported
consumer path and must not assume that a source-tree build proves registry
installation or consumer compatibility.

## Release Gates

### Documentation Gate

- Living documents use current capability status rather than historical phase checklists.
- Stable, gated, experimental, unavailable, production-validated, and deferred claims are distinct.
- Counts are generated or dated with a reproducible command.

### Quality Gate

- Gitea PR and `main` workflows pass lint, format, type-check ratchet, full test/coverage, smoke, and package-build jobs.
- The deterministic benchmark audit completes with no errors.
- The retained operational validation report remains reproducible.

### Supply-Chain Gate

- Python and TypeScript versions, source commit, tag, and release notes agree.
- Wheel, sdist, npm package, SBOM, license report, and vulnerability report are retained.
- Critical findings require remediation or an explicit, reviewed acceptance record.

### Installation Gate

- Supported Python versions install wheel and sdist without source-tree leakage.
- Gitea PyPI and npm installation paths use the candidate artifact hashes.
- CLI help, benchmark listing, deterministic audit, TypeScript invocation, and a minimal provider smoke pass from clean environments.

### Adoption Gate

- matric-cli CI passes against the released client contract.
- A representative consumer evaluation completes through the client.
- Migration and rollback work from a clean checkout.
- Ownership, support boundaries, and deliberate compatibility changes are documented.

## Deferred Work

Issues #95 through #97 are excluded from the 0.2.0 sequence. Their issue bodies
contain explicit promotion triggers. Do not bundle leaderboard/reporting, Rust
bindings, or normalized token/cost accounting into release work without changing
tracker state and reviewing the resulting scope.

## Verification Commands

```bash
uv run matric-eval list-benchmarks
uv run matric-eval audit-benchmarks --fail-on-error
make operational-validation
make lint
make format-check
make type-check
make test-coverage-fail
```

Hosted workflow results, package hashes, and consumer evidence remain required;
local command success alone is not release approval.
