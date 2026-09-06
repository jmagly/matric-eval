"""Contract tests for the pinned Qwen3.5 vLLM text adapter."""

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("vllm")
adapter_module = pytest.importorskip("matric_eval.studies.qwen35_vllm")
model_class = adapter_module.Qwen3_5TextForCausalLM


def test_text_mrope_matches_qwen_multimodal_text_positions() -> None:
    assert model_class.is_hybrid is True
    assert callable(model_class.get_mamba_state_shape_from_config)
    assert callable(model_class.get_mamba_state_dtype_from_config)
    assert callable(model_class.get_mamba_state_copy_func)
    model = model_class.__new__(model_class)

    positions, delta = model.get_mrope_input_positions([4, 8, 15, 16], [])

    assert torch.equal(positions, torch.tensor([[0, 1, 2, 3]]).repeat(3, 1))
    assert delta == 0


def test_text_mrope_rejects_multimodal_features() -> None:
    model = model_class.__new__(model_class)

    with pytest.raises(ValueError, match="text-only"):
        model.get_mrope_input_positions([1], [object()])
