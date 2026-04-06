"""
Project-level scorer for NL2Repo style multi-file project generation.

Evaluates model-generated projects based on:
- Build success (weight: 0.4)
- Test pass rate (weight: 0.6)

The scorer reads execution results from task metadata, which are populated
by the agentic-sandbox after running build and test commands.

Weights:
    BUILD_WEIGHT = 0.4
    TEST_WEIGHT  = 0.6
"""

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

BUILD_WEIGHT = 0.4
TEST_WEIGHT = 0.6


@scorer(metrics=[mean()])
def project_scorer() -> Scorer:
    """Scorer for multi-file project generation evaluation (NL2Repo style).

    Computes a weighted score from two components:
    - Build success (40%): Whether the generated project builds without errors
    - Test pass rate (60%): Fraction of tests that pass after generation

    The scorer reads the following metadata from the task state
    (populated by the agentic-sandbox after execution):
    - "build_success" (bool): Whether the build step succeeded
    - "tests_passed" (int): Number of tests that passed
    - "tests_total" (int): Total number of tests run

    Score formula:
        score = 0.4 * build_score + 0.6 * test_score

    Where:
        build_score = 1.0 if build_success else 0.0
        test_score  = tests_passed / tests_total (0.0 if tests_total == 0)

    Returns:
        Scorer function compatible with Inspect AI
    """

    async def score(state: TaskState, target: Target) -> Score:
        """Score a model-generated project.

        Args:
            state: TaskState with model output and sandbox-populated metadata
            target: Target (unused; correctness determined by build + tests)

        Returns:
            Weighted Score in [0.0, 1.0]
        """
        metadata = state.metadata or {}

        build_success: bool = bool(metadata.get("build_success", False))
        tests_passed: int = int(metadata.get("tests_passed", 0))
        tests_total: int = int(metadata.get("tests_total", 0))

        # Build component
        build_score = 1.0 if build_success else 0.0

        # Test pass rate component
        if tests_total > 0:
            test_score = tests_passed / tests_total
        else:
            test_score = 0.0

        # Weighted combination
        final_score = BUILD_WEIGHT * build_score + TEST_WEIGHT * test_score

        # Clamp to [0.0, 1.0] for safety
        final_score = max(0.0, min(1.0, final_score))

        explanation_parts = [
            f"Build: {'passed' if build_success else 'failed'} ({build_score:.1f})",
            f"Tests: {tests_passed}/{tests_total} ({test_score:.2f})",
            f"Weighted score: {BUILD_WEIGHT} * {build_score:.1f} + {TEST_WEIGHT} * {test_score:.2f} = {final_score:.3f}",
        ]

        return Score(
            value=final_score,
            explanation=" | ".join(explanation_parts),
            metadata={
                "build_success": build_success,
                "build_score": build_score,
                "tests_passed": tests_passed,
                "tests_total": tests_total,
                "test_score": test_score,
                "build_weight": BUILD_WEIGHT,
                "test_weight": TEST_WEIGHT,
            },
        )

    return score
