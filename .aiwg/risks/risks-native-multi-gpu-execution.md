# Risk register: native 1+ GPU execution

| ID | Risk | Severity | Mitigation / evidence |
|---|---|---:|---|
| MG-01 | Partial cleanup releases a lease while one rank survives. | Critical | Exact container cgroup plus per-GPU CUDA scan; fail entire set pending; kill-path integration tests. |
| MG-02 | Ambiguous scalar/list migration changes schedule fingerprints. | High | One canonical serialized form; explicit versioned compatibility reader; golden evidence tests. |
| MG-03 | Docker exposes more or different GPUs than leased. | Critical | UUID-only selection; in-container enumeration equals lease order/set; no `all` or indexes. |
| MG-04 | Protocol says TP1 while runtime uses TP2. | High | Protocol-authorized named profiles; selected profile in canonical plan and server receipt. |
| MG-05 | Bad topology or IOMMU/ACS causes NCCL failure or corruption. | Critical | Fresh target-host P2P/topology canary; qualification receipt; no unsupported profile promotion. |
| MG-06 | Aggregate VRAM passes while per-rank headroom is insufficient. | High | Per-device minimums in profile plus resident model-load qualification; retain aggregate broker reservation. |
| MG-07 | Multi-worker startup exceeds freshness/readiness windows. | Medium | Profile-specific bounded readiness and admission freshness tests. |
| MG-08 | Three A100s are assumed to support TP3. | Medium | Initial allowlist is TP1/TP2 only; model-dimension and runtime proof required for additions. |
