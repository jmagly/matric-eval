"""
Tests for tool calling evaluation task (matric_eval.tasks.tool_calling).

Covers:
- Function call extraction from responses
- Parameter matching and scoring
- Scenario-specific evaluation
- Synthetic sample generation
- Task definition
"""

import json
import pytest
from inspect_ai.dataset import Sample

from matric_eval.tasks.tool_calling import (
    SCENARIOS,
    calculate_function_call_score,
    calculate_param_match,
    extract_function_call,
    load_tool_calling,
    record_to_sample,
    tool_calling,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton."""
    monkeypatch.delenv("EVAL_TOOL_CALLING_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    import matric_eval.config.settings as settings_module
    settings_module._settings = None


@pytest.fixture
def simple_function_call() -> dict:
    """Sample simple function call."""
    return {
        "name": "get_weather",
        "parameters": {"location": "New York", "unit": "celsius"},
    }


@pytest.fixture
def parallel_function_calls() -> list:
    """Sample parallel function calls."""
    return [
        {"name": "search_flights", "parameters": {"origin": "NYC", "destination": "LAX", "date": "2024-03-15"}},
        {"name": "search_hotels", "parameters": {"location": "LAX", "checkin": "2024-03-15", "checkout": "2024-03-20"}},
    ]


# =============================================================================
# Function Call Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestExtractFunctionCall:
    """Tests for extract_function_call() function."""

    def test_extract_raw_json(self) -> None:
        """Should extract raw JSON function call."""
        response = '{"name": "get_weather", "parameters": {"location": "Paris"}}'
        result = extract_function_call(response)
        assert result is not None
        assert result["name"] == "get_weather"
        assert result["parameters"]["location"] == "Paris"

    def test_extract_json_in_code_block(self) -> None:
        """Should extract JSON from markdown code block."""
        response = '''Here's the function call:
```json
{"name": "get_stock_price", "parameters": {"symbol": "AAPL"}}
```'''
        result = extract_function_call(response)
        assert result is not None
        assert result["name"] == "get_stock_price"

    def test_extract_json_in_generic_code_block(self) -> None:
        """Should extract JSON from generic code block."""
        response = '''
```
{"name": "send_email", "parameters": {"to": "test@example.com"}}
```'''
        result = extract_function_call(response)
        assert result is not None
        assert result["name"] == "send_email"

    def test_extract_json_array(self) -> None:
        """Should extract JSON array of function calls."""
        response = '[{"name": "func1"}, {"name": "func2"}]'
        result = extract_function_call(response)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_extract_with_surrounding_text(self) -> None:
        """Should extract JSON with surrounding text."""
        response = '{"name": "get_weather", "parameters": {"location": "London"}}'
        result = extract_function_call(response)
        assert result is not None
        assert result["name"] == "get_weather"

    def test_extract_invalid_json_returns_none(self) -> None:
        """Should return None for invalid JSON."""
        response = "I cannot make this function call"
        result = extract_function_call(response)
        assert result is None

    def test_extract_empty_response_returns_none(self) -> None:
        """Should return None for empty response."""
        result = extract_function_call("")
        assert result is None

    def test_extract_inline_backticks(self) -> None:
        """Should extract from inline backticks."""
        response = 'The call is `{"name": "test_func", "parameters": {}}`'
        result = extract_function_call(response)
        assert result is not None
        assert result["name"] == "test_func"


# =============================================================================
# Parameter Matching Tests
# =============================================================================


@pytest.mark.unit
class TestCalculateParamMatch:
    """Tests for calculate_param_match() function."""

    def test_exact_match(self) -> None:
        """Should return 1.0 for exact parameter match."""
        actual = {"location": "New York", "unit": "celsius"}
        expected = {"location": "New York", "unit": "celsius"}
        assert calculate_param_match(actual, expected) == 1.0

    def test_partial_match(self) -> None:
        """Should return partial score for partial match."""
        actual = {"location": "New York", "unit": "fahrenheit"}
        expected = {"location": "New York", "unit": "celsius"}
        score = calculate_param_match(actual, expected)
        assert 0.5 < score < 1.0

    def test_missing_param(self) -> None:
        """Should penalize missing parameters."""
        actual = {"location": "New York"}
        expected = {"location": "New York", "unit": "celsius"}
        score = calculate_param_match(actual, expected)
        assert score < 1.0

    def test_empty_expected(self) -> None:
        """Should return 1.0 when no parameters expected."""
        actual = {}
        expected = {}
        assert calculate_param_match(actual, expected) == 1.0

    def test_string_partial_match(self) -> None:
        """Should partial match similar strings."""
        actual = {"location": "new york city"}
        expected = {"location": "New York"}
        score = calculate_param_match(actual, expected)
        assert score > 0.5  # Partial credit for substring match

    def test_type_mismatch(self) -> None:
        """Should give partial credit for type mismatch."""
        actual = {"count": "5"}
        expected = {"count": 5}
        score = calculate_param_match(actual, expected)
        assert 0 < score < 1.0


# =============================================================================
# Function Call Scoring Tests
# =============================================================================


@pytest.mark.unit
class TestCalculateFunctionCallScore:
    """Tests for calculate_function_call_score() function."""

    def test_perfect_single_call(self, simple_function_call: dict) -> None:
        """Should score 1.0 for perfect single function call."""
        score, explanation = calculate_function_call_score(
            simple_function_call,
            simple_function_call,
        )
        assert score == 1.0
        assert "Perfect match" in explanation

    def test_wrong_function_name(self, simple_function_call: dict) -> None:
        """Should score 0.0 for wrong function name."""
        actual = {"name": "wrong_func", "parameters": simple_function_call["parameters"]}
        score, explanation = calculate_function_call_score(actual, simple_function_call)
        assert score == 0.0
        assert "Wrong function" in explanation

    def test_none_actual(self, simple_function_call: dict) -> None:
        """Should score 0.0 when actual is None."""
        score, explanation = calculate_function_call_score(None, simple_function_call)
        assert score == 0.0
        assert "parse" in explanation.lower()

    def test_multi_call_scoring(self, parallel_function_calls: list) -> None:
        """Should score multiple function calls."""
        score, explanation = calculate_function_call_score(
            parallel_function_calls,
            parallel_function_calls,
        )
        assert score > 0.9
        assert "Multi-call" in explanation

    def test_multi_call_wrong_count(self, parallel_function_calls: list) -> None:
        """Should penalize wrong number of calls."""
        actual = [parallel_function_calls[0]]  # Only one call
        score, explanation = calculate_function_call_score(actual, parallel_function_calls)
        assert score < 0.5
        assert "Expected 2" in explanation

    def test_error_handling_correct(self) -> None:
        """Should score correctly for error handling."""
        expected = {"error": "No suitable function"}
        actual = {"error": "Cannot find appropriate function"}
        score, _ = calculate_function_call_score(actual, expected)
        assert score > 0.7

    def test_error_handling_missed(self) -> None:
        """Should penalize when error not detected."""
        expected = {"error": "No suitable function"}
        actual = {"name": "some_func", "parameters": {}}
        score, explanation = calculate_function_call_score(actual, expected)
        assert score < 0.5
        assert "should have indicated" in explanation.lower()


# =============================================================================
# Record to Sample Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() function."""

    def test_basic_conversion(self) -> None:
        """Should convert record to Sample."""
        record = {
            "id": "test_1",
            "functions": [{"name": "test_func", "parameters": {}}],
            "query": "Test query",
            "expected_call": {"name": "test_func", "parameters": {}},
            "scenario": "simple",
        }
        sample = record_to_sample(record)
        assert isinstance(sample, Sample)
        assert "test_func" in sample.input
        assert sample.id == "tool_call_test_1"

    def test_includes_function_definitions(self) -> None:
        """Should include function definitions in input."""
        record = {
            "functions": [
                {
                    "name": "get_weather",
                    "description": "Get weather info",
                    "parameters": {"type": "object"},
                }
            ],
            "query": "What's the weather?",
            "expected_call": {},
        }
        sample = record_to_sample(record)
        assert "get_weather" in sample.input
        assert "Get weather info" in sample.input

    def test_target_is_json(self) -> None:
        """Should have JSON target."""
        record = {
            "functions": [],
            "query": "Test",
            "expected_call": {"name": "func", "parameters": {"a": 1}},
        }
        sample = record_to_sample(record)
        parsed = json.loads(sample.target)
        assert parsed["name"] == "func"

    def test_metadata_includes_scenario(self) -> None:
        """Should include scenario in metadata."""
        record = {
            "functions": [],
            "query": "Test",
            "expected_call": {},
            "scenario": "parallel",
        }
        sample = record_to_sample(record)
        assert sample.metadata["scenario"] == "parallel"


# =============================================================================
# Load Tool Calling Tests
# =============================================================================


@pytest.mark.unit
class TestLoadToolCalling:
    """Tests for load_tool_calling() function."""

    def test_load_smoke_returns_samples(self) -> None:
        """Should return samples for smoke tier."""
        samples = load_tool_calling(tier="smoke")
        assert len(samples) == 5
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_quick_returns_more_samples(self) -> None:
        """Should return more samples for quick tier."""
        smoke_samples = load_tool_calling(tier="smoke")
        quick_samples = load_tool_calling(tier="quick")
        assert len(quick_samples) > len(smoke_samples)

    def test_load_with_scenario_filter(self) -> None:
        """Should filter by scenario when specified."""
        samples = load_tool_calling(tier="smoke", scenario="simple")
        for sample in samples:
            assert sample.metadata.get("scenario") == "simple"

    def test_load_reproducible_with_seed(self) -> None:
        """Should return same samples with same seed."""
        samples1 = load_tool_calling(tier="smoke")
        samples2 = load_tool_calling(tier="smoke")
        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]
        assert ids1 == ids2

    def test_samples_have_required_fields(self) -> None:
        """Should have all required Sample fields."""
        samples = load_tool_calling(tier="smoke")
        for sample in samples:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert "scenario" in sample.metadata


# =============================================================================
# Tool Calling Task Tests
# =============================================================================


@pytest.mark.unit
class TestToolCallingTask:
    """Tests for tool_calling() task function."""

    def test_task_creation(self) -> None:
        """Should create a valid Task."""
        from inspect_ai import Task
        task = tool_calling(tier="smoke")
        assert isinstance(task, Task)

    def test_task_has_dataset(self) -> None:
        """Should have dataset with samples."""
        task = tool_calling(tier="smoke")
        assert len(task.dataset) == 5

    def test_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = tool_calling(tier="smoke")
        assert task.solver is not None

    def test_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = tool_calling(tier="smoke")
        assert task.scorer is not None

    def test_task_name_includes_scenario(self) -> None:
        """Should include scenario in task name when specified."""
        task = tool_calling(tier="smoke", scenario="simple")
        assert "simple" in task.name

    def test_task_name_default(self) -> None:
        """Should have default name when no scenario."""
        task = tool_calling(tier="smoke")
        assert task.name == "tool_calling"


# =============================================================================
# Scenarios Tests
# =============================================================================


@pytest.mark.unit
class TestScenarios:
    """Tests for scenario definitions."""

    def test_all_scenarios_defined(self) -> None:
        """Should have all 6 scenarios defined."""
        expected_scenarios = ["simple", "parallel", "nested", "error_handling", "complex_types", "multi_turn"]
        for scenario in expected_scenarios:
            assert scenario in SCENARIOS

    def test_scenarios_have_descriptions(self) -> None:
        """Should have descriptions for all scenarios."""
        for scenario, description in SCENARIOS.items():
            assert description, f"No description for {scenario}"
            assert len(description) > 10


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_functions_list(self) -> None:
        """Should handle empty functions list."""
        record = {
            "functions": [],
            "query": "Do something",
            "expected_call": {},
        }
        sample = record_to_sample(record)
        assert sample.input is not None

    def test_deeply_nested_parameters(self) -> None:
        """Should handle deeply nested parameters."""
        expected = {
            "name": "complex_func",
            "parameters": {
                "nested": {
                    "deeply": {
                        "value": 42
                    }
                }
            }
        }
        actual = {
            "name": "complex_func",
            "parameters": {
                "nested": {
                    "deeply": {
                        "value": 42
                    }
                }
            }
        }
        score, _ = calculate_function_call_score(actual, expected)
        assert score > 0.5  # Structural match

    def test_array_parameters(self) -> None:
        """Should handle array parameters."""
        expected = {
            "name": "bulk_update",
            "parameters": {
                "ids": [1, 2, 3]
            }
        }
        actual = {
            "name": "bulk_update",
            "parameters": {
                "ids": [1, 2, 3]
            }
        }
        score, _ = calculate_function_call_score(actual, expected)
        assert score == 1.0

    def test_unicode_in_parameters(self) -> None:
        """Should handle unicode in parameters."""
        expected = {
            "name": "send_message",
            "parameters": {
                "text": "Hello 世界 🌍"
            }
        }
        actual = {
            "name": "send_message",
            "parameters": {
                "text": "Hello 世界 🌍"
            }
        }
        score, _ = calculate_function_call_score(actual, expected)
        assert score == 1.0
