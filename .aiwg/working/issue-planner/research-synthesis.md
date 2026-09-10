# Native 1+ GPU execution: synthesis

## Decision

Adopt a canonical GPU allocation object and a separate protocol-declared model parallelism profile. The initial supported profiles are single-A100 TP1 and two-A100 TP2 on one host. Do not support TP3 until model/runtime qualification exists.

## Consensus findings

1. No broker redesign is required for aggregate capacity: the deployed broker already reserves aggregate MiB over repeated exact GPU UUIDs.
2. Repository inputs are the blocker. Scalar GPU fields occur in lifecycle, scheduler, wrappers, replay, tests, and docs while internal evidence is already list-shaped.
3. Runtime parallelism must be part of study identity. An undocumented CLI override would make reports and protocol hashes misleading.
4. Multi-GPU cleanup must remain fail-closed across the entire set, including lost acknowledgments, partial CUDA survival, and overlapping attempts.
5. Basilisk can qualify TP2. GPU0/GPU2 is the preferred topology because it has NVLink; other A100 pairs require separate performance evidence.

## Open risks

- Existing schedule fingerprints and stored evidence require a schema migration strategy.
- Docker device-selector quoting can silently expose the wrong set if implemented incorrectly.
- vLLM worker subprocesses broaden process/cgroup cleanup coverage and startup time.
- P2P/IOMMU/ACS behavior can differ after host changes; topology evidence needs a freshness policy.
- Runtime profile changes amend the frozen study execution contract and must be explicit in protocol history and reporting.

## Recommended delivery waves

1. Allocation schema/value object and compatibility reader.
2. Lifecycle/scheduler exact-set semantics and protocol parallelism profiles.
3. Wrapper/replay/report migration.
4. Basilisk TP2 qualification and TAU admission.
5. Documentation, deprecation, and release adoption.
