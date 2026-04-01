"""
OpenRouter provider for matric-eval.

OpenRouter provides a unified API for 100+ models from multiple providers
(OpenAI, Anthropic, Google, Meta, Mistral, etc.) via an OpenAI-compatible
endpoint.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from matric_eval.providers.base import (
    ModelInfo,
    ProviderConfig,
    ProviderConnectionError,
    ProviderModelNotFoundError,
)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api"


class OpenRouterProvider:
    """
    OpenRouter inference provider.

    Accesses 100+ models via OpenRouter's OpenAI-compatible API.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig(
            base_url=_OPENROUTER_BASE_URL,
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
        if not self._config.base_url:
            self._config.base_url = _OPENROUTER_BASE_URL

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def display_name(self) -> str:
        return "OpenRouter"

    def _make_request(self, path: str, method: str = "GET") -> dict:
        """Make an authenticated request to OpenRouter API."""
        url = f"{self._config.base_url}{path}"
        req = urllib.request.Request(url, method=method)
        if self._config.api_key:
            req.add_header("Authorization", f"Bearer {self._config.api_key}")
        req.add_header("HTTP-Referer", "https://github.com/jmagly/matric-eval")
        req.add_header("X-Title", "matric-eval")
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.URLError as e:
            raise ProviderConnectionError(
                f"Cannot reach OpenRouter at {self._config.base_url}: {e}"
            )

    def is_available(self) -> bool:
        if not self._config.api_key:
            return False
        try:
            self._make_request("/v1/models")
            return True
        except ProviderConnectionError:
            return False

    def list_models(self, max_size_gb: float = 0.0) -> list[ModelInfo]:
        data = self._make_request("/v1/models")

        models = []
        for model_data in data.get("data", []):
            model_id = model_data.get("id", "unknown")
            pricing = model_data.get("pricing", {})
            context_length = model_data.get("context_length", 0)

            models.append(ModelInfo(
                name=model_id,
                metadata={
                    "context_length": context_length,
                    "pricing": pricing,
                    "description": model_data.get("description", ""),
                    "top_provider": model_data.get("top_provider", {}),
                },
            ))
        return models

    def get_model_info(self, model: str) -> ModelInfo:
        models = self.list_models()
        for m in models:
            if m.name == model:
                return m
        raise ProviderModelNotFoundError(
            f"Model '{model}' not found on OpenRouter."
        )

    def format_model_id(self, model: str) -> str:
        # OpenRouter uses OpenAI-compatible API
        if model.startswith("openai/"):
            return model
        return f"openai/{model}"

    def get_eval_kwargs(self, model: str, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model_base_url": f"{self._config.base_url}/v1",
            "model_args": {
                "api_key": self._config.api_key,
                "extra_headers": {
                    "HTTP-Referer": "https://github.com/jmagly/matric-eval",
                    "X-Title": "matric-eval",
                },
            },
        }

        # OpenRouter-specific routing preferences
        extra = self._config.extra
        if extra:
            transforms = extra.get("transforms", [])
            route = extra.get("route", None)
            provider_prefs = extra.get("provider", None)

            extra_body: dict[str, Any] = {}
            if transforms:
                extra_body["transforms"] = transforms
            if route:
                extra_body["route"] = route
            if provider_prefs:
                extra_body["provider"] = provider_prefs
            if extra_body:
                kwargs["extra_body"] = extra_body

        kwargs.update(overrides)
        return kwargs
