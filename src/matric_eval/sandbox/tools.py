"""Inspect AI tool wrappers bridging to agentic-sandbox exec API.

These tools are registered with Inspect AI's solver framework and
execute commands inside the sandbox task via the gRPC exec API or
REST-based command dispatch.

Security: All path parameters are validated to prevent shell injection.
"""

from __future__ import annotations

import re

# Regex for validating safe paths — alphanumeric, underscores, dots,
# hyphens, and forward slashes only. No shell metacharacters.
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_/.\-]+$")


class UnsafePathError(ValueError):
    """Raised when a path contains unsafe characters."""


def validate_path(path: str) -> str:
    """Validate a path is safe for shell use.

    Args:
        path: Path string to validate

    Returns:
        The validated path

    Raises:
        UnsafePathError: If path contains shell metacharacters
    """
    if not _SAFE_PATH_RE.match(path):
        raise UnsafePathError(
            f"Path contains unsafe characters: {path!r}. "
            "Only alphanumeric, underscore, dot, hyphen, and slash are allowed."
        )
    # Block directory traversal
    if ".." in path:
        raise UnsafePathError(
            f"Path contains directory traversal: {path!r}"
        )
    return path


def validate_cwd(cwd: str | None) -> str | None:
    """Validate an optional cwd parameter.

    Args:
        cwd: Working directory path or None

    Returns:
        Validated path or None

    Raises:
        UnsafePathError: If cwd contains unsafe characters
    """
    if cwd is None:
        return None
    return validate_path(cwd)
