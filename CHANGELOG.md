# Changelog

All notable changes to matric-eval are documented here. The project follows
CalVer `YYYY.M.PATCH`, documented in [the release guide](docs/development/releasing.md).
The patch counter starts at zero each UTC month; historical SemVer tags remain unchanged.

## [2026.9.2] - 2026-09-11

### Added

- Added native exact ordered 1+ GPU allocation, lifecycle, vLLM profile,
  wrapper, replay, reporting and TP2 qualification contracts.
- Added a governed AIWG-wide agent-platform evaluation pipeline whose matrix is
  derived from the maintained provider registry and whose credentialed runs stay
  outside pull-request CI.
- Added bounded two-A100 qualification tooling with topology, per-rank capacity,
  content-free canary, TAU diagnostic and set-atomic cleanup evidence gates.

### Changed

- Propagate exact GPU UUID sets and tensor-parallel profiles across requests,
  leases, containers, CUDA visibility, server receipts and cleanup.
- Restore bounded real-provider smoke diagnostics and normalize Ollama inference
  requests onto its supported OpenAI-compatible endpoint.
- Record every current or future AIWG provider and the supported direct endpoint
  families with explicit, machine-readable execution dispositions.

### Fixed

- Reject foreign CUDA processes during TP2 admission even when nominal free
  memory exceeds the per-rank floor.
- Accept a virtual environment's conventional executable symlink while attesting
  the resolved regular-file interpreter.
- Redact agent-pipeline evidence while streaming and reject unsafe environment,
  fixture, command and result inputs before they can weaken isolation or public
  normalization.

### Compatibility

- Python 3.11+ and Node.js 18+ remain required. Existing result and study
  contracts remain readable; the agentic pipeline introduces its own versioned
  configuration and result schemas.
- The TP2 harness is delivered but hardware qualification remains blocked in
  #183 because the exact GPU0/GPU2 pair is occupied by unrelated workloads.
  Dependent documentation #184 and epic #178 remain open, and no TP2 scoring
  success is claimed.
- TAU research/scoring (#154), grader qualification (#126), and remaining
  OBLITERATUS dataset work (#164) remain explicitly deferred.

## [2026.9.1] - 2026-09-10

### Added

- Added an OBLITERATUS prompt importer with pinned source identities, per-record
  provenance, qualification evidence and CLI support for reproducible dataset
  materialization.
- Added bounded local and simulator-backed TAU replay tooling, canaries and
  retained root-cause evidence for the preregistered Qwen3.8 study.
- Added an implementation-ready architecture, risk assessment and test strategy
  for exact ordered 1+ GPU allocations and qualified tensor-parallel profiles.
- Added a schema-validated, config-driven release flow covering local builds,
  exact-commit CI, checked tags, forge mirroring and publication verification.

### Changed

- Preserve model-service admission through readiness, keep exact simulator
  manifest order and normalize wire tool arguments before context accounting.
- Record independent human-calibration selection inputs without coupling them
  to OBLITERATUS prompt-source qualification.

### Fixed

- Settle synchronous broker rejections and release run leases only after
  confirmed owned-container teardown.
- Isolate replay service names and support portable pidfd inspection without
  weakening live-process ownership checks.

### Compatibility

- Python 3.11+ and Node.js 18+ remain required. Result, protocol and evidence
  schema versions are unchanged.
- TAU scoring (#154), reusable human-calibrated graders (#126) and the remaining
  OBLITERATUS dataset work (#164) remain deferred; this release does not claim
  those qualification gates have passed.

## [2026.9.0] - 2026-09-09

### Changed

- Adopted synchronized CalVer versions for Python, TypeScript and their lockfiles,
  with one checked bump command and strict tag/package agreement.
- Changed release distribution to verified Gitea and GitHub downloads. Python and npm
  registry publication is disabled.
- Require the tagged source to belong to main and pass exact-commit CI before
  release uploads. Draft staging and digest checks make retries safe.
- Locked CI dependency setup, retained combined client coverage, removed duplicate
  unit-test smoke execution and aligned mirror package checks.

- Raised minimum Click, GitPython and pypdf versions to patched releases.
- Bound dependency license and unindexed source reviews to exact installed bytes;
  retained expiring reviews for the remaining protobuf and NLTK advisories.

### Added

- Staged study preflight, durable GPU/service cleanup, correlated progress and
  failure diagnostics, independent suite scheduling and compatible result reuse.
- Actual client/broker conformance and bounded storage/model-load qualification.
  Deferred TAU scoring and frozen study protocols remain unchanged.

### Fixed

- Handle launcher exit during ownership inspection without reporting a false
  cleanup failure; live processes still require verified ownership.

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

[2026.9.2]: https://git.integrolabs.net/roctinam/matric-eval/compare/v2026.9.1...v2026.9.2
[2026.9.1]: https://git.integrolabs.net/roctinam/matric-eval/compare/v2026.9.0...v2026.9.1
[2026.9.0]: https://git.integrolabs.net/roctinam/matric-eval/compare/v0.2.0...v2026.9.0
[0.2.0]: https://git.integrolabs.net/roctinam/matric-eval/compare/v0.1.0...v0.2.0
[0.1.0]: https://git.integrolabs.net/roctinam/matric-eval/releases/tag/v0.1.0
