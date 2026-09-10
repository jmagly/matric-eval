"""Content-free contracts for the Basilisk two-A100 TP2 qualification."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from matric_eval.studies.gpu import (
    A100_80GB_PCIE,
    A100_TP1_PROFILE_ID,
    A100_TP2_PROFILE,
    NVLINK_P2P_TOPOLOGY_POLICY,
    GpuAllocation,
    GpuExecutionBinding,
    validate_gpu_binding,
)
from matric_eval.studies.protocol import StudyProtocol

QUALIFICATION_SCHEMA = "matric-eval.basilisk-tp2-qualification/1"
PROTOCOL_OVERLAY_SCHEMA = "matric-eval.tp2-protocol-overlay/1"
TAU_DIAGNOSTIC_IDS = ("banking_knowledge:task_021", "airline:3")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    """Exclusively and durably create one private JSON evidence file."""

    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite qualification evidence: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(value), handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise FileExistsError(
                f"refusing to overwrite qualification evidence: {path}"
            ) from error
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_tp2_protocol_overlay(source: Path, output: Path) -> dict[str, Any]:
    """Create the one-field TP2 qualification overlay without changing frozen input."""

    source_bytes = source.read_bytes()
    base = StudyProtocol.from_yaml(source, validate_registry=False)
    if base.parallelism_profile.id != A100_TP1_PROFILE_ID:
        raise ValueError(
            "TP2 qualification source protocol must declare the registered TP1 profile"
        )
    raw = copy.deepcopy(base.raw)
    raw["study"]["execution"]["model_server"]["parallelism_profile"] = A100_TP2_PROFILE.id
    qualified = StudyProtocol.from_dict(raw, validate_registry=False)
    if qualified.parallelism_profile is not A100_TP2_PROFILE:
        raise RuntimeError("qualification overlay did not resolve to the registered TP2 profile")
    write_private_json(output, raw)
    output_bytes = output.read_bytes()
    reloaded = StudyProtocol.from_yaml(output, validate_registry=False)
    if reloaded.canonical_sha256 != qualified.canonical_sha256:
        raise RuntimeError("persisted TP2 qualification protocol changed canonical identity")
    return {
        "schema": PROTOCOL_OVERLAY_SCHEMA,
        "source_path": str(source),
        "source_file_sha256": _sha256_bytes(source_bytes),
        "source_protocol_sha256": base.canonical_sha256,
        "overlay_path": str(output),
        "overlay_file_sha256": _sha256_bytes(output_bytes),
        "overlay_protocol_sha256": qualified.canonical_sha256,
        "changed_paths": ["study.execution.model_server.parallelism_profile"],
        "profile": A100_TP2_PROFILE.to_dict(),
    }


def build_tp2_agentic_inputs_overlay(
    *,
    protocol: Path,
    source_manifest: Path,
    source_summary: Path,
    output_manifest: Path,
    output_summary: Path,
) -> dict[str, Any]:
    """Rebind frozen pilot inputs to the private TP2 protocol identity."""

    study = StudyProtocol.from_yaml(protocol, validate_registry=False)
    if study.parallelism_profile is not A100_TP2_PROFILE:
        raise ValueError("agentic input overlay requires the registered TP2 protocol")
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    summary = json.loads(source_summary.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(summary, dict):
        raise ValueError("source manifest and summary must contain JSON objects")
    source_declared_hash = manifest.get("manifest_sha256")
    source_hash_input = dict(manifest)
    source_hash_input.pop("manifest_sha256", None)
    source_actual_hash = _canonical_sha256(source_hash_input)
    if (
        source_declared_hash != source_actual_hash
        or summary.get("manifest_sha256") != source_actual_hash
        or summary.get("protocol_sha256") != manifest.get("protocol_sha256")
    ):
        raise ValueError("source manifest and agentic summary identities do not agree")

    qualified_manifest = copy.deepcopy(manifest)
    qualified_manifest.pop("manifest_sha256", None)
    qualified_manifest["protocol_sha256"] = study.canonical_sha256
    qualified_manifest_sha256 = _canonical_sha256(qualified_manifest)
    qualified_manifest["manifest_sha256"] = qualified_manifest_sha256

    qualified_summary = copy.deepcopy(summary)
    qualified_summary["protocol_sha256"] = study.canonical_sha256
    qualified_summary["manifest_sha256"] = qualified_manifest_sha256
    write_private_json(output_manifest, qualified_manifest)
    write_private_json(output_summary, qualified_summary)
    return {
        "schema": PROTOCOL_OVERLAY_SCHEMA,
        "source_manifest_sha256": _sha256_bytes(source_manifest.read_bytes()),
        "source_summary_sha256": _sha256_bytes(source_summary.read_bytes()),
        "protocol_sha256": study.canonical_sha256,
        "manifest_path": str(output_manifest),
        "manifest_sha256": qualified_manifest_sha256,
        "manifest_file_sha256": _sha256_bytes(output_manifest.read_bytes()),
        "summary_path": str(output_summary),
        "summary_file_sha256": _sha256_bytes(output_summary.read_bytes()),
        "changed_paths": [
            "manifest.manifest_sha256",
            "manifest.protocol_sha256",
            "summary.manifest_sha256",
            "summary.protocol_sha256",
        ],
    }


def parse_nvidia_matrix(output: str) -> dict[str, dict[str, str]]:
    """Parse one ``nvidia-smi topo`` matrix while ignoring its prose legend."""

    lines = [_ANSI.sub("", line).strip() for line in output.splitlines()]
    header = next(
        (
            fields
            for line in lines
            if len(fields := line.split()) >= 2 and fields[0] == "GPU0" and fields[1] == "GPU1"
        ),
        None,
    )
    if header is None:
        raise ValueError("NVIDIA topology output lacks a GPU header")
    gpu_columns = [value for value in header if re.fullmatch(r"GPU[0-9]+", value)]
    if not gpu_columns:
        raise ValueError("NVIDIA topology output lacks GPU columns")
    result: dict[str, dict[str, str]] = {}
    for line in lines:
        fields = line.split()
        if fields[: len(gpu_columns)] == gpu_columns:
            continue
        if not fields or not re.fullmatch(r"GPU[0-9]+", fields[0]):
            continue
        if len(fields) < len(gpu_columns) + 1:
            raise ValueError("NVIDIA topology row is shorter than its GPU header")
        if fields[0] in result:
            raise ValueError("NVIDIA topology output repeats a GPU row")
        result[fields[0]] = dict(zip(gpu_columns, fields[1 : len(gpu_columns) + 1], strict=True))
    if set(result) != set(gpu_columns):
        raise ValueError("NVIDIA topology matrix is incomplete")
    return result


def validate_host_topology(
    *,
    gpu_uuids: Sequence[str],
    inventory: Sequence[Mapping[str, Any]],
    topology: str,
    p2p_read: str,
    p2p_write: str,
    p2p_nvlink: str,
) -> dict[str, Any]:
    """Validate the exact pair as two A100s with NVLink and bidirectional P2P."""

    allocation = GpuAllocation(
        tuple(gpu_uuids),
        A100_TP2_PROFILE.required_device_count * A100_TP2_PROFILE.minimum_memory_mib_per_device,
        NVLINK_P2P_TOPOLOGY_POLICY,
    )
    binding = GpuExecutionBinding(allocation, A100_TP2_PROFILE)
    by_uuid = {item.get("uuid"): item for item in inventory}
    if len(by_uuid) != len(inventory):
        raise ValueError("GPU inventory contains missing or duplicate UUIDs")
    try:
        selected = [by_uuid[value] for value in gpu_uuids]
    except KeyError as error:
        raise ValueError("qualified GPU UUID is absent from the host inventory") from error
    if any(item.get("name") != A100_80GB_PCIE for item in selected):
        raise ValueError("qualified pair must contain only NVIDIA A100 80GB PCIe devices")
    memory: list[int] = []
    for item in selected:
        value = item.get("memory_mib")
        if type(value) is not int:
            raise ValueError("GPU inventory lacks integer memory evidence")
        memory.append(value)
    validate_gpu_binding(
        allocation,
        A100_TP2_PROFILE,
        observed_accelerator_models=[str(item["name"]) for item in selected],
        available_memory_mib=memory,
    )
    labels = [str(item.get("index")) for item in selected]
    if any(not value.isdecimal() for value in labels):
        raise ValueError("GPU inventory lacks canonical indexes")
    ranks = [f"GPU{value}" for value in labels]
    matrices = {
        "topology": parse_nvidia_matrix(topology),
        "p2p_read": parse_nvidia_matrix(p2p_read),
        "p2p_write": parse_nvidia_matrix(p2p_write),
        "p2p_nvlink": parse_nvidia_matrix(p2p_nvlink),
    }
    first, second = ranks
    if (
        matrices["topology"][first][second] != "NV12"
        or matrices["topology"][second][first] != "NV12"
    ):
        raise ValueError("qualified pair does not have the required NV12 topology")
    for name in ("p2p_read", "p2p_write", "p2p_nvlink"):
        if matrices[name][first][second] != "OK" or matrices[name][second][first] != "OK":
            raise ValueError(f"qualified pair failed bidirectional {name} support")
    return {
        "binding": binding.to_dict(),
        "binding_sha256": binding.fingerprint(),
        "rank_order": [
            {
                "rank": rank,
                "index": int(item["index"]),
                "uuid": item["uuid"],
                "name": item["name"],
                "memory_mib": item["memory_mib"],
                "pci_bus_id": item["pci_bus_id"],
            }
            for rank, item in enumerate(selected)
        ],
        "link": "NV12",
        "p2p": {"read": "OK", "write": "OK", "nvlink": "OK"},
    }


def sanitize_broker_status(status: Mapping[str, Any]) -> dict[str, Any]:
    """Retain allocation state without copying tokens or foreign process details."""

    gpus = status.get("gpus")
    leases = status.get("leases")
    if not isinstance(gpus, list) or not isinstance(leases, list):
        raise ValueError("broker status lacks GPU or lease arrays")
    return {
        "backend_available": status.get("backend_available"),
        "backend_checked_at": status.get("backend_checked_at"),
        "gpus": [
            {key: item.get(key) for key in ("uuid", "total_mib", "used_mib", "free_mib")}
            for item in gpus
            if isinstance(item, Mapping)
        ],
        "leases": [
            {
                key: item.get(key)
                for key in ("owner", "gpu_uuids", "requested_mib", "state", "created_at")
            }
            for item in leases
            if isinstance(item, Mapping)
        ],
    }


def content_free_inference_canary(
    endpoint: str,
    model_id: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Execute a fixed harmless inference and retain shape/hash evidence only."""

    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with exactly READY."}],
        "temperature": 0,
        "max_tokens": 8,
    }
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with opener(request, timeout=60) as response:
        encoded = response.read(1024 * 1024)
        status = response.status
    if status != 200:
        raise RuntimeError(f"content-free inference returned HTTP {status}")
    document = json.loads(encoded)
    choices = document.get("choices") if isinstance(document, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise RuntimeError("content-free inference response has an invalid choice shape")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or content.strip() != "READY":
        raise RuntimeError("content-free inference did not return the fixed canary response")
    usage = document.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("content-free inference response lacks usage evidence")
    return {
        "http_status": status,
        "model": document.get("model"),
        "finish_reason": choices[0].get("finish_reason"),
        "usage": {
            key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
        "response_sha256": _sha256_bytes(encoded),
        "response_bytes": len(encoded),
        "content_retained": False,
    }


def validate_tau_diagnostic_receipt(value: Mapping[str, Any], model_id: str) -> dict[str, Any]:
    """Project two bounded TAU trajectories without retaining raw task content or scores."""

    execution = value.get("execution")
    scope = execution.get("scope") if isinstance(execution, Mapping) else None
    results = value.get("scored_results")
    if (
        value.get("model_id") != model_id
        or value.get("scored_samples") != len(TAU_DIAGNOSTIC_IDS)
        or not isinstance(scope, Mapping)
        or scope.get("kind") != "diagnostic-subset"
        or scope.get("official_comparison") is not False
        or scope.get("selected_ids") != list(TAU_DIAGNOSTIC_IDS)
        or not isinstance(results, list)
        or [item.get("canonical_id") for item in results if isinstance(item, Mapping)]
        != list(TAU_DIAGNOSTIC_IDS)
    ):
        raise ValueError("TAU receipt does not represent the required bounded diagnostics")
    statuses = value.get("analytic_status_counts")
    if (
        not isinstance(statuses, Mapping)
        or any(type(value) is not int or value < 0 for value in statuses.values())
        or sum(statuses.values()) != len(TAU_DIAGNOSTIC_IDS)
    ):
        raise ValueError("TAU diagnostic receipt has invalid analytic status counts")
    for item in results:
        if not isinstance(item, Mapping):
            raise ValueError("TAU diagnostic result must be an object")
        digest = item.get("raw_result_sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError("TAU diagnostic result lacks its private raw-result hash")
    terminations = value.get("termination_counts")
    if not isinstance(terminations, Mapping) or any(
        type(count) is not int or count < 0 for count in terminations.values()
    ):
        raise ValueError("TAU diagnostic receipt has invalid termination counts")
    return {
        "selected_ids": list(TAU_DIAGNOSTIC_IDS),
        "scored_samples": len(TAU_DIAGNOSTIC_IDS),
        "analytic_status_counts": dict(sorted(statuses.items())),
        "termination_counts": dict(sorted(terminations.items())),
        "execution_scope": dict(scope),
        "raw_content_retained": False,
    }
