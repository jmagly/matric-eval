# Changelog

All notable changes to matric-eval are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-08-03

### Added

- Expanded the task registry to 39 protocol-pinned benchmark entries spanning
  core, agentic, security, multimodal, repository, long-context, memory, and
  successor suites.
- Added EvalPlus, MMLU-Pro, MMMU-Pro, GAIA2, InjecAgent, CyberSecEval 4,
  SWE-bench variants, RULER, BABILong, InfiniteBench, and gated official-runner
  integrations documented in the Wave 1-3 protocol records.
- Added Ollama, llama.cpp, vLLM, OpenRouter, and Chutes provider adapters plus
  multi-provider matrix execution and thinking-model controls.
- Added source freshness auditing, benchmark/run provenance, multimodal helpers,
  sandbox runners, pass@k, patch/retrieval scoring, and retained operational
  validation records.
- Added a scheduled/manual real-provider Ollama smoke workflow with retained
  logs, results, checkpoints, runtime metadata, and model digest.
- Added a release contract for synchronized Python/npm versions, package-content
  checks, CycloneDX SBOMs, dependency licenses, vulnerability audits, hashes, and
  immutable candidate artifacts.

### Changed

- Connected checkpoint persistence and resume to end-to-end CLI/engine execution,
  including duplicate prevention and gap-only continuation.
- Made Gitea Actions authoritative for lint, formatting, type-check ratchet,
  full test/coverage, smoke, benchmark freshness, and package-build gates.
- Replaced the historical parity checklist with a supported-capability roadmap
  that distinguishes stable, gated, experimental, unavailable, validated, and
  deferred work.
- Updated all managed dependency locks and removed vendored `node_modules` from
  source control and source distributions.

### Fixed

- HumanEval now rebuilds body-only completions against the canonical prompt and
  invokes `check(candidate)`; syntactically valid but incorrect implementations
  no longer pass without executing the canonical test harness.
- Stabilized CI checkout, external-loader isolation, artifact upload runtime, and
  mypy dependency boundaries on Gitea runners.

### Compatibility

- Python 3.11 or newer remains required.
- Node.js 18 or newer remains required by `@matric/eval-client`.
- HumanEval scores may decrease where earlier runs accepted syntactically valid
  code without invoking the canonical test function. This is an intentional
  correctness fix.
- Gated benchmarks require their documented official runner, accepted dataset,
  hardware, or license prerequisite and reject unsupported completion-only runs.

## [0.1.0] - 2026-01-24

- Initial Python package and TypeScript client release.
- Core benchmark tasks, tiered CLI, checkpoint state structures, parallel
  execution, logging, and recommendation support.

[0.2.0]: https://git.integrolabs.net/roctinam/matric-eval/compare/v0.1.0...v0.2.0
[0.1.0]: https://git.integrolabs.net/roctinam/matric-eval/releases/tag/v0.1.0
