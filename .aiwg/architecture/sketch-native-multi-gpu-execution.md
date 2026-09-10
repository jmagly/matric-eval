# Architecture sketch: native 1+ GPU execution

```text
Protocol parallelism profile ─┐
                              ├─> ExecutionBinding ─> Preflight/topology receipt
Exact ordered GPU allocation ─┘          │
                                         v
                              ResourceLifecycle intent
                                         │ exact UUID list + aggregate MiB
                                         v
                                 Broker scoped lease
                                         │
                      ┌──────────────────┴──────────────────┐
                      v                                     v
            Docker exact device set                vLLM TP/PP arguments
                      └──────────────────┬──────────────────┘
                                         v
                       readiness + lease + server receipts
                                         │
                                         v
                         set-atomic cgroup/CUDA cleanup
```

## Proposed contracts

- `GpuAllocation`: non-empty ordered unique `gpu_uuids`, positive aggregate `memory_mib`, optional topology policy identifier.
- `ParallelismProfile`: stable ID, tensor/pipeline sizes, required device count, supported GPU model, optional topology policy.
- `ResidentService`: embeds `GpuAllocation` and selected profile ID; accepts legacy `gpu` only through an explicit compatibility validator.
- Resource record schema retains `gpu_uuids` and adds the normalized allocation/profile identity.
- Server receipt records effective TP/PP sizes and exact visible UUIDs; reports consume receipt evidence rather than only protocol defaults.

## Boundary rules

- Broker allocation and vLLM parallelism are separate but cross-validated.
- GPU UUID order is evidence-bearing because it determines CUDA rank order.
- No automatic expansion to all visible devices.
- No partial lease acquisition or release.
