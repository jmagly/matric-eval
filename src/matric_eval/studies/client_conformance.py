"""Transport qualification contracts; semantic simulator calibration is separate.

The public broker is an explicit identity, never inferred from a backend URL.
Unknown admission states fail closed: an unacknowledged request is never replayed.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import platform
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

SCHEMA = "matric-eval.client-conformance/1"


class ConformanceError(RuntimeError):
    """Stable, content-free failure classification."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.broker_evidence: dict[str, Any] = {}


def normalize_model(model: str) -> str:
    for prefix in ("ollama_chat/", "ollama/", "openai/", "hosted_vllm/"):
        if model.startswith(prefix):
            model = model[len(prefix) :]
            break
    return model.removesuffix(":latest")


def verify_public_model_metadata(profile: ClientProfile, request_id: str) -> dict[str, Any]:
    """Read public metadata; this is tag evidence, never an execution attestation."""
    import httpx

    profile.arguments(request_id)
    path = "/api/tags" if profile.route == "native" else "/models"
    try:
        with httpx.Client(timeout=min(profile.timeout, 10), follow_redirects=False) as client:
            response = client.get(
                profile.api_base.rstrip("/") + path,
                headers={"X-Request-ID": request_id, "Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        models = payload.get("models" if profile.route == "native" else "data", [])
        matching = [
            item
            for item in models
            if normalize_model(str(item.get("name", item.get("id", ""))))
            == normalize_model(profile.model)
        ]
        if len(matching) != 1 or matching[0].get("digest") != profile.model_digest:
            raise ConformanceError("public_metadata_model_digest_mismatch")
    except ConformanceError:
        raise
    except Exception:
        raise ConformanceError("public_metadata_unavailable") from None
    return {
        "kind": "public_metadata_tag",
        "model_digest": profile.model_digest,
        "execution_digest_binding": "unverified",
        "request_id": request_id,
    }


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
    admission_wait_ms: int = 1000
    admission_total_seconds: float = 30.0
    admission_max_attempts: int = 3
    seed: int | None = None
    schema: str = SCHEMA

    def validate(self) -> None:
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ConformanceError("invalid_seed")
        if self.phase_timing != "unavailable" or self.admission_protocol not in (
            "reject_wait_yield_resume",
            "ollama-unify-body-free-resume/1",
        ):
            raise ConformanceError("unsupported_broker_phase_or_resume_guarantee")
        for value, lower, upper in (
            (self.admission_wait_ms, 100, 300000),
            (self.admission_total_seconds, 0.1, 300),
            (self.admission_max_attempts, 1, 10),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not lower <= value <= upper
            ):
                raise ConformanceError("invalid_admission_budget")
        if not isinstance(self.admission_wait_ms, int) or not isinstance(
            self.admission_max_attempts, int
        ):
            raise ConformanceError("invalid_admission_budget")
        if self.admission_protocol != "reject_wait_yield_resume" and self.route != "native":
            raise ConformanceError("unsupported_openai_broker_resume")
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
        if normalize_model(self.model) == normalize_model(self.target_model):
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
        identity["python_version"] = platform.python_version()
        versions = {}
        for package in (
            "litellm",
            "httpx",
            "openai",
            "pydantic",
            "pydantic-settings",
            "jsonschema",
        ):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = "absent"
        identity["installed_dependencies"] = versions
        identity["adapter_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        identity["broker_adapter_sha256"] = hashlib.sha256(
            Path(__file__).with_name("broker_admission.py").read_bytes()
        ).hexdigest()
        identity["runtime_adapter_sha256"] = hashlib.sha256(
            Path(__file__).with_name("auxiliary_runtime.py").read_bytes()
        ).hexdigest()
        identity["embedding_adapter_sha256"] = hashlib.sha256(
            Path(__file__).with_name("embedding_transport.py").read_bytes()
        ).hexdigest()
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def arguments(self, request_id: str) -> dict[str, Any]:
        self.validate()
        if (
            not request_id
            or len(request_id) > 80
            or any(not (c.isascii() and (c.isalnum() or c in "-_")) for c in request_id)
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
        result["headers"]["X-Ollama-Unify-Logical-Request-Id"] = request_id
        if self.admission_protocol == "ollama-unify-body-free-resume/1":
            result["headers"].update(
                {
                    "X-Ollama-Unify-Queue-Policy": "wait",
                    "X-Ollama-Unify-Admission-Wait-Ms": str(self.admission_wait_ms),
                    "X-Ollama-Unify-Workload-Class": "background",
                }
            )
        if self.route == "native":
            result["think"] = self.thinking
        if self.seed is not None:
            result["seed"] = self.seed
        return result


def qualify_completion(
    profile: ClientProfile,
    request_id: str,
    messages: list[dict[str, Any]],
    *,
    completion: Callable[..., Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return invoke_completion(profile, request_id, messages, completion=completion, tools=tools)[1]


def invoke_completion(
    profile: ClientProfile,
    request_id: str,
    messages: list[dict[str, Any]],
    *,
    completion: Callable[..., Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[Any, dict[str, Any]]:
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
    wire_models: list[str] = []
    wire_failures: list[str] = []
    http_client = None
    broker_evidence: dict[str, Any] = {}
    if profile.route == "native":
        import httpx

        def inspect_response(raw: httpx.Response) -> None:
            # Per-call client sees only this request; retain no raw text/headers.
            if raw.is_success:
                raw.read()
                try:
                    wire_models.append(str(raw.json().get("model", "")))
                    validate_wire(
                        profile,
                        raw.request.url.path,
                        dict(raw.request.headers),
                        json.loads(raw.request.content),
                    )
                except Exception:
                    wire_failures.append("wire_response_or_request_invalid")

        from matric_eval.studies.broker_admission import admission_transport

        transport = (
            admission_transport(profile, request_id, broker_evidence)
            if profile.admission_protocol == "ollama-unify-body-free-resume/1"
            else None
        )
        http_client = httpx.Client(
            transport=transport,
            timeout=profile.timeout,
            follow_redirects=False,
            event_hooks={"response": [inspect_response]},
        )
        handler = importlib.import_module("litellm.llms.custom_httpx.http_handler").HTTPHandler
        arguments["client"] = handler(client=http_client)
    try:
        response = completion(model=profile.model, messages=messages, tools=tools, **arguments)
    except Exception as exc:
        if isinstance(exc, ConformanceError):
            exc.broker_evidence = dict(broker_evidence)
            raise
        status = getattr(exc, "status_code", None)
        timed_out = "timeout" in type(exc).__name__.lower()
        # LiteLLM 1.81.11 wraps native Ollama 429 as APIConnectionError(500).
        # Preserve the original structured status; never parse exception text.
        nested = exc.__cause__ or exc.__context__
        seen = {id(exc)}
        while nested is not None and id(nested) not in seen:
            seen.add(id(nested))
            if isinstance(nested, ConformanceError):
                nested.broker_evidence = dict(broker_evidence)
                raise nested from None
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
        failure = ConformanceError(reason)
        failure.broker_evidence = dict(broker_evidence)
        raise failure from None
    finally:
        if http_client is not None:
            http_client.close()
    try:
        if profile.route == "native":
            if wire_failures or len(wire_models) != 1:
                raise ConformanceError("wire_identity_unavailable_or_duplicate")
            if normalize_model(wire_models[0]) != normalize_model(profile.model):
                raise ConformanceError("response_model_mismatch")
        try:
            message = response.choices[0].message.model_dump()
        except (AttributeError, IndexError, TypeError):
            raise ConformanceError("model_invalid_output") from None
        if normalize_model(str(getattr(response, "model", ""))) != normalize_model(profile.model):
            raise ConformanceError("response_model_mismatch")
        reasoning = any(message.get(key) for key in ("reasoning", "reasoning_content", "thinking"))
        provider_fields = message.get("provider_specific_fields") or {}
        reasoning = reasoning or any(
            provider_fields.get(key) for key in ("reasoning", "reasoning_content", "thinking")
        )
        content = message.get("content")
        if not profile.thinking and (
            reasoning or (isinstance(content, str) and "<think>" in content)
        ):
            raise ConformanceError("thinking_off_violated")
        tool_calls = message.get("tool_calls")
        if profile.tools and not tool_calls:
            raise ConformanceError("tool_call_missing")
        if not profile.tools and tool_calls:
            raise ConformanceError("unexpected_tool_call")
        if tool_calls:
            requested = {
                tool["function"]["name"]: tool["function"].get("parameters", {})
                for tool in tools or []
            }
            try:
                validate = importlib.import_module("jsonschema").validate

                for call in tool_calls:
                    function = call["function"]
                    if function["name"] not in requested:
                        raise ValueError("unrequested function")
                    arguments_value = function["arguments"]
                    decoded = (
                        json.loads(arguments_value)
                        if isinstance(arguments_value, str)
                        else arguments_value
                    )
                    if not isinstance(decoded, dict):
                        raise ValueError("non-object arguments")
                    validate(decoded, requested[function["name"]])
            except Exception:
                raise ConformanceError("tool_name_or_arguments_invalid") from None
        if not tool_calls and (not isinstance(content, str) or not content.strip()):
            raise ConformanceError("empty_output")
        return response, {
            "schema": SCHEMA,
            "profile_sha256": profile.fingerprint(),
            "request_id": request_id,
            "client_response": "passed",
            "live_qualification": "pending_broker_evidence",
            "retry_policy": "one_client_call_no_body_replay",
            "broker_admission": broker_evidence,
            "reasoning_present": bool(reasoning),
            "tool_calls_present": bool(tool_calls),
            "response_model_check": "client_reported_identity_only",
            "execution_digest_binding": "unverified",
        }
    except ConformanceError as exc:
        exc.broker_evidence = dict(broker_evidence)
        raise
    except Exception:
        failure = ConformanceError("model_invalid_output")
        failure.broker_evidence = dict(broker_evidence)
        raise failure from None


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
    broker_identity: str,
    broker_revision: str,
    admission_protocol: str = "reject_wait_yield_resume",
    profile: ClientProfile | None = None,
) -> dict[str, Any]:
    """Exercise LiteLLM embedding serialization; digest comes from scoped broker evidence."""
    if not model.startswith("ollama/"):
        raise ConformanceError("unsupported_embedding_route")
    if importlib.metadata.version("litellm") != client_version:
        raise ConformanceError("client_version_changed")
    # Validate all identity and bound inputs before touching the endpoint.
    profile = profile or ClientProfile(
        model.replace("ollama/", "ollama_chat/", 1),
        expected_digest,
        "",
        broker_identity,
        broker_revision,
        api_base,
        "native",
        client_version,
        timeout=timeout,
        admission_protocol=admission_protocol,
    )
    if (
        normalize_model(profile.model) != normalize_model(model)
        or profile.model_digest != expected_digest
        or profile.api_base != api_base
        or profile.client_version != client_version
        or profile.broker_identity != broker_identity
        or profile.broker_revision != broker_revision
        or profile.timeout != timeout
        or profile.admission_protocol != admission_protocol
    ):
        raise ConformanceError("embedding_profile_arguments_mismatch")
    arguments = profile.arguments(request_id)
    if expected_digest != observed_digest:
        raise ConformanceError("embedding_model_digest_mismatch")
    if dimensions <= 0:
        raise ConformanceError("embedding_dimensions_or_values_invalid")
    embedding = importlib.import_module("litellm").embedding
    from matric_eval.studies.embedding_transport import embedding_client

    evidence: dict[str, Any] = {}
    try:
        with (
            embedding_client(profile, request_id, evidence)
            if admission_protocol == "ollama-unify-body-free-resume/1"
            else nullcontext()
        ):
            response = embedding(
                model=model,
                input=["transport fixture"],
                api_base=api_base,
                timeout=timeout,
                num_retries=0,
                headers=arguments["headers"],
            )
            vector = response.data[0]["embedding"]
    except Exception as exc:
        failure = ConformanceError("embedding_transport_or_output_failure_no_replay")
        failure.broker_evidence = dict(evidence)
        nested: BaseException | None = exc
        seen: set[int] = set()
        while nested is not None and id(nested) not in seen:
            seen.add(id(nested))
            if isinstance(nested, ConformanceError):
                nested.broker_evidence = dict(evidence)
                raise nested from None
            nested = nested.__cause__ or nested.__context__
        raise failure from None
    try:
        measured = validate_embedding(
            vector,
            dimensions=dimensions,
            expected_digest=expected_digest,
            observed_digest=observed_digest,
        )
        if normalize_model(str(getattr(response, "model", ""))) != normalize_model(model):
            raise ConformanceError("response_model_mismatch")
    except ConformanceError as exc:
        exc.broker_evidence = dict(evidence)
        raise
    identity = {
        "client_profile_sha256": profile.fingerprint(),
        "dimensions": dimensions,
        "operation": "embedding",
        "model": model,
    }
    return {
        "schema": SCHEMA,
        "request_id": request_id,
        "client_version": client_version,
        "model": model,
        "profile_sha256": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
        "execution_digest_binding": "unverified",
        "digest_evidence_kind": "caller_supplied_metadata",
        "broker_admission": evidence,
        "measured": measured,
        "live_qualification": "pending_broker_evidence",
    }
