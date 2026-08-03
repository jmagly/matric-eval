"""Tests for the agentic-sandbox integration (issue #34, ADR-001)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from matric_eval.sandbox.client import (
    SandboxClient,
    SandboxTaskError,
    SandboxUnavailableError,
)
from matric_eval.sandbox.config import SandboxConfig
from matric_eval.sandbox.context import SandboxInterface, get_sandbox
from matric_eval.sandbox.runners import (
    GoTestRunner,
    JavaTestRunner,
    NodeTestRunner,
    PythonTestRunner,
    TestResult,
    TestRunner,
    get_runner,
)
from matric_eval.sandbox.tools import UnsafePathError, validate_cwd, validate_path

# =============================================================================
# SandboxConfig Tests
# =============================================================================


class TestSandboxConfig:
    def test_defaults(self) -> None:
        cfg = SandboxConfig()
        assert cfg.base_url == "http://localhost:8122"
        assert cfg.profile == "agentic-dev"
        assert cfg.network_mode == "isolated"
        assert cfg.timeout == "5m"
        assert cfg.cpus == 2
        assert cfg.memory == "4G"

    def test_custom_values(self) -> None:
        cfg = SandboxConfig(
            base_url="http://sandbox:9000",
            profile="basic",
            network_mode="outbound",
            timeout="1h",
        )
        assert cfg.base_url == "http://sandbox:9000"
        assert cfg.profile == "basic"
        assert cfg.network_mode == "outbound"

    def test_frozen(self) -> None:
        cfg = SandboxConfig()
        with pytest.raises(AttributeError):
            cfg.profile = "basic"  # type: ignore[misc]


# =============================================================================
# SandboxClient Tests (mocked HTTP)
# =============================================================================


class TestSandboxClient:
    def _make_client(self, config: SandboxConfig | None = None) -> SandboxClient:
        return SandboxClient(config=config or SandboxConfig())

    def test_check_health_success(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(client._client, "get", return_value=mock_resp):
            assert client.check_health() is True

    def test_check_health_failure(self) -> None:
        import httpx

        client = self._make_client()
        with patch.object(client._client, "get", side_effect=httpx.ConnectError("refused")):
            assert client.check_health() is False

    def test_submit_task_success(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {"task_id": "abc-123", "accepted": True}
        with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
            task_id = client.submit_task(
                "test-eval",
                repo_url="https://github.com/test/repo.git",
                branch="main",
                prompt="Run tests",
            )
            assert task_id == "abc-123"
            # Verify manifest structure
            call_args = mock_post.call_args
            body = call_args.kwargs.get("json") or call_args[1].get("json")
            manifest = body["manifest"]
            assert manifest["version"] == "1"
            assert manifest["kind"] == "Task"
            assert manifest["repository"]["url"] == "https://github.com/test/repo.git"
            assert manifest["vm"]["profile"] == "agentic-dev"
            assert manifest["vm"]["network_mode"] == "isolated"

    def test_submit_task_with_commit(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {"task_id": "xyz-789", "accepted": True}
        with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
            client.submit_task(
                "test",
                repo_url="https://example.com/repo.git",
                branch="main",
                commit="abc123def",
            )
            body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            assert body["manifest"]["repository"]["commit"] == "abc123def"

    def test_submit_task_custom_profile(self) -> None:
        cfg = SandboxConfig(profile="basic", network_mode="outbound")
        client = self._make_client(cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {"task_id": "t1", "accepted": True}
        with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
            client.submit_task("test", repo_url="https://example.com/r.git")
            body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            assert body["manifest"]["vm"]["profile"] == "basic"
            assert body["manifest"]["vm"]["network_mode"] == "outbound"

    def test_submit_task_server_error(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"error": "Invalid manifest", "accepted": False}
        with patch.object(client._client, "post", return_value=mock_resp):
            with pytest.raises(SandboxTaskError, match="Invalid manifest"):
                client.submit_task("test", repo_url="https://example.com/r.git")

    def test_submit_task_unavailable(self) -> None:
        import httpx

        client = self._make_client()
        with patch.object(client._client, "post", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(SandboxUnavailableError):
                client.submit_task("test", repo_url="https://example.com/r.git")

    def test_get_task_status(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "t1",
            "name": "eval",
            "state": "running",
            "exit_code": None,
            "error": None,
        }
        with patch.object(client._client, "get", return_value=mock_resp):
            status = client.get_task_status("t1")
            assert status["state"] == "running"

    def test_get_task_status_not_found(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch.object(client._client, "get", return_value=mock_resp):
            with pytest.raises(SandboxTaskError, match="not found"):
                client.get_task_status("nonexistent")

    def test_list_artifacts(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "artifacts": [
                {
                    "name": "output.json",
                    "path": "/out/output.json",
                    "size_bytes": 1024,
                    "content_type": "application/json",
                }
            ]
        }
        with patch.object(client._client, "get", return_value=mock_resp):
            arts = client.list_artifacts("t1")
            assert len(arts) == 1
            assert arts[0]["name"] == "output.json"

    def test_download_artifact(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"file contents"
        with patch.object(client._client, "get", return_value=mock_resp):
            data = client.download_artifact("t1", "output.json")
            assert data == b"file contents"

    def test_download_artifact_not_found(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch.object(client._client, "get", return_value=mock_resp):
            with pytest.raises(SandboxTaskError, match="not found"):
                client.download_artifact("t1", "missing.txt")

    def test_cancel_task(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True}
        with patch.object(client._client, "request", return_value=mock_resp):
            assert client.cancel_task("t1", reason="test") is True

    def test_cancel_task_failure(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch.object(client._client, "request", return_value=mock_resp):
            assert client.cancel_task("t1") is False

    def test_context_manager(self) -> None:
        with SandboxClient() as client:
            assert client is not None


# =============================================================================
# SandboxInterface Protocol Tests
# =============================================================================


class TestSandboxInterface:
    def test_client_implements_protocol(self) -> None:
        """SandboxClient must satisfy the SandboxInterface protocol."""
        assert isinstance(SandboxClient(), SandboxInterface)

    def test_mock_implements_protocol(self) -> None:
        """A mock with the right methods should satisfy the protocol."""
        mock = MagicMock(spec=SandboxClient)
        assert isinstance(mock, SandboxInterface)


class TestGetSandbox:
    def test_returns_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import matric_eval.sandbox.context as ctx_module

        monkeypatch.setattr(ctx_module, "_sandbox", None)
        sandbox = get_sandbox()
        assert isinstance(sandbox, SandboxClient)

    def test_monkeypatch_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import matric_eval.sandbox.context as ctx_module

        mock = MagicMock(spec=SandboxClient)
        monkeypatch.setattr(ctx_module, "_sandbox", mock)
        assert get_sandbox() is mock


# =============================================================================
# Path Validation Tests
# =============================================================================


class TestPathValidation:
    def test_valid_paths(self) -> None:
        assert validate_path("/home/user/project") == "/home/user/project"
        assert validate_path("src/main.py") == "src/main.py"
        assert validate_path("tests/test_foo.py") == "tests/test_foo.py"
        assert validate_path("a-b_c.d/e") == "a-b_c.d/e"

    def test_reject_semicolon(self) -> None:
        with pytest.raises(UnsafePathError):
            validate_path("/tmp; rm -rf /")

    def test_reject_pipe(self) -> None:
        with pytest.raises(UnsafePathError):
            validate_path("foo | bar")

    def test_reject_backtick(self) -> None:
        with pytest.raises(UnsafePathError):
            validate_path("`whoami`")

    def test_reject_dollar(self) -> None:
        with pytest.raises(UnsafePathError):
            validate_path("$HOME/file")

    def test_reject_ampersand(self) -> None:
        with pytest.raises(UnsafePathError):
            validate_path("foo & bar")

    def test_reject_directory_traversal(self) -> None:
        with pytest.raises(UnsafePathError, match="traversal"):
            validate_path("../../etc/passwd")

    def test_reject_spaces(self) -> None:
        with pytest.raises(UnsafePathError):
            validate_path("/path with spaces")

    def test_validate_cwd_none(self) -> None:
        assert validate_cwd(None) is None

    def test_validate_cwd_valid(self) -> None:
        assert validate_cwd("/workspace") == "/workspace"

    def test_validate_cwd_invalid(self) -> None:
        with pytest.raises(UnsafePathError):
            validate_cwd("; rm -rf /")


# =============================================================================
# Test Runner Tests
# =============================================================================


class TestRunners:
    def test_python_runner(self) -> None:
        runner = PythonTestRunner()
        assert runner.language == "python"
        cmd = runner.build_test_command("tests/")
        assert "pytest" in cmd
        assert "tests/" in cmd

    def test_node_runner(self) -> None:
        runner = NodeTestRunner()
        assert runner.language == "javascript"
        cmd = runner.build_test_command("src/__tests__")
        assert "jest" in cmd

    def test_go_runner(self) -> None:
        runner = GoTestRunner()
        assert runner.language == "go"
        cmd = runner.build_test_command("./...")
        assert "go test" in cmd

    def test_java_runner(self) -> None:
        runner = JavaTestRunner()
        assert runner.language == "java"
        cmd = runner.build_test_command("core")
        assert "mvn test" in cmd

    def test_get_runner(self) -> None:
        runner = get_runner("python")
        assert isinstance(runner, PythonTestRunner)

    def test_get_runner_unknown(self) -> None:
        with pytest.raises(KeyError, match="rust"):
            get_runner("rust")

    def test_runner_protocol(self) -> None:
        """All runners satisfy the TestRunner protocol."""
        for cls in (PythonTestRunner, NodeTestRunner, GoTestRunner, JavaTestRunner):
            runner = cls()
            assert isinstance(runner, TestRunner)

    def test_test_result(self) -> None:
        result = TestResult(passed=True, exit_code=0, output="OK", tests_run=5, tests_passed=5)
        assert result.passed is True
        assert result.tests_failed == 0
