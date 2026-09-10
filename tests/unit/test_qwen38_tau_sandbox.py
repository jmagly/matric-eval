"""Tests for Tau sandbox Unix-socket admission and replay temp lifecycle."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import qwen38_tau_sandbox as sandbox  # noqa: E402

SUPERVISOR_SPEC = importlib.util.spec_from_file_location(
    "qwen38_paired_replay_test", SCRIPTS / "run_qwen38_paired_replay.py"
)
assert SUPERVISOR_SPEC is not None and SUPERVISOR_SPEC.loader is not None
supervisor = importlib.util.module_from_spec(SUPERVISOR_SPEC)
SUPERVISOR_SPEC.loader.exec_module(supervisor)


def test_socket_budget_accepts_short_private_tmpdir() -> None:
    evidence = sandbox.sandbox_socket_path_evidence(Path("/srv/matric-eval/runtime-tmp/r7"))
    assert evidence["longest_bridge_socket_path_bytes"] <= 107
    assert evidence["linux_limit_bytes"] == 107


def test_socket_budget_rejects_the_r6_evidence_tmpdir() -> None:
    path = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09/replay-20260908-r6/tmp")
    with pytest.raises(RuntimeError, match="Unix-socket path limit"):
        sandbox.sandbox_socket_path_evidence(path)


def test_socket_budget_requires_absolute_tmpdir() -> None:
    with pytest.raises(RuntimeError, match="must be absolute"):
        sandbox.sandbox_socket_path_evidence(Path("relative/tmp"))


def test_standalone_canary_writes_one_private_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "canary.json"
    monkeypatch.setattr(
        sandbox,
        "knowledge_dependency_evidence",
        lambda: {"execution_canary": "passed"},
    )
    assert sandbox.main(["--receipt", str(output)]) == 0
    assert json.loads(output.read_text()) == {
        "schema": "matric-eval.tau-sandbox-preflight/1",
        "passed": True,
        "sandbox": {"execution_canary": "passed"},
        "failure": None,
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError, match="overwrite"):
        sandbox.main(["--receipt", str(output)])


def test_replay_runtime_tmp_is_private_exclusive_and_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(tempfile.mkdtemp(prefix="me-tau-", dir="/tmp"))
    replay = root / "replay-r7"
    monkeypatch.setattr(supervisor, "RUNTIME_TMP_ROOT", root)
    monkeypatch.setattr(supervisor, "RUNTIME_TMP", replay)
    try:
        evidence = supervisor.prepare_runtime_tmp()
        assert replay.is_dir()
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE(replay.stat().st_mode) == 0o700
        assert evidence["longest_bridge_socket_path_bytes"] <= 107
        with pytest.raises(RuntimeError, match="refusing to reuse"):
            supervisor.prepare_runtime_tmp()

        supervisor.cleanup_runtime_tmp()
        assert not replay.exists()
    finally:
        supervisor.cleanup_runtime_tmp()
        root.rmdir()


def test_paired_replay_requires_two_valid_noncomparative_admission_trajectories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "admission.json"
    payload = {
        "model_id": "source-model",
        "scored_samples": 2,
        "analytic_status_counts": {"valid": 2},
        "execution": {
            "scope": {
                "kind": "diagnostic-subset",
                "official_comparison": False,
                "selected_ids": list(supervisor.ADMISSION_IDS),
            }
        },
        "scored_results": [
            {
                "canonical_id": canonical_id,
                "analytic_status": "valid",
                "raw_result_sha256": "a" * 64,
            }
            for canonical_id in supervisor.ADMISSION_IDS
        ],
    }
    receipt.write_text(json.dumps(payload))
    monkeypatch.setattr(supervisor, "ADMISSION_RECEIPT", receipt)
    evidence = supervisor.validate_admission_receipt("source-model")
    assert evidence["valid_trajectories"] == 2
    assert len(evidence["receipt_sha256"]) == 64

    payload["scored_results"][0]["analytic_status"] = "invalid"
    receipt.write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match="does not prove"):
        supervisor.validate_admission_receipt("source-model")


def test_paired_replay_requires_current_bounded_launch_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    study = tmp_path / "study"
    out = study / "replay-r7"
    attempt = study / "run-control" / "replay-r7-source"
    evidence = attempt / "volumes" / "evidence"
    evidence.mkdir(parents=True)
    (attempt / "preflight-plan.json").write_text("{}")
    (attempt / "storage.json").write_text(
        json.dumps(
            {
                "allocations": [
                    {"kind": "evidence", "path": str(evidence)},
                ]
            }
        )
    )
    monkeypatch.setattr(supervisor, "STUDY", study)
    monkeypatch.setattr(supervisor, "OUT", out)

    contract = supervisor.load_launch_contract("source")
    assert contract["server_receipt"] == evidence / "server.json"
    assert contract["lease_receipt"] == evidence / "lease.private.json"
    assert contract["resource_directory"] == attempt / "resources"

    (attempt / "storage.json").write_text(
        json.dumps(
            {
                "allocations": [
                    {"kind": "evidence", "path": str(tmp_path / "unbounded")},
                ]
            }
        )
    )
    with pytest.raises(RuntimeError, match="evidence allocation does not match"):
        supervisor.load_launch_contract("source")


def test_paired_replay_releases_only_the_exact_ordered_gpu_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gpu_uuids = (
        "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    responses = iter(
        [
            "",
            json.dumps(
                {
                    "leases": [
                        {
                            "owner": "unit",
                            "gpu_uuids": list(gpu_uuids),
                            "token": "private-token",
                        }
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(supervisor.subprocess, "run", fake_run)
    monkeypatch.setattr(
        supervisor.subprocess,
        "check_output",
        lambda *args, **kwargs: next(responses),
    )

    supervisor.stop_server("unit", gpu_uuids)

    assert commands[-1][:-1] == ["sudo", "-n", "docker", "gpu", "release"]


def test_paired_replay_refuses_partial_or_reordered_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gpu_a = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    gpu_b = "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    responses = iter(
        [
            "",
            json.dumps(
                {
                    "leases": [
                        {
                            "owner": "unit",
                            "gpu_uuids": [gpu_a, gpu_b],
                            "token": "private-token",
                        }
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(
        supervisor.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
    )
    monkeypatch.setattr(
        supervisor.subprocess,
        "check_output",
        lambda *args, **kwargs: next(responses),
    )

    with pytest.raises(RuntimeError, match="refusing partial release"):
        supervisor.stop_server("unit", (gpu_b, gpu_a))
