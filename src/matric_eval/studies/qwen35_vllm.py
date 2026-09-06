"""Text-only Qwen3.5 adapter for the pinned vLLM 0.26 study runtime."""

from __future__ import annotations

import torch
from vllm.model_executor.models.qwen3_5 import (
    Qwen3_5ForCausalLM,
    Qwen3_5ForConditionalGeneration,
)


class Qwen3_5TextForCausalLM(Qwen3_5ForCausalLM):
    """Expose the text-only M-RoPE contract omitted by vLLM's causal-LM class."""

    supports_mrope = True
    is_hybrid = True

    @classmethod
    def get_mamba_state_dtype_from_config(cls, vllm_config: object) -> tuple[torch.dtype, ...]:
        """Delegate the cache dtype contract to vLLM's Qwen3.5 wrapper."""
        return Qwen3_5ForConditionalGeneration.get_mamba_state_dtype_from_config(vllm_config)

    @classmethod
    def get_mamba_state_shape_from_config(
        cls, vllm_config: object
    ) -> tuple[tuple[int, int], ...]:
        """Delegate the GDN/Mamba cache shapes to vLLM's Qwen3.5 wrapper."""
        return Qwen3_5ForConditionalGeneration.get_mamba_state_shape_from_config(vllm_config)

    @classmethod
    def get_mamba_state_copy_func(cls) -> tuple[object, ...]:
        """Delegate the GDN/Mamba cache copy functions to vLLM's Qwen3.5 wrapper."""
        return Qwen3_5ForConditionalGeneration.get_mamba_state_copy_func()

    def get_mrope_input_positions(
        self,
        input_tokens: list[int],
        mm_features: list[object],
    ) -> tuple[torch.Tensor, int]:
        """Return the same three identical position rows used for text by Qwen3.5 VL."""
        if mm_features:
            raise ValueError("the study Qwen3.5 adapter accepts text-only inputs")
        positions = torch.arange(len(input_tokens), dtype=torch.long).repeat(3, 1)
        return positions, 0
