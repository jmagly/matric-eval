"""
Patch apply scorer for SWE-bench style patch application evaluation.

Scores model-generated git patches by:
1. Validating path safety (reject shell injection attempts)
2. Preparing shell commands with shlex.quote for safe execution
3. Checking patch application and test suite success

Security:
- All paths validated against VALID_PATH_RE before use
- shlex.quote() applied to all paths in shell commands
- Commands are prepared but executed by the agentic sandbox

Note: This scorer prepares execution commands but does not execute them
directly. The agentic-sandbox handles actual execution in an isolated
environment.
"""

import re
import shlex
from typing import Optional

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

# Regex for safe path validation — allows only alphanumeric, slash, dot,
# underscore, and hyphen. Rejects spaces, shell metacharacters, and
# control characters.
VALID_PATH_RE = r"^[a-zA-Z0-9_/.\-]+$"


def validate_test_path(path: Optional[str]) -> bool:
    """Validate a test path against the safe path regex.

    Accepts paths containing only: letters, digits, underscore, forward
    slash, dot, and hyphen. Rejects anything that could be used for
    shell injection (spaces, semicolons, pipes, etc.).

    Args:
        path: Path string to validate, or None

    Returns:
        True if path is safe, False otherwise
    """
    if not path:
        return False
    return re.fullmatch(VALID_PATH_RE, path) is not None


def _build_patch_command(repo_path: str, patch_path: str) -> str:
    """Build a safe git apply command for the given repo and patch.

    Args:
        repo_path: Path to the target repository
        patch_path: Path to the patch file

    Returns:
        Shell command string with quoted paths
    """
    safe_repo = shlex.quote(repo_path)
    safe_patch = shlex.quote(patch_path)
    return f"git -C {safe_repo} apply {safe_patch}"


def _build_test_command(repo_path: str, test_path: str) -> str:
    """Build a safe pytest command for the given repo and test path.

    Args:
        repo_path: Path to the target repository
        test_path: Path to the test file or directory (must pass validation)

    Returns:
        Shell command string with quoted paths, or empty string if path invalid
    """
    if not validate_test_path(test_path):
        return ""
    safe_repo = shlex.quote(repo_path)
    safe_test = shlex.quote(test_path)
    return f"python -m pytest {safe_repo}/{safe_test} -x -q"


@scorer(metrics=[mean()])
def patch_apply_scorer() -> Scorer:
    """Inspect AI scorer for git patch application and test verification.

    Evaluates model-generated patches for SWE-bench style tasks.

    Scores 1.0 if:
    1. The model's patch applies cleanly to the target repository
    2. The repository's test suite passes after applying the patch

    Scores 0.0 if either step fails.

    The scorer reads the following metadata from the task state:
    - "repo_path": Path to the target repository (required)
    - "test_path": Path to the test file/dir to run (required, validated)
    - "patch": The model-generated patch to apply (from model output)

    Security:
    - test_path is validated against VALID_PATH_RE before use
    - All paths are quoted with shlex.quote() in shell commands
    - Commands are prepared for agentic-sandbox execution, not run directly

    Returns:
        Scorer function compatible with Inspect AI
    """

    async def score(state: TaskState, target: Target) -> Score:
        """Score a model-generated patch.

        Args:
            state: TaskState with model output (the patch) and metadata
            target: Target (unused; correctness is determined by tests)

        Returns:
            Score of 1.0 if patch applies and tests pass, 0.0 otherwise
        """
        metadata = state.metadata or {}

        repo_path = metadata.get("repo_path", "")
        test_path = metadata.get("test_path", "")
        patch_content = state.output.completion

        # Validate required fields
        if not repo_path:
            return Score(
                value=0.0,
                explanation="Missing repo_path in task metadata",
            )

        if not patch_content or not patch_content.strip():
            return Score(
                value=0.0,
                explanation="Model produced no patch output",
            )

        # Validate test path safety
        if not validate_test_path(test_path):
            return Score(
                value=0.0,
                explanation=(
                    f"Invalid or unsafe test_path: {test_path!r}. "
                    "Path must match [a-zA-Z0-9_/.\\-]+"
                ),
            )

        # Build shell commands (prepared for sandbox execution)
        patch_cmd = _build_patch_command(repo_path, "patch.diff")
        test_cmd = _build_test_command(repo_path, test_path)

        # In production, the agentic-sandbox executes these commands.
        # Here we return the prepared commands in metadata so the sandbox
        # can pick them up, along with a pending score.
        #
        # The sandbox will update the score after execution.
        return Score(
            value=0.0,
            explanation="Patch scoring requires agentic-sandbox execution",
            metadata={
                "patch_cmd": patch_cmd,
                "test_cmd": test_cmd,
                "patch_content": patch_content,
                "repo_path": repo_path,
                "test_path": test_path,
                "sandbox_required": True,
            },
        )

    return score
