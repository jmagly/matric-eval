# Benchmark Reproducibility and Freshness

## Supported framework versions

The project pins `inspect-ai==0.3.251` and `inspect-evals==0.16.0`. The lock file
is authoritative for transitive dependencies. Every result emitted by
`EvaluationEngine` records the installed `matric-eval`, `inspect-ai`,
`inspect-evals`, and Python versions.

The 0.3.203 to 0.3.251 Inspect AI review found no remaining use of removed task,
scorer, sandbox, model, log, or retry APIs. Current task construction, content
types, agents, sandbox specifications, scorer decorators, and synchronous
`eval()` result handling are covered by the unit suite.

| Integration strategy | Benchmarks |
| --- | --- |
| Maintained `inspect-evals` task/protocol | CyberSecEval 4, classic GAIA |
| Maintained `inspect-evals` solver/scorer with pinned local loader | SWE-bench Verified, Multilingual, Pro |
| Local Inspect task and scorer | ARC, DS-1000, GSM8K, HumanEval, IFEval, LiveCodeBench, MBPP, MMLU, MMMU, MT-Bench, RealWorldQA, tool calling, MATRIC tasks |
| Pinned external official runner | Claw-Eval, NL2RepoBench, OmniDocBench, QwenClawBench, Terminal-Bench, Video-MME-v2 |
| Quarantined pending public protocol | QwenWebBench |

Local implementations remain where the project has compatibility requirements,
multimodal materialization, local fixtures, or an official external batch runner
that cannot be represented as an ordinary Inspect completion task. Upstream
delegation is preferred when `inspect-evals` exposes the required current
protocol without changing leaderboard semantics.

Provider contract tests cover Ollama, vLLM, llama.cpp, OpenRouter, and Chutes.
Representative task tests cover text generation, multimodal content, tool use,
and Docker sandbox construction. Credentialed live model runs remain an
environmental release check and are not part of deterministic CI.

## Registry requirements

External public, gated, or private benchmarks must declare:

- canonical dataset source and source kind;
- immutable dataset revision, expected configs/splits, and sample count;
- protocol identifier and evaluator revision;
- access class, release policy, and license or upstream terms;
- prompt and container revisions when those artifacts affect the protocol.

Local benchmarks declare `access=local` and `release_policy=local`. Gated
benchmarks include a reason and fail clearly when required data or credentials
are absent. Unavailable benchmarks include a re-enable reason and cannot execute.
Legacy and experimental tasks retain the same provenance fields but their
lifecycle status prevents them from being mistaken for stable current results.

New result keys are additive. Existing result readers can continue consuming the
original status, score, and sample fields while provenance-aware readers use the
schema-versioned `provenance` object.

## Dataset loading

Use `load_hf_dataset(..., revision=<full commit hash>,
require_immutable_revision=True)` for remote data. Set `token=True` to use the
Hugging Face credential configured by the provider, or pass a token at runtime.
Tokens are passed only to `datasets.load_dataset()` and are never retained in
sample or result metadata.

`cache_dir` selects a deterministic cache root. `offline=True` sets the datasets
download configuration to local-files-only; a missing pinned snapshot raises
`DatasetOfflineError`. Gated access, missing sources, and missing revisions raise
`DatasetAccessError`, `DatasetSourceError`, and `DatasetRevisionError`
respectively. Samples retain source, revision, config, and split metadata.

## Freshness policy

Run the deterministic registry check with:

```bash
uv run matric-eval audit-benchmarks --output-format json \
  --output benchmark-freshness.json
```

Add `--live` to resolve public Hugging Face and GitHub sources without downloading
benchmark payloads. CI uses the live mode, fails on broken public sources,
mutable or missing revisions, placeholder scorers, and invalid dataset-shape
declarations, and retains the JSON report as an artifact.

Immutable benchmarks keep a pinned data/evaluator identity indefinitely; a new
upstream release is integrated as a separately reviewed protocol change.
Versioned suites advance only after schema, prompt, scorer, count, and parity
review. Continuously updated suites require a new immutable snapshot for every
reported run. Successors use a distinct benchmark name so historical results do
not silently change meaning.
