"""Own-request evidence and bounded, body-free Ollama Unify admission resume."""

from __future__ import annotations

import time
from typing import Any

PREFIX = "X-Ollama-Unify-"
PROTOCOL = "ollama-unify-body-free-resume/1"
REASONS = frozenset(
    {
        "queue_admission_timeout",
        "queue_full",
        "lease_transition",
        "lane_capacity_wait",
        "reclaimable_placement_wait",
        "host_memory_unavailable",
        "model_exceeds_gpu_capacity",
        "model_not_installed",
        "backend_start_failed",
        "logical_request_conflict",
        "logical_request_in_progress",
        "logical_request_not_found",
        "logical_request_cancelled",
        "logical_request_expired",
        "retained_request_unavailable",
        "request_body_exceeds_resume_limit",
        "request_retention_capacity",
        "resume_body_forbidden",
        "completed_response_unavailable",
        "invalid_admission_header",
    }
)


def admission_transport(profile: Any, logical_id: str, evidence: dict[str, Any]) -> Any:
    """Keep LiteLLM's initial serialization; only the transport may resume it."""
    import httpx

    from matric_eval.studies.client_conformance import ConformanceError

    class Transport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.inner = httpx.HTTPTransport(retries=0)
            self.started = False

        def close(self) -> None:
            self.inner.close()

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if self.started:
                raise ConformanceError("unexpected_library_replay_blocked")
            self.started = True
            deadline = time.monotonic() + profile.admission_total_seconds
            expected_id = None
            expected_ticket = None
            original = request
            for attempt in range(profile.admission_max_attempts):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ConformanceError("broker_resume_budget_exhausted")
                request.extensions["timeout"] = {
                    key: min(profile.timeout, remaining)
                    for key in ("connect", "read", "write", "pool")
                }
                evidence["http_attempts"] = attempt + 1
                # A failed socket read is ambiguous. Never replay a request body.
                response = self.inner.handle_request(request)
                chunks = []
                body_bytes = 0
                for chunk in response.iter_raw():
                    body_bytes += len(chunk)
                    if time.monotonic() >= deadline or body_bytes > 8 * 1024 * 1024:
                        response.close()
                        raise ConformanceError("broker_response_budget_exhausted")
                    chunks.append(chunk)
                # Rebuild a consumed transport response for LiteLLM normalization.
                received = response
                response = httpx.Response(
                    received.status_code,
                    headers=received.headers,
                    content=b"".join(chunks),
                    extensions=received.extensions,
                )
                received.close()
                headers = response.headers
                broker_id = headers.get(PREFIX + "Request-Id")
                ticket = headers.get(PREFIX + "Queue-Ticket")
                returned_logical = headers.get(PREFIX + "Logical-Request-Id")
                if (
                    returned_logical != logical_id
                    or not broker_id
                    or len(broker_id) > 128
                    or any(not (c.isascii() and (c.isalnum() or c in "._:-")) for c in broker_id)
                ):
                    response.close()
                    raise ConformanceError("broker_correlation_missing")
                if (expected_id is not None and broker_id != expected_id) or (
                    expected_ticket is not None and ticket is not None and ticket != expected_ticket
                ):
                    response.close()
                    raise ConformanceError("broker_correlation_changed")
                expected_id = broker_id
                if ticket is not None:
                    if not ticket.isascii() or not ticket.isdigit():
                        response.close()
                        raise ConformanceError("broker_ticket_invalid")
                    expected_ticket = ticket
                evidence.update(
                    {
                        "logical_request_id": logical_id,
                        "broker_request_id": broker_id,
                        "queue_ticket": expected_ticket,
                        "execution_digest_binding": "unverified",
                    }
                )
                if response.is_success:
                    lane = headers.get(PREFIX + "Lane")
                    queue_ms = headers.get(PREFIX + "Queue-Ms", "")
                    if (
                        not lane
                        or len(lane) > 128
                        or any(not (c.isascii() and (c.isalnum() or c in "._:-")) for c in lane)
                        or not queue_ms.isascii()
                        or not queue_ms.isdigit()
                        or ticket is None
                    ):
                        response.close()
                        raise ConformanceError("broker_admission_evidence_missing")
                    evidence.update(
                        {
                            "lane": lane,
                            "queue_ms_including_warmup": int(queue_ms),
                            "response_replayed": headers.get(PREFIX + "Response-Replayed")
                            == "true",
                        }
                    )
                    return response
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                reason = payload.get("reason_code") if isinstance(payload, dict) else None
                if reason not in REASONS:
                    response.close()
                    raise ConformanceError("broker_failure_unrecognized")
                evidence["reason_code"] = reason
                cause = payload.get("cause_reason_code")
                if cause in REASONS:
                    evidence["cause_reason_code"] = cause
                if (
                    payload.get("request_id", broker_id) != broker_id
                    or payload.get("logical_request_id", logical_id) != logical_id
                    or (ticket is not None and str(payload.get("queue_ticket", ticket)) != ticket)
                ):
                    response.close()
                    raise ConformanceError("broker_correlation_changed")
                retained = payload.get("admission_retained") is True
                allowed = reason == "logical_request_in_progress" or (
                    reason == "queue_admission_timeout" and retained
                )
                retry_ms = payload.get("retry_after_ms")
                ttl_ms = payload.get("resume_ttl_ms") if retained else None
                response.close()
                if not allowed or payload.get("retryable") is not True:
                    raise ConformanceError("broker_resume_rejected_" + reason)
                if (
                    isinstance(retry_ms, bool)
                    or not isinstance(retry_ms, (int, float))
                    or not (0 <= retry_ms <= 300000)
                ):
                    raise ConformanceError("broker_retry_delay_invalid")
                if retained and (
                    isinstance(ttl_ms, bool)
                    or not isinstance(ttl_ms, (int, float))
                    or not 0 < ttl_ms <= 300000
                    or retry_ms >= ttl_ms
                ):
                    raise ConformanceError("broker_resume_retention_expired")
                if attempt + 1 >= profile.admission_max_attempts or retry_ms / 1000 >= (
                    deadline - time.monotonic()
                ):
                    raise ConformanceError("broker_resume_budget_exhausted")
                time.sleep(retry_ms / 1000)
                resume_headers = dict(original.headers)
                for key in ("content-length", "transfer-encoding"):
                    resume_headers.pop(key, None)
                resume_headers[PREFIX + "Resume-Request"] = "true"
                request = httpx.Request(
                    original.method, original.url, headers=resume_headers, content=b""
                )
            raise ConformanceError("broker_resume_budget_exhausted")

    return Transport()


def verify_public_lane(profile: Any, evidence: dict[str, Any]) -> dict[str, Any]:
    """Observe only the admitted lane's current public GPU mapping; no lease claim."""
    import httpx

    from matric_eval.studies.client_conformance import ConformanceError, normalize_model

    try:
        with httpx.Client(timeout=min(profile.timeout, 10), follow_redirects=False) as client:
            response = client.get(
                profile.api_base.rstrip("/") + "/.well-known/ollama-unify-gpu-negotiator"
            )
            response.raise_for_status()
            document = response.json()
        lanes = [
            lane
            for lane in document["parallel_pool"]["lanes"]
            if lane.get("id") == evidence.get("lane")
        ]
        if len(lanes) != 1:
            raise ValueError("missing lane")
        lane = lanes[0]
        if (
            lane.get("kind") != "managed"
            or lane.get("state") != "ready"
            or lane.get("gpu_uuid") not in document["selected_gpu_ids"]
            or normalize_model(str(lane.get("model"))) != normalize_model(profile.model)
        ):
            raise ValueError("lane mismatch")
        return {
            "kind": "public_broker_lane_observation",
            "lane": lane["id"],
            "gpu_uuid": lane["gpu_uuid"],
            "logical_request_id": evidence["logical_request_id"],
            "broker_request_id": evidence["broker_request_id"],
            "execution_digest_binding": "unverified",
            "allocation_binding": "response_lane_and_current_public_mapping",
        }
    except Exception:
        raise ConformanceError("public_broker_lane_unverified") from None
