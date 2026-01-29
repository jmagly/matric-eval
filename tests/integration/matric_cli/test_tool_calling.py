"""
Tool calling scenario tests for matric-cli evaluation.

These tests validate the tool calling test data ported from matric-cli
and can be extended to run actual evaluations against models.
"""

import json
from pathlib import Path

import pytest

# Path to test data
DATA_DIR = Path(__file__).parent / "data"
TOOL_CALLING_FILE = DATA_DIR / "tool_calling_scenarios.json"


@pytest.fixture
def tool_calling_scenarios():
    """Load tool calling scenarios from JSON."""
    with open(TOOL_CALLING_FILE) as f:
        return json.load(f)


class TestToolCallingData:
    """Tests for tool calling scenario data integrity."""

    def test_scenarios_file_exists(self):
        """Verify tool calling scenarios file exists."""
        assert TOOL_CALLING_FILE.exists(), f"Missing: {TOOL_CALLING_FILE}"

    def test_scenarios_load_correctly(self, tool_calling_scenarios):
        """Verify scenarios load as valid JSON."""
        assert isinstance(tool_calling_scenarios, list)
        assert len(tool_calling_scenarios) > 0

    def test_all_scenarios_have_required_fields(self, tool_calling_scenarios):
        """Each scenario must have required fields."""
        required_fields = ["id", "name", "category", "difficulty", "prompt", "expected_behavior"]

        for scenario in tool_calling_scenarios:
            for field in required_fields:
                assert field in scenario, f"Missing '{field}' in scenario {scenario.get('id', 'unknown')}"

    def test_scenario_ids_are_unique(self, tool_calling_scenarios):
        """Scenario IDs must be unique."""
        ids = [s["id"] for s in tool_calling_scenarios]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"

    def test_difficulties_are_valid(self, tool_calling_scenarios):
        """Difficulties must be easy, medium, or hard."""
        valid_difficulties = {"easy", "medium", "hard"}

        for scenario in tool_calling_scenarios:
            assert scenario["difficulty"] in valid_difficulties, \
                f"Invalid difficulty '{scenario['difficulty']}' in {scenario['id']}"

    def test_prompts_are_non_empty(self, tool_calling_scenarios):
        """Prompts must be non-empty strings."""
        for scenario in tool_calling_scenarios:
            assert isinstance(scenario["prompt"], str)
            assert len(scenario["prompt"]) > 10, f"Prompt too short in {scenario['id']}"

    def test_tags_are_lists(self, tool_calling_scenarios):
        """Tags must be lists of strings."""
        for scenario in tool_calling_scenarios:
            if "tags" in scenario:
                assert isinstance(scenario["tags"], list)
                for tag in scenario["tags"]:
                    assert isinstance(tag, str)


class TestToolCallingScenarioCategories:
    """Tests for scenario category coverage."""

    def test_has_simple_scenarios(self, tool_calling_scenarios):
        """Should have at least one easy/simple scenario."""
        easy = [s for s in tool_calling_scenarios if s["difficulty"] == "easy"]
        assert len(easy) >= 1, "Need at least one easy scenario"

    def test_has_complex_scenarios(self, tool_calling_scenarios):
        """Should have at least one hard scenario."""
        hard = [s for s in tool_calling_scenarios if s["difficulty"] == "hard"]
        assert len(hard) >= 1, "Need at least one hard scenario"

    def test_covers_error_handling(self, tool_calling_scenarios):
        """Should have error handling scenarios."""
        error_scenarios = [
            s for s in tool_calling_scenarios
            if "error" in s["id"].lower() or "error-handling" in s.get("tags", [])
        ]
        assert len(error_scenarios) >= 1, "Need error handling scenarios"

    def test_covers_parallel_execution(self, tool_calling_scenarios):
        """Should have parallel execution scenarios."""
        parallel_scenarios = [
            s for s in tool_calling_scenarios
            if "parallel" in s["id"].lower() or "parallel" in s.get("tags", [])
        ]
        assert len(parallel_scenarios) >= 1, "Need parallel execution scenarios"
