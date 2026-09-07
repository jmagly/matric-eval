# CLI Reference

This reference matches the Click command definitions in `src/matric_eval/cli.py`. From a source checkout, prefix commands with `uv run`. Run `matric-eval COMMAND --help` to inspect the installed version.

## Common workflows

```bash
matric-eval run --model llama3.2:3b --benchmark gsm8k --tier smoke
matric-eval recommend --results-dir results/RUN_ID
matric-eval validate RUN_ID --output results
matric-eval run --resume results/RUN_ID --fill-gaps
```

Replace `RUN_ID` with the ID printed by your evaluation. Resume works at benchmark granularity: incomplete benchmarks rerun. Matrix runs have a separate execution path and do not support `--resume`. Global logging flags go before the command; command-specific output flags go after it.

The CLI does not expose `--parallel` or per-sample `--timeout` options. Without an explicit model, the default path discovers Ollama models under the configured size cap. Use explicit benchmarks for a bounded first run. `--thinking auto` selects off for detected thinking-capable models; use `on` or `both` deliberately when needed.

## Commands

```text
Usage: matric-eval [OPTIONS] COMMAND [ARGS]...

  matric-eval - Consolidated model evaluation framework.

  Evaluate LLM models across multiple providers using standardized benchmarks.

Options:
  --version                       Show the version and exit.
  --log-level [debug|info|warning|error]
                                  Set logging level (default: info)
  --log-json                      Output logs in JSON format (useful for log
                                  aggregation)
  --log-file PATH                 Write logs to file in addition to console
  --help                          Show this message and exit.

Commands:
  audit-benchmarks         Audit benchmark source health, revisions,...
  build-study-manifest     Build a deterministic ordered sample manifest...
  list-benchmarks          List registered and discovered benchmarks,...
  list-models              List available Ollama models.
  list-providers           List available inference providers.
  qualify-study-model      Hash all indexed model artifacts and write a...
  recommend                Generate model recommendations from evaluation...
  run                      Run model evaluation.
  run-study-offline-batch  Run one manifest-locked model cohort through...
  validate                 Validate run completeness and check for gaps.
  validate-study           Validate a preregistered matched-comparison...
```

## audit-benchmarks

```text
Usage: matric-eval audit-benchmarks [OPTIONS]

  Audit benchmark source health, revisions, protocols, and lifecycle state.

Options:
  --live                          Probe public canonical sources without
                                  downloading benchmark payloads.
  --output-format [table|json]    Output format (default: table).
  --output PATH                   Retain the machine-readable audit report at
                                  this path.
  --fail-on-error / --no-fail-on-error
                                  Exit nonzero when audit errors are present.
  --help                          Show this message and exit.
```

## build-study-manifest

```text
Usage: matric-eval build-study-manifest [OPTIONS] PROTOCOL ID_CATALOG

  Build a deterministic ordered sample manifest from canonical IDs.

Options:
  --cohort [pilot|full]  [required]
  --output FILE          [required]
  --help                 Show this message and exit.
```

## list-benchmarks

```text
Usage: matric-eval list-benchmarks [OPTIONS]

  List registered and discovered benchmarks, including unavailable entries.

  Examples:

      # List all benchmarks     matric-eval list-benchmarks

      # Show sample counts for smoke tier     matric-eval list-benchmarks
      --tier smoke

      # Output as JSON     matric-eval list-benchmarks --output-format json

Options:
  --tier [smoke|quick|full]     Show sample counts for specific tier
  --output-format [table|json]  Output format (default: table)
  --help                        Show this message and exit.
```

## list-models

```text
Usage: matric-eval list-models [OPTIONS]

  List available Ollama models.

  Examples:

      # List all models under 15GB     matric-eval list-models

      # List only small models     matric-eval list-models --max-size 5.0

      # Output as JSON     matric-eval list-models --output-format json

Options:
  --max-size FLOAT              Maximum model size in GB (default: 15.0)
  --output-format [table|json]  Output format (default: table)
  --help                        Show this message and exit.
```

## list-providers

```text
Usage: matric-eval list-providers [OPTIONS]

  List available inference providers.

  Examples:

      # List all providers     matric-eval list-providers

      # Check which providers are reachable     matric-eval list-providers
      --check-availability

Options:
  --check-availability          Check if each provider is reachable
  --output-format [table|json]  Output format (default: table)
  --help                        Show this message and exit.
```

## qualify-study-model

```text
Usage: matric-eval qualify-study-model [OPTIONS] PROTOCOL

  Hash all indexed model artifacts and write a qualification manifest.

Options:
  --model-id TEXT         Qualified model ID from the study protocol.
                          [required]
  --model-path DIRECTORY  Local model snapshot directory to hash and qualify.
                          [required]
  --output FILE           [required]
  --help                  Show this message and exit.
```

## recommend

```sh
matric-eval recommend --results-dir results/RUN_ID --capability-policy policy.json
```

Reads strict native or preserved historical results. Recommendations require an
explicit comparison identity and complete full-suite capability aggregation
policy. Otherwise JSON contains `no_recommendation`, retained sources and explicit
exclusions. `--output FILE` writes that report; `--min-score FLOAT` requires a
policy with a shared higher-is-better target scale. The legacy
`--output-format model-categories` conversion is explicitly refused because it
cannot represent these eligibility and missingness semantics.

## Result readers, conversion and history

```sh
matric-eval read-result result.json
matric-eval convert-result historical.json --output new-import.json
matric-eval trend-import model-result.json --database history.sqlite
matric-eval trend-series --database history.sqlite --model MODEL --benchmark BENCHMARK --metric METRIC --comparison-sha256 SHA256
```

Conversion never overwrites existing files. Trend import accepts individual v2
result envelopes and preserves every named measurement in separate versioned
SQLite tables. The default series requires unchanged model identity, which
generic envelopes cannot attest. `--allow-model-change` explicitly selects
declared measurement comparison without claiming unchanged model weights.
See [consumer migration](development/consumer-migration.md) for the implemented
profile, limits, TypeScript APIs and rollback.

## run

```text
Usage: matric-eval run [OPTIONS]

  Run model evaluation.

  Examples:

      # Run smoke test on specific model     matric-eval run --tier smoke
      --model llama3.2:3b

      # Run quick evaluation on all small models     matric-eval run --tier
      quick --max-size 5.0

      # Run specific benchmark only     matric-eval run --tier smoke --model
      llama3.2:3b --benchmark humaneval

      # Resume from checkpoint     matric-eval run --resume
      run-2024-01-20T10-30-00

      # Fill gaps in incomplete run     matric-eval run --resume
      run-2024-01-20T10-30-00 --fill-gaps

      # Output as JSON     matric-eval run --tier smoke --model llama3.2:3b
      --output-format json

Options:
  --tier [smoke|quick|full]      Evaluation tier (smoke=5 samples, quick=75,
                                 full=all)
  --model TEXT                   Specific model to evaluate (e.g.,
                                 llama3.2:3b). If omitted, evaluates all
                                 models under --max-size.
  --benchmark TEXT               Specific benchmark(s) to run. May be
                                 repeated. If omitted, runs all benchmarks for
                                 the tier.
  --max-size FLOAT               Maximum model size in GB (default: 15.0)
  --output PATH                  Output directory for results (default:
                                 ./results)
  --output-format [table|json]   Output format (default: table)
  --result-format [legacy|v2]    Result contract (default: legacy)
  --thinking [auto|on|off|both]  Thinking mode for capable models
                                 (auto=detect, on=enable, off=disable,
                                 both=run twice)
  --provider TEXT                Inference provider (ollama, llama-cpp, vllm,
                                 openrouter, chutes). Default: ollama.
  --provider-url TEXT            Override the provider's base URL (e.g.,
                                 http://localhost:8080)
  --api-key TEXT                 API key for authenticated providers
                                 (openrouter, chutes). Can also use env vars.
  --matrix PATH                  YAML evaluation matrix config file for multi-
                                 provider runs.
  --judge TEXT                   LLM judge for subjective evaluation (e.g.,
                                 ollama:llama3.1:8b). Adds judge scoring
                                 alongside deterministic scorers.
  --resume TEXT                  Resume from checkpoint (provide run-id or
                                 path to run directory)
  --fill-gaps                    When resuming, only fill gaps
                                 (incomplete/missing benchmarks)
  --help                         Show this message and exit.
```

## run-study-offline-batch

```text
Usage: matric-eval run-study-offline-batch [OPTIONS] PROTOCOL MANIFEST
                                           REQUESTS

  Run one manifest-locked model cohort through offline batch-invariant vLLM.

Options:
  --model-id TEXT             Qualified model ID from the study protocol.
                              [required]
  --model-path DIRECTORY      Local qualified model snapshot directory.
                              [required]
  --model-qualification FILE  JSON manifest of the exact local model artifacts
                              and their SHA-256 values.  [required]
  --chat-template FILE        Common chat template pinned by the study
                              protocol.  [required]
  --gpu-lease-receipt FILE    GPU broker lease receipt retained with the run
                              evidence.  [required]
  --output FILE               [required]
  --help                      Show this message and exit.
```

## validate

```text
Usage: matric-eval validate [OPTIONS] RUN_ID

  Validate run completeness and check for gaps.

  Examples:

      # Check run completeness     matric-eval validate
      run-2024-01-20T10-30-00

      # Force unlock stale lock     matric-eval validate
      run-2024-01-20T10-30-00 --force-unlock

      # Output as JSON     matric-eval validate run-2024-01-20T10-30-00
      --output-format json

Options:
  --output PATH                 Results directory (default: ./results)
  --force-unlock                Force unlock if lock file exists
  --output-format [table|json]  Output format (default: table)
  --help                        Show this message and exit.
```

## validate-study

```text
Usage: matric-eval validate-study [OPTIONS] PROTOCOL

  Validate a preregistered matched-comparison study protocol.

Options:
  --output-format [table|json]  Output format (default: table).
  --output PATH                 Retain the validation summary as JSON.
  --help                        Show this message and exit.
```

## Configuration and task prerequisites

Use `--provider-url` for explicit provider endpoint overrides and `--api-key` for explicit authenticated runs. `EVAL_DATASETS_DIR` selects the custom dataset root. Pydantic settings and sample overrides are defined in [`config/settings.py`](../src/matric_eval/config/settings.py); registry tier defaults are in [`tasks/registry.py`](../src/matric_eval/tasks/registry.py). Not every setting overrides an explicit CLI default.

A listed benchmark may need data access, a separate runner, model capabilities, or permission to use the dataset. See the [benchmark protocols](README.md#benchmark-protocols), [study index](../studies/README.md), and [architecture](architecture/overview.md).
