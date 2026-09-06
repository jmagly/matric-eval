"""Tests for preregistered matched-comparison study validation."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import matric_eval.studies.batch as batch_module
from matric_eval.cli import cli
from matric_eval.studies import StudyBatchRequest, StudyProtocol, run_offline_batch

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"


@pytest.fixture
def protocol_data() -> dict:
    data = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def synthetic_catalog(study: StudyProtocol) -> dict[str, list[object]]:
    catalog: dict[str, list[object]] = {}
    for allocation in study.benchmarks:
        ids = [f"{allocation.id}-{index:05d}" for index in range(allocation.available_samples)]
        if allocation.selection_strategy == "sha256-stratified-round-robin-v1":
            catalog[allocation.id] = [
                {"id": sample_id, "stratum": f"stratum-{index % 5}"}
                for index, sample_id in enumerate(ids)
            ]
        else:
            catalog[allocation.id] = ids
    return catalog


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


def test_generation_seed_is_stable_and_sample_specific() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)

    first = study.generation_seed("xstest-safe", "sample-0001")
    second = study.generation_seed("xstest-safe", "sample-0002")

    assert first == study.generation_seed("xstest-safe", "sample-0001")
    assert first != second
    assert 0 <= first < 2**32


def test_bfcl_selection_is_balanced_and_nested() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    allocation = next(item for item in study.benchmarks if item.id == "bfcl-v4-agentic")
    ids = [f"bfcl-{index:04d}" for index in range(allocation.available_samples)]
    strata = {sample_id: f"category-{index % 5}" for index, sample_id in enumerate(ids)}

    pilot = study.select_ids(allocation.id, ids, "pilot", strata=strata)
    full = study.select_ids(allocation.id, ids, "full", strata=strata)

    assert pilot == full[: allocation.pilot_samples]
    assert {strata[sample_id] for sample_id in pilot} == {
        "category-0",
        "category-1",
        "category-2",
        "category-3",
        "category-4",
    }
    counts = {
        stratum: sum(strata[item] == stratum for item in full) for stratum in set(strata.values())
    }
    assert counts == {f"category-{index}": 20 for index in range(5)}


def test_rejects_legacy_direct_endpoint_execution(protocol_data: dict) -> None:
    changed = copy.deepcopy(protocol_data)
    changed["study"]["benchmarks"][0]["execution_mode"] = "direct-endpoint"

    with pytest.raises(ValueError, match="execution_mode"):
        StudyProtocol.from_dict(changed)


def test_selection_manifest_is_content_addressed() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    catalog = synthetic_catalog(study)

    manifest = study.selection_manifest(catalog, "pilot")

    assert len(manifest["manifest_sha256"]) == 64
    assert len(manifest["allocations"]) == 11
    assert sum(len(item["selected_ids"]) for item in manifest["allocations"]) == 100


def test_batch_contract_rejects_tampered_manifest() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    catalog = synthetic_catalog(study)
    manifest = study.selection_manifest(catalog, "pilot")
    manifest["allocations"][0]["selected_ids"][0] = "tampered"

    with pytest.raises(ValueError, match="manifest_sha256"):
        batch_module.validate_batch_contract(study, manifest, [])


def test_batch_contract_accepts_one_complete_allocation() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    catalog = synthetic_catalog(study)
    manifest = study.selection_manifest(catalog, "pilot")
    selected = manifest["allocations"][0]["selected_ids"]
    requests = [
        StudyBatchRequest(
            request_id=f"request-{index}",
            allocation_id="xstest-safe",
            sample_id=sample_id,
            messages=({"role": "user", "content": "prompt"},),
        )
        for index, sample_id in enumerate(selected)
    ]

    batch_module.validate_batch_contract(study, manifest, requests)


def test_rejects_duplicate_canonical_ids() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)

    with pytest.raises(ValueError, match="duplicate canonical IDs"):
        study.select_ids("xstest-safe", ["same"] * 100, "pilot")


def test_build_study_manifest_cli(tmp_path: Path) -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    catalog = synthetic_catalog(study)
    catalog_path = tmp_path / "catalog.json"
    output_path = tmp_path / "pilot-manifest.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "build-study-manifest",
            str(PROTOCOL),
            str(catalog_path),
            "--cohort",
            "pilot",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    assert manifest["manifest_sha256"] == result.output.strip()
    assert sum(len(item["selected_ids"]) for item in manifest["allocations"]) == 100


def test_offline_batch_runner_locks_manifest_seeds_and_artifacts(
    tmp_path: Path,
    protocol_data: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = "{% for message in messages %}{{ message['content'] }}{% endfor %}"
    template_sha = hashlib.sha256(template.encode()).hexdigest()
    for raw_model in protocol_data["study"]["models"]:
        runtime = copy.deepcopy(raw_model["runtime"])
        runtime["chat_template_sha256"] = template_sha
        raw_model["runtime"] = runtime
    protocol_data["study"]["primary_comparison"]["common_chat_template"]["sha256"] = template_sha
    protocol_path = tmp_path / "protocol.yaml"
    protocol_path.write_text(yaml.safe_dump(protocol_data), encoding="utf-8")
    study = StudyProtocol.from_yaml(protocol_path)

    catalog = synthetic_catalog(study)
    manifest = study.selection_manifest(catalog, "pilot")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    offline_ids = {
        allocation.id
        for allocation in study.benchmarks
        if allocation.execution_mode == "offline-batch"
    }
    expected = [
        (allocation["allocation_id"], sample_id)
        for allocation in manifest["allocations"]
        if allocation["allocation_id"] in offline_ids
        for sample_id in allocation["selected_ids"]
    ]
    requests_path = tmp_path / "requests.jsonl"
    requests_path.write_text(
        "".join(
            json.dumps(
                {
                    "request_id": f"request-{index}",
                    "allocation_id": allocation_id,
                    "sample_id": sample_id,
                    "messages": [{"role": "user", "content": f"prompt {index}"}],
                }
            )
            + "\n"
            for index, (allocation_id, sample_id) in enumerate(expected)
        ),
        encoding="utf-8",
    )

    model_path = tmp_path / "model"
    model_path.mkdir()
    artifacts = {
        "config.json": b"{}",
        "tokenizer_config.json": b"{}",
        "chat_template.jinja": template.encode(),
        "model-00001-of-00001.safetensors": b"tensor",
        "model.safetensors.index.json": json.dumps(
            {"weight_map": {"layer.weight": "model-00001-of-00001.safetensors"}}
        ).encode(),
    }
    for relative, content in artifacts.items():
        (model_path / relative).write_bytes(content)
    qualification = {
        "schema_version": "1",
        "model_id": study.models[0].id,
        "model_source": study.models[0].source,
        "model_revision": study.models[0].checkpoint_revision,
        "model_index": "model.safetensors.index.json",
        "files": [
            {
                "path": relative,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for relative, content in artifacts.items()
        ],
    }
    qualification["qualification_sha256"] = hashlib.sha256(
        json.dumps(qualification, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    qualification_path = tmp_path / "qualification.json"
    qualification_path.write_text(json.dumps(qualification), encoding="utf-8")
    template_path = tmp_path / "template.jinja"
    template_path.write_text(template, encoding="utf-8")
    lease_path = tmp_path / "lease.json"
    lease_path.write_text("{}", encoding="utf-8")
    output_path = tmp_path / "result.jsonl"

    class FakeTokenizer:
        def apply_chat_template(self, messages: list[dict], **kwargs: object) -> str:
            return str(messages[0]["content"])

    class FakeCandidate:
        text = "completion"
        finish_reason = "stop"
        token_ids = [1, 2]

    class FakeResult:
        outputs = [FakeCandidate()]
        prompt_token_ids = [1]

    class FakeEngine:
        def generate(self, prompts: list[str], params: list[dict], **kwargs: object) -> list:
            assert len(prompts) == len(expected)
            assert len({item["seed"] for item in params}) == len(expected)
            return [FakeResult() for _ in prompts]

    monkeypatch.setattr(batch_module.platform, "node", lambda: "basilisk")
    summary = run_offline_batch(
        protocol_path=protocol_path,
        manifest_path=manifest_path,
        requests_path=requests_path,
        model_id=study.models[0].id,
        model_path=model_path,
        model_qualification_path=qualification_path,
        chat_template_path=template_path,
        lease_receipt_path=lease_path,
        output_path=output_path,
        tokenizer_factory=lambda *args, **kwargs: FakeTokenizer(),
        sampling_factory=lambda **kwargs: kwargs,
        engine_factory=lambda **kwargs: FakeEngine(),
    )

    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert summary["requests"] == 80
    assert len(rows) == 80
    assert rows[0]["generation_seed"] == study.generation_seed(*expected[0])
    assert rows[0]["runtime"]["batch_invariant"] is True
    assert rows[0]["model_revision"] == study.models[0].checkpoint_revision
