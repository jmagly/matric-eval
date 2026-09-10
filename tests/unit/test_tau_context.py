"""Unit tests for the pinned Tau request-guard contract."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import UserDict
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import qwen38_tau_context as tau_context  # noqa: E402

PATCH_MANIFEST = ROOT / "studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-context-guard.json"


def _budget() -> dict[str, int]:
    return {
        "max_context_tokens": 32768,
        "max_input_tokens": 24544,
        "max_output_tokens": 8192,
        "safety_margin_tokens": 32,
    }


def test_patch_manifest_is_content_addressed() -> None:
    contract = tau_context.load_patch_contract(PATCH_MANIFEST)
    assert contract.upstream_revision == "672227c6b6676edc20d57ea53b7000262aae77b9"
    assert contract.patch_sha256 == hashlib.sha256(contract.patch_path.read_bytes()).hexdigest()
    assert contract.patch_sha256 == contract.patched_diff_sha256
    assert contract.changed_paths == (
        "pyproject.toml",
        "src/tau2/utils/llm_utils.py",
        "uv.lock",
    )


def test_guard_accepts_24544_rejects_24545_and_filters_non_target() -> None:
    count = 24544

    def counter(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> int:
        return count

    guard = tau_context.TargetContextGuard("hosted_vllm/target", _budget(), counter)
    guard("external", [{"role": "user", "content": "ignored"}], None, None, "agent_response", {})
    guard(
        "hosted_vllm/target",
        [{"role": "user", "content": "accepted"}],
        None,
        None,
        "agent_response",
        {"max_tokens": 8192},
    )
    assert guard.observations[-1]["combined_tokens"] == 32768

    count = 24545
    with pytest.raises(tau_context.TargetContextRuntimeInvalid) as caught:
        guard(
            "hosted_vllm/target",
            [{"role": "user", "content": "rejected"}],
            None,
            "auto",
            "agent_response",
            {"max_tokens": 8192},
        )
    assert caught.value.observation["combined_tokens"] == 32769
    assert guard.last_request is not None


def test_guard_rejects_output_budget_drift() -> None:
    guard = tau_context.TargetContextGuard("target", _budget(), lambda messages, tools: 1)
    with pytest.raises(RuntimeError, match="output budget diverged"):
        guard("target", [], None, None, "agent_response", {"max_tokens": 4096})


def test_token_counter_passes_exact_template_controls() -> None:
    captured: dict[str, Any] = {}

    class Tokenizer:
        def apply_chat_template(
            self, conversation: list[dict[str, Any]], **kwargs: Any
        ) -> dict[str, list[int]]:
            captured.update(kwargs)
            captured["conversation"] = conversation
            return {"input_ids": [1, 2, 3], "attention_mask": [1, 1, 1]}

    count = tau_context.build_token_counter(Tokenizer(), "sealed-template")
    messages = [{"role": "user", "content": "fixture"}]
    tools = [{"type": "function", "function": {"name": "fixture"}}]
    assert count(messages, tools) == 3
    assert captured == {
        "conversation": messages,
        "tools": tools,
        "tokenize": True,
        "add_generation_prompt": True,
        "chat_template": "sealed-template",
        "enable_thinking": False,
    }


def test_token_counter_accepts_non_dict_mapping_batch_encoding() -> None:
    class Tokenizer:
        def apply_chat_template(self, conversation: Any, **kwargs: Any) -> UserDict:
            return UserDict({"input_ids": [1, 2, 3], "attention_mask": [1, 1, 1]})

    counter = tau_context.build_token_counter(Tokenizer(), "sealed-template")
    assert counter([{"role": "user", "content": "fixture"}], None) == 3


def test_token_counter_decodes_wire_format_tool_arguments_without_mutation() -> None:
    captured: dict[str, Any] = {}

    class Tokenizer:
        def apply_chat_template(self, conversation: Any, **kwargs: Any) -> list[int]:
            captured["conversation"] = conversation
            return [1]

    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "arguments": '{"account_id":"fixture"}',
                    },
                }
            ],
        }
    ]
    counter = tau_context.build_token_counter(Tokenizer(), "sealed-template")
    assert counter(messages, None) == 1
    assert captured["conversation"][0]["tool_calls"][0]["function"]["arguments"] == {
        "account_id": "fixture"
    }
    assert messages[0]["tool_calls"][0]["function"]["arguments"] == ('{"account_id":"fixture"}')


@pytest.mark.parametrize("arguments", ["not-json", "[]", 7])
def test_token_counter_rejects_non_object_tool_arguments(arguments: Any) -> None:
    class Tokenizer:
        def apply_chat_template(self, conversation: Any, **kwargs: Any) -> list[int]:
            raise AssertionError("invalid arguments must fail before template rendering")

    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {"type": "function", "function": {"name": "lookup", "arguments": arguments}}
            ],
        }
    ]
    counter = tau_context.build_token_counter(Tokenizer(), "sealed-template")
    with pytest.raises(RuntimeError, match="tool-call arguments"):
        counter(messages, None)


def test_attested_tokenizer_requires_assets_template_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = tmp_path / "model"
    model.mkdir()
    (model / "tokenizer.json").write_text("{}", encoding="utf-8")
    (model / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    template = tmp_path / "template.jinja"
    template.write_text("fixture-template", encoding="utf-8")
    digest = hashlib.sha256(b"fixture-template").hexdigest()
    monkeypatch.setattr(tau_context.importlib.metadata, "version", lambda _: "5.14.1")

    class Tokenizer:
        def apply_chat_template(
            self, conversation: list[dict[str, Any]], **kwargs: Any
        ) -> list[int]:
            return [1]

    counter, evidence = tau_context.load_attested_tokenizer(
        model_path=model,
        chat_template_path=template,
        expected_template_sha256=digest,
        expected_transformers_version="5.14.1",
        tokenizer_factory=lambda *args, **kwargs: Tokenizer(),
    )
    assert counter([{"role": "user", "content": "x"}], None) == 1
    assert evidence["chat_template_sha256"] == digest
    assert set(evidence["tokenizer_files"]) == {"tokenizer.json", "tokenizer_config.json"}

    with pytest.raises(RuntimeError, match="Transformers version"):
        tau_context.load_attested_tokenizer(
            model_path=model,
            chat_template_path=template,
            expected_template_sha256=digest,
            expected_transformers_version="0.0.0",
            tokenizer_factory=lambda *args, **kwargs: Tokenizer(),
        )


def test_apply_patch_requires_clean_exact_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch = tmp_path / "guard.patch"
    patch.write_text("fixture", encoding="utf-8")
    contract = tau_context.TauPatchContract(
        upstream_revision="a" * 40,
        patch_path=patch,
        patch_sha256="b" * 64,
        patched_diff_sha256="c" * 64,
        changed_paths=("source.py",),
        transformers_version="5.14.1",
    )
    outputs = iter(["a" * 40 + "\n", " M source.py\n"])
    monkeypatch.setattr(tau_context, "_git", lambda *args, **kwargs: next(outputs))
    with pytest.raises(RuntimeError, match="clean tracked worktree"):
        tau_context.apply_tau_patch(tmp_path, contract)


def test_verify_checkout_rejects_wrong_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = tau_context.TauPatchContract(
        upstream_revision="a" * 40,
        patch_path=Path("guard.patch"),
        patch_sha256="b" * 64,
        patched_diff_sha256="c" * 64,
        changed_paths=("source.py",),
        transformers_version="5.14.1",
    )
    outputs: list[str | bytes] = ["a" * 40 + "\n", " M source.py\n", b"wrong"]
    monkeypatch.setattr(tau_context, "_git", lambda *args, **kwargs: outputs.pop(0))
    with pytest.raises(RuntimeError, match="content-addressed patch"):
        tau_context.verify_tau_checkout(Path("/tau"), contract)


def _checkout_contract(tmp_path: Path, expected_diff: bytes) -> tau_context.TauPatchContract:
    return tau_context.TauPatchContract(
        upstream_revision="a" * 40,
        patch_path=tmp_path / "guard.patch",
        patch_sha256=hashlib.sha256(expected_diff).hexdigest(),
        patched_diff_sha256=hashlib.sha256(expected_diff).hexdigest(),
        changed_paths=("source.py",),
        transformers_version="5.14.1",
    )


def test_checkout_rejects_staged_drift_hidden_from_unstaged_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_diff = b"expected unstaged patch"
    contract = _checkout_contract(tmp_path, expected_diff)

    def git(checkout: Path, arguments: list[str], **kwargs: Any) -> str | bytes:
        if arguments[0] == "rev-parse":
            return "a" * 40 + "\n"
        if arguments[0] == "status":
            return "MM source.py\n"
        assert arguments[0] == "diff"
        assert kwargs["text"] is False
        return b"staged tampering plus patch" if "HEAD" in arguments else expected_diff

    monkeypatch.setattr(tau_context, "_git", git)
    with pytest.raises(RuntimeError, match="content-addressed patch"):
        tau_context.verify_tau_checkout(tmp_path, contract)


def test_checkout_accepts_exact_patch_even_if_staged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_diff = b"expected full patch"
    contract = _checkout_contract(tmp_path, expected_diff)

    def git(checkout: Path, arguments: list[str], **kwargs: Any) -> str | bytes:
        if arguments[0] == "rev-parse":
            return "a" * 40 + "\n"
        if arguments[0] == "status":
            return "M  source.py\n"
        assert arguments[0] == "diff"
        return expected_diff if "HEAD" in arguments else b""

    monkeypatch.setattr(tau_context, "_git", git)
    result = tau_context.verify_tau_checkout(tmp_path, contract)
    assert result["tracked_diff_sha256"] == contract.patched_diff_sha256


@pytest.mark.parametrize("operation", ["verify", "apply"])
def test_untracked_source_cannot_bypass_checkout_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    expected_diff = b"expected patch"
    contract = _checkout_contract(tmp_path, expected_diff)

    def git(checkout: Path, arguments: list[str], **kwargs: Any) -> str | bytes:
        if arguments[0] == "rev-parse":
            return "a" * 40 + "\n"
        if arguments[0] == "status":
            tracked = " M source.py\n" if operation == "verify" else ""
            return tracked + ("?? injected.py\n" if "--untracked-files=all" in arguments else "")
        return expected_diff

    monkeypatch.setattr(tau_context, "_git", git)
    if operation == "verify":
        with pytest.raises(RuntimeError, match="changed paths"):
            tau_context.verify_tau_checkout(tmp_path, contract)
    else:
        with pytest.raises(RuntimeError, match="clean"):
            tau_context.apply_tau_patch(tmp_path, contract)


def test_relative_manifest_resolves_patch_before_git_changes_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_dir = tmp_path / "patches"
    patch_dir.mkdir()
    patch_path = patch_dir / "guard.patch"
    patch_path.write_bytes(b"fixture patch")
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    manifest_path = patch_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "patch_file": "guard.patch",
                "patch_sha256": digest,
                "patched_diff_sha256": digest,
                "upstream_revision": "a" * 40,
                "changed_paths": ["source.py"],
                "transformers_version": "5.14.1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    contract = tau_context.load_patch_contract(Path("patches/manifest.json"))
    assert contract.patch_path == patch_path.resolve()
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> None:
        calls.append(command)
        assert command[0:3] == ["git", "-C", str(tmp_path / "other-checkout")]
        assert Path(command[-1]).is_absolute()
        assert Path(command[-1]).read_bytes() == b"fixture patch"

    monkeypatch.setattr(tau_context.subprocess, "run", run)
    outputs = iter(["a" * 40 + "\n", ""])
    monkeypatch.setattr(tau_context, "_git", lambda *args, **kwargs: next(outputs))
    monkeypatch.setattr(tau_context, "verify_tau_checkout", lambda *args: {"verified": True})
    assert tau_context.apply_tau_patch(tmp_path / "other-checkout", contract) == {"verified": True}
    assert len(calls) == 2
    assert calls[0][3:5] == ["apply", "--check"]
    assert calls[1][3] == "apply"


def test_exception_chain_is_bounded_and_content_free_shape() -> None:
    try:
        try:
            raise ValueError("inner")
        except ValueError as exc:
            raise RuntimeError("outer") from exc
    except RuntimeError as exc:
        chain = tau_context.exception_chain(exc)
    assert chain == [
        {"type": "RuntimeError", "message": "outer"},
        {"type": "ValueError", "message": "inner"},
    ]
