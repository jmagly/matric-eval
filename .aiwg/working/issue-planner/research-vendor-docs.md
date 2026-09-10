# Native 1+ GPU execution: vendor documentation review

## vLLM

- vLLM documents tensor parallelism as sharding model parameters across multiple GPUs on one node. `--tensor-parallel-size N` is the serving control for an N-GPU tensor-parallel replica.
- vLLM recommends single-node tensor parallelism when a model does not fit on one GPU. Pipeline parallelism is an alternative for uneven splits or unfavorable interconnects.
- On a single node, vLLM normally uses multiprocessing when the configured parallel world size fits the visible GPU count.

References:

- https://docs.vllm.ai/en/latest/configuration/optimization/
- https://docs.vllm.ai/en/v0.20.0/serving/parallelism_scaling/
- https://docs.vllm.ai/en/latest/configuration/conserving_memory/

## NVIDIA container runtime

The NVIDIA Container Toolkit documents enumerating multiple specific devices with Docker's `--gpus` device selector. The repository must preserve UUID selection and correct quoting rather than fall back to indexes or `all`.

Reference: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/1.9.0/user-guide.html

## NCCL and topology

NCCL relies on GPU Direct/P2P where available and recommends validating actual P2P capability and bandwidth. PCIe ACS/IOMMU configuration can impair or invalidate GPU P2P even when topology looks plausible. NCCL tuning variables should be diagnostic controls, not unconditional production defaults.

References:

- https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting/gpu_troubleshooting.html
- https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html

## Implication

The supported first profile should be a two-A100, single-node, tensor-parallel replica with an exact two-UUID lease. Qualification must prove Docker visibility, vLLM startup, NCCL/P2P operation, model readiness, request success, receipt integrity, and set-atomic cleanup on Basilisk before it becomes the TAU default.
