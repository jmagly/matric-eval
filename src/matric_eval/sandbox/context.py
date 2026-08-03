"""Sandbox interface protocol and indirection for testability (BC-001)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from matric_eval.sandbox.config import SandboxConfig


@runtime_checkable
class SandboxInterface(Protocol):
    """Abstract interface for sandbox operations.

    Enables unit testing without a running agentic-sandbox server
    by allowing mock implementations via monkeypatch.
    """

    def check_health(self) -> bool:
        """Check if the sandbox server is reachable and healthy."""
        ...

    def submit_task(
        self,
        name: str,
        *,
        repo_url: str,
        branch: str = "main",
        commit: str | None = None,
        prompt: str = "",
        config: SandboxConfig | None = None,
    ) -> str:
        """Submit a task to the sandbox.

        Returns:
            Task ID string
        """
        ...

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get current task status.

        Returns dict with keys: id, name, state, exit_code, error, etc.
        """
        ...

    def get_task_logs(self, task_id: str) -> str:
        """Get task output logs."""
        ...

    def list_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        """List output artifacts for a completed task.

        Returns list of dicts with keys: name, path, size_bytes, content_type
        """
        ...

    def download_artifact(self, task_id: str, artifact_name: str) -> bytes:
        """Download a specific artifact."""
        ...

    def cancel_task(self, task_id: str, reason: str = "") -> bool:
        """Cancel a running task. Returns True if successful."""
        ...


# ---------------------------------------------------------------------------
# Global sandbox instance (mockable via monkeypatch)
# ---------------------------------------------------------------------------

_sandbox: SandboxInterface | None = None


def get_sandbox() -> SandboxInterface:
    """Get the active sandbox instance.

    Returns the global SandboxClient by default. Can be overridden
    in tests via monkeypatch on this module's _sandbox variable.

    Raises:
        RuntimeError: If no sandbox is configured
    """
    global _sandbox
    if _sandbox is None:
        from matric_eval.sandbox.client import SandboxClient

        _sandbox = SandboxClient()
    return _sandbox
