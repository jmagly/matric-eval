"""Unit tests for I/O execution scorer (LiveCodeBench)."""

from unittest.mock import MagicMock, patch

import pytest

from matric_eval.scorers.io_execution import (
    compare_outputs,
    io_execute,
    io_execution_scorer,
    normalize_output,
)


@pytest.mark.unit
class TestNormalizeOutput:
    """Tests for normalize_output function."""

    def test_normalize_empty(self) -> None:
        """Empty string returns empty string."""
        assert normalize_output("") == ""

    def test_normalize_none(self) -> None:
        """None returns empty string."""
        assert normalize_output(None) == ""

    def test_normalize_strips_trailing_whitespace(self) -> None:
        """Trailing whitespace on lines is stripped."""
        assert normalize_output("hello   \nworld  ") == "hello\nworld"

    def test_normalize_removes_trailing_empty_lines(self) -> None:
        """Trailing empty lines are removed."""
        assert normalize_output("hello\n\n\n") == "hello"

    def test_normalize_crlf_to_lf(self) -> None:
        """CRLF line endings are converted to LF."""
        assert normalize_output("hello\r\nworld\r\n") == "hello\nworld"

    def test_normalize_cr_to_lf(self) -> None:
        """CR line endings are converted to LF."""
        assert normalize_output("hello\rworld\r") == "hello\nworld"

    def test_normalize_preserves_internal_newlines(self) -> None:
        """Internal empty lines are preserved."""
        assert normalize_output("hello\n\nworld") == "hello\n\nworld"


@pytest.mark.unit
class TestCompareOutputs:
    """Tests for compare_outputs function."""

    def test_compare_identical(self) -> None:
        """Identical strings match."""
        assert compare_outputs("hello", "hello") is True

    def test_compare_whitespace_difference(self) -> None:
        """Trailing whitespace differences are ignored."""
        assert compare_outputs("hello  ", "hello") is True
        assert compare_outputs("hello\n", "hello") is True

    def test_compare_newline_ending_difference(self) -> None:
        """Trailing newlines are normalized."""
        assert compare_outputs("hello\n\n", "hello") is True

    def test_compare_crlf_vs_lf(self) -> None:
        """Different line endings are normalized."""
        assert compare_outputs("hello\r\nworld", "hello\nworld") is True

    def test_compare_different(self) -> None:
        """Different content returns False."""
        assert compare_outputs("hello", "world") is False

    def test_compare_empty(self) -> None:
        """Empty strings match."""
        assert compare_outputs("", "") is True


@pytest.mark.unit
class TestIoExecute:
    """Tests for io_execute function."""

    def test_execute_simple_print(self) -> None:
        """Simple print statement produces stdout."""
        code = 'print("hello")'
        result = io_execute(code, "")
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_execute_with_stdin(self) -> None:
        """Code can read from stdin."""
        code = 'x = input(); print(f"got: {x}")'
        result = io_execute(code, "test_input")
        assert result["success"] is True
        assert "got: test_input" in result["stdout"]

    def test_execute_multiline_input(self) -> None:
        """Code can read multiple lines from stdin."""
        code = 'a = input(); b = input(); print(a + b)'
        result = io_execute(code, "hello\nworld")
        assert result["success"] is True
        assert "helloworld" in result["stdout"]

    def test_execute_syntax_error(self) -> None:
        """Syntax errors are caught and reported."""
        code = 'print("unclosed'
        result = io_execute(code, "")
        assert result["success"] is False
        assert result["error"] is not None

    def test_execute_runtime_error(self) -> None:
        """Runtime errors are caught and reported."""
        code = 'x = 1 / 0'
        result = io_execute(code, "")
        assert result["success"] is False
        assert result["error"] is not None

    def test_execute_timeout(self) -> None:
        """Infinite loops are timed out."""
        code = 'while True: pass'
        result = io_execute(code, "", timeout=1)
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    def test_execute_empty_code(self) -> None:
        """Empty code executes successfully with no output."""
        result = io_execute("", "")
        assert result["success"] is True
        assert result["stdout"] == ""


@pytest.mark.unit
class TestIoExecutionScorer:
    """Tests for io_execution_scorer."""

    @pytest.mark.asyncio
    async def test_scorer_returns_scorer_function(self) -> None:
        """scorer() returns a callable."""
        scorer = io_execution_scorer()
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_scorer_passes_all_tests(self) -> None:
        """Scorer returns 1.0 when all tests pass."""
        scorer = io_execution_scorer()

        # Create mock state
        state = MagicMock()
        state.output.completion = 'print(input())'
        state.metadata = {
            "public_test_cases": [
                {"input": "hello", "output": "hello\n"},
                {"input": "world", "output": "world\n"},
            ],
            "private_test_cases": [],
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0
        assert "All" in result.explanation or "passed" in result.explanation

    @pytest.mark.asyncio
    async def test_scorer_partial_pass(self) -> None:
        """Scorer returns partial score when some tests pass."""
        scorer = io_execution_scorer()

        # Create mock state with code that only works for certain inputs
        state = MagicMock()
        state.output.completion = 'x = input(); print("hello" if x == "hello" else "wrong")'
        state.metadata = {
            "public_test_cases": [
                {"input": "hello", "output": "hello\n"},
                {"input": "world", "output": "world\n"},
            ],
            "private_test_cases": [],
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 0.5  # 1 of 2 tests pass

    @pytest.mark.asyncio
    async def test_scorer_no_code(self) -> None:
        """Scorer returns 0.0 when no code found."""
        scorer = io_execution_scorer()

        state = MagicMock()
        state.output.completion = ""
        state.metadata = {"public_test_cases": [{"input": "", "output": ""}]}

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 0.0
        assert "No code" in result.explanation

    @pytest.mark.asyncio
    async def test_scorer_no_tests(self) -> None:
        """Scorer returns 0.0 when no test cases available."""
        scorer = io_execution_scorer()

        state = MagicMock()
        state.output.completion = 'print("hello")'
        state.metadata = {
            "public_test_cases": [],
            "private_test_cases": [],
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 0.0
        assert "No test" in result.explanation

    @pytest.mark.asyncio
    async def test_scorer_extracts_code_from_markdown(self) -> None:
        """Scorer extracts code from markdown fences."""
        scorer = io_execution_scorer()

        state = MagicMock()
        state.output.completion = '```python\nprint(input())\n```'
        state.metadata = {
            "public_test_cases": [
                {"input": "test", "output": "test\n"},
            ],
            "private_test_cases": [],
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0


@pytest.mark.unit
class TestIoExecutionScorerRegressions:
    """Regression tests for I/O execution scorer."""

    @pytest.mark.asyncio
    async def test_regression_competitive_programming_format(self) -> None:
        """
        REGRESSION: Competitive programming style stdin/stdout should work.

        LiveCodeBench problems often have multiple lines of input with
        specific output format.
        """
        scorer = io_execution_scorer()

        # Typical competitive programming problem: sum N numbers
        code = '''
n = int(input())
nums = list(map(int, input().split()))
print(sum(nums))
'''

        state = MagicMock()
        state.output.completion = code
        state.metadata = {
            "public_test_cases": [
                {"input": "3\n1 2 3", "output": "6\n"},
                {"input": "5\n10 20 30 40 50", "output": "150\n"},
            ],
            "private_test_cases": [],
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0, f"Competitive programming format should work: {result.explanation}"

    @pytest.mark.asyncio
    async def test_regression_output_normalization(self) -> None:
        """
        REGRESSION: Output comparison should be normalized.

        Model might produce "6" while expected is "6\n" - should match.
        """
        scorer = io_execution_scorer()

        # Code that doesn't add trailing newline
        code = 'print(6, end="")'

        state = MagicMock()
        state.output.completion = code
        state.metadata = {
            "public_test_cases": [
                {"input": "", "output": "6\n"},  # Expected has newline
            ],
            "private_test_cases": [],
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0, f"Output normalization should work: {result.explanation}"
