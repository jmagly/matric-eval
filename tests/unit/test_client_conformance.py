"""Actual LiteLLM HTTP serialization, including the missing-header incident."""

from __future__ import annotations

import importlib.metadata
import json
import socket
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from matric_eval.studies.client_conformance import (
    ClientProfile,
    ConformanceError,
    bounded_external_arguments,
    qualify_completion,
    validate_wire,
)


def profile(base="http://127.0.0.1:1"):
    return ClientProfile(
        "ollama_chat/fixture",
        "sha256:model",
        "target",
        "fixture-broker",
        "fixture-v1",
        base,
        "native",
        "1.81.11",
    )


def test_contract_invalidates_and_rejects_unsupported_guarantees():
    p = profile()
    for changes in (
        {"client_version": "other"},
        {"broker_revision": "other"},
        {"model_digest": "other"},
        {"max_tokens": 32},
    ):
        assert replace(p, **changes).fingerprint() != p.fingerprint()
    with pytest.raises(ConformanceError, match="unsupported_openai_thinking_off"):
        replace(p, route="openai", model="openai/fixture").validate()
    with pytest.raises(ConformanceError, match="auxiliary_target"):
        replace(p, target_model="fixture").validate()
    for target in ("ollama_chat/fixture", "openai/fixture", "fixture:latest"):
        with pytest.raises(ConformanceError, match="auxiliary_target"):
            replace(p, target_model=target).validate()
    for bad in ({"num_retries": 1}, {"timeout": 0}, {"max_tokens": -1}, {"fallbacks": []}):
        with pytest.raises(ConformanceError):
            bounded_external_arguments(bad)


@pytest.mark.parametrize(
    "scenario",
    [
        "ok",
        "missing_header",
        "lost_ack",
        "timeout",
        "admission",
        "reasoning",
        "empty",
        "tools",
        "wrong_model",
        "wrong_tool",
        "invalid_arguments",
    ],
)
def test_actual_litellm_serialization(scenario):
    pytest.importorskip("litellm")
    calls = []
    failures = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(self.headers.get("X-Request-ID"))
            try:
                validate_wire(p, self.path, dict(self.headers), body)
            except ConformanceError as exc:
                failures.append(str(exc))
            if scenario == "timeout":
                time.sleep(0.2)
                self.connection.close()
                return
            if scenario == "lost_ack":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            if scenario == "admission":
                self.send_response(429)
                payload = b'{"error":"admission denied"}'
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            message = {"role": "assistant", "content": "ok"}
            if scenario == "reasoning":
                message["thinking"] = "hidden"
            if scenario == "empty":
                message["content"] = ""
            if scenario in ("tools", "wrong_tool", "invalid_arguments"):
                message["tool_calls"] = [{"function": {"name": "ping", "arguments": {}}}]
                if scenario == "wrong_tool":
                    message["tool_calls"][0]["function"]["name"] = "delete"
                if scenario == "invalid_arguments":
                    message["tool_calls"][0]["function"]["arguments"] = {"unexpected": 1}
            payload = json.dumps(
                {
                    "model": "wrong" if scenario == "wrong_model" else "fixture",
                    "created_at": "2026-09-08T00:00:00Z",
                    "message": message,
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 1,
                    "eval_count": 1,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    p = replace(
        profile(f"http://127.0.0.1:{server.server_port}"),
        client_version=importlib.metadata.version("litellm"),
        tools=scenario in ("tools", "wrong_tool", "invalid_arguments"),
        timeout=0.05 if scenario == "timeout" else 30,
    )
    tools = (
        [
            {
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "fixture ping",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        ]
        if p.tools
        else None
    )
    try:
        if scenario == "missing_header":
            import litellm

            args = p.arguments("fixture-request")
            del args["headers"]["Content-Type"]
            litellm.completion(model=p.model, messages=[{"role": "user", "content": "ok"}], **args)
            assert failures == ["missing_json_content_type"]
        elif scenario in (
            "lost_ack",
            "timeout",
            "admission",
            "reasoning",
            "empty",
            "wrong_model",
            "wrong_tool",
            "invalid_arguments",
        ):
            expected = {
                "lost_ack": "transport_failure_no_replay",
                "timeout": "response_timeout_phase_unknown_no_replay",
                "admission": "admission_unconfirmed_no_replay",
                "reasoning": "thinking_off_violated",
                "empty": "empty_output",
                "wrong_model": "response_model_mismatch",
                "wrong_tool": "tool_name_or_arguments_invalid",
                "invalid_arguments": "tool_name_or_arguments_invalid",
            }[scenario]
            with pytest.raises(ConformanceError, match=expected):
                qualify_completion(
                    p, "fixture-request", [{"role": "user", "content": "ok"}], tools=tools
                )
        else:
            receipt = qualify_completion(
                p, "fixture-request", [{"role": "user", "content": "ok"}], tools=tools
            )
            assert receipt["client_response"] == "passed"
        assert calls == ["fixture-request"]
        if scenario != "missing_header":
            assert not failures
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_embedding_requires_actual_dimensions_and_identity():
    from matric_eval.studies.client_conformance import validate_embedding

    assert (
        validate_embedding([0.1, 0.2], dimensions=2, expected_digest="a", observed_digest="a")[
            "dimensions"
        ]
        == 2
    )
    for vector, digest in (([0.1], "a"), ([0.1, float("nan")], "a"), ([0.1, 0.2], "b")):
        with pytest.raises(ConformanceError):
            validate_embedding(vector, dimensions=2, expected_digest="a", observed_digest=digest)


def test_actual_litellm_embedding():
    pytest.importorskip("litellm")
    from matric_eval.studies.client_conformance import qualify_embedding

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body["model"]))
            payload = b'{"embeddings":[[0.1,0.2]],"prompt_eval_count":2}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    kwargs = dict(
        model="ollama/fixture-embed",
        broker_identity="fixture-broker",
        broker_revision="fixture-revision",
        api_base=f"http://127.0.0.1:{server.server_port}",
        expected_digest="fixture-digest",
        observed_digest="fixture-digest",
        dimensions=2,
        request_id="embedding-fixture",
        client_version=importlib.metadata.version("litellm"),
    )
    try:
        original = qualify_embedding(**kwargs)
        assert original["measured"]["dimensions"] == 2
        for change in ({"broker_revision": "changed"}, {"timeout": 12.0}):
            changed = qualify_embedding(**{**kwargs, **change})
            assert changed["profile_sha256"] != original["profile_sha256"]
        with pytest.raises(ConformanceError, match="dimensions_or_values"):
            qualify_embedding(**{**kwargs, "dimensions": 3})
        with pytest.raises(ConformanceError, match="digest_mismatch"):
            qualify_embedding(**{**kwargs, "observed_digest": "changed"})
        assert requests == [("/api/embed", "fixture-embed")] * 4
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_actual_openai_route_separate_capability(monkeypatch):
    pytest.importorskip("litellm")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-not-a-credential")
    failures = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                validate_wire(p, self.path, dict(self.headers), body)
            except ConformanceError as exc:
                failures.append(str(exc))
            payload = json.dumps(
                {
                    "id": "fixture",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "fixture",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "OK",
                                "reasoning_content": "hidden",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    p = replace(
        profile(f"http://127.0.0.1:{server.server_port}/v1"),
        route="openai",
        model="openai/fixture",
        thinking=True,
        client_version=importlib.metadata.version("litellm"),
    )
    try:
        receipt = qualify_completion(p, "openai-fixture", [{"role": "user", "content": "OK"}])
        assert receipt["reasoning_present"] is True
        assert not failures
        with pytest.raises(ConformanceError, match="unsupported_openai_thinking_off"):
            qualify_completion(
                replace(p, thinking=False), "openai-fixture", [{"role": "user", "content": "OK"}]
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_public_metadata_digest_is_not_execution_attestation():
    from matric_eval.studies.client_conformance import verify_public_model_metadata

    digest = "sha256:model"
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append((self.path, self.headers.get("X-Request-ID")))
            payload = json.dumps(
                {"models": [{"name": "fixture:latest", "digest": digest}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    p = profile(f"http://127.0.0.1:{server.server_port}")
    try:
        result = verify_public_model_metadata(p, "metadata-fixture")
        assert result["kind"] == "public_metadata_tag"
        assert result["execution_digest_binding"] == "unverified"
        digest = "sha256:changed"
        with pytest.raises(ConformanceError, match="public_metadata_model_digest_mismatch"):
            verify_public_model_metadata(p, "metadata-changed")
        assert calls == [("/api/tags", "metadata-fixture"), ("/api/tags", "metadata-changed")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    "scenario", ["replay", "expired", "changed_ticket", "budget", "hidden_replay"]
)
def test_actual_client_body_free_broker_resume(scenario):
    pytest.importorskip("litellm")
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append((self.path, body, dict(self.headers)))
            first = len(calls) == 1
            success = not first and scenario in ("replay", "hidden_replay")
            reason = "queue_admission_timeout" if first else "logical_request_expired"
            if scenario == "budget":
                reason = "logical_request_in_progress"
            payload = {
                "reason_code": reason,
                "retryable": first or scenario == "budget",
                "request_id": "broker-1",
                "logical_request_id": "resume-fixture",
                "queue_ticket": 7,
                "retry_after_ms": 0,
                "admission_retained": first,
                "resume_ttl_ms": 30000,
                "queue": {"unrelated": "must-not-retain"},
                "error": "private text",
            }
            if success:
                payload = {
                    "model": "fixture",
                    "message": {"role": "assistant", "content": "OK"},
                    "done": True,
                    "done_reason": "stop",
                    "eval_count": 1,
                    "prompt_eval_count": 1,
                    "created_at": "2026-09-08T00:00:00Z",
                }
            encoded = json.dumps(payload).encode()
            self.send_response(200 if success else 503 if first else 409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("X-Ollama-Unify-Logical-Request-Id", "resume-fixture")
            self.send_header("X-Ollama-Unify-Request-Id", "broker-1")
            self.send_header(
                "X-Ollama-Unify-Queue-Ticket",
                "8" if scenario == "changed_ticket" and not first else "7",
            )
            self.send_header("X-Ollama-Unify-Lane", "lane-1")
            self.send_header("X-Ollama-Unify-Queue-Ms", "12")
            if success:
                self.send_header("X-Ollama-Unify-Response-Replayed", "true")
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    p = replace(
        profile(f"http://127.0.0.1:{server.server_port}"),
        client_version=importlib.metadata.version("litellm"),
        admission_protocol="ollama-unify-body-free-resume/1",
    )
    try:
        if scenario == "hidden_replay":
            import litellm

            def duplicate_client(**kwargs):
                litellm.completion(**kwargs)
                return litellm.completion(**kwargs)

            with pytest.raises(ConformanceError, match="unexpected_library_replay_blocked"):
                qualify_completion(
                    p,
                    "resume-fixture",
                    [{"role": "user", "content": "OK"}],
                    completion=duplicate_client,
                )
        elif scenario == "replay":
            receipt = qualify_completion(p, "resume-fixture", [{"role": "user", "content": "OK"}])
            assert receipt["broker_admission"]["http_attempts"] == 2
            assert receipt["broker_admission"]["response_replayed"] is True
            assert receipt["broker_admission"]["queue_ms_including_warmup"] == 12
            assert "private text" not in json.dumps(receipt)
            assert "must-not-retain" not in json.dumps(receipt)
        else:
            expected = {
                "expired": "broker_resume_rejected_logical_request_expired",
                "changed_ticket": "broker_correlation_changed",
                "budget": "broker_resume_budget_exhausted",
            }[scenario]
            with pytest.raises(ConformanceError, match=expected):
                qualify_completion(p, "resume-fixture", [{"role": "user", "content": "OK"}])
        assert len(calls) == (3 if scenario == "budget" else 2)
        validate_wire(p, calls[0][0], calls[0][2], json.loads(calls[0][1]))
        for path, body, headers in calls[1:]:
            lowered = {key.lower(): value for key, value in headers.items()}
            assert path == "/api/chat"
            assert body == b""
            assert lowered["x-ollama-unify-resume-request"] == "true"
            assert lowered["x-ollama-unify-logical-request-id"] == "resume-fixture"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("selected", [True, False])
def test_public_admitted_lane_mapping(selected):
    from matric_eval.studies.broker_admission import verify_public_lane

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            assert self.path == "/.well-known/ollama-unify-gpu-negotiator"
            payload = json.dumps(
                {
                    "selected_gpu_ids": ["GPU-own"] if selected else ["GPU-other"],
                    "parallel_pool": {
                        "lanes": [
                            {
                                "id": "own",
                                "gpu_uuid": "GPU-own",
                                "kind": "managed",
                                "state": "ready",
                                "model": "fixture",
                            },
                            {"id": "unrelated", "model": "private unrelated model"},
                        ]
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    p = profile(f"http://127.0.0.1:{server.server_port}")
    evidence = {"lane": "own", "logical_request_id": "logical", "broker_request_id": "broker"}
    try:
        if selected:
            result = verify_public_lane(p, evidence)
            assert result["gpu_uuid"] == "GPU-own"
            assert "unrelated" not in json.dumps(result)
            assert result["execution_digest_binding"] == "unverified"
        else:
            with pytest.raises(ConformanceError, match="public_broker_lane_unverified"):
                verify_public_lane(p, evidence)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
