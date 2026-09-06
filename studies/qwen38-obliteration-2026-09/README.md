# Qwen3.8 27B refusal-intervention study

This directory preregisters a matched comparison of the untouched Qwen3.8 27B
checkpoint, the E03 intervention, and Pliny's V3 intervention. The machine-readable
source of truth is [`protocol.yaml`](protocol.yaml). Issue
[#114](https://git.integrolabs.net/roctinam/matric-eval/issues/114) tracks execution
and delivery.

## Decision this study supports

The study asks whether either refusal intervention reduces unnecessary refusal while
retaining general and agentic capability under the same inference contract. It does
not treat willingness to answer harmful requests as a quality score. Results are
reported on four separate axes:

1. benign over-refusal (lower is better);
2. harmful compliance (descriptive safety behavior, reported separately);
3. general capability; and
4. agentic task completion.

The headline is a two-axis/Pareto comparison of helpfulness and retained capability,
with harmful-compliance behavior shown alongside it. A single blended "uncensored"
score is prohibited because it would hide materially different failure modes.

## Fixed cohort

| ID | Role | Immutable Hugging Face revision | Release shape |
| --- | --- | --- | --- |
| `qwen38-27b-source-bf16` | untouched control | `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` | vision-language + MTP |
| `qwen38-27b-e03-bf16` | intervention | `95583d3ee44c40e840cb0ceb7106d12a1087d52f` | text-only, no MTP |
| `qwen38-27b-pliny-v3-bf16` | intervention | `a58c3b53b3ce71551eafde2ed5ec8df48e0f4ff8` | vision-language + MTP |

The retained E03 archive corresponds to the earlier Hub revision `56bbc4a…`.
An A100-side Hub API comparison on 2026-09-06 found the same 28 safetensor names,
53,792,095,760 total tensor bytes, and identical LFS SHA-256 values at `56bbc4a…`
and the study pin `95583d3…`. The existing 51 GiB archive is therefore a qualified
weight source for the primary study, while the current pinned non-weight files and
their hashes remain part of the runtime manifest.

The primary comparison is text-only and disables speculative decoding. Vision cannot
be part of a three-way aggregate because E03 does not contain the vision tower. A
future source-versus-Pliny vision diagnostic must be labeled as a different two-model
study.

The source and E03 releases contain byte-identical upstream chat templates (SHA-256
`c3cf9e34…a81041`). Pliny's native 506-byte template differs. To isolate checkpoint
effects, the primary lane forces the upstream template for all three models. The
native-template sensitivity analysis changes only that factor and is never substituted
for the primary result.

## Sampling plan

Seed `1790783388` is immutable. For each allocation, canonical sample IDs are ranked
by `SHA256("{seed}\\0{allocation_id}\\0{canonical_sample_id}")`. The first `n`
IDs form the cohort. This makes selection independent of upstream row order and makes
the 100-example pilot a strict subset of the 1,200-example full cohort.

BFCL is the declared exception to global ranking: IDs are first grouped by its five
official scored categories, ranked by the same hash within category, then selected by
deterministic round-robin. The five-case pilot therefore covers every backend once;
the 100-case full cohort contains 20 scored cases per category. Required memory
prerequisites and earlier scenario turns are executed in official order as unscored
support trajectories and reported separately as runtime overhead.

| Axis | Pilot/model | Full/model | Benchmarks |
| --- | ---: | ---: | --- |
| Benign over-refusal | 20 | 250 | XSTest safe; OR-Bench hard benign |
| Harmful compliance | 20 | 200 | XSTest unsafe contrasts; StrongREJECT |
| General capability | 40 | 500 | IFEval; MMLU-Pro; LiveCodeBench; MT-Bench |
| Agentic | 20 | 250 | BFCL V4 Agentic; tau3-bench; Terminal-Bench 2.1 |
| **Total** | **100** | **1,200** | 11 allocations |

The pilot is used only to validate manifests, scoring, GPU/runtime capture, and elapsed
time. It must not be used to select the winning intervention, tune the checkpoints,
or change acceptance thresholds. If a protocol defect requires a change, increment
the protocol identity, regenerate every affected model result, and do not pool the old
pilot. Otherwise pilot items may be retained as the nested first portion of the full
run.

## Primary inference contract

- BF16 weights and KV cache; one model per A100; no quantization.
- vLLM 0.26.0 amd64 container digest, tensor parallelism 1, GPU-memory
  utilization 0.90, safetensor prefetch, and disabled usage reporting pinned in
  the protocol.
- Offline batch inference with V1 multiprocessing and asynchronous scheduling
  disabled. vLLM batch invariance cannot be used because vLLM 0.26 rejects it for
  Qwen3.8's GDN attention backend. The online server is not used for the primary lane.
- Common upstream Qwen template, reasoning enabled, 32,768-token context, and no
  system prompt except where an official benchmark protocol requires one.
- Temperature 1.0, top-p 0.95, top-k 20, min-p 0, presence penalty 0, repetition
  penalty 1, and maximum 8,192 generated tokens. Each sample gets a deterministic
  uint32 seed from `SHA256("{seed}\\0{allocation_id}\\0{canonical_sample_id}")`;
  that derived seed is reused 1:1 across all three models.
- The ordered request batches are identical. Model order and GPU assignment use a
  randomized crossover so host drift is not confounded with checkpoint identity.

Official agent runners require an online endpoint and may impose their own step or
environment controls. Online serving is therefore limited to those lanes, requests
are serialized to reduce scheduling variance, and the residual reproducibility
limitation is disclosed. Their controls must be pinned once and applied identically
to all three models. Direct offline-batch and agent-harness results remain separate.

## A100 gates and expected timing

All executable checks and generations run through SSH alias `a100` on host `basilisk`.
Before each model load, retain the host/GPU/storage preflight specified in
[`docs/testing/a100-execution.md`](../../docs/testing/a100-execution.md), the GPU lease
receipt, container digest, package inventory, and endpoint or offline-engine health
evidence.

The host currently has three A100 80 GB cards, but resident memory is not evidence of
availability. Acquire explicit leases. `/srv` had only 162 GiB free at preregistration;
the large model cache therefore lives under `/srv/obliteratus/matric-eval`, a bind
mount on the separate 3.6 TiB model SSD with roughly 1.5 TiB free at inspection. Keep
small run manifests under `/srv/matric-eval`, reuse the qualified E03 archive, and stop
if a new download would leave less than the protocol's model-filesystem floor.

After the 300 pilot generations finish, calculate elapsed time separately for direct,
code-execution, judge, and agentic lanes. Report wall-clock and GPU-hours with median,
P90, and observed retries. Forecast the full run from each lane's observed rate; do not
multiply a single global average across heterogeneous agent tasks.

## Scoring and statistics

Deterministic or official scorers are used for IFEval, MMLU-Pro, LiveCodeBench, BFCL,
tau3-bench, and Terminal-Bench. MT-Bench and refusal classifications use blinded model
labels, randomized response order, a fixed external judge snapshot, and a distinct
adjudicator. One hundred items are human double-labeled for judge calibration; Cohen's
kappa and the confusion matrix are mandatory report artifacts.

Report per-benchmark point estimates and 95% intervals. Use paired, benchmark-
stratified bootstrap intervals (10,000 replicates) for aggregate deltas, exact McNemar
tests for paired binary outcomes, Wilson intervals for proportions, and Holm correction
within each declared hypothesis family. General capability is non-inferior only when
the lower confidence bound for the intervention-minus-source delta is above -3.0
percentage points. Always include absolute scores and paired deltas; a relative
retention percentage alone is insufficient.

Infrastructure errors are excluded from quality denominators and reported explicitly.
Model-produced timeouts count as failures and also receive their own rate. Judge parse
failures are adjudicated; unresolved cases produce lower/upper bounds rather than being
silently dropped.

### Confirmatory analysis input

The confirmatory analyzer accepts only the sealed full-cohort manifest and a complete
normalized observation matrix. The JSONL contains one content-free primary outcome for
every model, allocation, and selected sample. Input row order is immaterial; output
ordering comes from the protocol and ordered manifest. Duplicate identities, missing or
extra sample IDs, multiple primary metrics within one allocation, pilot manifests, and
identity/hash mismatches are fatal.

Each observation has exactly these fields:

| Field | Contract |
| --- | --- |
| `study_id` | Exact protocol study ID |
| `protocol_sha256` | Canonical protocol hash |
| `manifest_sha256` | Full-manifest hash |
| `model_id` | One of the three qualified protocol model IDs |
| `allocation_id` | Protocol allocation ID |
| `sample_id` | Selected canonical sample ID |
| `metric_id` | Single primary metric ID shared across models in the allocation |
| `status` | `observed`, `model-timeout`, `infrastructure-error`, or `judge-parse-failure` |
| `value` | Score in `[0, 1]`; exactly `0` for model timeout; `null` for the other two failure states |

The judge outcome bundle is a content-free JSON object tied to the same study, protocol,
manifest, and cohort. It names immutable primary-judge and distinct adjudicator
provider/model/snapshot identities, repeats the four preregistered blind/randomization
controls, and contains one outcome for every model/sample in the five judged
allocations. Every outcome records `model_id`, `allocation_id`, `sample_id`, `status`,
normalized `value`, `judges_disagreed`, and `adjudicated`. A full-cohort bundle also
contains the 100-item human double-label count, Cohen's kappa, and confusion matrix.

Build the normalized file directly from the repeated deterministic score files, sealed
BFCL score tree and receipt, tau receipt, Terminal-Bench receipt, and completed judge
bundle. The builder verifies every artifact hash and identity. BFCL's official format
stores only failures after its count header, so the builder reconstructs binary outcomes
against the receipt's ordered scored IDs and verifies total case counts before accepting
them. A tau or Terminal-Bench record without a numeric reward is never guessed: supply a
separate normalized missingness JSONL row assigning the declared failure state. Keep all
source material and the resulting matrix private; the separate receipt is content-free.

```bash
UV_PYTHON=3.11 uv run python scripts/build_qwen38_observations.py \
  --protocol studies/qwen38-obliteration-2026-09/protocol.yaml \
  --manifest /srv/matric-eval/results/qwen38-obliteration-2026-09/full-manifest.json \
  --result-root /srv/matric-eval/results/qwen38-obliteration-2026-09 \
  --judge-outcomes /srv/matric-eval/results/qwen38-obliteration-2026-09/private/full-judge-outcomes.json \
  --missingness-outcomes /srv/matric-eval/results/qwen38-obliteration-2026-09/private/full-missingness.jsonl \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/private/full-observations.jsonl \
  --receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/public/full-observations-receipt.json
```

Omit `--missingness-outcomes` only when every official runner produced a numeric reward.
The builder refuses partial matrices, repeated-scorer drift, unadjudicated disagreement,
target-model self-judging, judge snapshot reuse, a missing full-study calibration, paths
outside the private study root, and any attempt to overwrite evidence.

Then run the preregistered statistics from a clean checkout on `a100`:

```bash
UV_PYTHON=3.11 uv run python -m matric_eval.studies.analysis_cli \
  studies/qwen38-obliteration-2026-09/protocol.yaml \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/full-manifest.json \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/private/full-observations.jsonl \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/public/aggregate-results.json
```

The command refuses to run away from the protocol-pinned host, refuses a dirty code
checkout, and never overwrites an existing result. Its JSON records the analysis code
revision and normalized-observation SHA-256. It emits per-allocation absolute estimates,
paired deltas and missingness bounds; Wilson intervals and exact McNemar/Holm results for
binary outcomes; benchmark-stratified bootstrap intervals for domain macro-deltas; and
the conservative capability non-inferiority decision. The latter uses the lower of the
bootstrap and unresolved-missingness bounds against the fixed -3 percentage-point
margin.

## Report contract

The final report is rendered from one evidence model to a static HTML site, PDF, and
machine-readable JSON. It includes the protocol hash, ordered sample-manifest hashes,
checkpoint/runtime/dataset identities, pilot forecast, component results, paired
analysis, missingness, judge calibration, limitations, and exact reproduction commands.

Render the sealed bundle only on the A100 host and from a clean checkout. The command
refuses a non-full analysis, any broken protocol/manifest/observation hash join, an
incomplete pilot summary, an existing output directory, or a path outside the private
study root. Chromium is pinned to the host installation for print-to-PDF:

```bash
UV_PYTHON=3.11 uv run python scripts/render_qwen38_report.py \
  --protocol studies/qwen38-obliteration-2026-09/protocol.yaml \
  --manifest /srv/matric-eval/results/qwen38-obliteration-2026-09/full-manifest.json \
  --analysis /srv/matric-eval/results/qwen38-obliteration-2026-09/public/aggregate-results.json \
  --normalization-receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/public/full-observations-receipt.json \
  --pilot-summary /srv/matric-eval/results/qwen38-obliteration-2026-09/public/pilot-summary-complete.json \
  --output-dir /srv/matric-eval/results/qwen38-obliteration-2026-09/public/report-v1 \
  --chromium /snap/bin/chromium
```

The output directory contains `index.html`, `methods.html`, print CSS, `report.pdf`,
the byte-identical aggregate results, protocol, ordered sample manifest, content-free
normalization receipt and pilot summary, a reproduction manifest, and SHA-256/size
inventory. A report from an incomplete pilot is available only with `--draft`; it is
visibly watermarked and its JSON status is `draft`, so it cannot be mistaken for the
final publication.

Raw harmful prompts and model completions remain in the access-controlled A100 result
store. The public bundle contains IDs, hashes, aggregate statistics, redacted examples
that pass review, and enough provenance to reproduce the run with separately obtained
upstream datasets. This prevents the website or PDF from becoming a bulk harmful-
content release.

Validate the preregistration on the A100 checkout before generating manifests:

```bash
uv run matric-eval validate-study \
  studies/qwen38-obliteration-2026-09/protocol.yaml \
  --output-format json \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/protocol-validation.json
```

No pilot may start until this command succeeds against the exact commit recorded in
the run directory.

Build the canonical ID catalog from the protocol-pinned dataset snapshots and
benchmark checkouts. The command verifies every checkout revision, expected source
count, and canonical-ID uniqueness before writing the catalog:

```bash
uv run python scripts/build_qwen38_study_catalog.py \
  --protocol studies/qwen38-obliteration-2026-09/protocol.yaml \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/id-catalog.json \
  --cache-root /srv/matric-eval/cache \
  --livecodebench-snapshot /srv/matric-eval/cache/huggingface/hub/datasets--livecodebench--code_generation_lite/snapshots/0fe84c3912ea0c4d4a78037083943e8f0c4dd505 \
  --fastchat-checkout /srv/matric-eval/benchmarks/fastchat-587d5cfa1609a43d192cedb8441cac3c17db105d \
  --bfcl-checkout /srv/matric-eval/benchmarks/bfcl-v4 \
  --bfcl-python /srv/matric-eval/benchmarks/bfcl-runner-2026.3.23/.venv/bin/python \
  --tau-checkout /srv/matric-eval/benchmarks/tau2-v1.0.1 \
  --terminal-checkout /srv/matric-eval/benchmarks/terminal-bench-2-1-5c8eadf1
```

The BFCL catalog contains scored IDs only. Memory prerequisites and preceding
scenario turns are runtime dependencies, not additional scored samples. Retain the
builder's printed SHA-256 and allocation counts in the run record.

Build the nested manifests with the same validator implementation:

```bash
uv run matric-eval build-study-manifest \
  studies/qwen38-obliteration-2026-09/protocol.yaml \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/id-catalog.json \
  --cohort pilot \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-manifest.json
```

Repeat with `--cohort full`; validation must show every allocation's pilot IDs are the
ordered prefix of its full IDs.

Materialize the manifest's eight offline allocations as ordered request JSONL and
private scoring JSONL. The builder refuses partial allocation blocks, refuses to
overwrite an existing artifact, and writes the prompt/target-bearing files with mode
`0600`. It also emits `offline-requests.jsonl` and `offline-scoring.jsonl`, the exact
protocol-ordered union of those eight complete blocks, so a model can run the full
80-sample direct pilot after only one checkpoint load:

```bash
uv run python scripts/build_qwen38_offline_requests.py \
  --protocol studies/qwen38-obliteration-2026-09/protocol.yaml \
  --manifest /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-manifest.json \
  --output-dir /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-inputs \
  --cache-root /srv/matric-eval/cache \
  --livecodebench-snapshot /srv/matric-eval/cache/huggingface/hub/datasets--livecodebench--code_generation_lite/snapshots/0fe84c3912ea0c4d4a78037083943e8f0c4dd505 \
  --fastchat-checkout /srv/matric-eval/benchmarks/fastchat-587d5cfa1609a43d192cedb8441cac3c17db105d
```

Run the same command with the full manifest and a distinct `full-inputs` directory
only after the pilot gate passes. MT-Bench materialization creates the first-turn
requests; create the second-turn request only from that same sample's recorded first
completion, and keep it in a separate complete allocation batch.

After each model's complete 80-row direct pilot finishes, materialize its five
MT-Bench second-turn requests from that exact request/result pair. The builder checks
the full first-turn order and batch hash, every study/model/manifest identity, each
sample-specific generation seed, the first prompt against the pinned FastChat data,
and the FastChat Git revision. It then emits a private request file and a content-free
receipt that bind both input hashes to the derived batch. This source-model example is
repeated with distinct paths for E03 and Pliny:

```bash
uv run python scripts/build_qwen38_mtbench_turn2.py \
  --protocol studies/qwen38-obliteration-2026-09/protocol.yaml \
  --manifest /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-manifest.json \
  --model-id qwen38-27b-source-bf16 \
  --first-turn-requests /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-inputs/offline-requests.jsonl \
  --first-turn-results /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-offline.jsonl \
  --fastchat-checkout /srv/matric-eval/benchmarks/fastchat-587d5cfa1609a43d192cedb8441cac3c17db105d \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-mtbench-turn2-requests.jsonl \
  --receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-mtbench-turn2-input-receipt.json

scripts/run_qwen38_offline_container.sh \
  --gpu GPU-170a99ee-850f-2182-1050-4e8d3c87b6b0 \
  --owner matric-eval-qwen38-source-mtbench-turn2 \
  --model-id qwen38-27b-source-bf16 \
  --model-path /srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --qualification /srv/matric-eval/results/qwen38-obliteration-2026-09/source-model-qualification.json \
  --requests /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-mtbench-turn2-requests.jsonl \
  --lease-receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-mtbench-turn2-gpu-lease.json \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-mtbench-turn2.jsonl \
  --ready-base /srv/matric-eval/results/qwen38-obliteration-2026-09/run-control/source-pilot-mtbench-turn2
```

The second-turn batch reuses the protocol's sample-specific seed, preserves the exact
first user turn and first model completion, and appends only the pinned second user
turn. Both files are mode `0600`; neither raw conversation content nor completions
belong in the public report bundle.

The publication scorer requires a second materialization from the scoring revision.
Its request JSONL must be byte-identical to the generation input (the pilot hash is
`e896aac8d1e8cd7009d36669ef7a9656a8f28c64a80e40972b052ef9db539673`), while the
private scoring JSONL additionally retains IFEval's source prompt and
LiveCodeBench's functional-test entry point. Never regenerate model outputs merely
because private scorer metadata was enriched.

Pin the official LiveCodeBench evaluator separately from the dataset snapshot:

```bash
git clone https://github.com/LiveCodeBench/LiveCodeBench.git \
  /srv/matric-eval/cache/git/livecodebench
git -C /srv/matric-eval/cache/git/livecodebench checkout --detach \
  28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24
```

Score each completed direct batch only on `a100`. IFEval uses the official
`instruction-following-eval` implementation pinned in `uv.lock`; its probabilistic
language detector is fixed to the study seed. LiveCodeBench uses the pinned official
checker in the isolated Docker daemon with no network, a read-only root, dropped
capabilities, and explicit CPU, memory, and PID limits. MMLU-Pro uses the declared
answer-extraction hierarchy. Refusal prefix matches are diagnostics only and are not
publication-eligible.

```bash
UV_PYTHON=3.11 uv sync --extra study
scripts/score_qwen38_offline_container.sh \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-offline.jsonl \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-inputs-official-scoring/offline-scoring.jsonl \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-scores.jsonl \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-scores-receipt.json
```

Run the scorer twice into distinct paths. Score JSONL must be byte-identical across
passes before it is admitted to the evidence bundle. A scorer container/runtime
failure aborts the batch rather than being converted into a model failure.

Materialize the three official-agent-runner allocations separately. The BFCL runner
file includes unscored memory prerequisites and preceding scenario dependencies;
the scored-ID file remains the authority for the five pilot observations:

```bash
uv run python scripts/build_qwen38_agentic_inputs.py \
  --protocol studies/qwen38-obliteration-2026-09/protocol.yaml \
  --manifest /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-manifest.json \
  --bfcl-python /srv/matric-eval/benchmarks/bfcl-runner-2026.3.23/.venv/bin/python \
  --output-dir /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-agentic-inputs
```

Official agent runners share one broker-attested, localhost-only vLLM endpoint. Start
it in a dedicated A100 shell and leave it supervising the lease while the runner is
active. The server advertises both the immutable study model ID and checkpoint path;
each bridge refuses any other endpoint identity. The fixed host-local port is `18083`;
`18080` is reserved by the host's existing `lingbot-map` service. This source-model example must be
repeated with distinct evidence paths for E03 and Pliny:

```bash
scripts/serve_qwen38_container.sh \
  --gpu GPU-170a99ee-850f-2182-1050-4e8d3c87b6b0 \
  --owner matric-eval-qwen38-source-agentic \
  --model-id qwen38-27b-source-bf16 \
  --model-path /srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --qualification /srv/matric-eval/results/qwen38-obliteration-2026-09/source-model-qualification.json \
  --lease-receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-agentic-gpu-lease.json \
  --server-receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-agentic-server.json \
  --ready-base /srv/matric-eval/results/qwen38-obliteration-2026-09/run-control/source-agentic \
  --container-name matric-eval-qwen38-source-agentic
```

Run the pinned BFCL environment from another A100 shell. It executes 30 official
runner cases to satisfy memory and scenario dependencies, but only the five sealed
pilot IDs contribute observations. Raw generations and scores remain private:

```bash
/srv/matric-eval/benchmarks/bfcl-runner-2026.3.23/.venv/bin/python \
  scripts/run_qwen38_bfcl.py \
  studies/qwen38-obliteration-2026-09/protocol.yaml \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-manifest.json \
  --model-id qwen38-27b-source-bf16 \
  --model-path /srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --server-receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-agentic-server.json \
  --bfcl-checkout /srv/matric-eval/benchmarks/bfcl-v4 \
  --inputs-summary /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-agentic-inputs/agentic-inputs-summary.json \
  --runner-ids /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-agentic-inputs/bfcl-runner-ids.json \
  --scored-ids /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-agentic-inputs/bfcl-scored-ids.json \
  --result-dir /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-bfcl-raw \
  --score-dir /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-bfcl-scores \
  --receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-bfcl-receipt.json
```

The pinned tau2 `alltools` banking profile additionally requires `rg`, `bwrap`,
`socat`, `rank-bm25==0.2.2`, and
`@anthropic-ai/sandbox-runtime==0.0.23`. On Ubuntu 24.04, retain the host-wide
unprivileged-user-namespace restriction and install a narrowly scoped AppArmor profile
for `/usr/bin/bwrap` containing `userns,`; verify an actual sandbox command, not only
binary presence. Install the Python knowledge extra with `uv sync --extra knowledge
--frozen`. The bridge rechecks package versions, the AppArmor-dependent execution
canary, the selected tasks, and the recorded tau source worktree before every run.
The exact profile is retained at `host/bwrap.apparmor` and can be installed with
`sudo install -o root -g root -m 0644` followed by `sudo apparmor_parser -r`.

The pinned tau2 1.0.1 defaults use `gpt-4.1-2025-04-14` for both the user simulator
and its official NL-assertion evaluator. Supply its credential only through the
environment; the bridge rejects credential-like keys in argument JSON and never copies
secret values into evidence. It invokes the official `run_single_task` API once per
task so the protocol's full 32-bit SHA-256 seed reaches the target and user simulator
unchanged, instead of being replaced by the batch runner's trial-seed generator:

```bash
/srv/matric-eval/benchmarks/tau2-v1.0.1/.venv/bin/python \
  scripts/run_qwen38_tau.py \
  studies/qwen38-obliteration-2026-09/protocol.yaml \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-manifest.json \
  --model-id qwen38-27b-source-bf16 \
  --model-path /srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --server-receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-agentic-server.json \
  --tau-checkout /srv/matric-eval/benchmarks/tau2-v1.0.1 \
  --inputs-summary /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-agentic-inputs/agentic-inputs-summary.json \
  --scored-ids /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-agentic-inputs/tau3-scored-ids.json \
  --user-model gpt-4.1-2025-04-14 \
  --nl-evaluator-model gpt-4.1-2025-04-14 \
  --required-secret-env OPENAI_API_KEY \
  --result-dir /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-tau-raw \
  --receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-tau-receipt.json
```

Terminal-Bench uses Harbor 0.22.0, its Terminus 2 agent, the pinned local task
checkout, and each task's official container verifier. As with tau, the bridge creates
one concurrency-one job per selected task so the full protocol seed is supplied to
every model call. Harbor's complete job directories are private; the separate receipt
contains only hashes, official rewards, exception classes, timing, and version data:

Harbor must use the isolated daemon on `/run/matric-eval-docker.sock`, whose data root
is on the model filesystem. Install `host/matric-eval-docker-daemon.json` as that
daemon's configuration and restart the transient service. Its default bridge stays
disabled, while iptables/NAT are enabled only for Harbor-created networks allocated
from the non-overlapping `10.241.0.0/16` pool. Grant the evaluation account access to
that dedicated socket (for this host, `sudo setfacl -m u:roctinam:rw
/run/matric-eval-docker.sock`) after each daemon restart. The bridge validates the
daemon configuration, socket access, and data root before creating any study output.

```bash
/srv/matric-eval/benchmarks/harbor-0.22.0/.venv/bin/python \
  scripts/run_qwen38_terminal.py \
  studies/qwen38-obliteration-2026-09/protocol.yaml \
  /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-manifest.json \
  --model-id qwen38-27b-source-bf16 \
  --model-path /srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --server-receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-agentic-server.json \
  --terminal-checkout /srv/matric-eval/benchmarks/terminal-bench-2-1-5c8eadf1 \
  --harbor-python /srv/matric-eval/benchmarks/harbor-0.22.0/.venv/bin/python \
  --harbor-executable /srv/matric-eval/benchmarks/harbor-0.22.0/.venv/bin/harbor \
  --inputs-summary /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-agentic-inputs/agentic-inputs-summary.json \
  --scored-ids /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-agentic-inputs/terminal-bench-scored-ids.json \
  --result-dir /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-terminal-raw \
  --receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-terminal-receipt.json
```

After both score passes match and all three MT-Bench second-turn batches finish, build
the content-free public pilot summary. It reports only pipeline-validation metrics and
scales the first-turn and MT-Bench second-turn timings separately, including both cold
model initializations. Agentic execution and judge time remain explicitly pending
until those lanes complete. Because the earlier first-turn-only summary is immutable,
write the complete direct-pilot summary to a distinct path:

```bash
uv run python scripts/build_qwen38_pilot_summary.py \
  --protocol studies/qwen38-obliteration-2026-09/protocol.yaml \
  --result-root /srv/matric-eval/results/qwen38-obliteration-2026-09 \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/public/pilot-summary-complete-direct.json
```

After an artifact qualification manifest has recorded and verified every indexed
tensor and required support-file SHA-256, execute each locked allocation batch on the
leased A100. The request path below is illustrative; use one of the immutable files
from `pilot-inputs/` and a distinct output path for each allocation and model:

```bash
uv run matric-eval qualify-study-model \
  studies/qwen38-obliteration-2026-09/protocol.yaml \
  --model-id qwen38-27b-source-bf16 \
  --model-path /srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/source-model-qualification.json

scripts/run_qwen38_offline_container.sh \
  --gpu GPU-170a99ee-850f-2182-1050-4e8d3c87b6b0 \
  --owner matric-eval-qwen38-source-xstest-safe \
  --model-id qwen38-27b-source-bf16 \
  --model-path /srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --qualification /srv/matric-eval/results/qwen38-obliteration-2026-09/source-model-qualification.json \
  --requests /srv/matric-eval/results/qwen38-obliteration-2026-09/pilot-inputs/xstest-safe-requests.jsonl \
  --lease-receipt /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-xstest-safe-gpu-lease.json \
  --output /srv/matric-eval/results/qwen38-obliteration-2026-09/source-pilot-xstest-safe.jsonl \
  --ready-base /srv/matric-eval/results/qwen38-obliteration-2026-09/run-control/source-pilot-xstest-safe
```

Choose the GPU UUID from the preregistered crossover schedule after `docker gpu
discover`; the UUID above is an example assignment, not a claim of availability.
The wrapper's outer broker command maintains the heartbeat and releases only after the
container has exited and freed CUDA memory. The runner writes a token-specific readiness marker
only after vLLM has made the model resident, waits for the broker to report that exact
scoped lease as active, captures the private mode-`0600` lease receipt, and only then
starts generation. The broker allows 900 seconds for a cold checkpoint prefetch and
engine warmup while its five-minute lease TTL continues to be heartbeated. Use a
unique owner, readiness base, receipt, and output for every
allocation/model invocation. The wrapper verifies that the dedicated Docker socket
contains the exact image digest and resolves to the isolated daemon whose data root is
on the model filesystem; never pull this image into the nearly full system Docker root.

The primary comparison is text-only. The pinned vLLM engine therefore runs with
`language_model_only=true`, which disables every multimodal input and skips loading and
profiling the Qwen vision tower. This keeps source and derivative inference paths
comparable: E03 does not contain the source model's vision-tower tensors, and none of
the frozen requests contain image or video input.

E03 is packaged directly as `Qwen3_5ForCausalLM`, while the source and Pliny artifacts
wrap the same text implementation in `Qwen3_5ForConditionalGeneration`. vLLM 0.26
ships the text class but does not list it in its built-in registry, so the runner uses
vLLM's public `ModelRegistry.register_model` API to bind the declared causal-LM
architecture to a minimal study adapter around the pinned built-in implementation.
The adapter supplies the interfaces omitted by vLLM's unregistered causal-LM class:
text M-RoPE uses three identical position rows and zero delta, exactly matching vLLM's
multimodal wrapper for a prompt without media, while hybrid GDN/Mamba cache metadata is
delegated to that same pinned wrapper. It rejects any multimodal features. The
registration target is frozen in `protocol.yaml` and copied into every result row; it
changes loader routing and fills those interface gaps, not the language-model
implementation or checkpoint tensors.

Each invocation may contain one allocation or multiple complete allocation blocks in
protocol order. This supports benchmark-specific scoring and MT-Bench's dependent
second turn without weakening cohort identity: partial allocation samples are refused.
The runner also refuses an unqualified artifact, a mismatched template, a non-A100
hostname, or an existing output path. It records each derived seed and prompt hash
next to the completion; records the immutable checkpoint architecture, exact request
batch hash and size, initialization time, and generation time; and hashes the lease
and model qualification evidence. Because vLLM's deterministic scheduling is not
batch-invariant for Qwen GDN, the request-batch hash and order are part of the primary
inference contract and must match across models.

## Primary sources

- Model cards: [Qwen source](https://huggingface.co/Qwen/Qwen3.8-27B),
  [E03](https://huggingface.co/manitcor/Qwen3.8-27B-Obliterated-E03), and
  [Pliny V3](https://huggingface.co/OBLITERATUS/Qwen3.8-27B-OBLITERATED).
- Refusal datasets and protocols: [XSTest](https://github.com/paul-rottger/xstest),
  [OR-Bench](https://github.com/justincui03/or-bench), and
  [StrongREJECT](https://github.com/dsbowen/strong_reject).
- Agentic protocols: [BFCL](https://github.com/ShishirPatil/gorilla),
  [tau3-bench](https://github.com/sierra-research/tau2-bench), and
  [Terminal-Bench 2.1](https://github.com/terminal-bench/terminal-bench-2-1).
- Runtime controls: vLLM's official
  [reproducibility guidance](https://docs.vllm.ai/en/stable/usage/reproducibility/)
  and [batch-invariance documentation](https://docs.vllm.ai/en/stable/features/batch_invariance/).

All repository and dataset URLs resolve to the immutable revisions in `protocol.yaml`.
Model-card scores are treated as self-reported background, never as this study's
baseline.
