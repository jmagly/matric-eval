"""
Provider registry for matric-eval.

Central registry for discovering and instantiating providers.
"""

from __future__ import annotations

from typing import Any

from matric_eval.providers.base import Provider, ProviderConfig


class ProviderRegistry:
    """
    Registry of available inference providers.

    Providers register themselves at import time. The registry supports
    lazy instantiation — providers are only created when requested.
    """

    def __init__(self) -> None:
        self._factories: dict[str, type] = {}
        self._instances: dict[str, Provider] = {}

    def register(self, name: str, provider_class: type) -> None:
        """Register a provider class by name."""
        self._factories[name] = provider_class

    def get(
        self,
        name: str,
        config: ProviderConfig | None = None,
        **kwargs: Any,
    ) -> Provider:
        """
        Get or create a provider instance.

        Args:
            name: Provider name (e.g., 'ollama', 'vllm').
            config: Optional provider configuration.
            **kwargs: Extra config passed as ProviderConfig.extra.

        Returns:
            Provider instance.

        Raises:
            ValueError: If provider name is not registered.
        """
        if config or kwargs:
            # Create a fresh instance with custom config
            if name not in self._factories:
                raise ValueError(
                    f"Unknown provider: '{name}'. "
                    f"Available: {', '.join(self._factories.keys())}"
                )
            if config is None:
                config = ProviderConfig(extra=kwargs)
            return self._factories[name](config)

        # Return cached instance
        if name not in self._instances:
            if name not in self._factories:
                raise ValueError(
                    f"Unknown provider: '{name}'. "
                    f"Available: {', '.join(self._factories.keys())}"
                )
            self._instances[name] = self._factories[name]()
        return self._instances[name]

    def list_names(self) -> list[str]:
        """List all registered provider names."""
        return list(self._factories.keys())

    def clear_cache(self) -> None:
        """Clear cached provider instances."""
        self._instances.clear()


# Global registry instance
_registry = ProviderRegistry()


def _register_builtins() -> None:
    """Register all built-in providers."""
    from matric_eval.providers.ollama import OllamaProvider
    from matric_eval.providers.llamacpp import LlamaCppProvider
    from matric_eval.providers.vllm import VLLMProvider
    from matric_eval.providers.openrouter import OpenRouterProvider
    from matric_eval.providers.chutes import ChutesProvider

    _registry.register("ollama", OllamaProvider)
    _registry.register("llama-cpp", LlamaCppProvider)
    _registry.register("vllm", VLLMProvider)
    _registry.register("openrouter", OpenRouterProvider)
    _registry.register("chutes", ChutesProvider)


_register_builtins()


def get_provider(
    name: str,
    config: ProviderConfig | None = None,
    **kwargs: Any,
) -> Provider:
    """Get a provider instance by name."""
    return _registry.get(name, config, **kwargs)


def list_providers() -> list[str]:
    """List all registered provider names."""
    return _registry.list_names()


def register_provider(name: str, provider_class: type) -> None:
    """Register a custom provider class."""
    _registry.register(name, provider_class)
