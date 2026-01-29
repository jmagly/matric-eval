"""
DS-1000 specialized code execution scorer.

Uses the code_context test harnesses from the DS-1000 dataset
to validate model-generated data science code.

Based on https://github.com/xlang-ai/DS-1000
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path
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
    insert_in_function = re.search(
        r'def\s+\w+\s*\([^)]*\)\s*:\s*\n\s*\[insert\]',
        exec_context
    )

    if not insert_in_function:
        # [insert] is at top level, use full code
        return code

    # [insert] is inside a function, need to extract function body
    # Try to find a function definition in the model's output and extract its body

    # Look for function definitions in the code
    # Pattern: def funcname(...):\n    body
    func_match = re.search(
        r'def\s+\w+\s*\([^)]*\)\s*:\s*\n((?:[ \t]+[^\n]*\n?)+)',
        code,
        re.MULTILINE
    )

    if func_match:
        # Found a function, extract its body
        body = func_match.group(1)
        # The body is already indented, which is correct for [insert] inside a function
        return body

    # No function found, check if code already looks like a function body (indented)
    lines = code.split('\n')
    if lines and (lines[0].startswith('    ') or lines[0].startswith('\t')):
        # Already looks like function body
        return code

    # Fallback: indent the entire code as a function body
    # This handles cases where model outputs just the solution logic
    indented_lines = ['    ' + line if line.strip() else line for line in lines]
    return '\n'.join(indented_lines)


def execute_ds1000_test(
    code: str,
    code_context: str,
    timeout: int = 60,
) -> dict[str, Any]:
    """
    Execute DS-1000 test using the dataset's code_context test harness.

    The code_context contains:
    - generate_test_case(): Creates test inputs and expected outputs
    - exec_test(): Validates result against expected
    - test_execution(): Main test runner that injects solution at [insert]

    Args:
        code: Model-generated solution code
        code_context: DS-1000 code_context containing test infrastructure
        timeout: Maximum execution time in seconds (default: 60)

    Returns:
        Dictionary with keys:
        - passed: bool indicating if tests passed
        - error: str or None with error message if failed
        - output: str with any captured output
    """
    # Build the test script
    # The code_context has test_execution(solution: str) that:
    # 1. Injects solution at [insert] marker
    # 2. Runs test cases
    # 3. Asserts results

    # Extract exec_context from code_context to understand [insert] placement
    # DS-1000 uses triple-quoted strings: exec_context = r""" ... """
    exec_context_match = re.search(
        r'exec_context\s*=\s*r?(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')',
        code_context,
        re.DOTALL
    )
    if exec_context_match:
        # Match group 1 for """ or group 2 for '''
        exec_context = exec_context_match.group(1) or exec_context_match.group(2) or ""
    else:
        exec_context = ""

    # Extract appropriate solution based on [insert] context
    solution = extract_solution_for_context(code, exec_context)

    # Use base64 encoding to safely embed solution code
    # This avoids all escaping issues with quotes, backslashes, etc.
    import base64
    encoded_code = base64.b64encode(solution.encode()).decode()

    test_script = f'''
import base64
{code_context}

# Run the test with the model's solution
solution = base64.b64decode("{encoded_code}").decode()

try:
    test_execution(solution)
    print("PASS")
except AssertionError as e:
    print(f"FAIL: AssertionError - {{e}}")
except Exception as e:
    print(f"FAIL: {{type(e).__name__}} - {{e}}")
'''

    try:
        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            timeout=timeout,
            text=True,
        )

        output = result.stdout + result.stderr

        if result.returncode == 0 and "PASS" in result.stdout:
            return {
                "passed": True,
                "error": None,
                "output": output,
            }
        else:
            # Extract error message
            error_lines = [
                line for line in output.split("\n")
                if line.startswith("FAIL:") or "Error" in line or "error" in line
            ]
            error_msg = error_lines[0] if error_lines else "Test execution failed"

            return {
                "passed": False,
                "error": error_msg,
                "output": output,
            }

    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "error": f"Execution timeout after {timeout} seconds",
            "output": "",
        }
    except Exception as e:
        return {
            "passed": False,
            "error": f"Execution error: {str(e)}",
            "output": "",
        }


@scorer(metrics=[mean()])
def ds1000_scorer(timeout: int = 60) -> Scorer:
    """
    Create Inspect AI scorer for DS-1000 data science problems.

    Uses the code_context test harnesses from the DS-1000 dataset
    to validate model-generated code. The test harnesses include
    sophisticated comparison logic for pandas DataFrames, numpy arrays,
    and other data science objects.

    Args:
        timeout: Maximum execution time per problem in seconds (default: 60)
                 DS-1000 problems may require more time for data operations

    Returns:
        Scorer function compatible with Inspect AI

    Example:
        >>> task = Task(
        ...     dataset=ds1000_samples,
        ...     solver=[generate()],
        ...     scorer=ds1000_scorer(timeout=120)
        ... )
    """

    async def score(state: TaskState, target: Target) -> Score:
        """
        Score a model response using DS-1000 test harness.

        Args:
            state: Current task state with model output and metadata
            target: Target (reference code, not used directly)

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

        # Get code_context from metadata
        metadata = state.metadata or {}
        code_context = metadata.get("code_context", "")

        if not code_context:
            return Score(
                value=0.0,
                explanation="No code_context available for testing",
            )

        # Check if code_context has the required test_execution function
        if "test_execution" not in code_context:
            return Score(
                value=0.0,
                explanation="code_context missing test_execution function",
            )

        # Execute the test
        result = execute_ds1000_test(code, code_context, timeout=timeout)

        if result["passed"]:
            return Score(
                value=1.0,
                explanation="All tests passed",
            )
        else:
            return Score(
                value=0.0,
                explanation=result["error"] or "Test execution failed",
            )

    return score
