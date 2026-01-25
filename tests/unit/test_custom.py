"""
Unit tests for custom matric test framework.

Tests loading, sampling, and task creation for app-specific evaluations.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.custom import (
    CustomTestMetadata,
    CustomTestNotFoundError,
    InvalidCustomTestError,
    custom_task,
    discover_custom_tests,
    load_custom_tests,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def custom_test_dir(tmp_path: Path) -> Path:
    """Create temporary custom test directory structure."""
    datasets_dir = tmp_path / "datasets" / "custom"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    return datasets_dir


@pytest.fixture
def matric_cli_dir(custom_test_dir: Path) -> Path:
    """Create matric-cli test directory."""
    cli_dir = custom_test_dir / "matric-cli"
    cli_dir.mkdir(parents=True, exist_ok=True)
    return cli_dir


@pytest.fixture
def matric_memory_dir(custom_test_dir: Path) -> Path:
    """Create matric-memory test directory."""
    memory_dir = custom_test_dir / "matric-memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


@pytest.fixture
def tool_calling_samples() -> list[dict[str, Any]]:
    """Sample tool calling test data."""
    return [
        {
            "id": "tool-001",
            "prompt": "Read the file config.json",
            "expected": {
                "tool": "read_file",
                "args": {"path": "config.json"}
            },
            "scorer_type": "tool_match"
        },
        {
            "id": "tool-002",
            "prompt": "List all files in the current directory",
            "expected": {
                "tool": "list_files",
                "args": {"path": "."}
            },
            "scorer_type": "tool_match"
        },
        {
            "id": "tool-003",
            "prompt": "Write 'Hello' to output.txt",
            "expected": {
                "tool": "write_file",
                "args": {"path": "output.txt", "content": "Hello"}
            },
            "scorer_type": "tool_match"
        },
    ]


@pytest.fixture
def agent_scenario_samples() -> list[dict[str, Any]]:
    """Sample agent scenario test data."""
    return [
        {
            "id": "agent-001",
            "prompt": "Find and fix the bug in module.py",
            "expected": {
                "steps": ["read_file", "analyze", "write_file", "test"],
                "outcome": "bug_fixed"
            },
            "scorer_type": "workflow_match"
        },
        {
            "id": "agent-002",
            "prompt": "Create a new feature according to spec.md",
            "expected": {
                "steps": ["read_file", "plan", "implement", "test"],
                "outcome": "feature_created"
            },
            "scorer_type": "workflow_match"
        },
    ]


@pytest.fixture
def title_generation_samples() -> list[dict[str, Any]]:
    """Sample title generation test data."""
    return [
        {
            "id": "title-001",
            "prompt": "This is a note about Python async programming patterns",
            "expected": "Python Async Programming Patterns",
            "scorer_type": "semantic_similarity"
        },
        {
            "id": "title-002",
            "prompt": "Meeting notes from the quarterly planning session",
            "expected": "Quarterly Planning Meeting Notes",
            "scorer_type": "semantic_similarity"
        },
    ]


@pytest.fixture
def semantic_similarity_samples() -> list[dict[str, Any]]:
    """Sample semantic similarity test data."""
    return [
        {
            "id": "semantic-001",
            "prompt": "Find notes related to machine learning",
            "expected": {
                "keywords": ["ML", "neural networks", "training"],
                "min_similarity": 0.8
            },
            "scorer_type": "semantic_similarity"
        },
    ]


@pytest.fixture
def tool_calling_file(matric_cli_dir: Path, tool_calling_samples: list[dict[str, Any]]) -> Path:
    """Create tool_calling.jsonl test file."""
    test_file = matric_cli_dir / "tool_calling.jsonl"
    with open(test_file, "w") as f:
        for sample in tool_calling_samples:
            f.write(json.dumps(sample) + "\n")
    return test_file


@pytest.fixture
def agent_scenarios_file(matric_cli_dir: Path, agent_scenario_samples: list[dict[str, Any]]) -> Path:
    """Create agent_scenarios.jsonl test file."""
    test_file = matric_cli_dir / "agent_scenarios.jsonl"
    with open(test_file, "w") as f:
        for sample in agent_scenario_samples:
            f.write(json.dumps(sample) + "\n")
    return test_file


@pytest.fixture
def title_generation_file(matric_memory_dir: Path, title_generation_samples: list[dict[str, Any]]) -> Path:
    """Create title_generation.jsonl test file."""
    test_file = matric_memory_dir / "title_generation.jsonl"
    with open(test_file, "w") as f:
        for sample in title_generation_samples:
            f.write(json.dumps(sample) + "\n")
    return test_file


@pytest.fixture
def semantic_similarity_file(matric_memory_dir: Path, semantic_similarity_samples: list[dict[str, Any]]) -> Path:
    """Create semantic_similarity.jsonl test file."""
    test_file = matric_memory_dir / "semantic_similarity.jsonl"
    with open(test_file, "w") as f:
        for sample in semantic_similarity_samples:
            f.write(json.dumps(sample) + "\n")
    return test_file


# =============================================================================
# Test: load_custom_tests
# =============================================================================


@pytest.mark.unit
class TestLoadCustomTests:
    """Tests for load_custom_tests function."""

    def test_load_all_samples_smoke_tier(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path,
        tool_calling_samples: list[dict[str, Any]]
    ) -> None:
        """Test loading all samples in smoke tier (5 max)."""
        samples = load_custom_tests(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert len(samples) == min(len(tool_calling_samples), 5)
        assert all(isinstance(s, Sample) for s in samples)
        assert samples[0].id == "tool-001"
        assert samples[0].input == "Read the file config.json"
        assert samples[0].metadata is not None
        assert samples[0].metadata.get("scorer_type") == "tool_match"

    def test_load_all_samples_quick_tier(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path,
        tool_calling_samples: list[dict[str, Any]]
    ) -> None:
        """Test loading all samples in quick tier (20 max)."""
        samples = load_custom_tests(
            app="matric-cli",
            test_name="tool_calling",
            tier="quick",
            datasets_root=str(custom_test_dir)
        )

        assert len(samples) == len(tool_calling_samples)
        assert samples[2].id == "tool-003"

    def test_load_all_samples_full_tier(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path,
        tool_calling_samples: list[dict[str, Any]]
    ) -> None:
        """Test loading all samples in full tier (no limit)."""
        samples = load_custom_tests(
            app="matric-cli",
            test_name="tool_calling",
            tier="full",
            datasets_root=str(custom_test_dir)
        )

        assert len(samples) == len(tool_calling_samples)

    def test_target_field_from_expected(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test that expected field is converted to target field."""
        samples = load_custom_tests(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert samples[0].target is not None
        # Target is JSON-serialized for Inspect AI compatibility
        import json
        assert samples[0].target == json.dumps({
            "tool": "read_file",
            "args": {"path": "config.json"}
        })
        # Original value stored in metadata
        assert samples[0].metadata.get("expected_value") == {
            "tool": "read_file",
            "args": {"path": "config.json"}
        }

    def test_metadata_includes_scorer_type(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test that metadata includes scorer_type."""
        samples = load_custom_tests(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert samples[0].metadata is not None
        assert "scorer_type" in samples[0].metadata
        assert samples[0].metadata["scorer_type"] == "tool_match"

    def test_file_not_found_error(
        self,
        matric_cli_dir: Path,
        custom_test_dir: Path
    ) -> None:
        """Test error when custom test file doesn't exist."""
        with pytest.raises(CustomTestNotFoundError) as exc_info:
            load_custom_tests(
                app="matric-cli",
                test_name="nonexistent",
                tier="smoke",
                datasets_root=str(custom_test_dir)
            )

        assert "nonexistent" in str(exc_info.value)
        assert "matric-cli" in str(exc_info.value)

    def test_app_directory_not_found_error(
        self,
        custom_test_dir: Path
    ) -> None:
        """Test error when app directory doesn't exist."""
        with pytest.raises(CustomTestNotFoundError) as exc_info:
            load_custom_tests(
                app="nonexistent-app",
                test_name="test",
                tier="smoke",
                datasets_root=str(custom_test_dir)
            )

        assert "nonexistent-app" in str(exc_info.value)

    def test_invalid_json_format_error(
        self,
        matric_cli_dir: Path,
        custom_test_dir: Path
    ) -> None:
        """Test error when JSONL file has invalid format."""
        invalid_file = matric_cli_dir / "invalid.jsonl"
        with open(invalid_file, "w") as f:
            f.write("not valid json\n")

        with pytest.raises(InvalidCustomTestError) as exc_info:
            load_custom_tests(
                app="matric-cli",
                test_name="invalid",
                tier="smoke",
                datasets_root=str(custom_test_dir)
            )

        assert "invalid" in str(exc_info.value).lower()

    def test_missing_required_fields_error(
        self,
        matric_cli_dir: Path,
        custom_test_dir: Path
    ) -> None:
        """Test error when sample is missing required fields."""
        incomplete_file = matric_cli_dir / "incomplete.jsonl"
        with open(incomplete_file, "w") as f:
            # Missing 'prompt' field
            f.write(json.dumps({"id": "test-001", "expected": "output"}) + "\n")

        with pytest.raises(InvalidCustomTestError) as exc_info:
            load_custom_tests(
                app="matric-cli",
                test_name="incomplete",
                tier="smoke",
                datasets_root=str(custom_test_dir)
            )

        assert "required" in str(exc_info.value).lower() or "prompt" in str(exc_info.value).lower()

    def test_default_datasets_root(
        self,
        tool_calling_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        custom_test_dir: Path
    ) -> None:
        """Test that default datasets_root is used when not specified."""
        # Change to parent directory so datasets/custom/ exists
        project_root = custom_test_dir.parent.parent
        monkeypatch.chdir(project_root)

        samples = load_custom_tests(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke"
        )

        assert len(samples) > 0

    def test_tiered_sampling_consistency(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test that tiered sampling is consistent across calls."""
        samples1 = load_custom_tests(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        samples2 = load_custom_tests(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert len(samples1) == len(samples2)
        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Test: custom_task
# =============================================================================


@pytest.mark.unit
class TestCustomTask:
    """Tests for custom_task function."""

    def test_create_task_with_tool_calling(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test creating a task for tool calling tests."""
        task = custom_task(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert isinstance(task, Task)
        assert task.name == "custom_matric-cli_tool_calling"
        assert task.dataset is not None
        assert len(task.dataset) > 0

    def test_create_task_with_agent_scenarios(
        self,
        agent_scenarios_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test creating a task for agent scenarios."""
        task = custom_task(
            app="matric-cli",
            test_name="agent_scenarios",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert isinstance(task, Task)
        assert task.name == "custom_matric-cli_agent_scenarios"
        assert len(task.dataset) > 0

    def test_create_task_with_title_generation(
        self,
        title_generation_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test creating a task for title generation."""
        task = custom_task(
            app="matric-memory",
            test_name="title_generation",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert isinstance(task, Task)
        assert task.name == "custom_matric-memory_title_generation"

    def test_task_has_solver(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test that created task has a solver configured."""
        task = custom_task(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert task.solver is not None
        assert len(task.solver) > 0

    def test_task_has_scorer(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test that created task has a scorer configured."""
        task = custom_task(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert task.scorer is not None

    def test_auto_detect_scorer_tool_match(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test auto-detection of tool_match scorer type."""
        task = custom_task(
            app="matric-cli",
            test_name="tool_calling",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        # Scorer should be set based on scorer_type in metadata
        assert task.scorer is not None

    def test_auto_detect_scorer_semantic_similarity(
        self,
        title_generation_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test auto-detection of semantic_similarity scorer type."""
        task = custom_task(
            app="matric-memory",
            test_name="title_generation",
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )

        assert task.scorer is not None


# =============================================================================
# Test: discover_custom_tests
# =============================================================================


@pytest.mark.unit
class TestDiscoverCustomTests:
    """Tests for discover_custom_tests function."""

    def test_discover_all_tests(
        self,
        tool_calling_file: Path,
        agent_scenarios_file: Path,
        title_generation_file: Path,
        semantic_similarity_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test discovering all custom tests across all apps."""
        tests = discover_custom_tests(datasets_root=str(custom_test_dir))

        assert len(tests) == 4

        # Check that all apps are discovered
        apps = {t.app for t in tests}
        assert "matric-cli" in apps
        assert "matric-memory" in apps

    def test_discover_tests_for_specific_app(
        self,
        tool_calling_file: Path,
        agent_scenarios_file: Path,
        title_generation_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test discovering tests for a specific app."""
        tests = discover_custom_tests(
            app="matric-cli",
            datasets_root=str(custom_test_dir)
        )

        assert len(tests) == 2
        assert all(t.app == "matric-cli" for t in tests)

        test_names = {t.test_name for t in tests}
        assert "tool_calling" in test_names
        assert "agent_scenarios" in test_names

    def test_discovered_metadata_structure(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path,
        tool_calling_samples: list[dict[str, Any]]
    ) -> None:
        """Test structure of discovered test metadata."""
        tests = discover_custom_tests(
            app="matric-cli",
            datasets_root=str(custom_test_dir)
        )

        tool_test = next(t for t in tests if t.test_name == "tool_calling")
        assert isinstance(tool_test, CustomTestMetadata)
        assert tool_test.app == "matric-cli"
        assert tool_test.test_name == "tool_calling"
        assert tool_test.path.endswith("tool_calling.jsonl")
        assert tool_test.sample_count == len(tool_calling_samples)
        assert "scorer_type" in tool_test.metadata_sample

    def test_discover_empty_directory(
        self,
        custom_test_dir: Path
    ) -> None:
        """Test discovering tests in empty directory returns empty list."""
        tests = discover_custom_tests(datasets_root=str(custom_test_dir))

        assert len(tests) == 0

    def test_discover_app_not_found(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test discovering tests for non-existent app returns empty list."""
        tests = discover_custom_tests(
            app="nonexistent-app",
            datasets_root=str(custom_test_dir)
        )

        assert len(tests) == 0

    def test_discover_ignores_non_jsonl_files(
        self,
        matric_cli_dir: Path,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test that discovery ignores non-JSONL files."""
        # Create non-JSONL files
        (matric_cli_dir / "README.md").write_text("# Tests")
        (matric_cli_dir / "config.json").write_text("{}")

        tests = discover_custom_tests(
            app="matric-cli",
            datasets_root=str(custom_test_dir)
        )

        # Should only find the .jsonl file
        assert len(tests) == 1
        assert tests[0].test_name == "tool_calling"

    def test_discover_handles_corrupted_file_gracefully(
        self,
        matric_cli_dir: Path,
        custom_test_dir: Path
    ) -> None:
        """Test that discovery handles corrupted files gracefully."""
        corrupted_file = matric_cli_dir / "corrupted.jsonl"
        corrupted_file.write_text("invalid json\n")

        # Should not raise, but may skip the corrupted file
        tests = discover_custom_tests(
            app="matric-cli",
            datasets_root=str(custom_test_dir)
        )

        # Either no tests or metadata indicates error
        assert isinstance(tests, list)

    def test_discover_sorts_by_app_and_name(
        self,
        tool_calling_file: Path,
        agent_scenarios_file: Path,
        title_generation_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test that discovered tests are sorted by app and test name."""
        tests = discover_custom_tests(datasets_root=str(custom_test_dir))

        # Check sorting
        for i in range(len(tests) - 1):
            current = (tests[i].app, tests[i].test_name)
            next_test = (tests[i + 1].app, tests[i + 1].test_name)
            assert current <= next_test


# =============================================================================
# Test: CustomTestMetadata
# =============================================================================


@pytest.mark.unit
class TestCustomTestMetadata:
    """Tests for CustomTestMetadata dataclass."""

    def test_metadata_creation(self) -> None:
        """Test creating CustomTestMetadata instance."""
        metadata = CustomTestMetadata(
            app="test-app",
            test_name="test_name",
            path="/path/to/test.jsonl",
            sample_count=10,
            metadata_sample={"scorer_type": "match"}
        )

        assert metadata.app == "test-app"
        assert metadata.test_name == "test_name"
        assert metadata.path == "/path/to/test.jsonl"
        assert metadata.sample_count == 10
        assert metadata.metadata_sample == {"scorer_type": "match"}

    def test_metadata_repr(self) -> None:
        """Test string representation of CustomTestMetadata."""
        metadata = CustomTestMetadata(
            app="test-app",
            test_name="test_name",
            path="/path/to/test.jsonl",
            sample_count=10,
            metadata_sample={}
        )

        repr_str = repr(metadata)
        assert "test-app" in repr_str
        assert "test_name" in repr_str
        assert "10" in repr_str


# =============================================================================
# Test: Exception Classes
# =============================================================================


@pytest.mark.unit
class TestExceptionClasses:
    """Tests for custom exception classes."""

    def test_custom_test_not_found_error(self) -> None:
        """Test CustomTestNotFoundError exception."""
        error = CustomTestNotFoundError("test-app", "test_name")

        assert "test-app" in str(error)
        assert "test_name" in str(error)
        assert isinstance(error, Exception)

    def test_invalid_custom_test_error(self) -> None:
        """Test InvalidCustomTestError exception."""
        error = InvalidCustomTestError("test_name", "Invalid format")

        assert "test_name" in str(error)
        assert "Invalid format" in str(error)
        assert isinstance(error, Exception)


# =============================================================================
# Integration Test: End-to-End Workflow
# =============================================================================


@pytest.mark.unit
class TestCustomTestWorkflow:
    """Integration tests for complete custom test workflow."""

    def test_complete_workflow(
        self,
        tool_calling_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test complete workflow from discovery to task creation."""
        # 1. Discover tests
        tests = discover_custom_tests(
            app="matric-cli",
            datasets_root=str(custom_test_dir)
        )
        assert len(tests) > 0

        # 2. Get test metadata
        test_meta = tests[0]
        assert test_meta.app == "matric-cli"

        # 3. Load samples
        samples = load_custom_tests(
            app=test_meta.app,
            test_name=test_meta.test_name,
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )
        assert len(samples) > 0

        # 4. Create task
        task = custom_task(
            app=test_meta.app,
            test_name=test_meta.test_name,
            tier="smoke",
            datasets_root=str(custom_test_dir)
        )
        assert isinstance(task, Task)
        assert task.name == f"custom_{test_meta.app}_{test_meta.test_name}"

    def test_multiple_apps_workflow(
        self,
        tool_calling_file: Path,
        title_generation_file: Path,
        custom_test_dir: Path
    ) -> None:
        """Test workflow with multiple apps."""
        # Discover all tests
        all_tests = discover_custom_tests(datasets_root=str(custom_test_dir))
        assert len(all_tests) >= 2

        # Group by app
        by_app: dict[str, list[CustomTestMetadata]] = {}
        for test in all_tests:
            if test.app not in by_app:
                by_app[test.app] = []
            by_app[test.app].append(test)

        # Should have both apps
        assert "matric-cli" in by_app
        assert "matric-memory" in by_app

        # Create tasks for each app
        tasks = []
        for app, tests in by_app.items():
            for test_meta in tests:
                task = custom_task(
                    app=test_meta.app,
                    test_name=test_meta.test_name,
                    tier="smoke",
                    datasets_root=str(custom_test_dir)
                )
                tasks.append(task)

        assert len(tasks) >= 2
