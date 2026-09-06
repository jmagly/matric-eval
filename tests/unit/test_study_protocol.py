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
import matric_eval.studies.runner_cli as runner_cli
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


def test_runtime_protocol_can_skip_only_registry_import(
    protocol_data: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(benchmarks: object) -> None:
        raise RuntimeError("registry imported")

    monkeypatch.setattr(StudyProtocol, "_validate_registry", fail_if_called)

    study = StudyProtocol.from_dict(protocol_data, validate_registry=False)

    assert study.id == "qwen38-obliteration-2026-09"
    with pytest.raises(RuntimeError, match="registry imported"):
        StudyProtocol.from_dict(protocol_data)


def test_runtime_environment_requires_pinned_container_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / ".dockerenv"
    marker.touch()
    server = {"image": "example@sha256:" + "a" * 64, "version": "0.26.0"}
    monkeypatch.setenv("MATRIC_EVAL_RUNTIME_IMAGE", "wrong")

    with pytest.raises(RuntimeError, match="protocol-pinned image"):
        batch_module.verify_runtime_environment(server, container_marker=marker)

    monkeypatch.setenv("MATRIC_EVAL_RUNTIME_IMAGE", str(server["image"]))
    monkeypatch.setattr(
        batch_module.importlib.metadata,
        "version",
        lambda package: "0.26.0" if package == "vllm" else "5.14.1",
    )

    assert batch_module.verify_runtime_environment(server, container_marker=marker) == {
        "vllm": "0.26.0",
        "transformers": "5.14.1",
    }


def test_active_gpu_lease_receipt_is_scoped_and_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "lease-test"
    gpu_uuid = "GPU-170a99ee-850f-2182-1050-4e8d3c87b6b0"
    states = iter(("pending", "active"))

    def status(_socket_path: Path) -> dict[str, object]:
        return {
            "ok": True,
            "backend_available": True,
            "backend_checked_at": 123.0,
            "gpus": [{"uuid": gpu_uuid, "total_mib": 81920}],
            "leases": [
                {
                    "token": token,
                    "owner": "matric-eval-qwen38",
                    "state": next(states),
                    "requested_mib": 70000,
                    "gpu_uuids": [gpu_uuid],
                }
            ],
        }

    monkeypatch.setenv("OLLAMA_UNIFY_GPU_LEASE", token)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", gpu_uuid)
    receipt_path = tmp_path / "lease.json"

    digest = batch_module.capture_active_gpu_lease(
        receipt_path,
        status_factory=status,
        sleep=lambda _seconds: None,
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert digest == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert receipt["lease"]["state"] == "active"
    assert receipt["lease"]["gpu_uuids"] == [gpu_uuid]
    assert receipt_path.stat().st_mode & 0o777 == 0o600


def test_active_gpu_lease_rejects_visible_device_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_UNIFY_GPU_LEASE", "lease-test")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-requested")

    with pytest.raises(RuntimeError, match="does not exactly match"):
        batch_module.capture_active_gpu_lease(
            tmp_path / "lease.json",
            status_factory=lambda _path: {
                "ok": True,
                "leases": [
                    {
                        "token": "lease-test",
                        "state": "active",
                        "gpu_uuids": ["GPU-different"],
                    }
                ],
            },
        )


def test_model_resident_marker_is_token_specific(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "lease-test_123"
    base = tmp_path / "source-xstest-safe"
    monkeypatch.setenv("OLLAMA_UNIFY_GPU_LEASE", token)
    monkeypatch.setenv("MATRIC_EVAL_MODEL_READY_BASE", str(base))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-test")

    marker = batch_module.signal_model_resident("source")

    assert marker == tmp_path / f"source-xstest-safe.{token}.ready"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["lease_token_sha256"] == hashlib.sha256(token.encode()).hexdigest()
    assert payload["cuda_visible_devices"] == "GPU-test"
    assert marker.stat().st_mode & 0o777 == 0o600


def test_lean_runner_cli_forwards_locked_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def fake_run(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"requests": 5, "output_sha256": "a" * 64}

    monkeypatch.setattr(runner_cli, "run_offline_batch", fake_run)
    paths = [tmp_path / name for name in ("protocol", "manifest", "requests")]
    result = runner_cli.main(
        [
            *(str(path) for path in paths),
            "--model-id",
            "model",
            "--model-path",
            str(tmp_path / "model"),
            "--model-qualification",
            str(tmp_path / "qualification"),
            "--chat-template",
            str(tmp_path / "template"),
            "--gpu-lease-receipt",
            str(tmp_path / "lease"),
            "--output",
            str(tmp_path / "output"),
        ]
    )

    assert result == 0
    assert captured["protocol_path"] == paths[0]
    assert captured["output_path"] == tmp_path / "output"
    assert json.loads(capsys.readouterr().out)["requests"] == 5


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


def test_rejects_unpinned_gpu_memory_utilization(protocol_data: dict) -> None:
    changed = copy.deepcopy(protocol_data)
    del changed["study"]["execution"]["model_server"]["gpu_memory_utilization"]

    with pytest.raises(ValueError, match="gpu_memory_utilization"):
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

    with pytest.raises(ValueError, match="read-only model filesystem"):
        batch_module.verify_model_artifact(
            study.models[0],
            model_path,
            qualification,
            verify_tensor_hashes=False,
        )

    class ReadOnlyFilesystem:
        f_flag = batch_module.os.ST_RDONLY

    monkeypatch.setattr(batch_module.os, "statvfs", lambda _path: ReadOnlyFilesystem())
    tensor_path = model_path / "model-00001-of-00001.safetensors"
    tensor_path.write_bytes(b"mutate")
    assert (
        batch_module.verify_model_artifact(
            study.models[0],
            model_path,
            qualification,
            verify_tensor_hashes=False,
        )
        == qualification["qualification_sha256"]
    )
    tensor_path.write_bytes(b"tensor")

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

    engine_kwargs: dict[str, object] = {}

    def fake_engine_factory(**kwargs: object) -> FakeEngine:
        engine_kwargs.update(kwargs)
        return FakeEngine()

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
        engine_factory=fake_engine_factory,
    )

    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert summary["requests"] == 80
    assert len(rows) == 80
    assert rows[0]["generation_seed"] == study.generation_seed(*expected[0])
    assert rows[0]["runtime"]["batch_invariant"] is True
    assert rows[0]["runtime"]["versions"]["vllm"] == "injected-test-double"
    assert rows[0]["runtime"]["model_verification"] == "full-sha256"
    assert engine_kwargs["gpu_memory_utilization"] == 0.9
    assert rows[0]["model_revision"] == study.models[0].checkpoint_revision
