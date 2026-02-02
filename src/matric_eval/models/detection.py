"""
Model capability detection.

Provides functions to detect model capabilities like thinking support
using the Ollama API.
"""

import json
import subprocess
from typing import Any


def get_ollama_model_info(model: str) -> dict[str, Any]:
    """
    Get model information from Ollama.

    Uses 'ollama show' command to retrieve model metadata including
    capabilities, parameters, and modelfile.

    Args:
        model: Model identifier (e.g., "qwen3:14b", "llama3.2:3b")

    Returns:
        Dictionary containing model information

    Raises:
        ValueError: If model not found or Ollama returns invalid data
    """
    try:
        result = subprocess.run(
            ["ollama", "show", model, "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise ValueError("Ollama not found. Is it installed?")

    if result.returncode != 0:
        raise ValueError(f"Model '{model}' not found or Ollama error: {result.stderr}")

    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response from Ollama: {e}")

    return info


def has_thinking_capability(model: str) -> bool:
    """
    Check if a model supports extended thinking mode.

    Queries Ollama for model capabilities and checks if 'thinking'
    is listed as a supported capability.

    Args:
        model: Model identifier (e.g., "qwen3:14b", "llama3.2:3b")

    Returns:
        True if model supports thinking, False otherwise

    Example:
        >>> has_thinking_capability("qwen3:14b")
        True
        >>> has_thinking_capability("llama3.2:3b")
        False
    """
    try:
        info = get_ollama_model_info(model)
    except ValueError:
        # Model not found or Ollama error - assume no thinking
        return False

    capabilities = info.get("capabilities", [])
    return "thinking" in capabilities
