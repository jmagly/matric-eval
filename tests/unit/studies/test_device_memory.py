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
    declared_ceiling,
    effective_utilization,
    evidence,
    operator_ceiling,
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


def test_declared_ceiling_prefers_the_explicit_field():
    server = {"gpu_memory_utilization": 0.87, "max_device_memory_fraction": 0.9}
    assert declared_ceiling(server) == 0.9


def test_declared_ceiling_falls_back_so_existing_protocols_keep_behaviour():
    assert declared_ceiling({"gpu_memory_utilization": 0.87}) == 0.87


def test_operator_ceiling_defaults_when_unset():
    assert operator_ceiling({}) == DEFAULT_DEVICE_MEMORY_CEILING


@pytest.mark.parametrize("raw", ["0.80", " 0.80 "])
def test_operator_ceiling_reads_the_environment(raw):
    assert operator_ceiling({"MATRIC_EVAL_DEVICE_MEMORY_CEILING": raw}) == 0.80


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_operator_ceiling_falls_back_to_the_default(raw):
    assert operator_ceiling({"MATRIC_EVAL_DEVICE_MEMORY_CEILING": raw}) == (
        DEFAULT_DEVICE_MEMORY_CEILING
    )


@pytest.mark.parametrize("raw", ["not-a-number", "1.5", "0.1"])
def test_invalid_operator_ceiling_is_refused(raw):
    with pytest.raises(ValueError):
        operator_ceiling({"MATRIC_EVAL_DEVICE_MEMORY_CEILING": raw})


def test_operator_ceiling_clamps_a_pinned_protocol_it_cannot_edit():
    """The real case: the protocol says 0.9 and is hash-pinned, the host allows less."""
    server = {"gpu_memory_utilization": 0.9}
    assert effective_utilization(server, {}) == DEFAULT_DEVICE_MEMORY_CEILING
    assert resolve_ceiling(server, {}) == DEFAULT_DEVICE_MEMORY_CEILING


def test_a_protocol_tighter_than_the_operator_is_left_alone():
    server = {"gpu_memory_utilization": 0.6}
    assert effective_utilization(server, {}) == 0.6


def test_policy_clamps_rather_than_rejecting_a_looser_protocol():
    # Rejecting would make a pinned protocol unusable on a tighter host; the
    # operator owns the hardware, so the tighter value simply wins.
    server = {"gpu_memory_utilization": 0.95}
    assert validate_device_memory_policy(server, A100_TP1_PROFILE, {}) == (
        DEFAULT_DEVICE_MEMORY_CEILING
    )


def test_policy_accepts_the_shipped_protocol_shape():
    server = {"gpu_memory_utilization": 0.9}
    assert validate_device_memory_policy(server, A100_TP1_PROFILE, {}) == 0.87


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


def test_operator_ceiling_reaches_every_study_container():
    """A ceiling the container never sees is a silent divergence.

    The container environment is explicitly enumerated with --env flags, so a
    variable absent from that list does not propagate. The lease would honour an
    operator override while the model server quietly used the protocol value.
    """
    for script in (
        Path("scripts/serve_qwen38_container.sh"),
        Path("scripts/run_qwen38_offline_container.sh"),
    ):
        body = script.read_text(encoding="utf-8")
        assert "--env MATRIC_EVAL_DEVICE_MEMORY_CEILING" in body, script


def test_both_execution_paths_clamp_the_protocol_fraction():
    """Online serving and offline batch must agree on the effective fraction."""
    online = Path("src/matric_eval/studies/server_cli.py").read_text(encoding="utf-8")
    offline = Path("src/matric_eval/studies/batch.py").read_text(encoding="utf-8")
    for source, where in ((online, "server_cli"), (offline, "batch")):
        assert "effective_utilization" in source, where
        assert 'server["gpu_memory_utilization"]),' not in source, where


def _status(*rows: tuple[str, int, int]) -> dict:
    return {"gpus": [{"uuid": u, "total_mib": t, "used_mib": m} for u, t, m in rows]}


def test_free_reservation_guard_passes_on_an_empty_card():
    observed = device_memory.assert_free_from_status(
        _status(("GPU-a", 81_920, 18)), ["GPU-a"], 71_270
    )
    assert observed[0].used_mib == 18


def test_free_reservation_guard_rejects_a_card_holding_a_co_tenant():
    """The pliny failure: 60,788 MiB resident, a 71,270 MiB reservation requested."""
    with pytest.raises(device_memory.DeviceMemoryCeilingError) as error:
        device_memory.assert_free_from_status(_status(("GPU-a", 81_920, 60_788)), ["GPU-a"], 71_270)
    message = str(error.value)
    assert "GPU-a" in message
    assert "71270" in message
    assert "60788" in message, "the operator needs to see what was already resident"


def test_free_reservation_guard_passes_at_the_exact_boundary():
    device_memory.assert_free_from_status(_status(("GPU-a", 81_920, 10_650)), ["GPU-a"], 71_270)


def test_free_reservation_guard_reports_every_short_device():
    with pytest.raises(device_memory.DeviceMemoryCeilingError) as error:
        device_memory.assert_free_from_status(
            _status(("GPU-a", 81_920, 60_788), ("GPU-b", 81_920, 70_000)),
            ["GPU-a", "GPU-b"],
            71_270,
        )
    assert "GPU-a" in str(error.value) and "GPU-b" in str(error.value)


def test_free_reservation_guard_ignores_unleased_devices():
    device_memory.assert_free_from_status(
        _status(("GPU-a", 81_920, 18), ("GPU-busy", 81_920, 80_000)), ["GPU-a"], 71_270
    )


def test_free_reservation_guard_is_inert_without_device_evidence():
    """An older broker publishes no device section; that must not block a run."""
    assert device_memory.assert_free_from_status({"leases": []}, ["GPU-a"], 71_270) == ()


def test_free_reservation_guard_refuses_a_missing_leased_device():
    with pytest.raises(device_memory.DeviceMemoryCeilingError, match="omits leased device"):
        device_memory.assert_free_from_status(_status(("GPU-other", 81_920, 18)), ["GPU-a"], 71_270)


def test_free_reservation_guard_refuses_non_integer_memory():
    status = {"gpus": [{"uuid": "GPU-a", "total_mib": "81920", "used_mib": 18}]}
    with pytest.raises(device_memory.DeviceMemoryCeilingError, match="integer memory"):
        device_memory.assert_free_from_status(status, ["GPU-a"], 71_270)


@pytest.mark.parametrize("amount", [0, -1])
def test_free_reservation_guard_refuses_a_nonsense_reservation(amount):
    with pytest.raises(device_memory.DeviceMemoryCeilingError, match="positive MiB"):
        device_memory.assert_free_from_status(_status(("GPU-a", 81_920, 18)), ["GPU-a"], amount)


def test_foreign_intrusion_detected_on_a_leased_card():
    status = {"foreign_gpu_processes": {"3692206@GPU-a": 30972}}
    assert device_memory.foreign_intrusions(status, ["GPU-a"], {}) == {"3692206@GPU-a": 30972}


def test_foreign_process_present_at_acquisition_is_not_an_intrusion():
    baseline = {"1984040@GPU-a": 416}
    status = {"foreign_gpu_processes": dict(baseline)}
    assert device_memory.foreign_intrusions(status, ["GPU-a"], baseline) == {}


def test_foreign_process_on_an_unleased_card_is_ignored():
    status = {"foreign_gpu_processes": {"3174044@GPU-other": 19368}}
    assert device_memory.foreign_intrusions(status, ["GPU-a"], {}) == {}


def test_intrusion_alongside_a_baseline_process_is_still_detected():
    baseline = {"1984040@GPU-a": 416}
    status = {"foreign_gpu_processes": {**baseline, "3692206@GPU-a": 30972}}
    assert device_memory.foreign_intrusions(status, ["GPU-a"], baseline) == {"3692206@GPU-a": 30972}


def test_the_studys_own_server_is_not_an_intrusion():
    """The broker calls every process it does not own foreign, and the per-lease
    baseline predates our own allocation, so ownership must be excluded explicitly."""
    status = {"foreign_gpu_processes": {"723708@GPU-a": 52476}}
    assert device_memory.foreign_intrusions(status, ["GPU-a"], {}) == {"723708@GPU-a": 52476}
    assert device_memory.foreign_intrusions(status, ["GPU-a"], {}, owned_pids={723708}) == {}


def test_a_co_tenant_is_still_detected_beside_our_own_server():
    """Excluding ourselves must not disarm the guard for a real co-tenant."""
    status = {"foreign_gpu_processes": {"723708@GPU-a": 52476, "999001@GPU-a": 34871}}
    assert device_memory.foreign_intrusions(status, ["GPU-a"], {}, owned_pids={723708}) == {
        "999001@GPU-a": 34871
    }


def test_unparseable_pid_cannot_be_proven_ours():
    status = {"foreign_gpu_processes": {"notapid@GPU-a": 1024}}
    assert device_memory.foreign_intrusions(status, ["GPU-a"], {}, owned_pids={723708}) == {
        "notapid@GPU-a": 1024
    }


def test_absent_foreign_map_is_not_an_intrusion():
    assert device_memory.foreign_intrusions({}, ["GPU-a"], {}) == {}


def test_malformed_foreign_map_is_refused():
    with pytest.raises(device_memory.DeviceMemoryCeilingError, match="malformed"):
        device_memory.foreign_intrusions({"foreign_gpu_processes": ["nope"]}, ["GPU-a"], {})
