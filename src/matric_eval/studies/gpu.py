"""Versioned, fail-closed contracts for exact one-or-more GPU execution.

GPU allocation and model-server parallelism are deliberately separate
identities.  An allocation records what the broker must reserve; a profile
records how one supported server configuration consumes that reservation.
Neither contract discovers devices or widens a caller-supplied set.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from matric_eval.state.observation_identity import canonical_json

GPU_ALLOCATION_SCHEMA = "matric-eval.gpu-allocation/1"
PARALLELISM_PROFILE_SCHEMA = "matric-eval.parallelism-profile/1"
GPU_EXECUTION_BINDING_SCHEMA = "matric-eval.gpu-execution-binding/1"
LEGACY_SCALAR_GPU_SCHEMA = "matric-eval.legacy-scalar-gpu/1"

A100_80GB_PCIE = "NVIDIA A100 80GB PCIe"
A100_TP1_PROFILE_ID = "a100-80gb-pcie-tp1/1"
A100_TP2_PROFILE_ID = "a100-80gb-pcie-tp2/1"
NVLINK_P2P_TOPOLOGY_POLICY = "nvlink-p2p-required/1"

_GPU_UUID_RE = re.compile(r"^GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?/[1-9][0-9]*$")
_MAX_JSON_INTEGER = 9_007_199_254_740_991


class GpuContractErrorCode(str, Enum):
    """Stable, content-free diagnostics for callers and retained evidence."""

    UNSUPPORTED_SCHEMA = "unsupported_schema"
    MISSING_FIELD = "missing_field"
    UNKNOWN_FIELD = "unknown_field"
    INVALID_FIELD_TYPE = "invalid_field_type"
    EMPTY_ALLOCATION = "empty_allocation"
    MALFORMED_GPU_UUID = "malformed_gpu_uuid"
    DUPLICATE_GPU_UUID = "duplicate_gpu_uuid"
    INVALID_MEMORY_MIB = "invalid_memory_mib"
    INVALID_IDENTIFIER = "invalid_identifier"
    INVALID_PARALLELISM = "invalid_parallelism"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    PROFILE_DEFINITION_MISMATCH = "profile_definition_mismatch"
    PROFILE_DEVICE_COUNT_MISMATCH = "profile_device_count_mismatch"
    TOPOLOGY_POLICY_MISMATCH = "topology_policy_mismatch"
    INSUFFICIENT_AGGREGATE_MEMORY = "insufficient_aggregate_memory"
    ACCELERATOR_COUNT_MISMATCH = "accelerator_count_mismatch"
    MIXED_ACCELERATOR_MODELS = "mixed_accelerator_models"
    UNSUPPORTED_ACCELERATOR_MODEL = "unsupported_accelerator_model"
    DEVICE_MEMORY_COUNT_MISMATCH = "device_memory_count_mismatch"
    INSUFFICIENT_DEVICE_MEMORY = "insufficient_device_memory"
    AMBIGUOUS_ALLOCATION_RECORD = "ambiguous_allocation_record"
    INVALID_SOURCE_RECORD = "invalid_source_record"


class GpuContractError(ValueError):
    """A typed GPU contract failure safe to retain in public diagnostics."""

    def __init__(
        self,
        code: GpuContractErrorCode,
        message: str,
        *,
        path: str | None = None,
    ) -> None:
        self.code = code
        self.path = path
        detail = f"{path}: {message}" if path else message
        super().__init__(f"{code.value}: {detail}")


def _error(
    code: GpuContractErrorCode, message: str, *, path: str | None = None
) -> GpuContractError:
    return GpuContractError(code, message, path=path)


def _validate_schema(actual: object, expected: str, path: str) -> None:
    if actual != expected:
        raise _error(
            GpuContractErrorCode.UNSUPPORTED_SCHEMA,
            f"expected {expected!r}",
            path=path,
        )


def _validate_keys(
    data: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    path: str,
) -> None:
    missing = sorted(required - data.keys())
    if missing:
        raise _error(
            GpuContractErrorCode.MISSING_FIELD,
            ", ".join(missing),
            path=path,
        )
    unknown = sorted(data.keys() - required - optional)
    if unknown:
        raise _error(
            GpuContractErrorCode.UNKNOWN_FIELD,
            ", ".join(unknown),
            path=path,
        )


def _positive_int(value: object, path: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_JSON_INTEGER:
        raise _error(
            GpuContractErrorCode.INVALID_FIELD_TYPE,
            "must be a positive JSON-safe integer",
            path=path,
        )
    return value


def _identifier(value: object, path: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str or not _IDENTIFIER_RE.fullmatch(value):
        raise _error(
            GpuContractErrorCode.INVALID_IDENTIFIER,
            "must be a versioned lowercase identifier",
            path=path,
        )
    return value


def _fingerprint(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(document)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GpuAllocation:
    """One non-empty ordered set requested from the broker as a unit.

    ``gpu_uuids`` order is rank-bearing evidence.  Validation therefore never
    sorts, deduplicates, indexes, or expands it from ambient host visibility.
    ``memory_mib`` is the aggregate request for the whole set, not a claim that
    CUDA exposes a single physically pooled address space.
    """

    gpu_uuids: tuple[str, ...]
    memory_mib: int
    topology_policy: str | None = None
    schema: str = GPU_ALLOCATION_SCHEMA

    def __post_init__(self) -> None:
        _validate_schema(self.schema, GPU_ALLOCATION_SCHEMA, "allocation.schema")
        if not isinstance(self.gpu_uuids, (list, tuple)):
            raise _error(
                GpuContractErrorCode.INVALID_FIELD_TYPE,
                "must be an ordered array",
                path="allocation.gpu_uuids",
            )
        values = tuple(self.gpu_uuids)
        if not values:
            raise _error(
                GpuContractErrorCode.EMPTY_ALLOCATION,
                "at least one exact GPU UUID is required",
                path="allocation.gpu_uuids",
            )
        for index, value in enumerate(values):
            if type(value) is not str or not _GPU_UUID_RE.fullmatch(value):
                raise _error(
                    GpuContractErrorCode.MALFORMED_GPU_UUID,
                    "must be a canonical NVIDIA GPU UUID",
                    path=f"allocation.gpu_uuids[{index}]",
                )
        if len(values) != len(set(values)):
            raise _error(
                GpuContractErrorCode.DUPLICATE_GPU_UUID,
                "GPU UUIDs must be unique",
                path="allocation.gpu_uuids",
            )
        if type(self.memory_mib) is not int or not 1 <= self.memory_mib <= _MAX_JSON_INTEGER:
            raise _error(
                GpuContractErrorCode.INVALID_MEMORY_MIB,
                "must be a positive JSON-safe aggregate MiB value",
                path="allocation.memory_mib",
            )
        topology = _identifier(
            self.topology_policy,
            "allocation.topology_policy",
            optional=True,
        )
        object.__setattr__(self, "gpu_uuids", values)
        object.__setattr__(self, "topology_policy", topology)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GpuAllocation:
        _validate_keys(
            data,
            required={"schema", "gpu_uuids", "memory_mib"},
            optional={"topology_policy"},
            path="allocation",
        )
        return cls(
            schema=data["schema"],
            gpu_uuids=data["gpu_uuids"],
            memory_mib=data["memory_mib"],
            topology_policy=data.get("topology_policy"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "gpu_uuids": list(self.gpu_uuids),
            "memory_mib": self.memory_mib,
            "topology_policy": self.topology_policy,
        }

    def fingerprint(self) -> str:
        """Hash the versioned canonical wire form without changing UUID order."""
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class ParallelismProfile:
    """A versioned declaration of one model-server parallelism shape."""

    id: str
    tensor_parallel_size: int
    pipeline_parallel_size: int
    required_device_count: int
    supported_accelerator_model: str
    minimum_memory_mib_per_device: int
    topology_policy: str | None = None
    schema: str = PARALLELISM_PROFILE_SCHEMA

    def __post_init__(self) -> None:
        _validate_schema(self.schema, PARALLELISM_PROFILE_SCHEMA, "profile.schema")
        profile_id = _identifier(self.id, "profile.id")
        assert profile_id is not None
        tensor = _positive_int(self.tensor_parallel_size, "profile.tensor_parallel_size")
        pipeline = _positive_int(self.pipeline_parallel_size, "profile.pipeline_parallel_size")
        count = _positive_int(self.required_device_count, "profile.required_device_count")
        if tensor * pipeline != count:
            raise _error(
                GpuContractErrorCode.INVALID_PARALLELISM,
                "tensor_parallel_size * pipeline_parallel_size must equal required_device_count",
                path="profile",
            )
        if (
            type(self.supported_accelerator_model) is not str
            or not self.supported_accelerator_model.strip()
            or self.supported_accelerator_model != self.supported_accelerator_model.strip()
        ):
            raise _error(
                GpuContractErrorCode.INVALID_FIELD_TYPE,
                "must be a non-empty canonical model name",
                path="profile.supported_accelerator_model",
            )
        minimum = _positive_int(
            self.minimum_memory_mib_per_device,
            "profile.minimum_memory_mib_per_device",
        )
        topology = _identifier(
            self.topology_policy,
            "profile.topology_policy",
            optional=True,
        )
        object.__setattr__(self, "id", profile_id)
        object.__setattr__(self, "tensor_parallel_size", tensor)
        object.__setattr__(self, "pipeline_parallel_size", pipeline)
        object.__setattr__(self, "required_device_count", count)
        object.__setattr__(self, "minimum_memory_mib_per_device", minimum)
        object.__setattr__(self, "topology_policy", topology)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ParallelismProfile:
        _validate_keys(
            data,
            required={
                "schema",
                "id",
                "tensor_parallel_size",
                "pipeline_parallel_size",
                "required_device_count",
                "supported_accelerator_model",
                "minimum_memory_mib_per_device",
            },
            optional={"topology_policy"},
            path="profile",
        )
        return cls(
            schema=data["schema"],
            id=data["id"],
            tensor_parallel_size=data["tensor_parallel_size"],
            pipeline_parallel_size=data["pipeline_parallel_size"],
            required_device_count=data["required_device_count"],
            supported_accelerator_model=data["supported_accelerator_model"],
            minimum_memory_mib_per_device=data["minimum_memory_mib_per_device"],
            topology_policy=data.get("topology_policy"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "id": self.id,
            "tensor_parallel_size": self.tensor_parallel_size,
            "pipeline_parallel_size": self.pipeline_parallel_size,
            "required_device_count": self.required_device_count,
            "supported_accelerator_model": self.supported_accelerator_model,
            "minimum_memory_mib_per_device": self.minimum_memory_mib_per_device,
            "topology_policy": self.topology_policy,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


A100_TP1_PROFILE = ParallelismProfile(
    id=A100_TP1_PROFILE_ID,
    tensor_parallel_size=1,
    pipeline_parallel_size=1,
    required_device_count=1,
    supported_accelerator_model=A100_80GB_PCIE,
    minimum_memory_mib_per_device=75_000,
)
A100_TP2_PROFILE = ParallelismProfile(
    id=A100_TP2_PROFILE_ID,
    tensor_parallel_size=2,
    pipeline_parallel_size=1,
    required_device_count=2,
    supported_accelerator_model=A100_80GB_PCIE,
    minimum_memory_mib_per_device=37_500,
    topology_policy=NVLINK_P2P_TOPOLOGY_POLICY,
)
PARALLELISM_PROFILES: Mapping[str, ParallelismProfile] = MappingProxyType(
    {
        A100_TP1_PROFILE.id: A100_TP1_PROFILE,
        A100_TP2_PROFILE.id: A100_TP2_PROFILE,
    }
)


def registered_parallelism_profile(
    value: str | ParallelismProfile | Mapping[str, Any],
) -> ParallelismProfile:
    """Resolve only an exact registered profile definition.

    A known ID with altered fields is not silently replaced by the catalog
    value.  This prevents a receipt from claiming TP1 while requesting TP2.
    """
    if isinstance(value, str):
        profile = PARALLELISM_PROFILES.get(value)
        if profile is None:
            raise _error(
                GpuContractErrorCode.UNSUPPORTED_PROFILE,
                "profile is not in the qualified allowlist",
                path="profile.id",
            )
        return profile
    candidate = (
        value if isinstance(value, ParallelismProfile) else ParallelismProfile.from_dict(value)
    )
    profile = PARALLELISM_PROFILES.get(candidate.id)
    if profile is None:
        raise _error(
            GpuContractErrorCode.UNSUPPORTED_PROFILE,
            "profile is not in the qualified allowlist",
            path="profile.id",
        )
    if candidate.to_dict() != profile.to_dict():
        raise _error(
            GpuContractErrorCode.PROFILE_DEFINITION_MISMATCH,
            "profile fields do not match the registered definition",
            path="profile",
        )
    return profile


def validate_gpu_binding(
    allocation: GpuAllocation,
    profile: str | ParallelismProfile | Mapping[str, Any],
    *,
    observed_accelerator_models: Sequence[str] | None = None,
    available_memory_mib: Sequence[int] | None = None,
) -> ParallelismProfile:
    """Cross-validate an allocation against one registered server profile.

    Optional observed hardware values are runtime evidence supplied by a
    preflight adapter; this function never probes the host itself.
    """
    selected = registered_parallelism_profile(profile)
    if len(allocation.gpu_uuids) != selected.required_device_count:
        raise _error(
            GpuContractErrorCode.PROFILE_DEVICE_COUNT_MISMATCH,
            "allocation size does not match the selected profile",
            path="allocation.gpu_uuids",
        )
    if allocation.topology_policy != selected.topology_policy:
        raise _error(
            GpuContractErrorCode.TOPOLOGY_POLICY_MISMATCH,
            "allocation and profile topology policies must agree exactly",
            path="allocation.topology_policy",
        )
    minimum_aggregate = selected.required_device_count * selected.minimum_memory_mib_per_device
    if allocation.memory_mib < minimum_aggregate:
        raise _error(
            GpuContractErrorCode.INSUFFICIENT_AGGREGATE_MEMORY,
            f"profile requires at least {minimum_aggregate} aggregate MiB",
            path="allocation.memory_mib",
        )

    if observed_accelerator_models is not None:
        models = tuple(observed_accelerator_models)
        if len(models) != selected.required_device_count:
            raise _error(
                GpuContractErrorCode.ACCELERATOR_COUNT_MISMATCH,
                "observed accelerator count does not match the profile",
                path="observed_accelerator_models",
            )
        if any(type(model) is not str or not model.strip() for model in models):
            raise _error(
                GpuContractErrorCode.INVALID_FIELD_TYPE,
                "observed accelerator names must be non-empty strings",
                path="observed_accelerator_models",
            )
        if len(set(models)) != 1:
            raise _error(
                GpuContractErrorCode.MIXED_ACCELERATOR_MODELS,
                "one allocation cannot mix accelerator models",
                path="observed_accelerator_models",
            )
        if models[0] != selected.supported_accelerator_model:
            raise _error(
                GpuContractErrorCode.UNSUPPORTED_ACCELERATOR_MODEL,
                "observed accelerator model is not supported by the profile",
                path="observed_accelerator_models",
            )

    if available_memory_mib is not None:
        available = tuple(available_memory_mib)
        if len(available) != selected.required_device_count:
            raise _error(
                GpuContractErrorCode.DEVICE_MEMORY_COUNT_MISMATCH,
                "per-device memory count does not match the profile",
                path="available_memory_mib",
            )
        for index, amount in enumerate(available):
            if type(amount) is not int or amount < selected.minimum_memory_mib_per_device:
                raise _error(
                    GpuContractErrorCode.INSUFFICIENT_DEVICE_MEMORY,
                    (
                        "each device must satisfy the profile minimum of "
                        f"{selected.minimum_memory_mib_per_device} MiB"
                    ),
                    path=f"available_memory_mib[{index}]",
                )
    return selected


@dataclass(frozen=True)
class GpuExecutionBinding:
    """The fingerprinted relationship between an allocation and a profile."""

    allocation: GpuAllocation
    profile: ParallelismProfile
    schema: str = GPU_EXECUTION_BINDING_SCHEMA

    def __post_init__(self) -> None:
        _validate_schema(self.schema, GPU_EXECUTION_BINDING_SCHEMA, "binding.schema")
        selected = validate_gpu_binding(self.allocation, self.profile)
        object.__setattr__(self, "profile", selected)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GpuExecutionBinding:
        _validate_keys(
            data,
            required={"schema", "allocation", "profile"},
            optional=set(),
            path="binding",
        )
        allocation = data["allocation"]
        profile = data["profile"]
        if not isinstance(allocation, Mapping) or not isinstance(profile, Mapping):
            raise _error(
                GpuContractErrorCode.INVALID_FIELD_TYPE,
                "allocation and profile must be objects",
                path="binding",
            )
        return cls(
            schema=data["schema"],
            allocation=GpuAllocation.from_dict(allocation),
            profile=registered_parallelism_profile(profile),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "allocation": self.allocation.to_dict(),
            "profile": self.profile.to_dict(),
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


class GpuAllocationSource(str, Enum):
    """Whether a normalized allocation came from native or legacy evidence."""

    NATIVE_V1 = GPU_ALLOCATION_SCHEMA
    LEGACY_SCALAR_V1 = LEGACY_SCALAR_GPU_SCHEMA


@dataclass(frozen=True)
class GpuAllocationRead:
    """A normalized view that remains bound to the unchanged source record."""

    allocation: GpuAllocation
    source_format: GpuAllocationSource
    source_sha256: str


def read_gpu_allocation(record: Mapping[str, Any]) -> GpuAllocationRead:
    """Read native or legacy scalar allocation evidence without rewriting it.

    A legacy service record supplies ``gpu`` and ``memory_mib``.  Additional
    service fields are retained in ``source_sha256`` but never copied into the
    normalized allocation.  Records containing both scalar and native forms
    are ambiguous and fail closed.
    """
    try:
        source_sha256 = _fingerprint(record)
    except (TypeError, ValueError, OverflowError):
        raise _error(
            GpuContractErrorCode.INVALID_SOURCE_RECORD,
            "source must contain strict finite JSON values",
            path="record",
        ) from None

    has_legacy = "gpu" in record
    has_nested = "gpu_allocation" in record
    has_native = has_nested or "gpu_uuids" in record
    if has_legacy and has_native:
        raise _error(
            GpuContractErrorCode.AMBIGUOUS_ALLOCATION_RECORD,
            "record contains both legacy and native allocation fields",
            path="record",
        )

    if has_nested:
        payload = record["gpu_allocation"]
        if not isinstance(payload, Mapping):
            raise _error(
                GpuContractErrorCode.INVALID_FIELD_TYPE,
                "must be an allocation object",
                path="record.gpu_allocation",
            )
        allocation = GpuAllocation.from_dict(payload)
        return GpuAllocationRead(
            allocation=allocation,
            source_format=GpuAllocationSource.NATIVE_V1,
            source_sha256=source_sha256,
        )

    if "gpu_uuids" in record or record.get("schema") == GPU_ALLOCATION_SCHEMA:
        allocation = GpuAllocation.from_dict(record)
        return GpuAllocationRead(
            allocation=allocation,
            source_format=GpuAllocationSource.NATIVE_V1,
            source_sha256=source_sha256,
        )

    if has_legacy:
        if "schema" in record and record["schema"] not in (None, LEGACY_SCALAR_GPU_SCHEMA):
            raise _error(
                GpuContractErrorCode.UNSUPPORTED_SCHEMA,
                "legacy scalar GPU record has an unknown schema",
                path="record.schema",
            )
        if "memory_mib" not in record:
            raise _error(
                GpuContractErrorCode.MISSING_FIELD,
                "memory_mib",
                path="record",
            )
        allocation = GpuAllocation(
            gpu_uuids=(record["gpu"],),
            memory_mib=record["memory_mib"],
            topology_policy=record.get("topology_policy"),
        )
        return GpuAllocationRead(
            allocation=allocation,
            source_format=GpuAllocationSource.LEGACY_SCALAR_V1,
            source_sha256=source_sha256,
        )

    raise _error(
        GpuContractErrorCode.MISSING_FIELD,
        "expected gpu_allocation, gpu_uuids, or legacy gpu",
        path="record",
    )
