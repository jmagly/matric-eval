"""
Provider abstraction for matric-eval.

Supports multiple inference backends: Ollama, llama.cpp, vLLM, OpenRouter, Chutes.
"""

from matric_eval.providers.base import (
    ModelInfo,
    Provider,
    ProviderConfig,
    ProviderConnectionError,
    ProviderError,
    ProviderModelNotFoundError,
)
from matric_eval.providers.chutes import ChutesProvider
from matric_eval.providers.llamacpp import LlamaCppProvider
from matric_eval.providers.ollama import OllamaProvider
from matric_eval.providers.openrouter import OpenRouterProvider
from matric_eval.providers.registry import (
    ProviderRegistry,
    get_provider,
    list_providers,
    register_provider,
)
from matric_eval.providers.vllm import VLLMProvider

__all__ = [
    # Base
    "Provider",
    "ProviderConfig",
    "ProviderError",
    "ProviderConnectionError",
    "ProviderModelNotFoundError",
    "ModelInfo",
    # Registry
    "ProviderRegistry",
    "get_provider",
    "list_providers",
    "register_provider",
    # Providers
    "OllamaProvider",
    "LlamaCppProvider",
    "VLLMProvider",
    "OpenRouterProvider",
    "ChutesProvider",
]
