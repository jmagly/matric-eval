"""Transport qualification contracts; semantic simulator calibration is separate.

The public broker is an explicit identity, never inferred from a backend URL.
Unknown admission states fail closed: an unacknowledged request is never replayed.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

SCHEMA = "matric-eval.client-conformance/1"


class ConformanceError(RuntimeError):
    """Stable, content-free failure classification."""


def bounded_external_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Shared by the scored runner and qualification; forbid hidden replay."""
    result = {"timeout": 120.0, "num_retries": 0, "max_tokens": 4096, **arguments}
    if result["num_retries"] != 0 or isinstance(result["num_retries"], bool):
        raise ConformanceError("unsupported_library_retries")
    for key, limit in (("timeout", 300), ("max_tokens", 32768)):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= limit:
            raise ConformanceError(f"unbounded_{key}")
    if not isinstance(result["max_tokens"], int):
        raise ConformanceError("invalid_max_tokens")
    if any(key in result for key in ("fallbacks", "context_window_fallback_dict", "retry_policy")):
        raise ConformanceError("unsupported_library_replay")
    return result


@dataclass(frozen=True)
class ClientProfile:
    model: str
    model_digest: str
    target_model: str
    broker_identity: str
    broker_revision: str
    api_base: str
    route: str
    client_version: str
    max_tokens: int = 64
    timeout: float = 30.0
    thinking: bool = False
    tools: bool = False
    phase_timing: str = "unavailable"
    admission_protocol: str = "reject_wait_yield_resume"
    schema: str = SCHEMA

    def validate(self) -> None:
        if (
            self.phase_timing != "unavailable"
            or self.admission_protocol != "reject_wait_yield_resume"
        ):
            raise ConformanceError("unsupported_broker_phase_or_resume_guarantee")
        url = urlsplit(self.api_base)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ConformanceError("invalid_public_broker_url")
        if self.schema != SCHEMA or not all(
            (self.model_digest, self.broker_identity, self.broker_revision, self.client_version)
        ):
            raise ConformanceError("missing_identity")
        if self.model.removeprefix("ollama_chat/").removeprefix("openai/") == self.target_model:
            raise ConformanceError("auxiliary_target_identity_overlap")
        if self.route not in ("native", "openai"):
            raise ConformanceError("unsupported_route")
        prefix = "ollama_chat/" if self.route == "native" else "openai/"
        if not self.model.startswith(prefix):
            raise ConformanceError("route_model_mismatch")
        # The incident established that think:false is not an OpenAI guarantee.
        if self.route == "openai" and not self.thinking:
            raise ConformanceError("unsupported_openai_thinking_off")
        bounded_external_arguments({"timeout": self.timeout, "max_tokens": self.max_tokens})

    def fingerprint(self) -> str:
        self.validate()
        identity = asdict(self)
        versions = {}
        for package in ("litellm", "httpx", "openai"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = "absent"
        identity["installed_dependencies"] = versions
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def arguments(self, request_id: str) -> dict[str, Any]:
        self.validate()
        if (
            not request_id
            or len(request_id) > 80
            or any(not (c.isalnum() or c in "-_") for c in request_id)
        ):
            raise ConformanceError("invalid_request_id")
        result = bounded_external_arguments(
            {
                "api_base": self.api_base,
                "timeout": self.timeout,
                "max_tokens": self.max_tokens,
                "temperature": 0.0,
                "stream": False,
                "headers": {"Content-Type": "application/json", "X-Request-ID": request_id},
            }
        )
        if self.route == "native":
            result["think"] = self.thinking
        return result


def qualify_completion(
    profile: ClientProfile,
    request_id: str,
    messages: list[dict[str, Any]],
    *,
    completion: Callable[..., Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call the actual client once. No exception text, prompts or output in receipts.

    A successful response proves client output only. Broker-owner correlated
    admission/execution evidence is still required before live qualification.
    """
    arguments = profile.arguments(request_id)
    if importlib.metadata.version("litellm") != profile.client_version:
        raise ConformanceError("client_version_changed")
    if bool(tools) != profile.tools:
        raise ConformanceError("tool_capability_mismatch")
    if completion is None:
        completion = importlib.import_module("litellm").completion
    try:
        response = completion(model=profile.model, messages=messages, tools=tools, **arguments)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        timed_out = "timeout" in type(exc).__name__.lower()
        # LiteLLM 1.81.11 wraps native Ollama 429 as APIConnectionError(500).
        # Preserve the original structured status; never parse exception text.
        nested = exc.__cause__ or exc.__context__
        seen = {id(exc)}
        while nested is not None and id(nested) not in seen:
            seen.add(id(nested))
            timed_out = timed_out or "timeout" in type(nested).__name__.lower()
            nested_status = getattr(nested, "status_code", None)
            if nested_status in (202, 409, 429, 503):
                status = nested_status
                break
            nested = nested.__cause__ or nested.__context__
        if status in (202, 409, 429, 503):
            reason = "admission_unconfirmed_no_replay"
        elif timed_out:
            reason = "response_timeout_phase_unknown_no_replay"
        else:
            reason = "transport_failure_no_replay"
        raise ConformanceError(reason) from None
    try:
        message = response.choices[0].message.model_dump()
    except (AttributeError, IndexError, TypeError):
        raise ConformanceError("model_invalid_output") from None
    reasoning = any(message.get(key) for key in ("reasoning", "reasoning_content", "thinking"))
    provider_fields = message.get("provider_specific_fields") or {}
    reasoning = reasoning or any(
        provider_fields.get(key) for key in ("reasoning", "reasoning_content", "thinking")
    )
    content = message.get("content")
    if not profile.thinking and (reasoning or (isinstance(content, str) and "<think>" in content)):
        raise ConformanceError("thinking_off_violated")
    tool_calls = message.get("tool_calls")
    if profile.tools and not tool_calls:
        raise ConformanceError("tool_call_missing")
    if not profile.tools and tool_calls:
        raise ConformanceError("unexpected_tool_call")
    if not tool_calls and (not isinstance(content, str) or not content.strip()):
        raise ConformanceError("empty_output")
    return {
        "schema": SCHEMA,
        "profile_sha256": profile.fingerprint(),
        "request_id": request_id,
        "client_response": "passed",
        "live_qualification": "pending_broker_evidence",
        "retry_policy": "one_client_call_no_replay",
        "reasoning_present": bool(reasoning),
        "tool_calls_present": bool(tool_calls),
    }


def validate_wire(
    profile: ClientProfile, path: str, headers: dict[str, str], body: dict[str, Any]
) -> None:
    """Check captured own-request serialization without retaining message contents."""
    expected = "/api/chat" if profile.route == "native" else "/v1/chat/completions"
    if path != expected:
        raise ConformanceError("wrong_endpoint_path")
    normalized = {key.lower(): value for key, value in headers.items()}
    if normalized.get("content-type", "").split(";", 1)[0] != "application/json":
        raise ConformanceError("missing_json_content_type")
    if body.get("model") != profile.model.split("/", 1)[1]:
        raise ConformanceError("wrong_wire_model")
    if profile.route == "native":
        if body.get("think") is not profile.thinking:
            raise ConformanceError("thinking_option_missing")
        cap = body.get("options", {}).get("num_predict")
    else:
        cap = body.get("max_tokens", body.get("max_completion_tokens"))
    stream = body.get("stream", False) if profile.route == "openai" else body.get("stream")
    if cap != profile.max_tokens or stream is not False:
        raise ConformanceError("unbounded_wire_options")


def validate_embedding(
    vector: list[float], *, dimensions: int, expected_digest: str, observed_digest: str
) -> dict[str, Any]:
    """Require measured dimensionality and server-attested model identity."""
    import math

    if not expected_digest or expected_digest != observed_digest:
        raise ConformanceError("embedding_model_digest_mismatch")
    if (
        dimensions <= 0
        or len(vector) != dimensions
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in vector
        )
    ):
        raise ConformanceError("embedding_dimensions_or_values_invalid")
    return {"dimensions": dimensions, "model_digest": observed_digest}


def qualify_embedding(
    *,
    model: str,
    api_base: str,
    expected_digest: str,
    observed_digest: str,
    dimensions: int,
    request_id: str,
    client_version: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Exercise LiteLLM embedding serialization; digest comes from scoped broker evidence."""
    if not model.startswith("ollama/"):
        raise ConformanceError("unsupported_embedding_route")
    if importlib.metadata.version("litellm") != client_version:
        raise ConformanceError("client_version_changed")
    # Validate all identity and bound inputs before touching the endpoint.
    profile = ClientProfile(
        model.replace("ollama/", "ollama_chat/", 1),
        expected_digest,
        "",
        "embedding-broker",
        "scoped-evidence-required",
        api_base,
        "native",
        client_version,
        timeout=timeout,
    )
    arguments = profile.arguments(request_id)
    if expected_digest != observed_digest:
        raise ConformanceError("embedding_model_digest_mismatch")
    if dimensions <= 0:
        raise ConformanceError("embedding_dimensions_or_values_invalid")
    embedding = importlib.import_module("litellm").embedding
    try:
        response = embedding(
            model=model,
            input=["transport fixture"],
            api_base=api_base,
            timeout=timeout,
            num_retries=0,
            headers=arguments["headers"],
        )
        vector = response.data[0]["embedding"]
    except Exception:
        raise ConformanceError("embedding_transport_or_output_failure_no_replay") from None
    measured = validate_embedding(
        vector,
        dimensions=dimensions,
        expected_digest=expected_digest,
        observed_digest=observed_digest,
    )
    return {
        "schema": SCHEMA,
        "request_id": request_id,
        "client_version": client_version,
        "model": model,
        "measured": measured,
        "live_qualification": "pending_broker_evidence",
    }
