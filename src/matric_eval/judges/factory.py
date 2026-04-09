"""
Judge factory for creating judges from configuration strings or dicts.

Supports shorthand notation: "ollama:llama3.1:8b", "openai:gpt-4o", etc.
"""

import os
from typing import Optional

from matric_eval.judges.base import Judge
from matric_eval.judges.ollama import OllamaJudge
from matric_eval.judges.openai_compat import OpenAICompatibleJudge


class JudgeFactory:
    """
    Create judge instances from configuration.

    Supports both shorthand strings and config dicts.

    Shorthand format: "provider:model"
    Examples:
        "ollama:llama3.1:8b"
        "openai:gpt-4o"
        "openrouter:anthropic/claude-3.5-sonnet"
        "vllm:meta-llama/Llama-3.2-3B"
    """

    # Provider -> (JudgeClass, default_model, env_var_for_api_key)
    PROVIDERS: dict[str, tuple[type, str, Optional[str]]] = {
        "ollama": (OllamaJudge, "llama3.1:8b", None),
        "openai": (OpenAICompatibleJudge, "gpt-4o", "OPENAI_API_KEY"),
        "anthropic": (OpenAICompatibleJudge, "claude-sonnet-4-20250514", "ANTHROPIC_API_KEY"),
        "openrouter": (OpenAICompatibleJudge, "anthropic/claude-3.5-sonnet", "OPENROUTER_API_KEY"),
        "vllm": (OpenAICompatibleJudge, "meta-llama/Llama-3.2-3B", None),
        "groq": (OpenAICompatibleJudge, "llama-3.1-8b-instant", "GROQ_API_KEY"),
        "together": (OpenAICompatibleJudge, "meta-llama/Llama-3.2-3B-Instruct-Turbo", "TOGETHER_API_KEY"),
    }

    # Base URLs for known providers
    BASE_URLS: dict[str, str] = {
        "openrouter": "https://openrouter.ai/api/v1",
        "groq": "https://api.groq.com/openai/v1",
        "together": "https://api.together.xyz/v1",
    }

    @classmethod
    def create(cls, judge_spec: str, **kwargs) -> Judge:
        """
        Create a judge from a shorthand specification string.

        Args:
            judge_spec: Format "provider:model" (e.g., "ollama:llama3.1:8b")
            **kwargs: Additional keyword arguments passed to the judge constructor

        Returns:
            Configured Judge instance

        Raises:
            ValueError: If provider is not recognized
        """
        provider, model = cls._parse_spec(judge_spec)

        if provider not in cls.PROVIDERS:
            raise ValueError(
                f"Unknown judge provider: '{provider}'. "
                f"Available: {', '.join(sorted(cls.PROVIDERS.keys()))}"
            )

        judge_class, default_model, api_key_env = cls.PROVIDERS[provider]
        model = model or default_model

        # Build constructor kwargs
        ctor_kwargs = {"model": model, **kwargs}

        # Add base_url for providers that need it
        if provider in cls.BASE_URLS and "base_url" not in ctor_kwargs:
            ctor_kwargs["base_url"] = cls.BASE_URLS[provider]

        # Add API key from environment if available
        if api_key_env and "api_key" not in ctor_kwargs:
            api_key = os.environ.get(api_key_env)
            if api_key:
                ctor_kwargs["api_key"] = api_key

        return judge_class(**ctor_kwargs)

    @classmethod
    def from_config(cls, config: dict) -> Judge:
        """
        Create a judge from a config dict.

        Args:
            config: Dict with "type" key and optional model/settings.
                Example: {"type": "ollama", "model": "llama3.1:8b", "temperature": 0}

        Returns:
            Configured Judge instance
        """
        config = dict(config)  # Don't mutate input
        judge_type = config.pop("type")
        model = config.pop("model", None)
        spec = f"{judge_type}:{model}" if model else judge_type
        return cls.create(spec, **config)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List available judge provider names."""
        return sorted(cls.PROVIDERS.keys())

    @classmethod
    def _parse_spec(cls, spec: str) -> tuple[str, Optional[str]]:
        """
        Parse "provider:model" spec string.

        Handles the tricky case where Ollama models contain colons
        (e.g., "ollama:llama3.1:8b" -> provider="ollama", model="llama3.1:8b").
        """
        if ":" not in spec:
            return spec, None

        parts = spec.split(":", 1)
        provider = parts[0]

        if provider in cls.PROVIDERS:
            model = parts[1] if len(parts) > 1 and parts[1] else None
            return provider, model

        # If first part looks like a provider name (simple word) but isn't
        # recognized, return it as-is so create() raises a clear error
        if provider.isalpha():
            return provider, parts[1] if len(parts) > 1 else None

        # Otherwise treat entire string as model name (e.g., "org/model:tag")
        # Default to ollama for bare model names
        return "ollama", spec


def create_judge(judge_spec: str, **kwargs) -> Judge:
    """
    Convenience function to create a judge from a spec string.

    Args:
        judge_spec: Format "provider:model" (e.g., "ollama:llama3.1:8b")
        **kwargs: Additional keyword arguments

    Returns:
        Configured Judge instance
    """
    return JudgeFactory.create(judge_spec, **kwargs)
