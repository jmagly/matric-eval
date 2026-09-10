import json
import subprocess
import sys
from pathlib import Path

import pytest

from matric_eval.studies import StudyProtocol
from matric_eval.studies.gpu import (
    A100_TP1_PROFILE,
    A100_TP2_PROFILE,
    NVLINK_P2P_TOPOLOGY_POLICY,
)
from matric_eval.studies.wrapper import resolve_wrapper_gpu_contract

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
GPU_A = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
GPU_B = "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_tp1_wrapper_contract_preserves_legacy_single_gpu_argv() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    contract = resolve_wrapper_gpu_contract(study, [GPU_A])

    assert contract.docker_selector == f"device={GPU_A}"
    assert contract.lifecycle_arguments == (
        "--memory-mib",
        "75000",
        "--gpu",
        GPU_A,
    )
    assert contract.binding.profile is A100_TP1_PROFILE


def test_tp2_wrapper_contract_preserves_rank_order_in_every_projection() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    study.raw["study"]["execution"]["model_server"]["parallelism_profile"] = A100_TP2_PROFILE.id
    contract = resolve_wrapper_gpu_contract(
        study,
        [GPU_B, GPU_A],
        parallelism_profile=A100_TP2_PROFILE.id,
    )

    assert contract.docker_selector == f"device={GPU_B},{GPU_A}"
    assert contract.lifecycle_arguments == (
        "--memory-mib",
        "75000",
        "--topology-policy",
        NVLINK_P2P_TOPOLOGY_POLICY,
        "--gpu",
        GPU_B,
        "--gpu",
        GPU_A,
    )
    assert contract.to_dict()["gpu_uuids"] == [GPU_B, GPU_A]


@pytest.mark.parametrize(
    ("gpu_uuids", "profile", "message"),
    [
        ([GPU_A, GPU_A], None, "duplicate_gpu_uuid"),
        (["0"], None, "malformed_gpu_uuid"),
        (["all"], None, "malformed_gpu_uuid"),
        ([GPU_A, GPU_B], None, "profile_device_count_mismatch"),
        ([GPU_A], "a100-80gb-pcie-tp3/1", "unsupported_profile"),
        ([GPU_A], A100_TP2_PROFILE.id, "must exactly match"),
    ],
)
def test_wrapper_contract_rejects_malformed_or_unsupported_bindings(
    gpu_uuids: list[str],
    profile: str | None,
    message: str,
) -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    with pytest.raises(ValueError, match=message):
        resolve_wrapper_gpu_contract(
            study,
            gpu_uuids,
            parallelism_profile=profile,
        )


def test_wrapper_cli_emits_exact_machine_consumable_argv() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "matric_eval.studies.wrapper",
            "--protocol",
            str(PROTOCOL),
            "--format",
            "json",
            "--gpu",
            GPU_A,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["docker_selector"] == f"device={GPU_A}"
    assert payload["lifecycle_arguments"] == ["--memory-mib", "75000", "--gpu", GPU_A]
    assert payload["allocation"]["gpu_uuids"] == [GPU_A]
