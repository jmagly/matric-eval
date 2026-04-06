"""Agentic sandbox integration for matric-eval.

Provides a thin REST API client adapter for the agentic-sandbox project,
enabling agentic benchmark evaluations (SWE-bench, Terminal-Bench, etc.)
to run in isolated VMs or Docker containers.
"""

from matric_eval.sandbox.client import SandboxClient
from matric_eval.sandbox.config import SandboxConfig
from matric_eval.sandbox.context import SandboxInterface, get_sandbox

__all__ = [
    "SandboxClient",
    "SandboxConfig",
    "SandboxInterface",
    "get_sandbox",
]
