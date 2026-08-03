"""Sandbox configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxConfig:
    """Configuration for agentic-sandbox integration.

    Attributes:
        base_url: agentic-sandbox management server REST API URL
        profile: VM/container profile ("agentic-dev" or "basic")
        network_mode: Network isolation ("isolated", "outbound", "full")
        timeout: Task timeout string (e.g., "5m", "1h", "24h")
        cpus: CPU cores for the sandbox
        memory: Memory allocation (e.g., "4G")
        disk: Disk allocation (e.g., "20G")
        inbox_path: Host path for task input staging
        outbox_path: Host path for task output collection
    """

    base_url: str = "http://localhost:8122"
    profile: str = "agentic-dev"
    network_mode: str = "isolated"
    timeout: str = "5m"
    cpus: int = 2
    memory: str = "4G"
    disk: str = "20G"
    inbox_path: str = "/srv/agentshare/inbox"
    outbox_path: str = "/srv/agentshare/outbox"
