"""Process-safe vLLM architecture registrations for study runtimes."""

from __future__ import annotations

import json
import os
from typing import Any

REGISTRATIONS_ENV = "MATRIC_EVAL_VLLM_ARCHITECTURE_REGISTRATIONS"
PLUGIN_NAME = "matric_eval_architecture_registry"


def _registrations_from_environment() -> dict[str, str]:
    """Load the protocol-selected registrations inherited by every vLLM process."""
    raw = os.environ.get(REGISTRATIONS_ENV)
    if raw is None:
        return {}
    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{REGISTRATIONS_ENV} must contain valid JSON") from exc
    if not isinstance(value, dict) or any(
        not isinstance(architecture, str) or not isinstance(implementation, str)
        for architecture, implementation in value.items()
    ):
        raise ValueError(f"{REGISTRATIONS_ENV} must map architecture strings to class strings")
    return value


def register_models() -> None:
    """Register protocol-declared adapters in API, EngineCore, and worker processes."""
    registrations = _registrations_from_environment()
    if not registrations:
        return
    try:
        from vllm import ModelRegistry  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - pinned A100 image only
        raise RuntimeError("the matric-eval vLLM plugin requires vLLM") from exc
    for architecture, implementation in registrations.items():
        ModelRegistry.register_model(architecture, implementation)
