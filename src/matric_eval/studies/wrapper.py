"""Protocol-aware GPU binding for study shell wrappers and replay tools."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from matric_eval.studies.gpu import (
    GpuAllocation,
    GpuExecutionBinding,
    registered_parallelism_profile,
)
from matric_eval.studies.protocol import StudyProtocol


@dataclass(frozen=True)
class WrapperGpuContract:
    """Validated argv-safe projection of one protocol execution binding."""

    binding: GpuExecutionBinding

    @property
    def docker_selector(self) -> str:
        return "device=" + ",".join(self.binding.allocation.gpu_uuids)

    @property
    def lifecycle_arguments(self) -> tuple[str, ...]:
        allocation = self.binding.allocation
        arguments = ["--memory-mib", str(allocation.memory_mib)]
        if allocation.topology_policy is not None:
            arguments.extend(["--topology-policy", allocation.topology_policy])
        for gpu_uuid in allocation.gpu_uuids:
            arguments.extend(["--gpu", gpu_uuid])
        return tuple(arguments)

    def to_dict(self) -> dict[str, object]:
        allocation = self.binding.allocation
        return {
            "parallelism_profile": self.binding.profile.id,
            "gpu_uuids": list(allocation.gpu_uuids),
            "memory_mib": allocation.memory_mib,
            "topology_policy": allocation.topology_policy,
            "docker_selector": self.docker_selector,
            "lifecycle_arguments": list(self.lifecycle_arguments),
            "allocation": allocation.to_dict(),
            "allocation_sha256": allocation.fingerprint(),
            "binding_sha256": self.binding.fingerprint(),
        }


def resolve_wrapper_gpu_contract(
    study: StudyProtocol,
    gpu_uuids: Sequence[str],
    *,
    parallelism_profile: str | None = None,
) -> WrapperGpuContract:
    """Bind repeated exact UUID arguments to the protocol's registered profile."""

    selected = registered_parallelism_profile(
        parallelism_profile if parallelism_profile is not None else study.parallelism_profile
    )
    if selected.id != study.parallelism_profile.id:
        raise ValueError(
            "wrapper parallelism profile must exactly match the protocol-declared profile"
        )
    allocation = GpuAllocation(
        gpu_uuids=tuple(gpu_uuids),
        memory_mib=selected.required_device_count * selected.minimum_memory_mib_per_device,
        topology_policy=selected.topology_policy,
    )
    return WrapperGpuContract(GpuExecutionBinding(allocation=allocation, profile=selected))


def _lines(contract: WrapperGpuContract) -> str:
    payload = contract.to_dict()
    values = (
        payload["docker_selector"],
        payload["memory_mib"],
        payload["topology_policy"] or "-",
        payload["parallelism_profile"],
        json.dumps(payload["allocation"], sort_keys=True, separators=(",", ":")),
    )
    return "\n".join(str(value) for value in values) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--gpu", action="append", required=True)
    parser.add_argument("--parallelism-profile")
    parser.add_argument("--format", choices=("json", "lines"), default="json")
    args = parser.parse_args(argv)
    study = StudyProtocol.from_yaml(args.protocol)
    contract = resolve_wrapper_gpu_contract(
        study,
        args.gpu,
        parallelism_profile=args.parallelism_profile,
    )
    if args.format == "lines":
        print(_lines(contract), end="")
    else:
        print(json.dumps(contract.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
