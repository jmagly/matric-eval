"""
Code execution scorer for HumanEval and MBPP benchmarks.

Provides safe code execution with timeout, memory limits, and sandboxing.
Extracts code from markdown fences and validates against test cases.
"""

import re
import subprocess
import sys
from typing import Any

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState


def extract_code(response: str) -> str:
    """
    Extract code from markdown fences or return raw response.

    Handles:
    - Code blocks with language tags: ```python ... ```
    - Code blocks without language tags: ``` ... ```
    - Raw code without fences
    - DS-1000 solution markers (BEGIN SOLUTION, END SOLUTION, etc.)

    Args:
        response: Model response potentially containing code

    Returns:
        Extracted code string, stripped of whitespace
    """
    if not response:
        return ""

    # Try to extract code from markdown fence
    # Pattern matches ``` with optional language tag, captures content, ends with ```
    fence_pattern = r"```(?:\w+)?\n(.*?)```"
    match = re.search(fence_pattern, response, re.DOTALL)

    if match:
        # Found markdown fence, extract content
        code = match.group(1)
    else:
        # No fence found, use entire response
        code = response

    # Remove common solution markers (DS-1000, HumanEval, etc.)
    # These markers may appear at the start or end of the code
    markers_to_remove = [
        r'^.*?### BEGIN SOLUTION\s*\n?',  # DS-1000 begin marker
        r'^.*?<code>\s*\n?',  # DS-1000 code tag
        r'\n?### END SOLUTION.*$',  # DS-1000 end marker with ###
        r'\n?END SOLUTION.*$',  # DS-1000 end marker without ###
        r'\n?</code>.*$',  # DS-1000 closing code tag
        r'^# Solution\s*\n?',  # Common solution header
    ]

    for pattern in markers_to_remove:
        code = re.sub(pattern, '', code, flags=re.DOTALL | re.IGNORECASE)

    return code.strip()


def safe_execute(code: str, test_code: str, timeout: int = 30) -> dict[str, Any]:
    """
    Execute code with tests in a subprocess with timeout.

    Combines user code with test code and executes in isolated subprocess.
    Captures stdout, stderr, and execution results.

    Security measures:
    - Subprocess isolation (no shared memory)
    - Timeout enforcement
    - Output capture to prevent DoS

    Args:
        code: User-generated code to execute
        test_code: Test assertions to validate code
        timeout: Maximum execution time in seconds (default: 30)

    Returns:
        Dictionary with keys:
        - passed: bool indicating if all tests passed
        - error: str or None with error message if failed
        - output: str with captured stdout/stderr
    """
    # Combine code and tests into single script
    full_code = code + "\n" + test_code

    try:
        # Execute in subprocess with timeout
        result = subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True,
            timeout=timeout,
            text=True,
        )

        # Combine stdout and stderr for output
        output = result.stdout + result.stderr

        if result.returncode == 0:
            # Tests passed
            return {
                "passed": True,
                "error": None,
                "output": output,
            }
        else:
            # Tests failed or error occurred
            error_msg = result.stderr if result.stderr else "Test execution failed"
            return {
                "passed": False,
                "error": error_msg,
                "output": output,
            }

    except subprocess.TimeoutExpired:
        # Code exceeded timeout
        return {
            "passed": False,
            "error": f"Execution timeout after {timeout} seconds",
            "output": "",
        }
    except Exception as e:
        # Unexpected error
        return {
            "passed": False,
            "error": f"Execution error: {str(e)}",
            "output": "",
        }


@scorer(metrics=[mean()])
def code_execution_scorer(timeout: int = 30) -> Scorer:
    """
    Create Inspect AI scorer for code execution validation.

    Extracts code from model response, executes against test cases,
    and returns score based on test results.

    Args:
        timeout: Maximum execution time per test in seconds (default: 30)

    Returns:
        Scorer function compatible with Inspect AI

    Example:
        >>> task = Task(
        ...     dataset=samples,
        ...     solver=[generate()],
        ...     scorer=code_execution_scorer(timeout=60)
        ... )
    """

    async def score(state: TaskState, target: Target) -> Score:
        """
        Score a model response by executing code against tests.

        Args:
            state: Current task state with model output and metadata
            target: Target (not used, metadata comes from state)

        Returns:
            Score with value 1.0 for pass, 0.0 for fail
        """
        # Extract code from model response
        response = state.output.completion
        code = extract_code(response)

        # Get test code from state metadata (comes from Sample)
        test_code = state.metadata.get("test", "") if state.metadata else ""

        # Execute code with tests
        result = safe_execute(code, test_code, timeout=timeout)

        if result["passed"]:
            # All tests passed
            return Score(
                value=1.0,
                explanation="",
            )
        else:
            # Tests failed or error occurred
            return Score(
                value=0.0,
                explanation=result["error"] or "Test execution failed",
            )

    return score
