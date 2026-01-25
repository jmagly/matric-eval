"""
Custom matric test framework for app-specific evaluations.

Provides functionality to load, discover, and execute custom test suites
for matric-cli, matric-memory, and other applications.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import match, model_graded_fact
from inspect_ai.solver import generate, system_message

# =============================================================================
# Constants
# =============================================================================

# Tier sample limits
TIER_LIMITS = {
    "smoke": 5,
    "quick": 20,
    "full": None,  # No limit
}

# Default datasets root directory
DEFAULT_DATASETS_ROOT = "datasets/custom"


# =============================================================================
# Exception Classes
# =============================================================================


class CustomTestNotFoundError(Exception):
    """Raised when a custom test file or app directory is not found."""

    def __init__(self, app: str, test_name: str | None = None) -> None:
        """
        Initialize the error.

        Args:
            app: Application name
            test_name: Test name (optional)
        """
        if test_name:
            message = f"Custom test '{test_name}' not found for app '{app}'"
        else:
            message = f"Custom test directory not found for app '{app}'"
        super().__init__(message)
        self.app = app
        self.test_name = test_name


class InvalidCustomTestError(Exception):
    """Raised when a custom test file has invalid format or structure."""

    def __init__(self, test_name: str, reason: str) -> None:
        """
        Initialize the error.

        Args:
            test_name: Test name
            reason: Reason for invalidity
        """
        message = f"Invalid custom test '{test_name}': {reason}"
        super().__init__(message)
        self.test_name = test_name
        self.reason = reason


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CustomTestMetadata:
    """Metadata about a discovered custom test."""

    app: str
    test_name: str
    path: str
    sample_count: int
    metadata_sample: dict[str, Any]

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"CustomTestMetadata(app='{self.app}', "
            f"test_name='{self.test_name}', "
            f"sample_count={self.sample_count})"
        )


# =============================================================================
# Core Functions
# =============================================================================


def load_custom_tests(
    app: str,
    test_name: str,
    tier: str,
    datasets_root: str | None = None,
) -> list[Sample]:
    """
    Load custom test samples from JSONL file.

    Args:
        app: Application name (e.g., "matric-cli", "matric-memory")
        test_name: Test suite name (e.g., "tool_calling")
        tier: Evaluation tier ("smoke", "quick", "full")
        datasets_root: Root directory for datasets (defaults to ./datasets/custom)

    Returns:
        List of Sample objects

    Raises:
        CustomTestNotFoundError: If test file or app directory not found
        InvalidCustomTestError: If test file has invalid format
    """
    # Determine datasets root
    if datasets_root is None:
        datasets_root = DEFAULT_DATASETS_ROOT

    datasets_path = Path(datasets_root)

    # Check if app directory exists
    app_dir = datasets_path / app
    if not app_dir.exists():
        raise CustomTestNotFoundError(app)

    # Check if test file exists
    test_file = app_dir / f"{test_name}.jsonl"
    if not test_file.exists():
        raise CustomTestNotFoundError(app, test_name)

    # Load samples from JSONL
    samples: list[Sample] = []
    line_num = 0

    try:
        with open(test_file, "r") as f:
            for line in f:
                line_num += 1
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    raise InvalidCustomTestError(
                        test_name,
                        f"Invalid JSON on line {line_num}: {e}"
                    )

                # Validate required fields
                if "id" not in data:
                    raise InvalidCustomTestError(
                        test_name,
                        f"Missing required field 'id' on line {line_num}"
                    )
                if "prompt" not in data:
                    raise InvalidCustomTestError(
                        test_name,
                        f"Missing required field 'prompt' on line {line_num}"
                    )
                if "expected" not in data:
                    raise InvalidCustomTestError(
                        test_name,
                        f"Missing required field 'expected' on line {line_num}"
                    )

                # Convert to Sample format
                # - prompt -> input
                # - expected -> target (store original in metadata)
                # - scorer_type and other fields -> metadata
                expected = data["expected"]
                metadata = {k: v for k, v in data.items() if k not in ["id", "prompt", "expected"]}

                # Store original expected value in metadata for scorer access
                metadata["expected_value"] = expected

                # Convert target to string format for Inspect AI
                # For structured data (dict/list), serialize to JSON string
                if isinstance(expected, (dict, list)):
                    target_str = json.dumps(expected)
                else:
                    target_str = str(expected)

                sample = Sample(
                    id=data["id"],
                    input=data["prompt"],
                    target=target_str,
                    metadata=metadata,
                )
                samples.append(sample)

    except (OSError, IOError) as e:
        raise InvalidCustomTestError(test_name, f"Error reading file: {e}")

    # Apply tier sampling
    limit = TIER_LIMITS.get(tier)
    if limit is not None and len(samples) > limit:
        samples = samples[:limit]

    return samples


def custom_task(
    app: str,
    test_name: str,
    tier: str,
    datasets_root: str | None = None,
) -> Task:
    """
    Create an Inspect AI task for custom tests.

    Args:
        app: Application name
        test_name: Test suite name
        tier: Evaluation tier
        datasets_root: Root directory for datasets (optional)

    Returns:
        Configured Task object

    Raises:
        CustomTestNotFoundError: If test not found
        InvalidCustomTestError: If test has invalid format
    """
    # Load samples
    samples = load_custom_tests(app, test_name, tier, datasets_root)

    # Auto-detect scorer type from first sample metadata
    scorer_type = "match"  # default
    if samples and samples[0].metadata:
        scorer_type = samples[0].metadata.get("scorer_type", "match")

    # Select scorer based on type
    scorer = _get_scorer_for_type(scorer_type)

    # Create task
    task_name = f"custom_{app}_{test_name}"

    return Task(
        dataset=MemoryDataset(samples),
        solver=[
            system_message(_get_system_message_for_scorer_type(scorer_type)),
            generate(),
        ],
        scorer=scorer,
        name=task_name,
    )


def discover_custom_tests(
    app: str | None = None,
    datasets_root: str | None = None,
) -> list[CustomTestMetadata]:
    """
    Discover available custom test files.

    Args:
        app: Optional application name to filter by
        datasets_root: Root directory for datasets (optional)

    Returns:
        List of CustomTestMetadata objects, sorted by app and test name
    """
    # Determine datasets root
    if datasets_root is None:
        datasets_root = DEFAULT_DATASETS_ROOT

    datasets_path = Path(datasets_root)

    if not datasets_path.exists():
        return []

    results: list[CustomTestMetadata] = []

    # Get app directories to scan
    if app:
        app_dirs = [datasets_path / app] if (datasets_path / app).exists() else []
    else:
        app_dirs = [d for d in datasets_path.iterdir() if d.is_dir()]

    # Scan each app directory
    for app_dir in app_dirs:
        app_name = app_dir.name

        # Find all .jsonl files
        for test_file in app_dir.glob("*.jsonl"):
            test_name = test_file.stem

            try:
                # Read first line to get metadata sample
                metadata_sample: dict[str, Any] = {}
                sample_count = 0

                with open(test_file, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue

                        sample_count += 1

                        # Get metadata from first sample
                        if sample_count == 1:
                            try:
                                data = json.loads(line)
                                metadata_sample = {
                                    k: v for k, v in data.items()
                                    if k not in ["id", "prompt", "expected"]
                                }
                            except json.JSONDecodeError:
                                # Skip corrupted files
                                pass

                # Only add if we successfully read at least one sample
                if sample_count > 0:
                    results.append(
                        CustomTestMetadata(
                            app=app_name,
                            test_name=test_name,
                            path=str(test_file),
                            sample_count=sample_count,
                            metadata_sample=metadata_sample,
                        )
                    )

            except (OSError, IOError):
                # Skip files that can't be read
                continue

    # Sort by app name, then test name
    results.sort(key=lambda x: (x.app, x.test_name))

    return results


# =============================================================================
# Helper Functions
# =============================================================================


def _get_scorer_for_type(scorer_type: str) -> Any:
    """
    Get scorer based on type.

    Args:
        scorer_type: Type of scorer

    Returns:
        Scorer instance
    """
    if scorer_type == "tool_match":
        # For tool calling, use match scorer with exact matching
        return match()
    elif scorer_type == "workflow_match":
        # For workflow/agent scenarios, use match scorer
        return match()
    elif scorer_type == "semantic_similarity":
        # For semantic similarity, use model-graded scoring
        return model_graded_fact()
    else:
        # Default to match
        return match()


def _get_system_message_for_scorer_type(scorer_type: str) -> str:
    """
    Get system message based on scorer type.

    Args:
        scorer_type: Type of scorer

    Returns:
        System message string
    """
    if scorer_type == "tool_match":
        return (
            "You are a helpful assistant that can use tools. "
            "When asked to perform a task, respond with the appropriate tool call."
        )
    elif scorer_type == "workflow_match":
        return (
            "You are an AI agent that can plan and execute multi-step workflows. "
            "Break down complex tasks into steps and execute them systematically."
        )
    elif scorer_type == "semantic_similarity":
        return (
            "You are a helpful assistant. Provide clear, accurate, and concise responses."
        )
    else:
        return "You are a helpful assistant."
