"""
Tests for code execution scorer (matric_eval.scorers.code_execution).

Covers:
- Code extraction from markdown fences
- Code extraction without fences
- Safe code execution with timeout
- Test execution and result capture
- Error handling (syntax errors, runtime errors, timeouts)
- Scorer integration with Inspect AI
"""

import subprocess
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest
from inspect_ai.scorer import Score, Target

from matric_eval.scorers.code_execution import (
    code_execution_scorer,
    extract_code,
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
        assert code == """def no_fence():
    return True"""

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
        assert 'string with `backticks`' in code


# =============================================================================
# Safe Execution Tests
# =============================================================================


@pytest.mark.unit
class TestSafeExecute:
    """Tests for safe_execute() function."""

    def test_safe_execute_passing_code(self) -> None:
        """Should return success for code that passes tests."""
        code = """def add(a, b):
    return a + b"""
        test_code = """
assert add(2, 3) == 5
assert add(0, 0) == 0
assert add(-1, 1) == 0
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is True
        assert result["error"] is None

    def test_safe_execute_failing_code(self) -> None:
        """Should return failure for code that fails tests."""
        code = """def add(a, b):
    return a - b  # Wrong operation!"""
        test_code = """
assert add(2, 3) == 5
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is False
        assert result["error"] is not None
        assert "AssertionError" in result["error"]

    def test_safe_execute_syntax_error(self) -> None:
        """Should return failure for code with syntax errors."""
        code = """def broken(
    return 42  # Missing closing paren"""
        test_code = """
assert broken() == 42
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is False
        assert result["error"] is not None
        assert "SyntaxError" in result["error"]

    def test_safe_execute_runtime_error(self) -> None:
        """Should return failure for code with runtime errors."""
        code = """def divide(a, b):
    return a / b"""
        test_code = """
assert divide(10, 0) == 0
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is False
        assert result["error"] is not None
        assert "ZeroDivisionError" in result["error"]

    def test_safe_execute_timeout(self) -> None:
        """Should timeout for code that runs too long."""
        code = """def infinite_loop():
    while True:
        pass"""
        test_code = """
infinite_loop()
"""
        result = safe_execute(code, test_code, timeout=1)
        assert result["passed"] is False
        assert result["error"] is not None
        assert "timeout" in result["error"].lower()

    def test_safe_execute_captures_stdout(self) -> None:
        """Should capture stdout from code execution."""
        code = """def greet():
    print("Hello, World!")
    return True"""
        test_code = """
assert greet() == True
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is True
        assert "Hello, World!" in result["output"]

    def test_safe_execute_captures_stderr(self) -> None:
        """Should capture stderr from code execution."""
        code = """import sys
def warn():
    print("Warning!", file=sys.stderr)
    return True"""
        test_code = """
assert warn() == True
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is True
        # stderr should be in error or output
        assert "Warning!" in (result["output"] + (result["error"] or ""))

    def test_safe_execute_respects_custom_timeout(self) -> None:
        """Should respect custom timeout parameter."""
        code = """import time
def slow():
    time.sleep(0.5)
    return True"""
        test_code = """
assert slow() == True
"""
        # Should pass with 2 second timeout
        result = safe_execute(code, test_code, timeout=2)
        assert result["passed"] is True

        # Should timeout with 0.1 second timeout
        result = safe_execute(code, test_code, timeout=0.1)
        assert result["passed"] is False
        assert "timeout" in result["error"].lower()

    def test_safe_execute_undefined_function_error(self) -> None:
        """Should return failure when calling undefined function."""
        code = """# No function defined"""
        test_code = """
assert undefined_func() == 42
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is False
        assert result["error"] is not None
        assert "NameError" in result["error"]

    def test_safe_execute_multiple_test_cases(self) -> None:
        """Should handle multiple test assertions."""
        code = """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)"""
        test_code = """
assert fibonacci(0) == 0
assert fibonacci(1) == 1
assert fibonacci(5) == 5
assert fibonacci(10) == 55
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is True

    def test_safe_execute_imports_in_code(self) -> None:
        """Should allow imports in code."""
        code = """import math
def circle_area(radius):
    return math.pi * radius ** 2"""
        test_code = """
result = circle_area(1)
assert abs(result - 3.14159) < 0.001
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is True

    def test_safe_execute_empty_code(self) -> None:
        """Should fail when code is empty but tests expect functionality."""
        code = ""
        test_code = """
assert add(1, 1) == 2
"""
        result = safe_execute(code, test_code, timeout=5)
        assert result["passed"] is False

    def test_safe_execute_empty_tests(self) -> None:
        """Should pass when tests are empty (no assertions)."""
        code = """def noop():
    pass"""
        test_code = ""
        result = safe_execute(code, test_code, timeout=5)
        # No assertions = no failures = pass
        assert result["passed"] is True


# =============================================================================
# Scorer Integration Tests
# =============================================================================


@pytest.mark.unit
class TestCodeExecutionScorer:
    """Tests for code_execution_scorer() Inspect AI scorer."""

    def test_scorer_returns_callable(self) -> None:
        """Should return a callable scorer."""
        scorer = code_execution_scorer()
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_scorer_passes_valid_code(self) -> None:
        """Should score 1.0 for valid code that passes tests."""
        scorer = code_execution_scorer()

        # Mock state with code response and metadata
        state = Mock()
        state.output.completion = """```python
def add(a, b):
    return a + b
```"""
        state.metadata = {
            "test": """
assert add(2, 3) == 5
assert add(0, 0) == 0
"""
        }

        # Target is just a placeholder
        target = Target(target="")

        score = await scorer(state, target)
        assert isinstance(score, Score)
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_scorer_fails_invalid_code(self) -> None:
        """Should score 0.0 for code that fails tests."""
        scorer = code_execution_scorer()

        state = Mock()
        state.output.completion = """```python
def add(a, b):
    return a - b  # Wrong!
```"""
        state.metadata = {
            "test": """
assert add(2, 3) == 5
"""
        }

        target = Target(target="")

        score = await scorer(state, target)
        assert isinstance(score, Score)
        assert score.value == 0.0
        assert score.explanation is not None
        assert len(score.explanation) > 0

    @pytest.mark.asyncio
    async def test_scorer_includes_error_in_explanation(self) -> None:
        """Should include error details in explanation for failures."""
        scorer = code_execution_scorer()

        state = Mock()
        state.output.completion = """def broken():
    return 1/0  # Division by zero"""
        state.metadata = {
            "test": """
assert broken() == 0
"""
        }

        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 0.0
        assert "ZeroDivisionError" in score.explanation

    @pytest.mark.asyncio
    async def test_scorer_handles_timeout(self) -> None:
        """Should score 0.0 and explain timeout errors."""
        scorer = code_execution_scorer()

        state = Mock()
        state.output.completion = """def infinite():
    while True:
        pass"""
        state.metadata = {
            "test": """
infinite()
"""
        }

        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 0.0
        assert "timeout" in score.explanation.lower()

    @pytest.mark.asyncio
    async def test_scorer_extracts_code_from_markdown(self) -> None:
        """Should automatically extract code from markdown fences."""
        scorer = code_execution_scorer()

        state = Mock()
        state.output.completion = """Here's the solution:

```python
def multiply(x, y):
    return x * y
```

This multiplies two numbers."""
        state.metadata = {
            "test": """
assert multiply(3, 4) == 12
"""
        }

        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_scorer_handles_missing_test_metadata(self) -> None:
        """Should handle gracefully when test metadata is missing."""
        scorer = code_execution_scorer()

        state = Mock()
        state.output.completion = """def func():
    return True"""
        state.metadata = {}

        target = Target(target="")

        score = await scorer(state, target)
        # Should pass (no failures)
        assert isinstance(score, Score)
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_scorer_handles_none_metadata(self) -> None:
        """Should handle gracefully when metadata is None."""
        scorer = code_execution_scorer()

        state = Mock()
        state.output.completion = """def func():
    return True"""
        state.metadata = None

        target = Target(target="")

        score = await scorer(state, target)
        # Should pass (no failures)
        assert isinstance(score, Score)
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_scorer_with_custom_timeout(self) -> None:
        """Should respect custom timeout parameter."""
        scorer = code_execution_scorer(timeout=2)

        state = Mock()
        state.output.completion = """import time
def slow():
    time.sleep(0.5)
    return True"""
        state.metadata = {
            "test": """
assert slow() == True
"""
        }

        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 1.0

    @pytest.mark.asyncio
    async def test_scorer_explanation_empty_on_success(self) -> None:
        """Should have empty explanation on success."""
        scorer = code_execution_scorer()

        state = Mock()
        state.output.completion = """def simple():
    return 42"""
        state.metadata = {
            "test": """
assert simple() == 42
"""
        }

        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 1.0
        assert score.explanation == ""

    @pytest.mark.asyncio
    async def test_scorer_with_output(self) -> None:
        """Should handle code that produces output."""
        scorer = code_execution_scorer()

        state = Mock()
        state.output.completion = """def debug():
    print("Debug output")
    return True"""
        state.metadata = {
            "test": """
assert debug() == True
"""
        }

        target = Target(target="")

        score = await scorer(state, target)
        assert score.value == 1.0
