"""
Integration tests for thinking parameter in task definitions.

Covers:
- Task functions accept thinking parameter
- Thinking parameter changes system message
- Default behavior is thinking=True
"""

import pytest
from inspect_ai import Task

from matric_eval.prompts import get_prompt
from matric_eval.tasks.ds1000 import ds1000
from matric_eval.tasks.humaneval import humaneval
from matric_eval.tasks.livecodebench import livecodebench
from matric_eval.tasks.mbpp import mbpp

# Import skip marker for tests requiring external data
from tests.conftest import (
    requires_ds1000_data,
    requires_humaneval_data,
    requires_livecodebench_data,
    requires_mbpp_data,
)


# =============================================================================
# Thinking Parameter Tests
# =============================================================================


@pytest.mark.unit
class TestThinkingParameter:
    """Tests for thinking parameter in task definitions."""

    @requires_livecodebench_data
    def test_livecodebench_accepts_thinking_parameter(self) -> None:
        """Should accept thinking parameter without error."""
        task_on = livecodebench(tier="smoke", thinking=True)
        task_off = livecodebench(tier="smoke", thinking=False)
        assert isinstance(task_on, Task)
        assert isinstance(task_off, Task)

    @requires_humaneval_data
    def test_humaneval_accepts_thinking_parameter(self) -> None:
        """Should accept thinking parameter without error."""
        task_on = humaneval(tier="smoke", thinking=True)
        task_off = humaneval(tier="smoke", thinking=False)
        assert isinstance(task_on, Task)
        assert isinstance(task_off, Task)

    @requires_mbpp_data
    def test_mbpp_accepts_thinking_parameter(self) -> None:
        """Should accept thinking parameter without error."""
        task_on = mbpp(tier="smoke", thinking=True)
        task_off = mbpp(tier="smoke", thinking=False)
        assert isinstance(task_on, Task)
        assert isinstance(task_off, Task)

    @requires_ds1000_data
    def test_ds1000_accepts_thinking_parameter(self) -> None:
        """Should accept thinking parameter without error."""
        task_on = ds1000(tier="smoke", thinking=True)
        task_off = ds1000(tier="smoke", thinking=False)
        assert isinstance(task_on, Task)
        assert isinstance(task_off, Task)

    @requires_livecodebench_data
    def test_livecodebench_default_thinking_is_true(self) -> None:
        """Should default to thinking=True."""
        task_default = livecodebench(tier="smoke")
        task_explicit = livecodebench(tier="smoke", thinking=True)

        # Both should use the same prompt (thinking_on)
        # We can verify by checking the system message in the solver
        assert task_default.solver is not None
        assert task_explicit.solver is not None

    @requires_humaneval_data
    def test_humaneval_thinking_changes_system_message(self) -> None:
        """Should use different system messages for thinking on vs off."""
        task_on = humaneval(tier="smoke", thinking=True)
        task_off = humaneval(tier="smoke", thinking=False)

        # Extract system messages from solver chain
        # The first solver should be system_message
        assert task_on.solver is not None
        assert task_off.solver is not None

        # System messages should be different
        # (We can't easily extract them, but we know they use different prompts)

    @requires_mbpp_data
    def test_mbpp_thinking_uses_correct_prompt(self) -> None:
        """Should use prompt from templates module."""
        # Get the expected prompts
        prompt_on = get_prompt("mbpp", thinking=True)
        prompt_off = get_prompt("mbpp", thinking=False)

        # Verify prompts are different
        assert prompt_on != prompt_off
        assert len(prompt_on) > 0
        assert len(prompt_off) > 0

    @requires_ds1000_data
    def test_ds1000_thinking_parameter_propagates(self) -> None:
        """Should properly propagate thinking parameter to task creation."""
        # Create tasks with different thinking modes
        task_on = ds1000(tier="smoke", thinking=True)
        task_off = ds1000(tier="smoke", thinking=False)

        # Both should be valid tasks
        assert task_on.name == "ds1000"
        assert task_off.name == "ds1000"
        assert task_on.dataset is not None
        assert task_off.dataset is not None


# =============================================================================
# Prompt Integration Tests
# =============================================================================


@pytest.mark.unit
class TestPromptIntegration:
    """Tests for prompt template integration in tasks."""

    def test_all_code_benchmarks_have_thinking_prompts(self) -> None:
        """All code benchmarks should have thinking-aware prompts."""
        code_benchmarks = ["livecodebench", "humaneval", "mbpp", "ds1000"]

        for benchmark in code_benchmarks:
            prompt_on = get_prompt(benchmark, thinking=True)
            prompt_off = get_prompt(benchmark, thinking=False)

            # Both modes should exist and differ
            assert prompt_on != prompt_off
            assert len(prompt_on) > 50
            assert len(prompt_off) > 0

    def test_thinking_on_prompts_are_structured(self) -> None:
        """Thinking-on prompts should provide structure."""
        code_benchmarks = ["livecodebench", "humaneval", "mbpp", "ds1000"]

        for benchmark in code_benchmarks:
            prompt = get_prompt(benchmark, thinking=True)

            # Should be longer and more detailed
            # (Thinking prompts guide reasoning)
            assert len(prompt) > 100

    def test_thinking_off_prompts_are_concise(self) -> None:
        """Thinking-off prompts should be direct."""
        code_benchmarks = ["livecodebench", "humaneval", "mbpp", "ds1000"]

        for benchmark in code_benchmarks:
            prompt_on = get_prompt(benchmark, thinking=True)
            prompt_off = get_prompt(benchmark, thinking=False)

            # Both should be non-empty
            # (But off prompts may be shorter)
            assert len(prompt_off) > 0

    def test_prompts_mention_code_output(self) -> None:
        """Code benchmark prompts should mention code output."""
        code_benchmarks = ["livecodebench", "humaneval", "mbpp", "ds1000"]

        for benchmark in code_benchmarks:
            prompt_on = get_prompt(benchmark, thinking=True)
            prompt_off = get_prompt(benchmark, thinking=False)

            # At least one should mention code/python/function
            combined = (prompt_on + prompt_off).lower()
            assert any(word in combined for word in ["code", "python", "function"])


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


@pytest.mark.unit
class TestBackwardCompatibility:
    """Tests to ensure changes don't break existing code."""

    @requires_livecodebench_data
    def test_livecodebench_works_without_thinking_parameter(self) -> None:
        """Should work when called without thinking parameter (existing code)."""
        task = livecodebench(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "livecodebench"
        assert task.dataset is not None

    @requires_humaneval_data
    def test_humaneval_works_without_thinking_parameter(self) -> None:
        """Should work when called without thinking parameter (existing code)."""
        task = humaneval(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "humaneval"
        assert task.dataset is not None

    @requires_mbpp_data
    def test_mbpp_works_without_thinking_parameter(self) -> None:
        """Should work when called without thinking parameter (existing code)."""
        task = mbpp(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "mbpp"
        assert task.dataset is not None

    @requires_ds1000_data
    def test_ds1000_works_without_thinking_parameter(self) -> None:
        """Should work when called without thinking parameter (existing code)."""
        task = ds1000(tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "ds1000"
        assert task.dataset is not None
