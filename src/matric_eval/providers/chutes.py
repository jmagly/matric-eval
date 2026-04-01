"""
Chutes provider for matric-eval.

Chutes provides serverless GPU inference with pay-per-token pricing.
Uses an OpenAI-compatible API.
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

_CHUTES_BASE_URL = "https://api.chutes.ai"


class ChutesProvider:
    """
    Chutes serverless GPU inference provider.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig(
            base_url=_CHUTES_BASE_URL,
            api_key=os.environ.get("CHUTES_API_KEY", ""),
        )
        if not self._config.base_url:
            self._config.base_url = _CHUTES_BASE_URL

    @property
    def name(self) -> str:
        return "chutes"

    @property
    def display_name(self) -> str:
        return "Chutes"

    def _make_request(self, path: str, method: str = "GET") -> dict:
        """Make an authenticated request to Chutes API."""
        url = f"{self._config.base_url}{path}"
        req = urllib.request.Request(url, method=method)
        if self._config.api_key:
            req.add_header("Authorization", f"Bearer {self._config.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.URLError as e:
            raise ProviderConnectionError(
                f"Cannot reach Chutes at {self._config.base_url}: {e}"
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
            models.append(ModelInfo(
                name=model_id,
                metadata=model_data,
            ))
        return models

    def get_model_info(self, model: str) -> ModelInfo:
        models = self.list_models()
        for m in models:
            if m.name == model:
                return m
        raise ProviderModelNotFoundError(
            f"Model '{model}' not found on Chutes."
        )

    def format_model_id(self, model: str) -> str:
        if model.startswith("openai/"):
            return model
        return f"openai/{model}"

    def get_eval_kwargs(self, model: str, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model_base_url": f"{self._config.base_url}/v1",
            "model_args": {"api_key": self._config.api_key},
        }

        # Chutes-specific: increase timeout for cold starts
        extra = self._config.extra
        cold_start_timeout = (extra or {}).get("cold_start_timeout", 300)
        kwargs.setdefault("model_args", {})["timeout"] = cold_start_timeout

        kwargs.update(overrides)
        return kwargs
