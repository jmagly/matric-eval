"""
Provider protocol and base types for matric-eval.

Defines the interface that all inference providers must implement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class ProviderError(Exception):
    """Base exception for provider errors."""


class ProviderConnectionError(ProviderError):
    """Raised when a provider cannot be reached."""


class ProviderModelNotFoundError(ProviderError):
    """Raised when a requested model is not available on the provider."""


@dataclass
class ModelInfo:
    """Information about a model available on a provider."""

    name: str
    """Model identifier as used by the provider (e.g., 'llama3.2:3b')."""

    size_gb: float = 0.0
    """Model size in GB (0 if unknown)."""

    capabilities: list[str] = field(default_factory=list)
    """Capabilities like 'thinking', 'tool_calling', 'vision'."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Provider-specific metadata."""

    def has_capability(self, capability: str) -> bool:
        """Check if the model has a specific capability."""
        return capability in self.capabilities


@dataclass
class ProviderConfig:
    """Configuration for a provider instance."""

    base_url: str = ""
    """Base URL for the provider's API endpoint."""

    api_key: str = ""
    """API key for authenticated providers."""

    timeout: int = 120
    """Request timeout in seconds."""

    max_retries: int = 3
    """Maximum number of retries on transient failures."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Provider-specific configuration options."""


@runtime_checkable
class Provider(Protocol):
    """
    Protocol that all inference providers must implement.

    A provider handles:
    - Model discovery and listing
    - Capability detection
    - Model string formatting for Inspect AI
    - Health checks
    """

    @property
    def name(self) -> str:
        """Provider identifier (e.g., 'ollama', 'vllm', 'openrouter')."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable provider name."""
        ...

    def is_available(self) -> bool:
        """
        Check if the provider is reachable and operational.

        Returns:
            True if provider is available, False otherwise.
        """
        ...

    def list_models(self, max_size_gb: float = 0.0) -> list[ModelInfo]:
        """
        List models available on this provider.

        Args:
            max_size_gb: Maximum model size filter (0 = no filter).

        Returns:
            List of available models.

        Raises:
            ProviderConnectionError: If provider is unreachable.
        """
        ...

    def get_model_info(self, model: str) -> ModelInfo:
        """
        Get detailed info for a specific model.

        Args:
            model: Model identifier.

        Returns:
            Model information.

        Raises:
            ProviderModelNotFoundError: If model is not found.
            ProviderConnectionError: If provider is unreachable.
        """
        ...

    def format_model_id(self, model: str) -> str:
        """
        Format a model name into the Inspect AI model identifier.

        Each provider uses a different prefix for Inspect AI:
        - Ollama: 'ollama/llama3.2:3b'
        - vLLM/OpenRouter/Chutes: 'openai/model-name' (OpenAI-compatible)
        - llama.cpp: 'openai/model-name' (OpenAI-compatible endpoint)

        Args:
            model: Model name as known to this provider.

        Returns:
            Full model identifier for Inspect AI's eval() function.
        """
        ...

    def get_eval_kwargs(self, model: str, **overrides: Any) -> dict[str, Any]:
        """
        Get provider-specific kwargs to pass to Inspect AI's eval().

        This includes things like base_url for OpenAI-compatible endpoints,
        API keys, and other provider-specific configuration.

        Args:
            model: Model identifier.
            **overrides: Override specific kwargs.

        Returns:
            Dictionary of kwargs for inspect_ai.eval().
        """
        ...
