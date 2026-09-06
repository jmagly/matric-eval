"""Tests for preregistered matched-comparison study validation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from matric_eval.cli import cli
from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"


@pytest.fixture
def protocol_data() -> dict:
    data = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_committed_protocol_is_valid_and_balanced() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    summary = study.summary()

    assert summary["status"] == "valid"
    assert summary["seed"] == 1790783388
    assert summary["model_count"] == 3
    assert summary["benchmarks"] == 11
    assert summary["samples_per_model"] == {"pilot": 100, "full": 1200}
    assert summary["total_generations"] == {"pilot": 300, "full": 3600}
    assert summary["axis_allocations"] == {
        "agentic": {"pilot": 20, "full": 250},
        "benign_overrefusal": {"pilot": 20, "full": 250},
        "capability": {"pilot": 40, "full": 500},
        "harmful_compliance": {"pilot": 20, "full": 200},
    }
    assert len(summary["source_sha256"]) == 64
    assert len(summary["canonical_sha256"]) == 64


def test_rejects_allocation_total_drift(protocol_data: dict) -> None:
    changed = copy.deepcopy(protocol_data)
    changed["study"]["benchmarks"][0]["pilot_samples"] += 1

    with pytest.raises(ValueError, match="pilot allocations"):
        StudyProtocol.from_dict(changed)


def test_rejects_model_seed_drift(protocol_data: dict) -> None:
    changed = copy.deepcopy(protocol_data)
    runtime = copy.deepcopy(changed["study"]["models"][1]["runtime"])
    runtime["sampler"]["seed"] = 42
    changed["study"]["models"][1]["runtime"] = runtime

    with pytest.raises(ValueError, match="runtime seed"):
        StudyProtocol.from_dict(changed)


def test_rejects_primary_runtime_drift(protocol_data: dict) -> None:
    changed = copy.deepcopy(protocol_data)
    runtime = copy.deepcopy(changed["study"]["models"][2]["runtime"])
    runtime["chat_template_sha256"] = "a" * 64
    changed["study"]["models"][2]["runtime"] = runtime

    with pytest.raises(ValueError, match="primary model runtimes must be identical"):
        StudyProtocol.from_dict(changed)


def test_rejects_missing_behavior_axis(protocol_data: dict) -> None:
    changed = copy.deepcopy(protocol_data)
    for allocation in changed["study"]["benchmarks"]:
        if allocation["axis"] == "harmful_compliance":
            allocation["axis"] = "benign_overrefusal"

    with pytest.raises(ValueError, match="missing: harmful_compliance"):
        StudyProtocol.from_dict(changed)


def test_validate_study_cli_json() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["validate-study", str(PROTOCOL), "--output-format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["study_id"] == "qwen38-obliteration-2026-09"
    assert payload["samples_per_model"]["full"] == 1200


def test_sha256_selection_is_stable_and_pilot_is_nested() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    allocation = next(item for item in study.benchmarks if item.id == "xstest-safe")
    ids = [f"sample-{index:04d}" for index in range(allocation.available_samples)]

    pilot = study.select_ids(allocation.id, list(reversed(ids)), "pilot")
    full = study.select_ids(allocation.id, ids, "full")

    assert pilot == full[: allocation.pilot_samples]
    assert pilot == study.select_ids(allocation.id, ids, "pilot")


def test_selection_manifest_is_content_addressed() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    catalog = {
        allocation.id: [
            f"{allocation.id}-{index:05d}" for index in range(allocation.available_samples)
        ]
        for allocation in study.benchmarks
    }

    manifest = study.selection_manifest(catalog, "pilot")

    assert len(manifest["manifest_sha256"]) == 64
    assert len(manifest["allocations"]) == 11
    assert sum(len(item["selected_ids"]) for item in manifest["allocations"]) == 100


def test_rejects_duplicate_canonical_ids() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)

    with pytest.raises(ValueError, match="duplicate canonical IDs"):
        study.select_ids("xstest-safe", ["same"] * 100, "pilot")
