"""Unit tests for I/O execution scorer (LiveCodeBench)."""

import math
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


def execution_result(status="passed", stdout="hello\n"):
    return {
        "status": status,
        "stdout": stdout,
        "stderr": "",
        "error": None if status == "passed" else status,
        "provenance": {"profile": "python-restricted/1", "cleanup": "verified_absent"},
    }


def state_for_tests(code="print(input())"):
    state = MagicMock()
    state.output.completion = code
    state.metadata = {
        "public_test_cases": [{"input": "hello", "output": "hello\n"}],
        "private_test_cases": [{"input": "world", "output": "world\n"}],
    }
    return state


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
def test_io_execute_forwards_input_and_preserves_runner_evidence(status):
    native = execution_result(status)
    with patch("matric_eval.scorers.io_execution.execute_python", return_value=native) as runner:
        result = io_execute("print(input())", "hello", timeout=7)
    runner.assert_called_once_with("print(input())", stdin_input="hello", timeout=7)
    assert result["success"] is (status == "passed")
    assert result["status"] == status
    assert result["provenance"] == native["provenance"]
    assert result["stdout"] == native["stdout"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("second", "expected"), [("world\n", 1.0), ("wrong\n", 0.5)])
async def test_io_scorer_keeps_test_fraction_and_normalized_comparison(second, expected):
    with patch(
        "matric_eval.scorers.io_execution.execute_python",
        side_effect=[
            execution_result(stdout="hello  \r\n"),
            execution_result(stdout=second),
        ],
    ) as runner:
        result = await io_execution_scorer()(
            state_for_tests("```python\nprint(input())\n```"), MagicMock()
        )
    assert result.value == expected
    assert runner.call_count == 2
    assert [call.kwargs["stdin_input"] for call in runner.call_args_list] == ["hello", "world"]
    assert all(call.args[0] == "print(input())" for call in runner.call_args_list)
    assert len(result.metadata["execution_records"]) == 2
    assert result.metadata["tests_requested"] == result.metadata["tests_attempted"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["incorrect", "timeout", "output_limit"])
async def test_confirmed_execution_failure_is_observed_incorrect(status):
    with patch(
        "matric_eval.scorers.io_execution.execute_python",
        side_effect=[
            execution_result(),
            execution_result(status),
        ],
    ):
        result = await io_execution_scorer()(state_for_tests(), MagicMock())
    assert result.value == 0.5
    assert result.metadata["failed_cases"][0]["error"] == status
    assert result.metadata["execution_records"][1]["runner_status"] == status


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["unavailable", "policy_denied", "infrastructure_error"])
async def test_any_unavailable_test_makes_entire_sample_unscored(status):
    state = state_for_tests()
    state.metadata["private_test_cases"].append({"input": "not run", "output": "not run"})
    with patch(
        "matric_eval.scorers.io_execution.execute_python",
        side_effect=[
            execution_result(),
            execution_result(status),
        ],
    ) as runner:
        result = await io_execution_scorer()(state, MagicMock())
    assert math.isnan(result.value)
    assert result.reason == "grader_failed"
    assert runner.call_count == 2
    assert result.metadata["tests_requested"] == 3
    assert result.metadata["tests_attempted"] == 2
    assert result.metadata["tests_passed_before_failure"] == 1
    assert result.metadata["runner_status"] == status
    assert (
        result.metadata["execution_records"][1]["execution_provenance"]["cleanup"]
        == "verified_absent"
    )


@pytest.mark.asyncio
async def test_missing_tests_is_unscored_without_execution():
    state = state_for_tests()
    state.metadata = {}
    with patch("matric_eval.scorers.io_execution.execute_python") as runner:
        result = await io_execution_scorer()(state, MagicMock())
    runner.assert_not_called()
    assert math.isnan(result.value)
    assert result.reason == "grader_failed"


@pytest.mark.asyncio
async def test_empty_response_with_tests_is_observed_incorrect():
    with patch("matric_eval.scorers.io_execution.execute_python") as runner:
        result = await io_execution_scorer()(state_for_tests(""), MagicMock())
    runner.assert_not_called()
    assert result.value == 0.0


@pytest.mark.asyncio
async def test_mismatch_diagnostics_are_bounded():
    state = state_for_tests()
    state.metadata = {"public_test_cases": [{"input": "", "output": "a" * 1000}] * 5}
    with patch(
        "matric_eval.scorers.io_execution.execute_python",
        return_value=execution_result(stdout="b" * 1000),
    ):
        result = await io_execution_scorer()(state, MagicMock())
    assert result.value == 0.0
    failures = result.metadata["failed_cases"]
    assert len(failures) == 3
    assert all(len(item["expected"]) == len(item["actual"]) == 100 for item in failures)
