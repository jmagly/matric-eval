"""Tests for the official BFCL study bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
SCRIPT = ROOT / "scripts/run_qwen38_bfcl.py"
SPEC = importlib.util.spec_from_file_location("qwen38_bfcl_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bfcl_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bfcl_runner
SPEC.loader.exec_module(bfcl_runner)


def test_protocol_and_generation_seed_match_study_contract() -> None:
    protocol = StudyProtocol.from_yaml(PROTOCOL)
    model = protocol.models[0]
    study_data, model_data, sampler = bfcl_runner._load_protocol(PROTOCOL, model.id)

    assert study_data["id"] == protocol.id
    assert model_data["checkpoint_revision"] == model.checkpoint_revision
    assert sampler["temperature"] == 1.0
    assert bfcl_runner._generation_seed(protocol.seed, "case-1") == protocol.generation_seed(
        "bfcl-v4-agentic", "case-1"
    )

    with pytest.raises(ValueError, match="unknown study model"):
        bfcl_runner._load_protocol(PROTOCOL, "unknown")


@pytest.mark.parametrize("cohort", ["pilot", "full"])
def test_manifest_verification_requires_exact_scored_ids(tmp_path: Path, cohort: str) -> None:
    manifest = {
        "study_id": "study",
        "cohort": cohort,
        "allocations": [{"allocation_id": "bfcl-v4-agentic", "selected_ids": ["one", "two"]}],
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest["manifest_sha256"] = manifest_hash
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        bfcl_runner._verify_manifest(
            path,
            {"manifest_sha256": manifest_hash, "cohort": cohort},
            ["one", "two"],
            "study",
        )
        == manifest_hash
    )
    with pytest.raises(ValueError, match="exactly match"):
        bfcl_runner._verify_manifest(
            path,
            {"manifest_sha256": manifest_hash, "cohort": cohort},
            ["two", "one"],
            "study",
        )


def test_registered_handler_sends_full_sampler_and_per_case_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapping: dict[str, Any] = {}
    captured: dict[str, Any] = {}

    class ModelConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class Client:
        class Completions:
            def create(self, **kwargs: Any) -> object:
                captured.update(kwargs)
                return object()

        completions = Completions()

    class QwenFCHandler:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.model_path_or_id = "/qualified/model"
            self.max_context_length = 65536
            self.tokenizer = SimpleNamespace(tokenize=lambda prompt: prompt.split())
            self.client = Client()

        def inference(
            self, test_entry: dict[str, Any], include_input_log: bool, exclude_state_log: bool
        ) -> str:
            return self._study_sample_id

        def _format_prompt(self, messages: list[Any], functions: list[Any]) -> str:
            return "one two three"

        def _query_prompting(self, inference_data: dict[str, Any]) -> tuple[Any, float]:
            raise NotImplementedError

    config_module = ModuleType("bfcl_eval.constants.model_config")
    config_module.MODEL_CONFIG_MAPPING = mapping  # type: ignore[attr-defined]
    config_module.ModelConfig = ModelConfig  # type: ignore[attr-defined]
    qwen_module = ModuleType("bfcl_eval.model_handler.local_inference.qwen_fc")
    qwen_module.QwenFCHandler = QwenFCHandler  # type: ignore[attr-defined]
    for name, module in {
        "bfcl_eval": ModuleType("bfcl_eval"),
        "bfcl_eval.constants": ModuleType("bfcl_eval.constants"),
        "bfcl_eval.constants.model_config": config_module,
        "bfcl_eval.model_handler": ModuleType("bfcl_eval.model_handler"),
        "bfcl_eval.model_handler.local_inference": ModuleType(
            "bfcl_eval.model_handler.local_inference"
        ),
        "bfcl_eval.model_handler.local_inference.qwen_fc": qwen_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    sampler = {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
        "max_tokens": 8192,
    }
    bfcl_runner._register_study_model("model", "model", sampler, 123, 32768)
    handler = mapping["model"].model_handler("model", 1.0, "model", True)

    assert handler.inference({"id": "case-1"}, False, False) == "case-1"
    response, elapsed = handler._query_prompting({"message": [], "function": []})

    assert response is not None and elapsed >= 0
    assert captured["temperature"] == 1.0
    assert captured["top_p"] == 0.95
    assert captured["presence_penalty"] == 0.0
    assert captured["max_tokens"] == 8192
    assert captured["seed"] == bfcl_runner._generation_seed(123, "case-1")
    assert captured["extra_body"] == {
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
    }


def test_endpoint_and_content_free_file_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return json.dumps({"data": [{"id": "model"}, {"id": "/qualified/model"}]}).encode()[
                :size
            ]

    monkeypatch.setattr(bfcl_runner.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    bfcl_runner._validate_endpoint("http://127.0.0.1:18080/v1", "model", Path("/qualified/model"))
    with pytest.raises(ValueError, match="localhost"):
        bfcl_runner._validate_endpoint("http://example.com/v1", "model", Path("/qualified/model"))

    result = tmp_path / "results" / "result.json"
    result.parent.mkdir()
    result.write_text('{"id": "case-1", "response": "private"}\n', encoding="utf-8")
    inventory = bfcl_runner._file_manifest(tmp_path / "results")

    assert bfcl_runner._collect_top_level_ids(tmp_path / "results") == {"case-1"}
    assert inventory[0]["path"] == "result.json"
    assert "private" not in json.dumps(inventory)


def test_private_tree_is_sealed_and_rejects_links(tmp_path: Path) -> None:
    root = tmp_path / "results"
    nested = root / "nested"
    nested.mkdir(parents=True)
    artifact = nested / "result.json"
    artifact.write_text("private", encoding="utf-8")

    bfcl_runner._seal_private_tree(root)

    assert root.stat().st_mode & 0o777 == 0o750
    assert nested.stat().st_mode & 0o777 == 0o750
    assert artifact.stat().st_mode & 0o777 == 0o600

    (root / "link").symlink_to(artifact)
    with pytest.raises(RuntimeError, match="symbolic link"):
        bfcl_runner._seal_private_tree(root)
