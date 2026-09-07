"""
Tests for code execution scorer (matric_eval.scorers.code_execution).

Covers:
- Code extraction from markdown fences
- Code extraction without fences
- Isolated runner request forwarding and evidence preservation
- Observed failures versus unavailable execution
- Missing harness and timeout policy
- Scorer integration with Inspect AI
"""

import math
from unittest.mock import Mock, patch

import pytest
from inspect_ai.scorer import Target

from matric_eval.scorers.code_execution import (
    code_execution_scorer,
    extract_code,
    prepare_code,
    prepare_test_code,
    safe_execute,
)

# =============================================================================
# Code Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestExtractCode:
    """Tests for extract_code() function."""

    def test_extract_code_from_simple_markdown_fence(self) -> None:
        """Should extract code from simple markdown fence."""
        response = """```python
def hello():
    return "world"
```"""
        code = extract_code(response)
        assert code == 'def hello():\n    return "world"'

    def test_extract_code_from_fence_without_language(self) -> None:
        """Should extract code from fence without language tag."""
        response = """```
def add(a, b):
    return a + b
```"""
        code = extract_code(response)
        assert code == "def add(a, b):\n    return a + b"

    def test_extract_code_with_text_before_fence(self) -> None:
        """Should extract code even when text appears before fence."""
        response = """Here is the solution:

```python
def multiply(x, y):
    return x * y
```

This function multiplies two numbers."""
        code = extract_code(response)
        assert code == "def multiply(x, y):\n    return x * y"

    def test_extract_code_with_multiple_fences_uses_first(self) -> None:
        """Should extract code from first fence when multiple exist."""
        response = """```python
def first():
    return 1
```

And here's another one:

```python
def second():
    return 2
```"""
        code = extract_code(response)
        assert code == "def first():\n    return 1"

    def test_extract_code_without_fences(self) -> None:
        """Should return entire response when no fences present."""
        response = """def no_fence():
    return True"""
        code = extract_code(response)
        assert (
            code
            == """def no_fence():
    return True"""
        )

    def test_extract_code_strips_whitespace(self) -> None:
        """Should strip leading and trailing whitespace."""
        response = """

```python
def func():
    pass
```

        """
        code = extract_code(response)
        assert code == "def func():\n    pass"

    def test_extract_code_handles_empty_response(self) -> None:
        """Should return empty string for empty response."""
        code = extract_code("")
        assert code == ""

    def test_extract_code_handles_whitespace_only_response(self) -> None:
        """Should return empty string for whitespace-only response."""
        code = extract_code("   \n\n   \t   \n")
        assert code == ""

    def test_extract_code_preserves_indentation(self) -> None:
        """Should preserve code indentation within fence."""
        response = """```python
def outer():
    def inner():
        return 42
    return inner()
```"""
        code = extract_code(response)
        assert code == "def outer():\n    def inner():\n        return 42\n    return inner()"

    def test_extract_code_handles_backticks_in_code(self) -> None:
        """Should handle backticks within code (e.g., in strings)."""
        response = """```python
def func():
    s = "string with `backticks`"
    return s
```"""
        code = extract_code(response)
        assert "string with `backticks`" in code


# =============================================================================
# Safe Execution Tests
# =============================================================================


class TestPrepareTestCode:
    """Tests for benchmark-specific executable harness construction."""

    def test_humaneval_invokes_canonical_check_function(self) -> None:
        test_code = prepare_test_code(
            {
                "entry_point": "add_one",
                "test": "def check(candidate):\n    assert candidate(1) == 2",
            }
        )

        assert test_code.endswith("check(add_one)")
        assert "assert candidate(1) == 2" in test_code

    def test_mbpp_assertions_are_not_modified(self) -> None:
        test_code = "assert add(1, 2) == 3"

        assert prepare_test_code({"entry_point": "add", "test": test_code}) == test_code


class TestPrepareCode:
    """Tests for HumanEval body-only compatibility."""

    def test_rebuilds_body_only_completion_from_prompt(self) -> None:
        code = prepare_code(
            "return value + 1",
            {
                "entry_point": "add_one",
                "prompt": 'def add_one(value):\n    """Increment value."""',
            },
        )

        assert code.endswith("    return value + 1")
        assert code.startswith("def add_one(value):")

    def test_preserves_complete_function(self) -> None:
        response = "def add_one(value):\n    return value + 1"

        assert prepare_code(response, {"entry_point": "add_one", "prompt": "ignored"}) == response


def execution_result(status="passed"):
    return {
        "status": status,
        "stdout": "bounded stdout",
        "stderr": "bounded stderr",
        "error": None if status == "passed" else status,
        "provenance": {"profile": "python-restricted/1", "cleanup": "verified_absent"},
    }


@pytest.mark.parametrize(
    "status",
    [
        "passed",
        "incorrect",
        "timeout",
        "output_limit",
        "unavailable",
        "policy_denied",
        "infrastructure_error",
    ],
)
def test_safe_execute_forwards_harness_and_preserves_runner_evidence(status):
    native = execution_result(status)
    with patch("matric_eval.scorers.code_execution.execute_python", return_value=native) as runner:
        result = safe_execute("def candidate(): return 1", "assert candidate() == 1", timeout=7)
    runner.assert_called_once_with(
        "def candidate(): return 1\nassert candidate() == 1", stdin_input="", timeout=7
    )
    assert result["passed"] is (status == "passed")
    assert result["status"] == status
    assert result["provenance"] == native["provenance"]
    assert result["output"] == native["stdout"] + native["stderr"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        "passed",
        "incorrect",
        "timeout",
        "output_limit",
        "unavailable",
        "policy_denied",
        "infrastructure_error",
    ],
)
async def test_scorer_distinguishes_model_failure_from_unavailable_execution(status):
    state = Mock()
    state.output.completion = "```python\ndef add(a, b): return a + b\n```"
    state.metadata = {
        "test": "def check(candidate):\n    assert candidate(1, 2) == 3",
        "entry_point": "add",
    }
    native = execution_result(status)
    with patch("matric_eval.scorers.code_execution.execute_python", return_value=native) as runner:
        result = await code_execution_scorer(timeout=7)(state, Target("unused"))
    runner.assert_called_once_with(
        "def add(a, b): return a + b\ndef check(candidate):\n    assert candidate(1, 2) == 3\n\ncheck(add)",
        stdin_input="",
        timeout=7,
    )
    if status in {"unavailable", "policy_denied", "infrastructure_error"}:
        assert math.isnan(result.value)
        assert result.reason == "grader_failed"
    else:
        assert result.value == (1.0 if status == "passed" else 0.0)
    assert result.metadata["runner_status"] == status
    assert result.metadata["execution_provenance"] == native["provenance"]
    assert result.metadata["runner_error"] == native["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [None, {}, {"test": "   "}])
async def test_missing_harness_is_unscored_without_execution(metadata):
    state = Mock()
    state.output.completion = "print('not a test')"
    state.metadata = metadata
    with patch("matric_eval.scorers.code_execution.execute_python") as runner:
        result = await code_execution_scorer()(state, Target("unused"))
    runner.assert_not_called()
    assert math.isnan(result.value)
    assert result.reason == "grader_failed"
    assert result.metadata["runner_status"] == "test_harness_unavailable"


@pytest.mark.asyncio
async def test_empty_response_with_valid_harness_is_incorrect_without_execution():
    state = Mock()
    state.output.completion = ""
    state.metadata = {"test": "assert candidate() == 1"}
    with patch("matric_eval.scorers.code_execution.execute_python") as runner:
        result = await code_execution_scorer()(state, Target("unused"))
    runner.assert_not_called()
    assert result.value == 0.0


@pytest.mark.asyncio
async def test_body_only_humaneval_completion_and_check_reach_runner_together():
    state = Mock()
    state.output.completion = "return value + 1"
    state.metadata = {
        "entry_point": "add_one",
        "prompt": 'def add_one(value):\n    """Increment value."""',
        "test": "def check(candidate):\n    assert candidate(1) == 2",
    }
    with patch(
        "matric_eval.scorers.code_execution.execute_python", return_value=execution_result()
    ) as runner:
        result = await code_execution_scorer()(state, Target("unused"))
    runner.assert_called_once_with(
        'def add_one(value):\n    """Increment value."""\n    return value + 1\n'
        "def check(candidate):\n    assert candidate(1) == 2\n\ncheck(add_one)",
        stdin_input="",
        timeout=30,
    )
    assert result.value == 1.0
