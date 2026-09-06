# matric-eval Session Initialization

Use this prompt when starting a coding-agent session in the repository. Replace
the final task line with the work you want to perform.

```text
I am working on matric-eval, an implemented Python 3.11+ evaluation framework
built on Inspect AI, with inference providers and TypeScript subprocess bindings.

Read WORKSPACE.md first, then AIWG.md, following the repository's AGENTS.md
bootstrap. Read README.md and CONTRIBUTING.md for project usage and development.

Inspect git status before making changes. Use current source and tests to verify
behavior; docs/development/planning.md and roadmap.md include historical plans.

Find commands in src/matric_eval/cli.py, active configuration in
src/matric_eval/config/settings.py, benchmarks in src/matric_eval/tasks/registry.py,
and runtime/recovery behavior in src/matric_eval/core/ and src/matric_eval/state/.

Development setup: uv sync --locked --extra dev --extra study
CLI discovery: uv run matric-eval --help
Benchmark discovery: uv run matric-eval list-benchmarks
Provider discovery: uv run matric-eval list-providers
Unit checks: make test-unit
Merge gates: make ci
Package build: uv build

For live evaluations, first read docs/testing/real-provider-smoke.md and the
relevant benchmark protocol. Confirm service, model, dataset, and optional
runtime prerequisites before running the selected benchmark.

The canonical repository/tracker is origin on git.integrolabs.net; github is a
public mirror. Follow .aiwg/aiwg.config for delivery: PR to main, green CI, no
force pushes.

Task: [describe the requested change and acceptance criteria]
```

The [workspace context](../../WORKSPACE.md) provides the maintained code map.
The [documentation index](../README.md) links benchmark protocols, testing,
architecture, and release guidance.
