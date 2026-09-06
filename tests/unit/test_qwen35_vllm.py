"""Contract tests for the pinned Qwen3.5 vLLM text adapter."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Any

import pytest


class _FakeTensor:
    def __init__(self, values: tuple[int, ...]) -> None:
        self.values: tuple[tuple[int, ...], ...] = (values,)

    def repeat(self, rows: int, _columns: int) -> _FakeTensor:
        self.values = self.values * rows
        return self


def _load_adapter(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, ModuleType]:
    torch = ModuleType("torch")
    torch.long = object()  # type: ignore[attr-defined]
    torch.Tensor = _FakeTensor  # type: ignore[attr-defined]
    torch.dtype = object  # type: ignore[attr-defined]
    torch.arange = lambda length, dtype: _FakeTensor(tuple(range(length)))  # type: ignore[attr-defined]

    qwen = ModuleType("vllm.model_executor.models.qwen3_5")

    class FakeCausalLM:
        pass

    class FakeConditionalGeneration:
        @classmethod
        def get_mamba_state_dtype_from_config(cls, _config: object) -> tuple[str, ...]:
            return ("dtype",)

        @classmethod
        def get_mamba_state_shape_from_config(cls, _config: object) -> tuple[tuple[int, int], ...]:
            return ((2, 3),)

        @classmethod
        def get_mamba_state_copy_func(cls) -> tuple[str, ...]:
            return ("copy",)

    qwen.Qwen3_5ForCausalLM = FakeCausalLM  # type: ignore[attr-defined]
    qwen.Qwen3_5ForConditionalGeneration = FakeConditionalGeneration  # type: ignore[attr-defined]
    modules = {
        "torch": torch,
        "vllm": ModuleType("vllm"),
        "vllm.model_executor": ModuleType("vllm.model_executor"),
        "vllm.model_executor.models": ModuleType("vllm.model_executor.models"),
        "vllm.model_executor.models.qwen3_5": qwen,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "matric_eval.studies.qwen35_vllm", raising=False)
    return importlib.import_module("matric_eval.studies.qwen35_vllm"), torch


def test_text_adapter_delegates_cache_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter_module, _ = _load_adapter(monkeypatch)
    model_class: Any = adapter_module.Qwen3_5TextForCausalLM

    assert model_class.is_hybrid is True
    assert model_class.supports_mrope is True
    assert model_class.get_mamba_state_dtype_from_config(object()) == ("dtype",)
    assert model_class.get_mamba_state_shape_from_config(object()) == ((2, 3),)
    assert model_class.get_mamba_state_copy_func() == ("copy",)


def test_text_mrope_matches_multimodal_text_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter_module, _ = _load_adapter(monkeypatch)
    model_class: Any = adapter_module.Qwen3_5TextForCausalLM
    model = model_class.__new__(model_class)

    positions, delta = model.get_mrope_input_positions([4, 8, 15, 16], [])

    assert positions.values == ((0, 1, 2, 3),) * 3
    assert delta == 0


def test_text_mrope_rejects_multimodal_features(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter_module, _ = _load_adapter(monkeypatch)
    model_class: Any = adapter_module.Qwen3_5TextForCausalLM
    model = model_class.__new__(model_class)

    with pytest.raises(ValueError, match="text-only"):
        model.get_mrope_input_positions([1], [object()])
