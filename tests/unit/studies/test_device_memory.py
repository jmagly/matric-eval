"""Unit coverage for the per-device GPU memory ceiling policy."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from matric_eval.studies import device_memory
from matric_eval.studies.device_memory import (
    DEFAULT_DEVICE_MEMORY_CEILING,
    DeviceMemoryCeilingError,
    DeviceObservation,
    assert_profile_within_ceiling,
    assert_within_ceiling,
    ceiling_mib,
    evidence,
    parse_observations,
    query_observations,
    resolve_ceiling,
    total_mib,
    validate_ceiling,
    validate_device_memory_policy,
)
from matric_eval.studies.gpu import A100_80GB_PCIE, A100_TP1_PROFILE, A100_TP2_PROFILE

A100_TOTAL_MIB = 81_920


class _Runner:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.calls: list[list[str]] = []

    def __call__(self, argv, **_kwargs):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def test_default_ceiling_leaves_headroom_under_a_ninety_percent_host_limit():
    # The operator limit is 90%; the default must sit below it so that memory the
    # server's own fraction does not account for still lands inside the limit.
    assert DEFAULT_DEVICE_MEMORY_CEILING < 0.90


def test_advertised_capacity_is_recorded_for_the_a100():
    assert total_mib(A100_80GB_PCIE) == A100_TOTAL_MIB


def test_unknown_accelerator_is_refused_rather_than_guessed():
    with pytest.raises(DeviceMemoryCeilingError, match="no advertised capacity"):
        total_mib("NVIDIA Imaginary 512GB")


@pytest.mark.parametrize("fraction", [0.5, 0.87, 0.999])
def test_valid_ceilings_are_accepted(fraction):
    assert validate_ceiling(fraction, path="x") == fraction


@pytest.mark.parametrize("fraction", [0.49, 1.0, 1.5, -0.1, None, "0.87", True, False])
def test_invalid_ceilings_are_rejected(fraction):
    with pytest.raises(ValueError):
        validate_ceiling(fraction, path="x")


def test_ceiling_arithmetic_is_the_operator_target():
    assert ceiling_mib(A100_80GB_PCIE, 0.87) == 71_270
    assert ceiling_mib(A100_80GB_PCIE, 0.90) == 73_728


def test_ceiling_never_rounds_above_the_fraction():
    for fraction in (0.5, 0.63, 0.87, 0.9, 0.99):
        assert ceiling_mib(A100_80GB_PCIE, fraction) <= A100_TOTAL_MIB * fraction


def test_tp1_profile_reservation_is_within_the_default_ceiling():
    # This is the regression the operator requirement turns on: the lease the
    # broker is asked to reserve must not exceed the ceiling.
    assert A100_TP1_PROFILE.minimum_memory_mib_per_device <= ceiling_mib(
        A100_80GB_PCIE, DEFAULT_DEVICE_MEMORY_CEILING
    )
    assert_profile_within_ceiling(A100_TP1_PROFILE, DEFAULT_DEVICE_MEMORY_CEILING)


def test_tp2_profile_reservation_is_within_the_default_ceiling():
    assert_profile_within_ceiling(A100_TP2_PROFILE, DEFAULT_DEVICE_MEMORY_CEILING)


def test_profile_above_the_ceiling_is_rejected_with_both_numbers():
    with pytest.raises(DeviceMemoryCeilingError) as error:
        assert_profile_within_ceiling(A100_TP1_PROFILE, 0.80)
    message = str(error.value)
    assert str(A100_TP1_PROFILE.minimum_memory_mib_per_device) in message
    assert str(ceiling_mib(A100_80GB_PCIE, 0.80)) in message


def test_resolve_ceiling_prefers_the_explicit_declaration():
    server = {"gpu_memory_utilization": 0.87, "max_device_memory_fraction": 0.9}
    assert resolve_ceiling(server) == 0.9


def test_resolve_ceiling_falls_back_so_existing_protocols_keep_behaviour():
    assert resolve_ceiling({"gpu_memory_utilization": 0.87}) == 0.87


def test_policy_rejects_a_server_fraction_above_the_ceiling():
    server = {"gpu_memory_utilization": 0.95, "max_device_memory_fraction": 0.87}
    with pytest.raises(ValueError, match="must not exceed max_device_memory_fraction"):
        validate_device_memory_policy(server, A100_TP1_PROFILE)


def test_policy_accepts_the_shipped_shape():
    server = {"gpu_memory_utilization": 0.87, "max_device_memory_fraction": 0.87}
    assert validate_device_memory_policy(server, A100_TP1_PROFILE) == 0.87


def test_observation_fraction_and_zero_capacity():
    observation = DeviceObservation(uuid="GPU-a", total_mib=81_920, used_mib=40_960)
    assert observation.fraction == pytest.approx(0.5)
    with pytest.raises(DeviceMemoryCeilingError, match="non-positive capacity"):
        DeviceObservation(uuid="GPU-b", total_mib=0, used_mib=1).fraction


def test_parse_observations_reads_nvidia_smi_rows():
    rows = ["GPU-a, 81920, 1000", "", "GPU-b, 81920 MiB, 2000 MiB"]
    parsed = parse_observations(rows)
    assert [item.uuid for item in parsed] == ["GPU-a", "GPU-b"]
    assert parsed[1].total_mib == 81_920 and parsed[1].used_mib == 2_000


@pytest.mark.parametrize("row", ["GPU-a, 81920", "GPU-a, eighty, 1000", "a,b,c,d"])
def test_malformed_observation_rows_are_refused(row):
    with pytest.raises(DeviceMemoryCeilingError):
        parse_observations([row])


def test_query_observations_asks_for_exactly_the_leased_devices():
    runner = _Runner(stdout="GPU-a, 81920, 1000\nGPU-b, 81920, 2000\n")
    observed = query_observations(["GPU-a", "GPU-b"], run=runner)
    assert [item.uuid for item in observed] == ["GPU-a", "GPU-b"]
    assert "--id=GPU-a,GPU-b" in runner.calls[0]


def test_query_observations_refuses_an_empty_allocation():
    with pytest.raises(DeviceMemoryCeilingError, match="empty allocation"):
        query_observations([], run=_Runner())


def test_query_observations_fails_closed_when_a_leased_device_is_missing():
    runner = _Runner(stdout="GPU-a, 81920, 1000\n")
    with pytest.raises(DeviceMemoryCeilingError, match="omitted leased devices"):
        query_observations(["GPU-a", "GPU-b"], run=runner)


def test_query_observations_surfaces_a_failed_query():
    runner = _Runner(returncode=9, stderr="No devices were found")
    with pytest.raises(DeviceMemoryCeilingError, match="No devices were found"):
        query_observations(["GPU-a"], run=runner)


def test_assert_within_ceiling_passes_at_the_boundary():
    at_ceiling = DeviceObservation(uuid="GPU-a", total_mib=81_920, used_mib=71_270)
    assert at_ceiling.fraction <= 0.87
    assert_within_ceiling([at_ceiling], 0.87, stage="test")


def test_assert_within_ceiling_fails_closed_and_names_the_card():
    breach = DeviceObservation(uuid="GPU-over", total_mib=81_920, used_mib=75_000)
    with pytest.raises(DeviceMemoryCeilingError) as error:
        assert_within_ceiling([breach], 0.87, stage="model server ready")
    message = str(error.value)
    assert "GPU-over" in message
    assert "model server ready" in message
    assert "75000/81920" in message


def test_evidence_records_the_high_water_card():
    observations = [
        DeviceObservation(uuid="GPU-a", total_mib=81_920, used_mib=10_000),
        DeviceObservation(uuid="GPU-b", total_mib=81_920, used_mib=60_000),
    ]
    payload = evidence(observations, 0.87)
    assert payload["high_water_uuid"] == "GPU-b"
    assert payload["high_water_used_mib"] == 60_000
    assert payload["ceiling_fraction"] == 0.87
    assert len(payload["devices"]) == 2


def test_evidence_is_well_formed_without_observations():
    assert evidence([], 0.87)["high_water_fraction"] is None


def test_no_launch_path_embeds_a_memory_fraction_literal():
    """A host-owner ceiling must have one source of truth: the protocol."""
    literal = re.compile(r"gpu_memory_utilization\s*[=:]\s*(?:float\s*=\s*)?0\.\d+")
    offenders: list[str] = []
    for root in (Path("src"), Path("scripts")):
        for path in root.rglob("*.py"):
            if path.name == device_memory.__name__.rsplit(".", 1)[-1] + ".py":
                continue
            if literal.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path))
    assert not offenders, f"hardcoded gpu_memory_utilization in {offenders}"
