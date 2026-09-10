# UC: Native one-or-more GPU resident execution

## Primary actor

Study operator executing a protocol-qualified model on a broker-managed GPU host.

## Main success scenario

1. The operator selects a protocol-authorized parallelism profile and an ordered set of exact GPU UUIDs.
2. Preflight validates device count, model compatibility, GPU model, topology, runtime image, storage, and exact command inputs.
3. The lifecycle persists the full allocation intent before requesting one aggregate broker lease.
4. Docker exposes exactly the leased UUIDs and vLLM starts one replica using the declared parallelism profile.
5. Readiness and server receipts attest the same device set and effective parallelism.
6. Evaluation runs without changing the selected allocation.
7. Cleanup proves all owned workers and CUDA allocations are gone before releasing the exact lease and storage reservation.

## Alternate paths

- A one-GPU legacy configuration is normalized to a one-element allocation.
- Insufficient aggregate capacity returns a structured rejection without launch.
- Any device/profile/topology mismatch fails before model load.
- Any partial cleanup leaves the entire allocation obligation pending.

## Acceptance outcomes

- Existing one-GPU schedules and evidence remain readable.
- New configurations cannot contain duplicate, empty, indexed, mixed-model, or unleased GPUs.
- The first multi-GPU production profile is two A100s with TP2; unsupported degrees fail closed.
