"""
Ollama provider for matric-eval.

Connects to a local Ollama instance for model discovery, capability
detection, and evaluation.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from matric_eval.providers.base import (
    ModelInfo,
    Provider,
    ProviderConfig,
    ProviderConnectionError,
    ProviderModelNotFoundError,
)

# Models that are embedding-only and shouldn't be evaluated
_EMBEDDING_PATTERNS = ["embed", "snowflake", "nomic", "minilm", "mxbai"]


class OllamaProvider:
    """
    Ollama inference provider.

    Connects to a local Ollama instance via CLI commands and the
    Ollama HTTP API.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig(
            base_url="http://localhost:11434",
        )

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama"

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def list_models(self, max_size_gb: float = 0.0) -> list[ModelInfo]:
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        except subprocess.CalledProcessError as e:
            raise ProviderConnectionError(f"Failed to query Ollama: {e}")
        except FileNotFoundError:
            raise ProviderConnectionError("Ollama not found. Is it installed?")

        models = []
        lines = result.stdout.strip().split("\n")[1:]  # Skip header

        for line in lines:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 3:
                continue

            name = parts[0]

            # Skip embedding models
            name_lower = name.lower()
            if any(pat in name_lower for pat in _EMBEDDING_PATTERNS):
                continue

            # Parse size
            try:
                size_val = float(parts[2])
                size_unit = parts[3] if len(parts) > 3 else "GB"

                if size_unit == "MB":
                    size_gb = size_val / 1024
                elif size_unit == "GB":
                    size_gb = size_val
                else:
                    size_gb = size_val

                if max_size_gb > 0 and size_gb > max_size_gb:
                    continue

                models.append(ModelInfo(
                    name=name,
                    size_gb=round(size_gb, 2),
                    metadata={"size_str": f"{size_val} {size_unit}"},
                ))
            except (ValueError, IndexError):
                continue

        return models

    def get_model_info(self, model: str) -> ModelInfo:
        try:
            result = subprocess.run(
                ["ollama", "show", model, "--json"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except FileNotFoundError:
            raise ProviderConnectionError("Ollama not found. Is it installed?")

        if result.returncode != 0:
            raise ProviderModelNotFoundError(
                f"Model '{model}' not found in Ollama: {result.stderr}"
            )

        try:
            info = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise ProviderModelNotFoundError(
                f"Invalid JSON from Ollama for model '{model}': {e}"
            )

        capabilities = info.get("capabilities", [])
        return ModelInfo(
            name=model,
            capabilities=capabilities,
            metadata=info,
        )

    def format_model_id(self, model: str) -> str:
        if model.startswith("ollama/"):
            return model
        return f"ollama/{model}"

    def get_eval_kwargs(self, model: str, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        # Ollama uses its native Inspect AI integration, no extra kwargs needed
        # unless a custom base URL is specified
        if self._config.base_url != "http://localhost:11434":
            kwargs["model_base_url"] = self._config.base_url
        kwargs.update(overrides)
        return kwargs
