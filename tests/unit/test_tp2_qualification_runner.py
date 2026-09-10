import json
import os
import runpy
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/qualify_qwen38_tp2.py"
CHECKER = ROOT / "scripts/check_qwen38_tp2_preflight.py"
GPU_A = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
GPU_B = "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _runner_namespace():
    return runpy.run_path(str(RUNNER))


def test_qualification_scripts_are_executable_and_content_free() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    checker = CHECKER.read_text(encoding="utf-8")

    for path in (RUNNER, CHECKER):
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode & 0o111 == 0o111
        assert mode & 0o002 == 0
    attempt = runner[runner.index("def _run_attempt") :]
    assert attempt.index("content_free_inference_canary(") < attempt.index('if kind == "success"')
    assert '"inject-container-stop"' in attempt
    assert "_verify_cleanup(" in attempt
    assert "_unmount_storage(" in attempt
    assert '"public_receipt_contains_raw_prompts_or_outputs": False' in runner
    assert '"public_receipt_contains_lease_credentials": False' in runner
    assert "DeviceRequests" in checker
    assert "validate_parallelism_attestation" in checker


def test_preflight_plan_preserves_two_gpu_rank_order(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    attempt = tmp_path / "attempt"
    attempt.mkdir()

    path = namespace["_preflight_plan"](
        workspace=ROOT,
        revision="a" * 40,
        protocol=tmp_path / "protocol.json",
        attempt=attempt,
        evidence=tmp_path / "evidence",
        gpus=(GPU_A, GPU_B),
        port=18093,
    )

    plan = json.loads(path.read_text(encoding="utf-8"))
    assert [check["stage"] for check in plan["checks"]] == [
        "static",
        "cpu",
        "auxiliary",
        "target",
    ]
    for check in plan["checks"]:
        command = check["command"]
        selected = [command[index + 1] for index, value in enumerate(command) if value == "--gpu"]
        assert selected == [GPU_A, GPU_B]


def test_pair_availability_requires_the_per_rank_floor() -> None:
    available = _runner_namespace()["_pair_is_available"]
    inventory = [
        {"uuid": GPU_A, "free_mib": 37_500},
        {"uuid": GPU_B, "free_mib": 37_500},
    ]

    assert available(inventory, (GPU_A, GPU_B), set()) is True
    inventory[1]["free_mib"] = 37_499
    assert available(inventory, (GPU_A, GPU_B), set()) is False


def test_pair_availability_rejects_active_compute_processes() -> None:
    namespace = _runner_namespace()
    available = namespace["_pair_is_available"]
    parse = namespace["_compute_process_gpu_uuids"]
    inventory = [
        {"uuid": GPU_A, "free_mib": 75_000},
        {"uuid": GPU_B, "free_mib": 75_000},
    ]

    active = parse(f"{GPU_A}, 1234\n")
    assert active == {GPU_A}
    assert available(inventory, (GPU_A, GPU_B), active) is False


def test_compute_process_parser_fails_closed_on_malformed_output() -> None:
    parse = _runner_namespace()["_compute_process_gpu_uuids"]

    try:
        parse(f"{GPU_A}\n")
    except RuntimeError as error:
        assert "malformed compute-process row" in str(error)
    else:
        raise AssertionError("malformed compute-process evidence must fail closed")


def test_runtime_python_accepts_executable_venv_symlink(tmp_path: Path) -> None:
    require_executable = _runner_namespace()["_require_resolved_executable"]
    target = tmp_path / "python3.11"
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    target.chmod(0o755)
    venv_python = tmp_path / "python"
    venv_python.symlink_to(target)

    assert require_executable(venv_python) == target

    target.chmod(0o644)
    assert not os.access(target, os.X_OK)
    try:
        require_executable(venv_python)
    except RuntimeError as error:
        assert str(venv_python) in str(error)
    else:
        raise AssertionError("runtime interpreter must be executable")
