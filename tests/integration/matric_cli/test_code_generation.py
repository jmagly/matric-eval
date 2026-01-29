"""
Code generation scenario tests for matric-cli evaluation.

These tests validate the code generation test data ported from matric-cli
and can be extended to run actual evaluations against models.
"""

import json
from pathlib import Path

import pytest

# Path to test data
DATA_DIR = Path(__file__).parent / "data"
CODE_GEN_FILE = DATA_DIR / "code_generation_scenarios.json"


@pytest.fixture
def code_generation_scenarios():
    """Load code generation scenarios from JSON."""
    with open(CODE_GEN_FILE) as f:
        return json.load(f)


class TestCodeGenerationData:
    """Tests for code generation scenario data integrity."""

    def test_scenarios_file_exists(self):
        """Verify code generation scenarios file exists."""
        assert CODE_GEN_FILE.exists(), f"Missing: {CODE_GEN_FILE}"

    def test_scenarios_load_correctly(self, code_generation_scenarios):
        """Verify scenarios load as valid JSON."""
        assert isinstance(code_generation_scenarios, list)
        assert len(code_generation_scenarios) > 0

    def test_all_scenarios_have_required_fields(self, code_generation_scenarios):
        """Each scenario must have required fields."""
        required_fields = ["id", "name", "category", "difficulty", "prompt", "expected_behavior"]

        for scenario in code_generation_scenarios:
            for field in required_fields:
                assert field in scenario, f"Missing '{field}' in scenario {scenario.get('id', 'unknown')}"

    def test_scenario_ids_are_unique(self, code_generation_scenarios):
        """Scenario IDs must be unique."""
        ids = [s["id"] for s in code_generation_scenarios]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"

    def test_difficulties_are_valid(self, code_generation_scenarios):
        """Difficulties must be easy, medium, or hard."""
        valid_difficulties = {"easy", "medium", "hard"}

        for scenario in code_generation_scenarios:
            assert scenario["difficulty"] in valid_difficulties, \
                f"Invalid difficulty '{scenario['difficulty']}' in {scenario['id']}"

    def test_prompts_contain_code_requirements(self, code_generation_scenarios):
        """Code gen prompts should mention functions, classes, or implementations."""
        code_keywords = ["function", "class", "implement", "write", "create", "fix", "complete"]

        for scenario in code_generation_scenarios:
            prompt_lower = scenario["prompt"].lower()
            has_code_keyword = any(kw in prompt_lower for kw in code_keywords)
            assert has_code_keyword, f"Prompt in {scenario['id']} doesn't seem to request code"


class TestCodeGenerationScenarioCategories:
    """Tests for code generation scenario category coverage."""

    def test_has_algorithm_scenarios(self, code_generation_scenarios):
        """Should have algorithm-related scenarios."""
        algo_scenarios = [
            s for s in code_generation_scenarios
            if "algorithm" in s.get("tags", []) or "fibonacci" in s["id"].lower() or "binary" in s["id"].lower()
        ]
        assert len(algo_scenarios) >= 1, "Need algorithm scenarios"

    def test_has_bugfix_scenarios(self, code_generation_scenarios):
        """Should have bug fixing scenarios."""
        bugfix_scenarios = [
            s for s in code_generation_scenarios
            if "bugfix" in s["id"].lower() or "debugging" in s.get("tags", []) or "fix" in s["name"].lower()
        ]
        assert len(bugfix_scenarios) >= 1, "Need bug fixing scenarios"

    def test_has_multi_file_scenarios(self, code_generation_scenarios):
        """Should have multi-file reasoning scenarios."""
        multifile_scenarios = [
            s for s in code_generation_scenarios
            if "multifile" in s["id"].lower() or "multi-file" in s.get("tags", [])
        ]
        assert len(multifile_scenarios) >= 1, "Need multi-file scenarios"

    def test_balanced_difficulty_distribution(self, code_generation_scenarios):
        """Should have scenarios at each difficulty level."""
        difficulties = {s["difficulty"] for s in code_generation_scenarios}
        assert "easy" in difficulties, "Need easy scenarios"
        assert "medium" in difficulties, "Need medium scenarios"
        assert "hard" in difficulties, "Need hard scenarios"
