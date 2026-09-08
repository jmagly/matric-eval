"""Request-scoped transport for LiteLLM 1.81's global native embedding client."""

from __future__ import annotations

import importlib
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from matric_eval.studies.broker_admission import admission_transport

_LOCK = threading.RLock()


@contextmanager
def embedding_client(profile: Any, request_id: str, evidence: dict[str, Any]) -> Iterator[None]:
    import httpx

    module: Any = importlib.import_module("litellm")
    # This version ignores a per-call client and headers on /api/embed. Serialize
    # our overrides; other threads retain the original client through the proxy.
    with _LOCK:
        original = module.module_level_client
        owner = threading.get_ident()
        with httpx.Client(
            transport=admission_transport(profile, request_id, evidence),
            headers=profile.arguments(request_id)["headers"],
            timeout=profile.timeout,
            follow_redirects=False,
        ) as client:

            class ScopedClient:
                def __getattr__(self, name: str) -> Any:
                    selected = client if threading.get_ident() == owner else original
                    return getattr(selected, name)

            scoped = ScopedClient()
            module.module_level_client = scoped
            try:
                yield
            finally:
                if module.module_level_client is scoped:
                    module.module_level_client = original
