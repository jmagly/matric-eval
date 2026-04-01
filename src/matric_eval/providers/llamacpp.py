"""
llama.cpp provider for matric-eval.

Connects to a llama.cpp HTTP server for model evaluation. The server
exposes OpenAI-compatible endpoints at /v1/chat/completions and
/v1/completions, plus native endpoints at /completion and /health.
"""

from __future__ import annotations

import urllib.error
import urllib.request
import json
from typing import Any

from matric_eval.providers.base import (
    ModelInfo,
    ProviderConfig,
    ProviderConnectionError,
    ProviderModelNotFoundError,
)


class LlamaCppProvider:
    """
    llama.cpp inference provider.

    Connects to a running llama.cpp server (llama-server or llama-cpp-python)
    via the OpenAI-compatible API.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig(
            base_url="http://localhost:8080",
        )

    @property
    def name(self) -> str:
        return "llama-cpp"

    @property
    def display_name(self) -> str:
        return "llama.cpp"

    def is_available(self) -> bool:
        try:
            url = f"{self._config.base_url}/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return data.get("status") == "ok"
        except Exception:
            return False

    def list_models(self, max_size_gb: float = 0.0) -> list[ModelInfo]:
        # llama.cpp server loads one model at a time.
        # Query the /v1/models endpoint to see what's loaded.
        try:
            url = f"{self._config.base_url}/v1/models"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise ProviderConnectionError(
                f"Cannot reach llama.cpp server at {self._config.base_url}: {e}"
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
            f"Model '{model}' not loaded on llama.cpp server. "
            f"Available: {[m.name for m in models]}"
        )

    def format_model_id(self, model: str) -> str:
        # llama.cpp exposes an OpenAI-compatible API, so we use the
        # openai/ prefix for Inspect AI
        if model.startswith("openai/"):
            return model
        return f"openai/{model}"

    def get_eval_kwargs(self, model: str, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model_base_url": f"{self._config.base_url}/v1",
        }
        # llama.cpp doesn't need an API key but Inspect AI's OpenAI
        # provider requires one — use a dummy value
        kwargs["model_args"] = {"api_key": "not-needed"}

        # Apply llama.cpp-specific generation parameters from config
        extra = self._config.extra
        if extra:
            generate_params = {}
            for key in ("temperature", "top_k", "top_p", "repeat_penalty",
                        "n_predict", "seed"):
                if key in extra:
                    generate_params[key] = extra[key]
            if generate_params:
                kwargs.setdefault("extra_body", {}).update(generate_params)

        kwargs.update(overrides)
        return kwargs
