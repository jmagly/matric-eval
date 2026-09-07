"""Exercise the real Inspect/SDK transport against localhost, without provider calls."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ResponseSchema
from inspect_ai.solver import generate

from matric_eval.providers.base import ProviderConfig
from matric_eval.providers.openrouter import OpenRouterProvider

pytestmark = pytest.mark.unit

FAKE_KEY = "openrouter-transport-test-secret-sentinel"


@pytest.fixture
def capture_server(monkeypatch):
    # Supply only fake credentials and prevent proxy routing of local requests.
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-openai-test-key")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
            if self.path != "/api/v1/chat/completions":
                self.send_error(400, "Unexpected endpoint")
                return
            response = {
                "id": "local-completion",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"answer":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
            encoded = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("model", ["moonshotai/kimi-k3", "z-ai/glm-5.3", "openai/gpt-4o"])
@pytest.mark.parametrize("output_format", ["text", "typed_schema", "native_schema"])
def test_openrouter_inspect_wire_contract(capture_server, tmp_path, caplog, model, output_format):
    base_url, requests = capture_server
    preferences = {"order": ["test-provider"], "allow_fallbacks": False}
    provider = OpenRouterProvider(
        ProviderConfig(
            base_url=base_url,
            api_key=FAKE_KEY,
            extra={"provider": preferences, "route": "fallback", "transforms": ["middle-out"]},
        )
    )
    kwargs = provider.get_eval_kwargs(model)
    kwargs["extra_body"]["reasoning"] = {"effort": "low"}
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    if output_format == "typed_schema":
        kwargs["response_schema"] = ResponseSchema(name="answer", json_schema=schema, strict=True)
    elif output_format == "native_schema":
        # Native extra_body bypasses Inspect's typed-schema keyword filtering.
        schema = {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "before": {"type": "string"},
                            "after": {"type": "string"},
                        },
                        "required": ["before", "after"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["edits"],
            "additionalProperties": False,
        }
        kwargs["extra_body"]["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "bounded_edits", "schema": schema, "strict": True},
        }
    logs = eval(
        Task(dataset=[Sample(input="Return an answer.")], solver=generate()),
        model=provider.format_model_id(model),
        log_dir=str(tmp_path),
        log_format="json",
        display="none",
        max_tokens=64,
        max_retries=0,
        **kwargs,
    )
    assert len(logs) == 1
    assert logs[0].status == "success"
    assert len(requests) == 1
    request = requests[0]
    assert request["path"] == "/api/v1/chat/completions"
    body = request["body"]
    assert body["model"] == model
    assert body["max_tokens"] == 64
    assert "max_completion_tokens" not in body
    assert body["provider"] == preferences
    assert body["route"] == "fallback"
    assert body["transforms"] == ["middle-out"]
    assert body["reasoning"] == {"effort": "low"}
    if output_format != "text":
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["schema"] == schema
        assert body["response_format"]["json_schema"]["strict"] is True
        if output_format == "native_schema":
            assert body["response_format"] == kwargs["extra_body"]["response_format"]
    else:
        assert "response_format" not in body
    headers = {key.lower(): value for key, value in request["headers"].items()}
    assert headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert headers["http-referer"] == "https://github.com/jmagly/matric-eval"
    assert headers["x-title"] == "matric-eval"
    # Authentication must reach the endpoint without appearing in eval artifacts.
    assert FAKE_KEY not in logs[0].model_dump_json()
    artifacts = list(tmp_path.rglob("*.json"))
    assert artifacts
    assert all(FAKE_KEY not in path.read_text() for path in artifacts)
    assert FAKE_KEY not in caplog.text
