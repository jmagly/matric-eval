# Test strategy: native 1+ GPU execution

## Unit and contract tests

- Normalize legacy scalar and native list allocations to one canonical shape.
- Reject empty, duplicate, malformed, mixed-model, and profile-count-mismatched allocations.
- Verify repeated lifecycle `--gpu`, aggregate memory propagation, exact broker request order, and overlap blocking.
- Exercise multi-GPU lease acceptance, lost acknowledgment recovery, partial CUDA survival, scope mutation, and exact release.
- Verify scheduler fingerprints and persisted bindings are stable after normalization.
- Verify Docker argv encodes the exact UUID set and server argv uses the selected TP/PP profile.
- Verify lease/readiness/server receipts agree on all UUIDs and effective parallelism.
- Keep the full single-GPU regression matrix green.

## Integration tests

- Unix-socket fake broker with two exact GPUs and aggregate capacity.
- Docker shim with two UUIDs, two worker PIDs, and partial-cleanup failure injection.
- Wrapper validation for repeated UUIDs, quoting, duplicate rejection, and unsupported profile rejection.
- Replay cleanup validates exact sets rather than a singleton literal.

## Basilisk qualification

1. Capture GPU model, UUID, topology, P2P, driver/runtime, broker executable hash, and pinned image identity.
2. Prefer GPU0+GPU2 (NV12); request 75,000 MiB aggregate through one exact scoped lease.
3. Confirm the container sees exactly two A100 UUIDs in declared rank order.
4. Run NCCL/P2P smoke plus vLLM TP2 model readiness.
5. Execute content-free inference canary, then the two TAU diagnostic trajectories.
6. Stop and prove both ranks, all CUDA allocations, the container, lease, storage, and mounts are gone.
7. Seal content-free receipts and hashes; never publish prompts, outputs, or lease tokens.
