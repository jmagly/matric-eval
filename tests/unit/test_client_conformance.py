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
    for bad in ({"num_retries": 1}, {"timeout": 0}, {"max_tokens": -1}, {"fallbacks": []}):
        with pytest.raises(ConformanceError):
            bounded_external_arguments(bad)


@pytest.mark.parametrize(
    "scenario",
    ["ok", "missing_header", "lost_ack", "timeout", "admission", "reasoning", "empty", "tools"],
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
            if scenario == "tools":
                message["tool_calls"] = [{"function": {"name": "ping", "arguments": {}}}]
            payload = json.dumps(
                {
                    "model": "fixture",
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
        tools=scenario == "tools",
        timeout=0.05 if scenario == "timeout" else 30,
    )
    tools = (
        [
            {
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "fixture ping",
                    "parameters": {"type": "object", "properties": {}},
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
        elif scenario in ("lost_ack", "timeout", "admission", "reasoning", "empty"):
            expected = {
                "lost_ack": "transport_failure_no_replay",
                "timeout": "response_timeout_phase_unknown_no_replay",
                "admission": "admission_unconfirmed_no_replay",
                "reasoning": "thinking_off_violated",
                "empty": "empty_output",
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
        api_base=f"http://127.0.0.1:{server.server_port}",
        expected_digest="fixture-digest",
        observed_digest="fixture-digest",
        dimensions=2,
        request_id="embedding-fixture",
        client_version=importlib.metadata.version("litellm"),
    )
    try:
        assert qualify_embedding(**kwargs)["measured"]["dimensions"] == 2
        with pytest.raises(ConformanceError, match="dimensions_or_values"):
            qualify_embedding(**{**kwargs, "dimensions": 3})
        with pytest.raises(ConformanceError, match="digest_mismatch"):
            qualify_embedding(**{**kwargs, "observed_digest": "changed"})
        assert requests == [("/api/embed", "fixture-embed")] * 2
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
