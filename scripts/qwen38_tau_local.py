"""Pinned local simulator amendment for the September paired diagnostic replay."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

API_BASE = "http://127.0.0.1:11434"
MODEL = "ollama_chat/matric-eval-tau-simulator:2026-09-07"
MODEL_DIGEST = "3dd01e51cac784fe1603daab6461ec3fa1ac8850d71375bb1be0bd3cf5b1798e"
EMBEDDER = "nomic-embed-text:latest"
EMBEDDER_DIGEST = "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"


def configure_local() -> dict[str, Any]:
    """Verify installed identities and adapt banking embeddings through the broker."""
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=30) as response:
        models = {m["name"]: m["digest"] for m in json.load(response)["models"]}
    for name, digest in (
        (MODEL.removeprefix("ollama_chat/"), MODEL_DIGEST),
        (EMBEDDER, EMBEDDER_DIGEST),
    ):
        if models.get(name) != digest:
            raise RuntimeError(f"Local model identity mismatch: {name}")

    from openai import OpenAI
    from tau2.knowledge.embedders.openai_embedder import OpenAIEmbedder

    def local_init(self: Any, model: str = "", api_key: str | None = None) -> None:
        self.model = EMBEDDER
        self.client = OpenAI(api_key="LOCAL_NO_CREDENTIAL", base_url=API_BASE + "/v1")

    OpenAIEmbedder.__init__ = local_init
    return {
        "status": "operator-authorized-paired-diagnostic-replay",
        "simulator_model": MODEL,
        "simulator_digest": MODEL_DIGEST,
        "embedder_model": EMBEDDER,
        "embedder_digest": EMBEDDER_DIGEST,
        "api_base": API_BASE,
        "target_output_cap": 4096,
        "scope": "TAU pilot replay; not a calibration-v2 stage release",
        "comparability": "Not comparable to default hosted-simulator leaderboard results",
    }


def external_arguments() -> dict[str, Any]:
    return {
        "api_base": API_BASE,
        "extra_headers": {"Content-Type": "application/json"},
        "temperature": 0.0,
        "max_tokens": 1024,
        "num_retries": 0,
        "timeout": 180,
        "reasoning_effort": "none",
        "num_ctx": 32768,
    }
