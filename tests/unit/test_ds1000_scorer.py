"""DS-1000 fails closed without a qualified dependency profile."""

import math
from unittest.mock import MagicMock, patch

import pytest

from matric_eval.scorers.ds1000_scorer import (
    ds1000_scorer,
    execute_ds1000_test,
    extract_solution_for_context,
)


@pytest.mark.parametrize("code", ["print('PASS')", "while True: pass", "import pandas", ""])
def test_unqualified_profile_never_launches_host_execution(code):
    with patch("subprocess.Popen") as launch:
        result = execute_ds1000_test(code, "def test_execution(solution): pass", timeout=120)
    launch.assert_not_called()
    assert result["passed"] is False
    assert result["status"] == "unavailable"
    assert result["error"] == "ds1000_profile_unqualified"
    assert result["output"] == ""
    assert result["provenance"] == {
        "profile": None,
        "required_profile": "ds1000",
        "reason": "ds1000_profile_unqualified",
        "cleanup": "not_created",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["```python\nimport pandas\n```", "", "invalid python"])
async def test_unqualified_profile_is_unscored_for_every_response(code):
    state = MagicMock()
    state.output.completion = code
    state.metadata = {"code_context": "def test_execution(solution): pass"}
    with patch("subprocess.Popen") as launch:
        result = await ds1000_scorer()(state, MagicMock())
    launch.assert_not_called()
    assert math.isnan(result.value)
    assert result.reason == "grader_failed"
    assert result.metadata["runner_status"] == "unavailable"
    assert result.metadata["runner_error"] == "ds1000_profile_unqualified"
    assert result.metadata["execution_provenance"]["required_profile"] == "ds1000"


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [None, {}, {"code_context": "no callable harness"}])
async def test_missing_harness_stays_unscored(metadata):
    state = MagicMock()
    state.output.completion = "print(1)"
    state.metadata = metadata
    with patch("matric_eval.scorers.ds1000_scorer.execute_ds1000_test") as execute:
        result = await ds1000_scorer()(state, MagicMock())
    execute.assert_not_called()
    assert math.isnan(result.value)
    assert result.reason == "grader_failed"
    assert result.metadata["runner_status"] == "test_harness_unavailable"


@pytest.mark.unit
class TestExtractSolutionForContext:
    """Tests for extract_solution_for_context function."""

    def test_top_level_insert_uses_full_code(self) -> None:
        """When [insert] is at top level, use full code."""
        exec_context = """
import pandas as pd
df = test_input
[insert]
"""
        code = "result = df.sum()"

        result = extract_solution_for_context(code, exec_context)
        assert result == code

    def test_insert_inside_function_extracts_body(self) -> None:
        """When [insert] is inside function, extract function body."""
        exec_context = """
import pandas as pd
def f(df):
[insert]
result = f(df)
"""
        # Model outputs full function
        code = """import pandas as pd

def f(df):
    total = sum(df)
    return total

result = f([1,2,3])"""

        result = extract_solution_for_context(code, exec_context)
        # Should extract just the function body with indentation
        assert "    total = sum(df)" in result
        assert "    return total" in result
        assert "import pandas" not in result
        assert "def f(" not in result

    def test_insert_inside_function_preserves_indentation(self) -> None:
        """Extracted function body should preserve indentation."""
        exec_context = """
def f(x):
[insert]
"""
        code = """def f(x):
    if x > 0:
        return x * 2
    else:
        return x"""

        result = extract_solution_for_context(code, exec_context)
        # Body lines should be indented - check raw result without strip
        lines = result.split("\n")
        # Filter out empty lines and check non-empty lines are indented
        non_empty_lines = [line for line in lines if line.strip()]
        assert len(non_empty_lines) > 0
        assert all(line.startswith("    ") for line in non_empty_lines)

    def test_already_indented_code_preserved(self) -> None:
        """If code is already indented (looks like body), preserve it."""
        exec_context = """
def f(x):
[insert]
"""
        # Already just the function body with proper indentation
        code = """    result = x * 2
    return result"""

        result = extract_solution_for_context(code, exec_context)
        assert result == code
