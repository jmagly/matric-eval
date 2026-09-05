# Agentic external runner setup

The external trajectory benchmarks do not share the core matric-eval Python
environment. Their official packages have conflicting dependency requirements,
so every runner uses its own pinned environment on the A100 host. Environment
inventories are captured with each validation or evaluation run.

## BFCL V4 Agentic

- Dataset/source review checkout: `ShishirPatil/gorilla` at
  `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8`.
- Official runner: `bfcl-eval==2026.3.23`, Python 3.10.
- Packaging exception: explicitly install `soundfile==0.13.1`. The official
  package imports it through Qwen Agent but does not declare it, and the CLI
  otherwise fails during import.
- A100 environment: `/srv/matric-eval/benchmarks/bfcl-runner-2026.3.23/.venv`.

The `bfcl test-categories` canary must list the `agentic` group and its memory
and web-search categories. Generation uses `bfcl generate`; scoring uses
`bfcl evaluate`. Do not replace the official trajectory evaluator with the
project's small deterministic tool-calling regression set.

## tau3-bench

- Official checkout: `sierra-research/tau2-bench` at
  `672227c6b6676edc20d57ea53b7000262aae77b9` (`v1.0.1`).
- Python: 3.12, installed from the upstream `uv.lock` with `uv sync`.
- A100 environment: `/srv/matric-eval/benchmarks/tau2-v1.0.1/.venv`.

Run `tau2 check-data` before an evaluation. The user-simulator model is an
experimental factor and must be identical across comparison cohorts. Use the
default `base` task split for agent evaluation and pin task IDs, seed, trials,
concurrency, and maximum steps in the run manifest.

## Terminal-Bench 2.1 / Harbor

- Dataset checkout: `harbor-framework/terminal-bench-2-1` at
  `5c8eadf1f393183288fa08b8f73ca9a469cc5e00`.
- Official runner: `harbor==0.22.0`, Python 3.12.
- A100 environment: `/srv/matric-eval/benchmarks/harbor-0.22.0/.venv`.

The CLI canary must expose `--dataset`, `--n-attempts`, and `--n-concurrent`.
Keep the 89-task Terminal-Bench 2.1 revision fixed; do not compare its scores to
2.0 as though the tasks were unchanged.

## SWE-bench-Live MultiLang

- Official checkout: `microsoft/SWE-bench-Live` at
  `9b4b11c5d77365107e91bc19d7a3aebbe8da76b7`.
- Dataset: `SWE-bench-Live/MultiLang` at
  `22091f6ce331c5c60c241d76512d4be7ee1a555b`.
- Required RepoLaunch submodule:
  `c4b623d930f3728e5338664bb634021b98492cbf`.
- Python: 3.11 in `/srv/matric-eval/benchmarks/swebench-live/.venv`.

Initialize the pinned submodule before invoking
`python -m evaluation.evaluation`; the editable package installation alone does
not populate `launch/` and fails to import `launch.core`. Preserve complete
agent trajectories and expose only the problem statement and task container to
the agent during rollout.

## A100 validation evidence

The initial setup canaries and frozen environment inventories are retained at
`/srv/matric-eval/results/validation-issue-110-20260905`. These prove runner
startup and data discovery only. They are not model-quality results and did not
claim a GPU.
