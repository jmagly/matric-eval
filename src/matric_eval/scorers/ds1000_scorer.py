"""
DS-1000 specialized code execution scorer.

Execution is unavailable until a dedicated DS-1000 image and dependency profile
are qualified. The standard-library Python profile cannot validate pandas,
NumPy, or other data-science dependencies, and this module never falls back to
host execution. The pure context extraction helper remains available.

Based on https://github.com/xlang-ai/DS-1000
"""

import re
from typing import Any

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from matric_eval.scorers.code_execution import extract_code


def extract_solution_for_context(code: str, exec_context: str) -> str:
    """
    Extract the appropriate solution code based on exec_context format.

    DS-1000 has two patterns for [insert] placement:
    1. Top-level: [insert] is not inside a function - use full code
    2. Inside function: [insert] is inside a function body - extract only function body

    Args:
        code: Model-generated code (may include imports, function def, etc.)
        exec_context: The exec_context template with [insert] marker

    Returns:
        Extracted solution appropriate for insertion at [insert]
    """
    # Check if [insert] is inside a function definition
    # Pattern: def funcname(...):\n[insert] or def funcname(...):\n    [insert]
    insert_in_function = re.search(r"def\s+\w+\s*\([^)]*\)\s*:\s*\n\s*\[insert\]", exec_context)

    if not insert_in_function:
        # [insert] is at top level, use full code
        return code

    # [insert] is inside a function, need to extract function body
    # Try to find a function definition in the model's output and extract its body

    # Look for function definitions in the code
    # Pattern: def funcname(...):\n    body
    func_match = re.search(
        r"def\s+\w+\s*\([^)]*\)\s*:\s*\n((?:[ \t]+[^\n]*\n?)+)", code, re.MULTILINE
    )

    if func_match:
        # Found a function, extract its body
        body = func_match.group(1)
        # The body is already indented, which is correct for [insert] inside a function
        return body

    # No function found, check if code already looks like a function body (indented)
    lines = code.split("\n")
    if lines and (lines[0].startswith("    ") or lines[0].startswith("\t")):
        # Already looks like function body
        return code

    # Fallback: indent the entire code as a function body
    # This handles cases where model outputs just the solution logic
    indented_lines = ["    " + line if line.strip() else line for line in lines]
    return "\n".join(indented_lines)


def execute_ds1000_test(
    code: str,
    code_context: str,
    timeout: int = 60,
) -> dict[str, Any]:
    """Refuse execution until a DS-1000 dependency profile is qualified.

    Arguments remain accepted for compatibility; no source is evaluated and no
    process is launched. A future qualified profile needs its own dependency,
    resource, isolation, and correctness validation before enabling this path.
    """
    return {
        "passed": False,
        "status": "unavailable",
        "error": "ds1000_profile_unqualified",
        "output": "",
        "provenance": {
            "profile": None,
            "required_profile": "ds1000",
            "reason": "ds1000_profile_unqualified",
            "cleanup": "not_created",
        },
    }


@scorer(metrics=[mean()])
def ds1000_scorer(timeout: int = 60) -> Scorer:
    """Return unscored observations until a DS-1000 runner profile is qualified.

    ``timeout`` remains an accepted compatibility argument, not authorization to
    run a data-science harness under the standard-library runner profile.
    """

    async def score(state: TaskState, target: Target) -> Score:
        code_context = (state.metadata or {}).get("code_context", "")
        if not code_context or "test_execution" not in code_context:
            return Score.unscored(
                reason="grader_failed",
                explanation="DS-1000 test harness unavailable",
                metadata={"runner_status": "test_harness_unavailable"},
            )
        result = execute_ds1000_test(
            extract_code(state.output.completion),
            code_context,
            timeout=timeout,
        )
        return Score.unscored(
            reason="grader_failed",
            explanation=result["error"],
            metadata={
                "runner_status": result["status"],
                "runner_error": result["error"],
                "execution_provenance": result["provenance"],
            },
        )

    return score
