import copy
import hashlib
import io
import json
import stat
from pathlib import Path

import pytest

from matric_eval.studies import StudyProtocol
from matric_eval.studies.gpu import A100_TP2_PROFILE_ID
from matric_eval.studies.tp2_qualification import (
    TAU_DIAGNOSTIC_IDS,
    build_tp2_agentic_inputs_overlay,
    build_tp2_protocol_overlay,
    content_free_inference_canary,
    parse_nvidia_matrix,
    sanitize_broker_status,
    validate_host_topology,
    validate_tau_diagnostic_receipt,
)

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
GPU_A = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
GPU_B = "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOPOLOGY = """
        GPU0    GPU1    GPU2    GPU3    CPU Affinity
GPU0    X       SYS     NV12    SYS     0-31
GPU1    SYS     X       SYS     SYS     0-31
GPU2    NV12    SYS     X       SYS     0-31
GPU3    SYS     SYS     SYS     X       0-31
"""
P2P = """
        GPU0    GPU1    GPU2    GPU3
GPU0    X       OK      OK      OK
GPU1    OK      X       OK      OK
GPU2    OK      OK      X       OK
GPU3    OK      OK      OK      X
"""


def _inventory() -> list[dict[str, object]]:
    return [
        {
            "index": 0,
            "uuid": GPU_A,
            "name": "NVIDIA A100 80GB PCIe",
            "memory_mib": 81_920,
            "pci_bus_id": "00000000:01:00.0",
        },
        {
            "index": 2,
            "uuid": GPU_B,
            "name": "NVIDIA A100 80GB PCIe",
            "memory_mib": 81_920,
            "pci_bus_id": "00000000:81:00.0",
        },
    ]


def test_builds_private_one_field_tp2_protocol_overlay(tmp_path: Path) -> None:
    output = tmp_path / "tp2.json"
    evidence = build_tp2_protocol_overlay(PROTOCOL, output)
    original = StudyProtocol.from_yaml(PROTOCOL, validate_registry=False)
    overlay = StudyProtocol.from_yaml(output, validate_registry=False)

    expected = copy.deepcopy(original.raw)
    expected["study"]["execution"]["model_server"]["parallelism_profile"] = A100_TP2_PROFILE_ID
    assert overlay.raw == expected
    assert evidence["changed_paths"] == ["study.execution.model_server.parallelism_profile"]
    assert overlay.canonical_sha256 == evidence["overlay_protocol_sha256"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_tp2_protocol_overlay(PROTOCOL, output)


def test_rebinds_agentic_inputs_to_tp2_protocol(tmp_path: Path) -> None:
    protocol = tmp_path / "tp2.json"
    build_tp2_protocol_overlay(PROTOCOL, protocol)
    original = StudyProtocol.from_yaml(PROTOCOL, validate_registry=False)
    source_manifest = tmp_path / "source-manifest.json"
    source_summary = tmp_path / "source-summary.json"
    manifest = {
        "schema_version": "1",
        "study_id": original.id,
        "protocol_sha256": original.canonical_sha256,
        "cohort": "pilot",
        "allocations": [],
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest["manifest_sha256"] = manifest_hash
    source_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    source_summary.write_text(
        json.dumps(
            {
                "study_id": original.id,
                "protocol_sha256": original.canonical_sha256,
                "manifest_sha256": manifest_hash,
            }
        ),
        encoding="utf-8",
    )

    evidence = build_tp2_agentic_inputs_overlay(
        protocol=protocol,
        source_manifest=source_manifest,
        source_summary=source_summary,
        output_manifest=tmp_path / "manifest.json",
        output_summary=tmp_path / "summary.json",
    )

    qualified_manifest = json.loads((tmp_path / "manifest.json").read_text())
    qualified_summary = json.loads((tmp_path / "summary.json").read_text())
    assert qualified_manifest["protocol_sha256"] != original.canonical_sha256
    assert qualified_summary["protocol_sha256"] == qualified_manifest["protocol_sha256"]
    assert qualified_summary["manifest_sha256"] == qualified_manifest["manifest_sha256"]
    assert evidence["manifest_sha256"] == qualified_manifest["manifest_sha256"]
    assert stat.S_IMODE((tmp_path / "manifest.json").stat().st_mode) == 0o600


def test_agentic_overlay_rejects_mismatched_source_identity(tmp_path: Path) -> None:
    protocol = tmp_path / "tp2.json"
    build_tp2_protocol_overlay(PROTOCOL, protocol)
    manifest = tmp_path / "manifest.json"
    summary = tmp_path / "summary.json"
    manifest.write_text(json.dumps({"manifest_sha256": "bad"}), encoding="utf-8")
    summary.write_text(json.dumps({}), encoding="utf-8")

    with pytest.raises(ValueError, match="identities do not agree"):
        build_tp2_agentic_inputs_overlay(
            protocol=protocol,
            source_manifest=manifest,
            source_summary=summary,
            output_manifest=tmp_path / "out-manifest.json",
            output_summary=tmp_path / "out-summary.json",
        )


def test_parses_and_validates_exact_nv12_pair() -> None:
    matrix = parse_nvidia_matrix("\x1b[0m" + TOPOLOGY)
    assert matrix["GPU0"]["GPU2"] == "NV12"

    evidence = validate_host_topology(
        gpu_uuids=(GPU_A, GPU_B),
        inventory=_inventory(),
        topology=TOPOLOGY,
        p2p_read=P2P,
        p2p_write=P2P,
        p2p_nvlink=P2P,
    )

    assert [item["uuid"] for item in evidence["rank_order"]] == [GPU_A, GPU_B]
    assert evidence["link"] == "NV12"
    assert evidence["binding"]["profile"]["id"] == A100_TP2_PROFILE_ID


@pytest.mark.parametrize(
    ("topology", "p2p", "message"),
    [
        (TOPOLOGY.replace("NV12", "SYS"), P2P, "required NV12"),
        (
            TOPOLOGY,
            P2P.replace("GPU0    X       OK      OK", "GPU0    X       OK      CNS"),
            "bidirectional",
        ),
    ],
)
def test_rejects_unqualified_topology(topology: str, p2p: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_host_topology(
            gpu_uuids=(GPU_A, GPU_B),
            inventory=_inventory(),
            topology=topology,
            p2p_read=p2p,
            p2p_write=P2P,
            p2p_nvlink=P2P,
        )


def test_broker_projection_drops_tokens_and_foreign_processes() -> None:
    result = sanitize_broker_status(
        {
            "backend_available": True,
            "backend_checked_at": 1.0,
            "foreign_gpu_processes": {"pid@gpu": 100},
            "gpus": [{"uuid": GPU_A, "total_mib": 81_920, "used_mib": 1, "free_mib": 2}],
            "leases": [
                {
                    "owner": "qualification",
                    "gpu_uuids": [GPU_A, GPU_B],
                    "requested_mib": 75_000,
                    "state": "active",
                    "created_at": 1.0,
                    "token": "never-retain",
                    "foreign_baseline": {"pid@gpu": 100},
                }
            ],
        }
    )

    encoded = json.dumps(result)
    assert "token" not in encoded
    assert "foreign" not in encoded
    assert result["leases"][0]["gpu_uuids"] == [GPU_A, GPU_B]


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_content_free_canary_retains_only_response_shape_and_hash() -> None:
    requests = []
    encoded = json.dumps(
        {
            "model": "model",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "READY"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
        }
    ).encode()

    def opener(request, timeout):
        requests.append((request, timeout))
        return _Response(encoded)

    evidence = content_free_inference_canary(
        "http://127.0.0.1:18083/v1",
        "model",
        opener=opener,
    )

    assert evidence["content_retained"] is False
    assert "READY" not in json.dumps(evidence)
    assert evidence["usage"]["total_tokens"] == 6
    assert requests[0][1] == 60


def test_validates_and_sanitizes_two_trajectory_tau_receipt() -> None:
    receipt = {
        "model_id": "model",
        "scored_samples": 2,
        "analytic_status_counts": {"valid": 1, "invalid": 1},
        "termination_counts": {"done": 1, "runtime_invalid": 1},
        "execution": {
            "scope": {
                "kind": "diagnostic-subset",
                "official_comparison": False,
                "selected_ids": list(TAU_DIAGNOSTIC_IDS),
            }
        },
        "scored_results": [
            {"canonical_id": identifier, "raw_result_sha256": "a" * 64, "reward": 0.5}
            for identifier in TAU_DIAGNOSTIC_IDS
        ],
    }

    result = validate_tau_diagnostic_receipt(receipt, "model")

    assert result["raw_content_retained"] is False
    assert "reward" not in json.dumps(result)
    broken = copy.deepcopy(receipt)
    broken["execution"]["scope"]["selected_ids"].reverse()
    with pytest.raises(ValueError, match="required bounded diagnostics"):
        validate_tau_diagnostic_receipt(broken, "model")
