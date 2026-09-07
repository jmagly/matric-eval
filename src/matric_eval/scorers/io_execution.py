"""
I/O-based code execution scorer for competitive programming benchmarks.

Executes code with stdin input and compares stdout against expected output.
Used for LiveCodeBench and similar stdin/stdout-based evaluations.
"""

from typing import Any

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from matric_eval.scorers.code_execution import extract_code
from matric_eval.scorers.isolated_execution import execute_python


def io_execute(code: str, stdin_input: str, timeout: int = 30) -> dict[str, Any]:
    """Execute with bounded stdin/stdout through the configured isolated runner."""
    result = execute_python(code, stdin_input=stdin_input, timeout=timeout)
    return {**result, "success": result["status"] == "passed"}


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
        timeout: Maximum execution time per test in seconds (0 < timeout <= 30)

    Returns:
        Scorer function compatible with Inspect AI

    Example:
        >>> task = Task(
        ...     dataset=samples,
        ...     solver=[generate()],
        ...     scorer=io_execution_scorer(timeout=30)
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

        # Get test cases from metadata
        metadata = state.metadata or {}
        public_tests = metadata.get("public_test_cases", [])
        private_tests = metadata.get("private_test_cases", [])

        # Combine tests (public first, then private)
        all_tests = public_tests + private_tests

        if not all_tests:
            return Score.unscored(
                reason="grader_failed",
                explanation="No test cases available for evaluation",
                metadata={"runner_status": "test_harness_unavailable"},
            )
        if not code:
            return Score(value=0.0, explanation="No code found in response")

        # Run all tests and track results
        passed = 0
        total = len(all_tests)
        failed_cases = []
        execution_records = []

        for i, test in enumerate(all_tests):
            test_input = test.get("input", "")
            expected_output = test.get("output", "")

            result = io_execute(code, test_input, timeout=timeout)

            execution_records.append(
                {
                    "test": i + 1,
                    "runner_status": result["status"],
                    "runner_error": result["error"],
                    "execution_provenance": result["provenance"],
                }
            )
            if result["status"] not in {"passed", "incorrect", "timeout", "output_limit"}:
                return Score.unscored(
                    reason="grader_failed",
                    explanation=result["error"] or "Execution unavailable",
                    metadata={
                        "runner_status": result["status"],
                        "execution_records": execution_records,
                        "tests_requested": total,
                        "tests_attempted": i + 1,
                        "tests_passed_before_failure": passed,
                        "failed_cases": failed_cases,
                    },
                )
            if result["success"] and compare_outputs(result["stdout"], expected_output):
                passed += 1
            else:
                if len(failed_cases) < 3:  # Limit failed case logging
                    failed_cases.append(
                        {
                            "test": i + 1,
                            "error": result.get("error") or "Output mismatch",
                            "expected": expected_output[:100] if expected_output else "",
                            "actual": result["stdout"][:100] if result["stdout"] else "",
                        }
                    )

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
            metadata={
                "execution_records": execution_records,
                "tests_requested": total,
                "tests_attempted": total,
                "tests_passed": passed,
                "failed_cases": failed_cases,
                "resource_outcome_policy": "confirmed-timeout-or-output-limit-is-incorrect/1",
            },
        )

    return score
