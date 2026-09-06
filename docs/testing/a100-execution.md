# A100 evaluation execution policy

## Scope

All executable validation and evaluation for the current model-comparison work
runs on the A100 host, available through the SSH alias `a100` (hostname
`basilisk`). Local workstations may edit code, inspect diffs, and prepare commits,
but must not run `matric-eval`, pytest, benchmark runners, lint/type gates, model
servers, canaries, or result aggregation.

This boundary keeps dependency, hardware, CUDA, runtime, and host behavior aligned
with the environment that produces the reported measurements. CI evidence from
another host remains useful for general project health but does not qualify an
A100 model-comparison run.

## A100 layout

Use the following paths; do not place new model or dataset caches on the nearly
full root filesystem:

| Purpose | Path |
| --- | --- |
| Source checkout | `/srv/matric-eval/workspaces/matric-eval` |
| uv cache | `/srv/matric-eval/cache/uv` |
| Small dataset cache | `/srv/matric-eval/cache/huggingface` |
| Large model/Hugging Face cache | `/srv/obliteratus/matric-eval/cache/huggingface` |
| External benchmark checkouts | `/srv/matric-eval/benchmarks` |
| Immutable run output | `/srv/matric-eval/results` |

`/srv/obliteratus` is a bind mount on the separate 3.6 TiB model SSD; do not infer
its capacity from `df -h /srv`. Before every dependency sync or benchmark run,
record `df -h / /srv` and `findmnt -T /srv/obliteratus -o
SOURCE,FSTYPE,SIZE,USED,AVAIL,USE%,TARGET`. Never download a second model copy when
a qualified local checkpoint or endpoint is already available. Stop before a run
if the projected cache and result size does not leave a safe operating margin on
the filesystem that will actually hold it.

## Required preflight

Capture this information in the run directory before loading a model:

```bash
hostname
git rev-parse HEAD
uv --version
python --version
nvidia-smi --query-gpu=index,name,uuid,driver_version,memory.total,memory.used \
  --format=csv,noheader
df -h / /srv
findmnt -T /srv/obliteratus -o SOURCE,FSTYPE,SIZE,USED,AVAIL,USE%,TARGET
```

Also record:

- the qualified matrix after validation, including every model and runtime spec;
- the exact benchmark checkout and dataset revisions;
- the selected task IDs and their ordered manifest hash;
- the GPU broker lease or equivalent exclusive allocation receipt;
- model-server command/configuration and endpoint health response;
- installed lockfile digest and package inventory;
- start/end timestamps, exit status, and infrastructure error classification.

Do not infer GPU availability from low utilization. A device with resident memory
belongs to its current lease or process until ownership is explicitly released.

## Validation sequence

From the A100 checkout, with cache paths exported to the locations above:

```bash
uv lock --check
uv sync --extra dev
uv run ruff check .
uv run mypy src
uv run pytest tests/unit
uv run pytest tests
```

Then run registry freshness auditing and external-runner canaries before any full
model matrix. A canary must use fixed task IDs, the same runtime specification as
the intended study, and isolated output paths. Full evaluation begins only after
the canary output proves that tool calls, trajectories, scorers, and result
provenance are being captured correctly.

## Matched-comparison rule

Within a comparison group, hold benchmark revision, ordered task IDs, seed,
prompts, scorer, tool environment, user simulator, token/step/time budgets, and
agent harness constant. Change only the preregistered factor. Run direct endpoint
and full agent-harness measurements as different lanes. Report infrastructure
failures separately; do not convert them to model-quality failures.
