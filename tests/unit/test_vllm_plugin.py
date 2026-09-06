"""Tests for process-safe vLLM architecture registration."""

from __future__ import annotations

import json
import sys
from types import ModuleType

import pytest

from matric_eval.studies import vllm_plugin


def test_plugin_registers_environment_mappings(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: list[tuple[str, str]] = []

    class Registry:
        @staticmethod
        def register_model(architecture: str, implementation: str) -> None:
            registered.append((architecture, implementation))

    vllm = ModuleType("vllm")
    vllm.ModelRegistry = Registry  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vllm", vllm)
    monkeypatch.setenv(
        vllm_plugin.REGISTRATIONS_ENV,
        json.dumps({"Qwen": "adapter:Class"}),
    )

    vllm_plugin.register_models()

    assert registered == [("Qwen", "adapter:Class")]


def test_plugin_is_inert_without_study_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(vllm_plugin.REGISTRATIONS_ENV, raising=False)

    vllm_plugin.register_models()


@pytest.mark.parametrize("value", ["not-json", "[]", '{"Qwen": 1}'])
def test_plugin_rejects_invalid_registration_environment(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(vllm_plugin.REGISTRATIONS_ENV, value)

    with pytest.raises(ValueError, match=vllm_plugin.REGISTRATIONS_ENV):
        vllm_plugin.register_models()
