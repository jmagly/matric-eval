"""Single source of truth for the per-device GPU memory ceiling.

A study declares how much of each card it may use. That declaration has to hold
in three places which previously disagreed: the lease the broker is asked to
reserve, the fraction handed to the model server, and what is actually resident
on the card once the server reports ready. This module owns the arithmetic and
the assertions so those three cannot drift apart.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
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

#: Operator override for the per-card ceiling.
#:
#: A study protocol is hash-pinned by its calibration and judge plans and is
#: documented as immutable once a study is underway, so a host owner's ceiling
#: cannot be applied by editing it. This variable clamps the protocol instead:
#: the effective fraction is the tighter of the two, the protocol file stays
#: byte-identical, and its pinned hash keeps verifying.
DEVICE_MEMORY_CEILING_ENV = "MATRIC_EVAL_DEVICE_MEMORY_CEILING"


def legacy_record_reservation_mib() -> int:
    """Reservation assumed for a version-one record that omits ``requested_mib``.

    Version-one records predate the field, so reading one has to assume a
    reservation. That assumption used to be a hardcoded 75,000 MiB, which is
    91.55% of an 81,920 MiB A100 and above the ceiling; derive it instead so a
    historical record cannot reserve more of a card than policy allows.
    """
    return ceiling_mib(A100_80GB_PCIE, DEFAULT_DEVICE_MEMORY_CEILING)


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


def operator_ceiling(env: Mapping[str, str] | None = None) -> float:
    """The host owner's per-card ceiling, from the environment or the default."""
    source = os.environ if env is None else env
    raw = source.get(DEVICE_MEMORY_CEILING_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_DEVICE_MEMORY_CEILING
    try:
        parsed = float(raw)
    except ValueError:
        raise ValueError(f"{DEVICE_MEMORY_CEILING_ENV} must be a number in [0.5, 1.0)") from None
    return validate_ceiling(parsed, path=DEVICE_MEMORY_CEILING_ENV)


def declared_ceiling(server: Mapping[str, object]) -> float:
    """The ceiling the protocol itself declares.

    ``max_device_memory_fraction`` is authoritative when present; it defaults to
    ``gpu_memory_utilization`` so an existing protocol keeps its behaviour.
    """
    # Name the field the value actually came from; reporting the wrong key sends
    # the reader to a field their protocol may not even set.
    field = "max_device_memory_fraction"
    declared = server.get(field)
    if declared is None:
        field = "gpu_memory_utilization"
        declared = server.get(field)
    return validate_ceiling(declared, path=f"study.execution.model_server.{field}")


def resolve_ceiling(server: Mapping[str, object], env: Mapping[str, str] | None = None) -> float:
    """The effective ceiling: the tighter of the protocol and the operator."""
    return min(declared_ceiling(server), operator_ceiling(env))


def effective_utilization(
    server: Mapping[str, object], env: Mapping[str, str] | None = None
) -> float:
    """The fraction actually handed to the model server.

    Clamped by the operator ceiling so a host owner can tighten a pinned
    protocol without editing it.
    """
    declared = validate_ceiling(
        server.get("gpu_memory_utilization"),
        path="study.execution.model_server.gpu_memory_utilization",
    )
    return min(declared, operator_ceiling(env))


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
    server: Mapping[str, object],
    profile: ParallelismProfile,
    env: Mapping[str, str] | None = None,
) -> float:
    """Validate a model-server block against its profile.

    Returns the effective ceiling. A protocol fraction above the operator
    ceiling is not an error: it is clamped, because the protocol is pinned and
    the operator owns the hardware.
    """
    declared = declared_ceiling(server)
    validate_ceiling(
        server.get("gpu_memory_utilization"),
        path="study.execution.model_server.gpu_memory_utilization",
    )
    fraction = min(declared, operator_ceiling(env))
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


def assert_free_from_status(
    status: Mapping[str, object], gpu_uuids: Sequence[str], required_mib: int
) -> tuple[DeviceObservation, ...]:
    """Refuse to launch when a leased card lacks room for its reservation.

    Reads the broker's own device evidence rather than shelling out, so the
    check runs wherever the lifecycle already talks to the broker and stays
    testable without hardware.

    The lease-capture check can only compare advertised capacity, because by
    then the study's own weights are resident. Nothing checked *free* memory
    before the load, so a card already holding a co-tenant was admitted, began
    loading, and was OOM-killed. See issue 213.
    """
    if required_mib <= 0:
        raise DeviceMemoryCeilingError("reservation must be a positive MiB amount")
    rows = status.get("gpus")
    if not rows:
        # An older broker publishes no device section; absence of evidence is
        # not evidence of room, but it is not grounds to block a run either.
        return ()
    if not isinstance(rows, Sequence):
        raise DeviceMemoryCeilingError("broker status device section is malformed")
    by_uuid: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if isinstance(row, Mapping) and isinstance(row.get("uuid"), str):
            by_uuid[str(row["uuid"])] = row
    observations: list[DeviceObservation] = []
    for uuid in gpu_uuids:
        row = by_uuid.get(uuid)
        if row is None:
            raise DeviceMemoryCeilingError(f"broker status omits leased device {uuid}")
        total, used = row.get("total_mib"), row.get("used_mib")
        if not isinstance(total, int) or not isinstance(used, int):
            raise DeviceMemoryCeilingError(f"broker status lacks integer memory for {uuid}")
        observations.append(DeviceObservation(uuid=uuid, total_mib=total, used_mib=used))
    short = [item for item in observations if item.total_mib - item.used_mib < required_mib]
    if short:
        detail = "; ".join(
            f"{item.uuid} has {item.total_mib - item.used_mib} MiB free of {item.total_mib}, "
            f"{item.used_mib} MiB already resident"
            for item in short
        )
        raise DeviceMemoryCeilingError(
            f"leased device lacks room for a {required_mib} MiB reservation -- {detail}"
        )
    return tuple(observations)


def foreign_intrusions(
    status: Mapping[str, object],
    gpu_uuids: Sequence[str],
    baseline: Mapping[str, int],
    owned_pids: Collection[int] = (),
) -> dict[str, int]:
    """Foreign allocations on leased cards that were absent at acquisition.

    ``owned_pids`` are the study's own CUDA processes. The broker calls every
    process it does not itself own "foreign", and the per-lease baseline is taken
    at acquisition, before the study has allocated anything — so without this
    exclusion the study's own model server is reported as an intruder on the very
    card it holds a lease for, and the heartbeat worker aborts the run. See
    issue 218.

    The broker records a per-lease ``foreign_baseline``, so anything on a leased
    UUID that is not in that baseline arrived afterwards and is competing with
    the study for the card it holds a lease on.
    """
    current = status.get("foreign_gpu_processes") or {}
    if not isinstance(current, Mapping):
        raise DeviceMemoryCeilingError("broker status foreign process map is malformed")
    leased = set(gpu_uuids)
    owned = {int(pid) for pid in owned_pids}
    intruders: dict[str, int] = {}
    for key, amount in current.items():
        if key in baseline:
            continue
        # Keys are "pid@GPU-uuid".
        pid, _, uuid = str(key).partition("@")
        if uuid not in leased or not isinstance(amount, int):
            continue
        try:
            if int(pid) in owned:
                continue
        except ValueError:
            # An unparseable pid cannot be proven ours, so treat it as foreign.
            pass
        intruders[str(key)] = amount
    return intruders
