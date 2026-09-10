# Native 1+ GPU execution: current-state audit

## Repository assumption map

| Surface | Current state | Required change |
|---|---|---|
| `resource_lifecycle.py` | Record and broker RPC use `gpu_uuids`, but `prepare` and CLI accept one `gpu` scalar. | Canonical non-empty ordered UUID collection; repeated CLI option; overlap and cleanup tests for multiple devices. |
| `schedule_cli.py` | `ResidentService.gpu: str` and controller argv emit one `--gpu`. | Versioned `gpus` field with backward-compatible scalar migration and stable fingerprints. |
| `serve_qwen38_container.sh` | One Bash scalar drives broker scope and Docker `device=`. | Repeated exact UUIDs, aggregate VRAM, declared parallelism profile, count validation, correctly quoted Docker selection. |
| `run_qwen38_offline_container.sh` | Legacy broker wrapper and Docker launch are singular. | Migrate to the same allocation/profile contract or explicitly retire the path. |
| `server_cli.py` | vLLM arguments come only from protocol `tensor_parallel_size`. | Select a protocol-authorized profile and attest the effective TP/PP/device count. |
| `protocol.py` / study YAML | Validator requires tensor parallel size exactly 1. | Define valid parallelism profiles and invariants without silently changing frozen runs. |
| `batch.py` | Lease capture already checks the complete visible list exactly. | Retain behavior; add multi-device receipt and ordering tests. |
| `run_qwen38_paired_replay.py` | Constant `GPU`, `[GPU]` cleanup comparison, scalar schedule entry. | Consume the canonical allocation and exact set cleanup contract. |
| `render_qwen38_report.py` | Reports protocol tensor-parallel value rather than a selected runtime profile. | Render attested effective profile and topology evidence. |
| Docs/tests | Examples and assertions repeatedly say one GPU. | Add 1/2-GPU matrices, migration examples, and target-host qualification. |

## Deployed broker capability

The Basilisk broker executable SHA-256 is `c5ff7b5c33bd5160b177179df0403543aac338464ab97a94f19b74f43dc0f37e`. Its `acquire` and `run` commands accept repeated `--gpu`; the control RPC accepts `gpu_uuids`; `_plan_lease_gpus` deduplicates exact UUIDs, rejects conflicts/unknown devices, and compares `requested_mib` with aggregate free MiB across the scoped devices.

## Target-host facts

- Three NVIDIA A100 80GB PCIe devices are available; the fourth GPU is a 2GB display card and must never enter an A100 profile.
- GPU0 and GPU2 have an NV12 link. GPU0/GPU1 and GPU1/GPU2 report CUDA P2P support over PCIe topology.
- The Qwen3.5 text configuration has hidden size 5120, 24 attention heads, 4 KV heads, 16 linear key heads, and 48 linear value heads. These dimensions support a two-way split; three-way support is not assumed.
- Existing unrelated workloads make single-device 75GiB admission fragile. A two-A100 exact scope can satisfy the aggregate broker reservation while reducing per-device model pressure.

## Compatibility constraints

Existing serialized schedules, fingerprints, evidence, and documentation use the scalar field. Migration must be explicit and deterministic so old evidence remains readable and new evidence cannot ambiguously represent the same allocation in two forms.
