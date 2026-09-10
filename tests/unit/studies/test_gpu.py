from __future__ import annotations

from copy import deepcopy

import pytest

from matric_eval.studies.gpu import (
    A100_80GB_PCIE,
    A100_TP1_PROFILE,
    A100_TP1_PROFILE_ID,
    A100_TP2_PROFILE,
    A100_TP2_PROFILE_ID,
    GPU_ALLOCATION_SCHEMA,
    GPU_EXECUTION_BINDING_SCHEMA,
    NVLINK_P2P_TOPOLOGY_POLICY,
    GpuAllocation,
    GpuAllocationSource,
    GpuContractError,
    GpuContractErrorCode,
    GpuExecutionBinding,
    ParallelismProfile,
    read_gpu_allocation,
    registered_parallelism_profile,
    validate_gpu_binding,
)

GPU_A = "GPU-170a99ee-850f-2182-1050-4e8d3c87b6b0"
GPU_B = "GPU-3538758b-6ba7-fa1b-a80c-e315a606c3f0"


def assert_code(error: pytest.ExceptionInfo[GpuContractError], code: GpuContractErrorCode) -> None:
    assert error.value.code is code
    assert str(error.value).startswith(code.value + ":")


def tp1_allocation() -> GpuAllocation:
    return GpuAllocation(gpu_uuids=(GPU_A,), memory_mib=75_000)


def tp2_allocation() -> GpuAllocation:
    return GpuAllocation(
        gpu_uuids=(GPU_A, GPU_B),
        memory_mib=75_000,
        topology_policy=NVLINK_P2P_TOPOLOGY_POLICY,
    )


def test_allocation_round_trip_preserves_rank_order_and_fingerprint() -> None:
    allocation = tp2_allocation()

    assert allocation.gpu_uuids == (GPU_A, GPU_B)
    assert allocation.to_dict()["gpu_uuids"] == [GPU_A, GPU_B]
    assert GpuAllocation.from_dict(allocation.to_dict()) == allocation
    assert GpuAllocation.from_dict(allocation.to_dict()).fingerprint() == allocation.fingerprint()
    assert (
        GpuAllocation(
            gpu_uuids=(GPU_B, GPU_A),
            memory_mib=75_000,
            topology_policy=NVLINK_P2P_TOPOLOGY_POLICY,
        ).fingerprint()
        != allocation.fingerprint()
    )


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"gpu_uuids": (), "memory_mib": 1}, GpuContractErrorCode.EMPTY_ALLOCATION),
        (
            {"gpu_uuids": (GPU_A, GPU_A), "memory_mib": 1},
            GpuContractErrorCode.DUPLICATE_GPU_UUID,
        ),
        (
            {"gpu_uuids": ("0",), "memory_mib": 1},
            GpuContractErrorCode.MALFORMED_GPU_UUID,
        ),
        (
            {"gpu_uuids": ("all",), "memory_mib": 1},
            GpuContractErrorCode.MALFORMED_GPU_UUID,
        ),
        (
            {"gpu_uuids": (GPU_A,), "memory_mib": True},
            GpuContractErrorCode.INVALID_MEMORY_MIB,
        ),
        (
            {"gpu_uuids": (GPU_A,), "memory_mib": 0},
            GpuContractErrorCode.INVALID_MEMORY_MIB,
        ),
        (
            {"gpu_uuids": (GPU_A,), "memory_mib": 1, "topology_policy": "NVLink"},
            GpuContractErrorCode.INVALID_IDENTIFIER,
        ),
    ],
)
def test_allocation_rejects_invalid_values(
    kwargs: dict[str, object], code: GpuContractErrorCode
) -> None:
    with pytest.raises(GpuContractError) as error:
        GpuAllocation(**kwargs)  # type: ignore[arg-type]
    assert_code(error, code)


def test_allocation_parser_rejects_unknown_version_and_fields() -> None:
    payload = tp1_allocation().to_dict()
    payload["schema"] = "matric-eval.gpu-allocation/2"
    with pytest.raises(GpuContractError) as error:
        GpuAllocation.from_dict(payload)
    assert_code(error, GpuContractErrorCode.UNSUPPORTED_SCHEMA)

    payload = tp1_allocation().to_dict()
    payload["ambient_gpu_count"] = 8
    with pytest.raises(GpuContractError) as error:
        GpuAllocation.from_dict(payload)
    assert_code(error, GpuContractErrorCode.UNKNOWN_FIELD)


def test_only_tp1_and_tp2_a100_profiles_are_registered() -> None:
    assert registered_parallelism_profile(A100_TP1_PROFILE_ID) is A100_TP1_PROFILE
    assert registered_parallelism_profile(A100_TP2_PROFILE_ID) is A100_TP2_PROFILE
    assert A100_TP1_PROFILE.required_device_count == 1
    assert A100_TP2_PROFILE.required_device_count == 2

    with pytest.raises(GpuContractError) as error:
        registered_parallelism_profile("a100-80gb-pcie-tp3/1")
    assert_code(error, GpuContractErrorCode.UNSUPPORTED_PROFILE)


def test_profile_rejects_count_mismatch_and_changed_registered_definition() -> None:
    with pytest.raises(GpuContractError) as error:
        ParallelismProfile(
            id="a100-80gb-pcie-tp2-bad/1",
            tensor_parallel_size=2,
            pipeline_parallel_size=1,
            required_device_count=1,
            supported_accelerator_model=A100_80GB_PCIE,
            minimum_memory_mib_per_device=37_500,
        )
    assert_code(error, GpuContractErrorCode.INVALID_PARALLELISM)

    changed = A100_TP2_PROFILE.to_dict()
    changed["minimum_memory_mib_per_device"] = 1
    with pytest.raises(GpuContractError) as error:
        registered_parallelism_profile(changed)
    assert_code(error, GpuContractErrorCode.PROFILE_DEFINITION_MISMATCH)


def test_tp1_and_tp2_bindings_validate_observed_hardware() -> None:
    assert (
        validate_gpu_binding(
            tp1_allocation(),
            A100_TP1_PROFILE,
            observed_accelerator_models=[A100_80GB_PCIE],
            available_memory_mib=[75_000],
        )
        is A100_TP1_PROFILE
    )
    assert (
        validate_gpu_binding(
            tp2_allocation(),
            A100_TP2_PROFILE_ID,
            observed_accelerator_models=[A100_80GB_PCIE, A100_80GB_PCIE],
            available_memory_mib=[40_000, 40_000],
        )
        is A100_TP2_PROFILE
    )


@pytest.mark.parametrize(
    ("allocation", "profile", "models", "memory", "code"),
    [
        (
            tp1_allocation(),
            A100_TP2_PROFILE,
            None,
            None,
            GpuContractErrorCode.PROFILE_DEVICE_COUNT_MISMATCH,
        ),
        (
            GpuAllocation(gpu_uuids=(GPU_A, GPU_B), memory_mib=75_000),
            A100_TP2_PROFILE,
            None,
            None,
            GpuContractErrorCode.TOPOLOGY_POLICY_MISMATCH,
        ),
        (
            GpuAllocation(
                gpu_uuids=(GPU_A, GPU_B),
                memory_mib=74_999,
                topology_policy=NVLINK_P2P_TOPOLOGY_POLICY,
            ),
            A100_TP2_PROFILE,
            None,
            None,
            GpuContractErrorCode.INSUFFICIENT_AGGREGATE_MEMORY,
        ),
        (
            tp2_allocation(),
            A100_TP2_PROFILE,
            [A100_80GB_PCIE],
            None,
            GpuContractErrorCode.ACCELERATOR_COUNT_MISMATCH,
        ),
        (
            tp2_allocation(),
            A100_TP2_PROFILE,
            [A100_80GB_PCIE, "NVIDIA H100 80GB HBM3"],
            None,
            GpuContractErrorCode.MIXED_ACCELERATOR_MODELS,
        ),
        (
            tp2_allocation(),
            A100_TP2_PROFILE,
            ["NVIDIA H100 80GB HBM3", "NVIDIA H100 80GB HBM3"],
            None,
            GpuContractErrorCode.UNSUPPORTED_ACCELERATOR_MODEL,
        ),
        (
            tp2_allocation(),
            A100_TP2_PROFILE,
            None,
            [40_000],
            GpuContractErrorCode.DEVICE_MEMORY_COUNT_MISMATCH,
        ),
        (
            tp2_allocation(),
            A100_TP2_PROFILE,
            None,
            [40_000, 37_499],
            GpuContractErrorCode.INSUFFICIENT_DEVICE_MEMORY,
        ),
    ],
)
def test_binding_rejects_mismatched_or_unsupported_hardware(
    allocation: GpuAllocation,
    profile: ParallelismProfile,
    models: list[str] | None,
    memory: list[int] | None,
    code: GpuContractErrorCode,
) -> None:
    with pytest.raises(GpuContractError) as error:
        validate_gpu_binding(
            allocation,
            profile,
            observed_accelerator_models=models,
            available_memory_mib=memory,
        )
    assert_code(error, code)


def test_execution_binding_has_versioned_stable_round_trip() -> None:
    binding = GpuExecutionBinding(allocation=tp2_allocation(), profile=A100_TP2_PROFILE)
    payload = binding.to_dict()

    assert payload["schema"] == GPU_EXECUTION_BINDING_SCHEMA
    assert GpuExecutionBinding.from_dict(payload) == binding
    assert GpuExecutionBinding.from_dict(payload).fingerprint() == binding.fingerprint()


def test_legacy_reader_normalizes_without_mutating_source_evidence() -> None:
    legacy = {
        "command": ["serve"],
        "gpu": GPU_A,
        "memory_mib": 75_000,
        "ready_timeout_seconds": 900.0,
    }
    before = deepcopy(legacy)
    first = read_gpu_allocation(legacy)
    second = read_gpu_allocation(legacy)

    assert legacy == before
    assert first.source_format is GpuAllocationSource.LEGACY_SCALAR_V1
    assert first.allocation == tp1_allocation()
    assert first.source_sha256 == second.source_sha256

    native = read_gpu_allocation(tp1_allocation().to_dict())
    assert native.source_format is GpuAllocationSource.NATIVE_V1
    assert native.allocation.fingerprint() == first.allocation.fingerprint()
    assert native.source_sha256 != first.source_sha256


def test_reader_accepts_nested_native_record_and_rejects_ambiguous_record() -> None:
    record = {"gpu_allocation": tp2_allocation().to_dict(), "service": "vllm"}
    assert read_gpu_allocation(record).allocation == tp2_allocation()

    record["gpu"] = GPU_A
    with pytest.raises(GpuContractError) as error:
        read_gpu_allocation(record)
    assert_code(error, GpuContractErrorCode.AMBIGUOUS_ALLOCATION_RECORD)


def test_native_wire_schema_is_explicit() -> None:
    assert tp1_allocation().to_dict()["schema"] == GPU_ALLOCATION_SCHEMA
