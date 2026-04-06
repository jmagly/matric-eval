"""REST API client for agentic-sandbox management server.

Implements SandboxInterface by wrapping the agentic-sandbox REST API
at /api/v1/. See agentic-sandbox management/src/http/tasks.rs for
the authoritative API schema.

API Endpoints Used:
    GET  /healthz                          - Liveness check
    POST /api/v1/tasks                     - Submit task (manifest JSON)
    GET  /api/v1/tasks/{id}                - Get task status
    GET  /api/v1/tasks/{id}/logs           - Stream task logs (SSE)
    GET  /api/v1/tasks/{id}/artifacts      - List artifacts
    GET  /api/v1/tasks/{id}/artifacts/{n}  - Download artifact
    DELETE /api/v1/tasks/{id}              - Cancel task
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from matric_eval.sandbox.config import SandboxConfig


class SandboxUnavailableError(ConnectionError):
    """Raised when the agentic-sandbox server is not reachable."""


class SandboxTaskError(RuntimeError):
    """Raised when a sandbox task submission or operation fails."""


class SandboxClient:
    """REST API client for agentic-sandbox.

    Provides synchronous HTTP calls to the agentic-sandbox management
    server. Runtime-agnostic — works with both VM and Docker backends.

    Args:
        config: Sandbox configuration. Defaults to localhost:8122.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        config: SandboxConfig | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.config = config or SandboxConfig()
        self._client = httpx.Client(
            base_url=self.config.base_url,
            timeout=timeout,
        )

    def check_health(self) -> bool:
        """Check if the agentic-sandbox server is healthy.

        Uses the /healthz liveness endpoint.
        """
        try:
            resp = self._client.get("/healthz")
            return resp.status_code == 200
        except httpx.ConnectError:
            return False

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
        """Submit an evaluation task to agentic-sandbox.

        Constructs a TaskManifest JSON and POSTs to /api/v1/tasks.

        Args:
            name: Human-readable task name
            repo_url: Git repository URL to clone
            branch: Git branch
            commit: Optional specific commit hash
            prompt: Claude prompt for the task
            config: Override config for this task (defaults to self.config)

        Returns:
            Task ID string

        Raises:
            SandboxUnavailableError: If server is not reachable
            SandboxTaskError: If task submission fails
        """
        cfg = config or self.config
        task_id = str(uuid.uuid4())

        manifest = {
            "version": "1",
            "kind": "Task",
            "metadata": {
                "id": task_id,
                "name": name,
                "labels": {"source": "matric-eval"},
            },
            "repository": {
                "url": repo_url,
                "branch": branch,
            },
            "claude": {
                "prompt": prompt,
                "headless": True,
                "skip_permissions": True,
                "output_format": "stream-json",
            },
            "vm": {
                "profile": cfg.profile,
                "cpus": cfg.cpus,
                "memory": cfg.memory,
                "disk": cfg.disk,
                "network_mode": cfg.network_mode,
            },
            "lifecycle": {
                "timeout": cfg.timeout,
                "failure_action": "destroy",
            },
        }

        if commit:
            manifest["repository"]["commit"] = commit

        try:
            resp = self._client.post(
                "/api/v1/tasks",
                json={"manifest": manifest},
            )
        except httpx.ConnectError as e:
            raise SandboxUnavailableError(
                f"Cannot connect to agentic-sandbox at {cfg.base_url}: {e}"
            ) from e

        if resp.status_code == 202:
            data = resp.json()
            return data["task_id"]

        # Error responses
        data = resp.json()
        error_msg = data.get("error", f"HTTP {resp.status_code}")
        raise SandboxTaskError(f"Task submission failed: {error_msg}")

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get current task status.

        Returns:
            Dict with: id, name, state, state_message, exit_code, error,
            vm_name, vm_ip, progress, created_at, started_at, state_changed_at

        Raises:
            SandboxUnavailableError: If server is not reachable
            SandboxTaskError: If task not found
        """
        try:
            resp = self._client.get(f"/api/v1/tasks/{task_id}")
        except httpx.ConnectError as e:
            raise SandboxUnavailableError(str(e)) from e

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            raise SandboxTaskError(f"Task not found: {task_id}")
        raise SandboxTaskError(f"Failed to get task status: HTTP {resp.status_code}")

    def get_task_logs(self, task_id: str) -> str:
        """Get task output logs.

        Note: The real endpoint (/api/v1/tasks/{id}/logs) uses SSE streaming.
        This method collects all SSE stdout events into a single string.
        For real-time streaming, use the SSE endpoint directly.

        Returns:
            Concatenated stdout log output
        """
        try:
            # Use a longer timeout for log streaming
            with self._client.stream(
                "GET", f"/api/v1/tasks/{task_id}/logs"
            ) as resp:
                if resp.status_code != 200:
                    return ""
                lines = []
                for line in resp.iter_lines():
                    if line.startswith("data:"):
                        lines.append(line[5:].strip())
                    elif line.startswith("event: completed"):
                        break
                    elif line.startswith("event: error"):
                        break
                return "\n".join(lines)
        except httpx.ConnectError as e:
            raise SandboxUnavailableError(str(e)) from e

    def list_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        """List output artifacts for a completed task.

        Returns:
            List of dicts with: name, path, size_bytes, content_type, checksum
        """
        try:
            resp = self._client.get(f"/api/v1/tasks/{task_id}/artifacts")
        except httpx.ConnectError as e:
            raise SandboxUnavailableError(str(e)) from e

        if resp.status_code == 200:
            return resp.json().get("artifacts", [])
        return []

    def download_artifact(self, task_id: str, artifact_name: str) -> bytes:
        """Download a specific artifact by name.

        Returns:
            Raw artifact bytes
        """
        try:
            resp = self._client.get(
                f"/api/v1/tasks/{task_id}/artifacts/{artifact_name}"
            )
        except httpx.ConnectError as e:
            raise SandboxUnavailableError(str(e)) from e

        if resp.status_code == 200:
            return resp.content
        raise SandboxTaskError(
            f"Artifact '{artifact_name}' not found for task {task_id}"
        )

    def cancel_task(self, task_id: str, reason: str = "") -> bool:
        """Cancel a running task.

        Args:
            task_id: Task to cancel
            reason: Cancellation reason

        Returns:
            True if cancellation succeeded
        """
        try:
            resp = self._client.request(
                "DELETE",
                f"/api/v1/tasks/{task_id}",
                json={"reason": reason or "Cancelled by matric-eval"},
            )
        except httpx.ConnectError as e:
            raise SandboxUnavailableError(str(e)) from e

        if resp.status_code == 200:
            return resp.json().get("success", False)
        return False

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> SandboxClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
