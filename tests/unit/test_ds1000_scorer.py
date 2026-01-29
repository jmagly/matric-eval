"""Unit tests for DS-1000 specialized scorer."""

from unittest.mock import MagicMock

import pytest

from matric_eval.scorers.ds1000_scorer import (
    ds1000_scorer,
    execute_ds1000_test,
    extract_solution_for_context,
)


@pytest.mark.unit
class TestExecuteDs1000Test:
    """Tests for execute_ds1000_test function."""

    def test_execute_passing_test(self) -> None:
        """Code that passes the test returns passed=True."""
        # Simple test harness that checks if result == expected
        code_context = '''
def generate_test_case(test_case_id):
    return 10, 100  # input, expected

def exec_test(result, ans):
    return 1 if result == ans else 0

def test_execution(solution: str):
    test_input, expected_result = generate_test_case(1)
    test_env = {"test_input": test_input}
    exec(f"x = test_input; result = x * 10", test_env)
    assert exec_test(test_env["result"], expected_result)
'''

        # Solution that computes x * 10
        code = "result = x * 10"

        result = execute_ds1000_test(code, code_context)
        assert result["passed"] is True

    def test_execute_failing_test(self) -> None:
        """Code that fails the test returns passed=False."""
        code_context = '''
def test_execution(solution: str):
    assert False, "Test always fails"
'''

        code = "pass"

        result = execute_ds1000_test(code, code_context)
        assert result["passed"] is False
        assert result["error"] is not None

    def test_execute_syntax_error_in_solution(self) -> None:
        """Syntax error in solution code returns passed=False."""
        code_context = '''
def test_execution(solution: str):
    exec(solution)
'''

        code = "def broken("  # Syntax error

        result = execute_ds1000_test(code, code_context)
        assert result["passed"] is False

    def test_execute_timeout(self) -> None:
        """Infinite loop in solution times out."""
        code_context = '''
def test_execution(solution: str):
    exec(solution)
'''

        code = "while True: pass"

        result = execute_ds1000_test(code, code_context, timeout=1)
        assert result["passed"] is False
        assert "timeout" in result["error"].lower()


@pytest.mark.unit
class TestDs1000Scorer:
    """Tests for ds1000_scorer."""

    @pytest.mark.asyncio
    async def test_scorer_returns_scorer_function(self) -> None:
        """scorer() returns a callable."""
        scorer = ds1000_scorer()
        assert callable(scorer)

    @pytest.mark.asyncio
    async def test_scorer_passes_with_correct_code(self) -> None:
        """Scorer returns 1.0 when code passes test harness."""
        scorer = ds1000_scorer()

        # Create mock state
        state = MagicMock()
        state.output.completion = "result = x * 2"  # Correct solution
        state.metadata = {
            "code_context": '''
def generate_test_case(test_case_id):
    return 5, 10  # input, expected

def exec_test(result, ans):
    return 1 if result == ans else 0

def test_execution(solution: str):
    test_input, expected_result = generate_test_case(1)
    exec_context = f"x = {test_input}\\n{solution}"
    test_env = {}
    exec(exec_context, test_env)
    assert exec_test(test_env["result"], expected_result)
'''
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0

    @pytest.mark.asyncio
    async def test_scorer_fails_with_incorrect_code(self) -> None:
        """Scorer returns 0.0 when code fails test harness."""
        scorer = ds1000_scorer()

        state = MagicMock()
        state.output.completion = "result = x * 3"  # Wrong: should be *2
        state.metadata = {
            "code_context": '''
def generate_test_case(test_case_id):
    return 5, 10  # input, expected (correct answer is x * 2)

def exec_test(result, ans):
    return 1 if result == ans else 0

def test_execution(solution: str):
    test_input, expected_result = generate_test_case(1)
    exec_context = f"x = {test_input}\\n{solution}"
    test_env = {}
    exec(exec_context, test_env)
    assert exec_test(test_env["result"], expected_result)
'''
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 0.0

    @pytest.mark.asyncio
    async def test_scorer_no_code(self) -> None:
        """Scorer returns 0.0 when no code found."""
        scorer = ds1000_scorer()

        state = MagicMock()
        state.output.completion = ""
        state.metadata = {"code_context": "def test_execution(s): pass"}

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 0.0
        assert "No code" in result.explanation

    @pytest.mark.asyncio
    async def test_scorer_no_code_context(self) -> None:
        """Scorer returns 0.0 when no code_context available."""
        scorer = ds1000_scorer()

        state = MagicMock()
        state.output.completion = "result = 42"
        state.metadata = {}

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 0.0
        assert "code_context" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_scorer_missing_test_execution(self) -> None:
        """Scorer returns 0.0 when code_context has no test_execution."""
        scorer = ds1000_scorer()

        state = MagicMock()
        state.output.completion = "result = 42"
        state.metadata = {
            "code_context": "# No test_execution function here"
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 0.0
        assert "test_execution" in result.explanation

    @pytest.mark.asyncio
    async def test_scorer_extracts_code_from_markdown(self) -> None:
        """Scorer extracts code from markdown fences."""
        scorer = ds1000_scorer()

        state = MagicMock()
        state.output.completion = '```python\nresult = x * 2\n```'
        state.metadata = {
            "code_context": '''
def test_execution(solution: str):
    test_env = {"x": 5}
    exec(solution, test_env)
    assert test_env["result"] == 10
'''
        }

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0


@pytest.mark.unit
class TestDs1000ScorerRegressions:
    """Regression tests for DS-1000 scorer."""

    @pytest.mark.asyncio
    async def test_regression_pandas_dataframe_comparison(self) -> None:
        """
        REGRESSION: DS-1000 uses pandas.testing.assert_frame_equal.

        The test harness from DS-1000 includes sophisticated comparison
        for pandas DataFrames that should be preserved.
        """
        # Skip if pandas not available
        pytest.importorskip("pandas")
        scorer = ds1000_scorer()

        # Realistic DS-1000 style code_context
        code_context = '''
import pandas as pd

def generate_test_case(test_case_id):
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    expected = df[df["A"] > 1]
    return df, expected

def exec_test(result, ans):
    try:
        pd.testing.assert_frame_equal(result, ans, check_dtype=False)
        return 1
    except:
        return 0

def test_execution(solution: str):
    test_input, expected_result = generate_test_case(1)
    test_env = {"df": test_input, "pd": pd}
    exec(solution, test_env)
    assert exec_test(test_env["result"], expected_result)
'''

        state = MagicMock()
        state.output.completion = 'result = df[df["A"] > 1]'
        state.metadata = {"code_context": code_context}

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0, f"Pandas comparison should work: {result.explanation}"

    @pytest.mark.asyncio
    async def test_regression_triple_quote_in_solution(self) -> None:
        """
        REGRESSION: Solutions with triple quotes should be handled.

        Model might produce code with docstrings or multi-line strings.
        """
        scorer = ds1000_scorer()

        code_context = '''
def test_execution(solution: str):
    test_env = {}
    exec(solution, test_env)
    assert test_env["result"] == "hello"
'''

        state = MagicMock()
        # Solution with triple quotes
        state.output.completion = '''
"""This is a docstring."""
result = "hello"
'''
        state.metadata = {"code_context": code_context}

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0, f"Triple quotes should be escaped: {result.explanation}"

    @pytest.mark.asyncio
    async def test_regression_insert_inside_function(self) -> None:
        """
        REGRESSION: When [insert] is inside a function definition,
        extract only the function body from model's output.

        This is the Pandas/114 pattern where exec_context has:
        def f(df):
        [insert]
        """
        scorer = ds1000_scorer()

        # Realistic DS-1000 code_context with [insert] inside function
        code_context = '''
exec_context = r"""
import pandas as pd
def f(df):
[insert]
df = test_input
result = f(df)
"""

def test_execution(solution: str):
    code = exec_context.replace("[insert]", solution)
    test_env = {"test_input": [1, 2, 3]}
    exec(code, test_env)
    assert test_env["result"] == 6, f"Expected 6, got {test_env['result']}"
'''

        state = MagicMock()
        # Model outputs full function definition (common pattern)
        state.output.completion = '''```python
import pandas as pd

def f(df):
    return sum(df)

result = f([1,2,3])
```'''
        state.metadata = {"code_context": code_context}

        target = MagicMock()

        result = await scorer(state, target)
        assert result.value == 1.0, f"Should extract function body: {result.explanation}"


@pytest.mark.unit
class TestExtractSolutionForContext:
    """Tests for extract_solution_for_context function."""

    def test_top_level_insert_uses_full_code(self) -> None:
        """When [insert] is at top level, use full code."""
        exec_context = '''
import pandas as pd
df = test_input
[insert]
'''
        code = "result = df.sum()"

        result = extract_solution_for_context(code, exec_context)
        assert result == code

    def test_insert_inside_function_extracts_body(self) -> None:
        """When [insert] is inside function, extract function body."""
        exec_context = '''
import pandas as pd
def f(df):
[insert]
result = f(df)
'''
        # Model outputs full function
        code = '''import pandas as pd

def f(df):
    total = sum(df)
    return total

result = f([1,2,3])'''

        result = extract_solution_for_context(code, exec_context)
        # Should extract just the function body with indentation
        assert "    total = sum(df)" in result
        assert "    return total" in result
        assert "import pandas" not in result
        assert "def f(" not in result

    def test_insert_inside_function_preserves_indentation(self) -> None:
        """Extracted function body should preserve indentation."""
        exec_context = '''
def f(x):
[insert]
'''
        code = '''def f(x):
    if x > 0:
        return x * 2
    else:
        return x'''

        result = extract_solution_for_context(code, exec_context)
        # Body lines should be indented - check raw result without strip
        lines = result.split('\n')
        # Filter out empty lines and check non-empty lines are indented
        non_empty_lines = [line for line in lines if line.strip()]
        assert len(non_empty_lines) > 0
        assert all(line.startswith('    ') for line in non_empty_lines)

    def test_already_indented_code_preserved(self) -> None:
        """If code is already indented (looks like body), preserve it."""
        exec_context = '''
def f(x):
[insert]
'''
        # Already just the function body with proper indentation
        code = '''    result = x * 2
    return result'''

        result = extract_solution_for_context(code, exec_context)
        assert result == code
