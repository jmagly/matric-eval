"""
vLLM provider for matric-eval.

Connects to a vLLM server which provides an OpenAI-compatible API
with high-throughput inference via PagedAttention and continuous batching.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from matric_eval.providers.base import (
    ModelInfo,
    ProviderConfig,
    ProviderConnectionError,
    ProviderModelNotFoundError,
)


class VLLMProvider:
    """
    vLLM inference provider.

    Connects to a vLLM server via its OpenAI-compatible API.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig(
            base_url="http://localhost:8000",
        )

    @property
    def name(self) -> str:
        return "vllm"

    @property
    def display_name(self) -> str:
        return "vLLM"

    def is_available(self) -> bool:
        try:
            url = f"{self._config.base_url}/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            # Some vLLM versions don't have /health, try /v1/models
            try:
                url = f"{self._config.base_url}/v1/models"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status == 200
            except Exception:
                return False

    def list_models(self, max_size_gb: float = 0.0) -> list[ModelInfo]:
        try:
            url = f"{self._config.base_url}/v1/models"
            req = urllib.request.Request(url, method="GET")
            if self._config.api_key:
                req.add_header("Authorization", f"Bearer {self._config.api_key}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise ProviderConnectionError(
                f"Cannot reach vLLM server at {self._config.base_url}: {e}"
            )

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
            f"Model '{model}' not served by vLLM. "
            f"Available: {[m.name for m in models]}"
        )

    def format_model_id(self, model: str) -> str:
        if model.startswith("openai/"):
            return model
        return f"openai/{model}"

    def get_eval_kwargs(self, model: str, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model_base_url": f"{self._config.base_url}/v1",
        }
        if self._config.api_key:
            kwargs["model_args"] = {"api_key": self._config.api_key}
        else:
            kwargs["model_args"] = {"api_key": "not-needed"}

        # vLLM-specific sampling parameters
        extra = self._config.extra
        if extra:
            generate_params = {}
            for key in ("temperature", "top_p", "top_k", "max_tokens",
                        "repetition_penalty", "best_of", "use_beam_search"):
                if key in extra:
                    generate_params[key] = extra[key]
            if generate_params:
                kwargs.setdefault("extra_body", {}).update(generate_params)

        kwargs.update(overrides)
        return kwargs
