"""Tests for the layered Tau simulator/interface patch contract."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "qwen38_tau_simulator.py"
MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-simulator-interface-guard.json"
)
SPEC = importlib.util.spec_from_file_location("qwen38_tau_simulator_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
simulator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = simulator
SPEC.loader.exec_module(simulator)


def test_patch_chain_is_content_addressed_and_preserves_context_layer() -> None:
    contract = simulator.load_simulator_patch_contract(MANIFEST)
    assert contract.upstream_revision == "672227c6b6676edc20d57ea53b7000262aae77b9"
    assert contract.context_contract.patch_sha256 == (
        "71bd8bbdded3dfac6e2cff06b541c4fc27dd7ab24a98687371890e9e1f446919"
    )
    assert contract.patch_sha256 == contract.layer_diff_sha256
    assert contract.context_manifest_sha256 == simulator.sha256_file(contract.context_manifest_path)
    assert set(contract.context_contract.changed_paths).issubset(contract.changed_paths)


@pytest.mark.parametrize(
    "field",
    [
        "context_manifest_sha256",
        "context_patch_sha256",
        "context_diff_sha256",
        "patch_sha256",
        "layer_diff_sha256",
        "cumulative_diff_sha256",
    ],
)
def test_patch_chain_rejects_tampered_hashes(tmp_path: Path, field: str) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name in (
        payload["context_manifest_file"],
        payload["patch_file"],
        "tau2-1.0.1-context-guard.patch",
    ):
        shutil.copy(MANIFEST.parent / name, tmp_path / name)
    payload[field] = "not-a-sha256"
    tampered = tmp_path / MANIFEST.name
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        simulator.load_simulator_patch_contract(tampered)


def test_patch_chain_rejects_missing_prerequisite_path(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["changed_paths"].remove("uv.lock")
    for name in (
        payload["context_manifest_file"],
        payload["patch_file"],
        "tau2-1.0.1-context-guard.patch",
    ):
        shutil.copy(MANIFEST.parent / name, tmp_path / name)
    candidate = tmp_path / MANIFEST.name
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="omit"):
        simulator.load_simulator_patch_contract(candidate)
