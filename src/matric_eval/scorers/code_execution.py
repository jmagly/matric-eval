"""
Code execution scorer for HumanEval and MBPP benchmarks.

Provides safe code execution with timeout, memory limits, and sandboxing.
Extracts code from markdown fences and validates against test cases.
"""

import re
from typing import Any

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from matric_eval.scorers.isolated_execution import execute_python


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
        r"^.*?### BEGIN SOLUTION\s*\n?",  # DS-1000 begin marker
        r"^.*?<code>\s*\n?",  # DS-1000 code tag
        r"\n?### END SOLUTION.*$",  # DS-1000 end marker with ###
        r"\n?END SOLUTION.*$",  # DS-1000 end marker without ###
        r"\n?</code>.*$",  # DS-1000 closing code tag
        r"^# Solution\s*\n?",  # Common solution header
    ]

    for pattern in markers_to_remove:
        code = re.sub(pattern, "", code, flags=re.DOTALL | re.IGNORECASE)

    return code.strip()


def safe_execute(code: str, test_code: str, timeout: int = 30) -> dict[str, Any]:
    """Execute the combined harness through the configured bounded Python runner.

    The compatibility ``passed`` flag never distinguishes incorrect code from
    unavailable execution; consumers must use ``status`` before assigning grades.
    There is no host-process fallback when isolation is unavailable.
    """
    result = execute_python(code + "\n" + test_code, stdin_input="", timeout=timeout)
    return {
        **result,
        "passed": result["status"] == "passed",
        "output": result["stdout"] + result["stderr"],
    }


def prepare_test_code(metadata: dict[str, Any] | None) -> str:
    """Build executable tests, including the canonical HumanEval check call."""
    if not metadata:
        return ""

    test_code = str(metadata.get("test", ""))
    entry_point = metadata.get("entry_point")
    if entry_point and re.search(r"^\s*def\s+check\s*\(", test_code, re.MULTILINE):
        test_code = f"{test_code.rstrip()}\n\ncheck({entry_point})"
    return test_code


def prepare_code(response: str, metadata: dict[str, Any] | None) -> str:
    """Extract generated code and rebuild HumanEval body-only completions."""
    code = extract_code(response)
    if not metadata:
        return code

    entry_point = metadata.get("entry_point")
    prompt = metadata.get("prompt")
    if (
        not entry_point
        or not prompt
        or re.search(rf"\bdef\s+{re.escape(str(entry_point))}\s*\(", code)
    ):
        return code

    indented = "\n".join(f"    {line}" if line.strip() else line for line in code.splitlines())
    return f"{str(prompt).rstrip()}\n{indented}"


@scorer(metrics=[mean()])
def code_execution_scorer(timeout: int = 30) -> Scorer:
    """
    Create Inspect AI scorer for code execution validation.

    Extracts code from model response, executes against test cases,
    and returns score based on test results.

    Args:
        timeout: Maximum execution time per test in seconds (0 < timeout <= 30)

    Returns:
        Scorer function compatible with Inspect AI

    Example:
        >>> task = Task(
        ...     dataset=samples,
        ...     solver=[generate()],
        ...     scorer=code_execution_scorer(timeout=30)
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
        code = prepare_code(response, state.metadata)

        # Get test code from state metadata (comes from Sample)
        test_code = prepare_test_code(state.metadata)

        if not test_code.strip():
            return Score.unscored(
                reason="grader_failed",
                explanation="Test harness unavailable",
                metadata={"runner_status": "test_harness_unavailable"},
            )
        if not code.strip():
            return Score(value=0.0, explanation="No code found in response")

        result = safe_execute(code, test_code, timeout=timeout)
        metadata = {
            "runner_status": result["status"],
            "runner_error": result["error"],
            "execution_provenance": result["provenance"],
            "resource_outcome_policy": "confirmed-timeout-or-output-limit-is-incorrect/1",
        }
        if result["status"] not in {"passed", "incorrect", "timeout", "output_limit"}:
            return Score.unscored(
                reason="grader_failed",
                explanation=result["error"] or "Execution unavailable",
                metadata=metadata,
            )
        return Score(
            value=1.0 if result["passed"] else 0.0,
            explanation="" if result["passed"] else result["error"] or "Test execution failed",
            metadata=metadata,
        )

    return score
