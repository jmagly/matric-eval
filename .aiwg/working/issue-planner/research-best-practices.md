# Native 1+ GPU execution: best-practices audit

## Objective

Make every resident model execution path represent and verify one or more exact GPUs without weakening lease ownership, cleanup, provenance, or single-GPU compatibility.

## Recommended patterns

- Model the allocation as one ordered, non-empty set of exact GPU UUIDs plus aggregate requested VRAM. Do not retain parallel scalar and list representations.
- Keep resource allocation separate from model parallelism. A GPU set answers ownership and isolation; a parallelism profile answers how vLLM maps one model replica onto that set.
- Require the selected profile to consume exactly the leased devices. Reject duplicates, unknown devices, partial visibility, and profile/device-count mismatches before launch.
- Preserve the ordered UUID list from request through broker lease, `CUDA_VISIBLE_DEVICES`, Docker device selection, readiness marker, server receipt, scheduler fingerprint, and cleanup.
- Treat cleanup as set-atomic. A surviving CUDA process or mismatched lease on any member keeps the whole resource obligation pending.
- Qualify topology before expensive model load. Record P2P capability and link class, but avoid hard-coded NCCL tuning unless a target-host qualification proves it necessary.
- Keep one-GPU configuration valid as a first-class profile and provide an explicit migration path for existing `gpu` scalar inputs.

## Anti-patterns

- Calling tensor parallelism generic GPU-memory aggregation. vLLM shards a model; CUDA does not expose arbitrary devices as one undifferentiated allocation.
- Inferring tensor-parallel size from whatever devices happen to be visible.
- Allowing a CLI override that is absent from the protocol and therefore missing from canonical study identity.
- Releasing a multi-GPU lease after checking only one device or only free VRAM.
- Using `--gpus all`, indexes, or ambient device order in an evidence-bearing run.
- Selecting three-way tensor parallelism merely because three A100s exist; model dimensions and runtime support must be qualified for the selected degree.

## Local applicability

The current lifecycle already stores `gpu_uuids`, compares exact lease lists, joins them for `CUDA_VISIBLE_DEVICES`, and checks CUDA processes across the list. The principal refactor is to make the public inputs and all consumers match this existing internal set representation.
