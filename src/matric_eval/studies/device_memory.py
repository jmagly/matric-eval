"""Single source of truth for the per-device GPU memory ceiling.

A study declares how much of each card it may use. That declaration has to hold
in three places which previously disagreed: the lease the broker is asked to
reserve, the fraction handed to the model server, and what is actually resident
on the card once the server reports ready. This module owns the arithmetic and
the assertions so those three cannot drift apart.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from matric_eval.studies.gpu import A100_80GB_PCIE, ParallelismProfile

#: Injection point for tests; matches the parts of ``subprocess.run`` used here.
Runner = Callable[..., "subprocess.CompletedProcess[str]"]

#: Advertised total memory per supported accelerator, in MiB.
ACCELERATOR_TOTAL_MIB: Mapping[str, int] = {A100_80GB_PCIE: 81_920}

#: Operator-approved default ceiling.
#:
#: Deliberately below a 90% host limit. The model server's own
#: ``--gpu-memory-utilization`` bounds its allocator but not everything resident
#: for that process: the CUDA context and NCCL communication buffers sit outside
#: the fraction it profiles. The margin keeps observed usage under the host
#: limit rather than exactly at it.
DEFAULT_DEVICE_MEMORY_CEILING = 0.87

MINIMUM_CEILING = 0.5


class DeviceMemoryCeilingError(RuntimeError):
    """Requested or observed device memory exceeds the declared ceiling."""


@dataclass(frozen=True)
class DeviceObservation:
    """One card's memory reading at a point in time."""

    uuid: str
    total_mib: int
    used_mib: int

    @property
    def fraction(self) -> float:
        if self.total_mib <= 0:
            raise DeviceMemoryCeilingError(f"device {self.uuid} reported non-positive capacity")
        return self.used_mib / self.total_mib

    def to_dict(self) -> dict[str, object]:
        return {
            "uuid": self.uuid,
            "total_mib": self.total_mib,
            "used_mib": self.used_mib,
            "used_fraction": round(self.fraction, 6),
        }


def total_mib(accelerator_model: str) -> int:
    """Advertised capacity for a supported accelerator."""
    try:
        return ACCELERATOR_TOTAL_MIB[accelerator_model]
    except KeyError:
        raise DeviceMemoryCeilingError(
            f"no advertised capacity recorded for accelerator {accelerator_model!r}; "
            "add it to ACCELERATOR_TOTAL_MIB before declaring a ceiling against it"
        ) from None


def validate_ceiling(fraction: object, *, path: str) -> float:
    """Accept only a real fraction in [0.5, 1.0)."""
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
        raise ValueError(f"{path} must be a number in [0.5, 1.0)")
    if not MINIMUM_CEILING <= float(fraction) < 1:
        raise ValueError(f"{path} must be in [0.5, 1.0)")
    return float(fraction)


def ceiling_mib(accelerator_model: str, fraction: float) -> int:
    """Largest whole MiB that stays within ``fraction`` of the card."""
    validate_ceiling(fraction, path="device memory ceiling")
    return int(total_mib(accelerator_model) * fraction)


def resolve_ceiling(server: Mapping[str, object]) -> float:
    """The declared ceiling for a model-server block.

    ``max_device_memory_fraction`` is authoritative when present. It defaults to
    ``gpu_memory_utilization`` so an existing protocol keeps its behaviour.
    """
    declared = server.get("max_device_memory_fraction")
    if declared is None:
        declared = server.get("gpu_memory_utilization")
    return validate_ceiling(
        declared, path="study.execution.model_server.max_device_memory_fraction"
    )


def assert_profile_within_ceiling(profile: ParallelismProfile, fraction: float) -> None:
    """Refuse a profile whose per-device reservation exceeds the ceiling.

    ``minimum_memory_mib_per_device`` becomes the lease the broker is asked to
    reserve, so a value above the ceiling commits more of the card than policy
    allows even when the server's own allocator stays under it.
    """
    allowed = ceiling_mib(profile.supported_accelerator_model, fraction)
    if profile.minimum_memory_mib_per_device > allowed:
        raise DeviceMemoryCeilingError(
            f"parallelism profile {profile.id!r} reserves "
            f"{profile.minimum_memory_mib_per_device} MiB per device, above the "
            f"{fraction:.2%} ceiling of {allowed} MiB for "
            f"{profile.supported_accelerator_model}"
        )


def validate_device_memory_policy(
    server: Mapping[str, object], profile: ParallelismProfile
) -> float:
    """Validate a model-server block against its profile. Returns the ceiling."""
    fraction = resolve_ceiling(server)
    utilization = validate_ceiling(
        server.get("gpu_memory_utilization"),
        path="study.execution.model_server.gpu_memory_utilization",
    )
    if utilization > fraction:
        raise ValueError(
            "study.execution.model_server.gpu_memory_utilization "
            f"({utilization}) must not exceed max_device_memory_fraction ({fraction})"
        )
    assert_profile_within_ceiling(profile, fraction)
    return fraction


def parse_observations(rows: Iterable[str]) -> tuple[DeviceObservation, ...]:
    """Parse ``uuid, total, used`` CSV rows as emitted by nvidia-smi."""
    observations: list[DeviceObservation] = []
    for row in rows:
        if not row.strip():
            continue
        fields = [field.strip() for field in row.split(",")]
        if len(fields) != 3:
            raise DeviceMemoryCeilingError(f"malformed device memory row: {row!r}")
        uuid, total, used = fields
        try:
            observations.append(
                DeviceObservation(
                    uuid=uuid,
                    total_mib=int(total.removesuffix("MiB").strip()),
                    used_mib=int(used.removesuffix("MiB").strip()),
                )
            )
        except ValueError:
            raise DeviceMemoryCeilingError(f"non-integer device memory row: {row!r}") from None
    return tuple(observations)


def query_observations(
    gpu_uuids: Sequence[str], *, run: Runner = subprocess.run
) -> tuple[DeviceObservation, ...]:
    """Read current memory for exactly ``gpu_uuids``."""
    if not gpu_uuids:
        raise DeviceMemoryCeilingError("refusing to sample device memory for an empty allocation")
    completed = run(
        [
            "nvidia-smi",
            f"--id={','.join(gpu_uuids)}",
            "--query-gpu=uuid,memory.total,memory.used",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode:
        raise DeviceMemoryCeilingError(
            f"device memory query failed: {(completed.stderr or '').strip() or completed.returncode}"
        )
    observations = parse_observations((completed.stdout or "").splitlines())
    observed = {observation.uuid for observation in observations}
    missing = [uuid for uuid in gpu_uuids if uuid not in observed]
    if missing:
        raise DeviceMemoryCeilingError(f"device memory query omitted leased devices: {missing}")
    return observations


def assert_within_ceiling(
    observations: Sequence[DeviceObservation], fraction: float, *, stage: str
) -> None:
    """Fail closed when any card is above the ceiling."""
    validate_ceiling(fraction, path="device memory ceiling")
    breaches = [observation for observation in observations if observation.fraction > fraction]
    if breaches:
        detail = "; ".join(
            f"{observation.uuid} at {observation.used_mib}/{observation.total_mib} MiB "
            f"({observation.fraction:.2%})"
            for observation in breaches
        )
        raise DeviceMemoryCeilingError(
            f"{stage}: device memory above the {fraction:.2%} ceiling -- {detail}"
        )


def evidence(observations: Sequence[DeviceObservation], fraction: float) -> dict[str, object]:
    """Receipt payload proving the ceiling held, including the high-water card."""
    if not observations:
        return {"ceiling_fraction": fraction, "devices": [], "high_water_fraction": None}
    peak = max(observations, key=lambda observation: observation.fraction)
    return {
        "ceiling_fraction": fraction,
        "devices": [observation.to_dict() for observation in observations],
        "high_water_uuid": peak.uuid,
        "high_water_fraction": round(peak.fraction, 6),
        "high_water_used_mib": peak.used_mib,
    }
