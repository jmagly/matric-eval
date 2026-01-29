"""
I/O-based code execution scorer for competitive programming benchmarks.

Executes code with stdin input and compares stdout against expected output.
Used for LiveCodeBench and similar stdin/stdout-based evaluations.
"""

import subprocess
import sys
from typing import Any

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from matric_eval.scorers.code_execution import extract_code


def io_execute(code: str, stdin_input: str, timeout: int = 30) -> dict[str, Any]:
    """
    Execute code with stdin input and capture stdout.

    Args:
        code: Python code to execute
        stdin_input: Input to provide via stdin
        timeout: Maximum execution time in seconds (default: 30)

    Returns:
        Dictionary with keys:
        - success: bool indicating if execution succeeded
        - stdout: captured stdout
        - stderr: captured stderr
        - error: error message if failed
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            input=stdin_input,
            capture_output=True,
            timeout=timeout,
            text=True,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.stderr if result.returncode != 0 else None,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": f"Execution timeout after {timeout} seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": f"Execution error: {str(e)}",
        }


def normalize_output(output: str) -> str:
    """
    Normalize output for comparison.

    - Strip leading/trailing whitespace
    - Normalize line endings
    - Remove trailing newlines from each line

    Args:
        output: Raw output string

    Returns:
        Normalized output string
    """
    if not output:
        return ""

    # Normalize line endings
    output = output.replace("\r\n", "\n").replace("\r", "\n")

    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in output.split("\n")]

    # Remove trailing empty lines
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def compare_outputs(actual: str, expected: str) -> bool:
    """
    Compare actual output against expected output.

    Uses normalized comparison to handle whitespace differences.

    Args:
        actual: Actual output from execution
        expected: Expected output from test case

    Returns:
        True if outputs match (after normalization)
    """
    return normalize_output(actual) == normalize_output(expected)


@scorer(metrics=[mean()])
def io_execution_scorer(timeout: int = 30) -> Scorer:
    """
    Create Inspect AI scorer for stdin/stdout code execution.

    Executes model-generated code with test inputs provided via stdin
    and compares stdout against expected outputs.

    Args:
        timeout: Maximum execution time per test in seconds (default: 30)

    Returns:
        Scorer function compatible with Inspect AI

    Example:
        >>> task = Task(
        ...     dataset=samples,
        ...     solver=[generate()],
        ...     scorer=io_execution_scorer(timeout=60)
        ... )
    """

    async def score(state: TaskState, target: Target) -> Score:
        """
        Score a model response by executing code with test inputs.

        Args:
            state: Current task state with model output and metadata
            target: Target (expected output from first test)

        Returns:
            Score with value 1.0 for pass, 0.0 for fail
        """
        # Extract code from model response
        response = state.output.completion
        code = extract_code(response)

        if not code:
            return Score(
                value=0.0,
                explanation="No code found in response",
            )

        # Get test cases from metadata
        metadata = state.metadata or {}
        public_tests = metadata.get("public_test_cases", [])
        private_tests = metadata.get("private_test_cases", [])

        # Combine tests (public first, then private)
        all_tests = public_tests + private_tests

        if not all_tests:
            # No tests available - use target as expected output
            # This is a fallback when test cases aren't structured properly
            return Score(
                value=0.0,
                explanation="No test cases available for evaluation",
            )

        # Run all tests and track results
        passed = 0
        total = len(all_tests)
        failed_cases = []

        for i, test in enumerate(all_tests):
            test_input = test.get("input", "")
            expected_output = test.get("output", "")

            result = io_execute(code, test_input, timeout=timeout)

            if result["success"] and compare_outputs(result["stdout"], expected_output):
                passed += 1
            else:
                if len(failed_cases) < 3:  # Limit failed case logging
                    failed_cases.append({
                        "test": i + 1,
                        "error": result.get("error") or "Output mismatch",
                        "expected": expected_output[:100] if expected_output else "",
                        "actual": result["stdout"][:100] if result["stdout"] else "",
                    })

        # Calculate score as fraction of tests passed
        score_value = passed / total if total > 0 else 0.0

        # Build explanation
        if passed == total:
            explanation = f"All {total} test(s) passed"
        else:
            explanation = f"Passed {passed}/{total} tests"
            if failed_cases:
                explanation += f"\nFirst failure: {failed_cases[0]['error']}"

        return Score(
            value=score_value,
            explanation=explanation,
        )

    return score
