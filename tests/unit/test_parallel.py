"""
Tests for parallel execution (matric_eval.parallel).

Covers:
- ParallelConfig validation
- ParallelExecutor strategies
- TaskResult and ParallelResult
- ModelEvaluator
- run_parallel_eval convenience function
"""

import time
import pytest
from typing import Any
from unittest.mock import MagicMock

from matric_eval.parallel import (
    EvalTask,
    ModelEvaluator,
    ParallelConfig,
    ParallelExecutor,
    ParallelResult,
    ParallelStrategy,
    TaskResult,
    run_parallel_eval,
)


# =============================================================================
# ParallelStrategy Tests
# =============================================================================


@pytest.mark.unit
class TestParallelStrategy:
    """Tests for ParallelStrategy enum."""

    def test_all_strategies_defined(self) -> None:
        """Should have all strategies."""
        assert ParallelStrategy.SEQUENTIAL == "sequential"
        assert ParallelStrategy.THREAD == "thread"
        assert ParallelStrategy.PROCESS == "process"
        assert ParallelStrategy.ASYNC == "async"


# =============================================================================
# ParallelConfig Tests
# =============================================================================


@pytest.mark.unit
class TestParallelConfig:
    """Tests for ParallelConfig dataclass."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = ParallelConfig()
        assert config.strategy == ParallelStrategy.THREAD
        assert config.max_workers == 4
        assert config.timeout == 300.0
        assert config.retry_on_failure is True
        assert config.max_retries == 3
        assert config.fail_fast is False

    def test_min_workers_enforced(self) -> None:
        """Should enforce minimum of 1 worker."""
        config = ParallelConfig(max_workers=0)
        assert config.max_workers == 1

        config = ParallelConfig(max_workers=-5)
        assert config.max_workers == 1

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = ParallelConfig(
            strategy=ParallelStrategy.ASYNC,
            max_workers=8,
            timeout=600.0,
            retry_on_failure=False,
            max_retries=5,
            fail_fast=True,
        )
        assert config.strategy == ParallelStrategy.ASYNC
        assert config.max_workers == 8
        assert config.timeout == 600.0
        assert config.retry_on_failure is False
        assert config.max_retries == 5
        assert config.fail_fast is True


# =============================================================================
# TaskResult Tests
# =============================================================================


@pytest.mark.unit
class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_successful_result(self) -> None:
        """Should create successful result."""
        result = TaskResult(
            task_id="task_1",
            success=True,
            result={"score": 0.85},
            duration_seconds=1.5,
        )
        assert result.task_id == "task_1"
        assert result.success is True
        assert result.result == {"score": 0.85}
        assert result.error is None

    def test_failed_result(self) -> None:
        """Should create failed result."""
        result = TaskResult(
            task_id="task_2",
            success=False,
            error="Connection timeout",
            duration_seconds=30.0,
            retries=3,
        )
        assert result.task_id == "task_2"
        assert result.success is False
        assert result.result is None
        assert result.error == "Connection timeout"
        assert result.retries == 3


# =============================================================================
# ParallelResult Tests
# =============================================================================


@pytest.mark.unit
class TestParallelResult:
    """Tests for ParallelResult dataclass."""

    def test_empty_result(self) -> None:
        """Should have sensible defaults."""
        result = ParallelResult()
        assert result.total_tasks == 0
        assert result.completed_tasks == 0
        assert result.successful_tasks == 0
        assert result.failed_tasks == 0
        assert len(result.results) == 0

    def test_success_rate_zero_completed(self) -> None:
        """Should return 0.0 when no completed tasks."""
        result = ParallelResult()
        assert result.success_rate == 0.0

    def test_success_rate_calculated(self) -> None:
        """Should calculate success rate correctly."""
        result = ParallelResult(completed_tasks=100, successful_tasks=80)
        assert result.success_rate == 80.0

    def test_get_successful_results(self) -> None:
        """Should return only successful results."""
        result = ParallelResult()
        result.results = [
            TaskResult("t1", success=True, result={"a": 1}),
            TaskResult("t2", success=False, error="fail"),
            TaskResult("t3", success=True, result={"b": 2}),
        ]

        successful = result.get_successful_results()
        assert len(successful) == 2
        assert {"a": 1} in successful
        assert {"b": 2} in successful

    def test_get_errors(self) -> None:
        """Should return errors from failed tasks."""
        result = ParallelResult()
        result.results = [
            TaskResult("t1", success=True, result={}),
            TaskResult("t2", success=False, error="Error 1"),
            TaskResult("t3", success=False, error="Error 2"),
        ]

        errors = result.get_errors()
        assert len(errors) == 2
        assert ("t2", "Error 1") in errors
        assert ("t3", "Error 2") in errors


# =============================================================================
# EvalTask Tests
# =============================================================================


@pytest.mark.unit
class TestEvalTask:
    """Tests for EvalTask dataclass."""

    def test_basic_creation(self) -> None:
        """Should create task with required fields."""
        task = EvalTask(
            task_id="eval_1",
            model="llama3.2:3b",
            benchmark="humaneval",
            samples=[{"id": 1}, {"id": 2}],
        )
        assert task.task_id == "eval_1"
        assert task.model == "llama3.2:3b"
        assert task.benchmark == "humaneval"
        assert len(task.samples) == 2

    def test_with_config(self) -> None:
        """Should accept config dict."""
        task = EvalTask(
            task_id="eval_2",
            model="mistral:7b",
            benchmark="mbpp",
            samples=[],
            config={"temperature": 0.0},
        )
        assert task.config["temperature"] == 0.0


# =============================================================================
# ParallelExecutor Tests
# =============================================================================


@pytest.mark.unit
class TestParallelExecutor:
    """Tests for ParallelExecutor class."""

    def test_context_manager(self) -> None:
        """Should work as context manager."""
        with ParallelExecutor() as executor:
            assert executor is not None

    def test_empty_tasks(self) -> None:
        """Should handle empty task list."""
        with ParallelExecutor() as executor:
            result = executor.execute([], lambda x: x)
            assert result.total_tasks == 0

    def test_sequential_execution(self) -> None:
        """Should execute tasks sequentially."""
        config = ParallelConfig(strategy=ParallelStrategy.SEQUENTIAL)
        results = []

        def track_task(x: int) -> int:
            results.append(x)
            return x * 2

        with ParallelExecutor(config) as executor:
            result = executor.execute([1, 2, 3], track_task)

        assert result.total_tasks == 3
        assert result.completed_tasks == 3
        assert result.successful_tasks == 3
        # Sequential order preserved
        assert results == [1, 2, 3]

    def test_threaded_execution(self) -> None:
        """Should execute tasks with threads."""
        config = ParallelConfig(strategy=ParallelStrategy.THREAD, max_workers=2)

        def slow_task(x: int) -> int:
            time.sleep(0.05)
            return x * 2

        with ParallelExecutor(config) as executor:
            result = executor.execute([1, 2, 3, 4], slow_task)

        assert result.total_tasks == 4
        assert result.successful_tasks == 4

    def test_async_execution(self) -> None:
        """Should execute tasks with asyncio."""
        config = ParallelConfig(strategy=ParallelStrategy.ASYNC, max_workers=2)

        def task(x: int) -> int:
            return x * 2

        with ParallelExecutor(config) as executor:
            result = executor.execute([1, 2, 3], task)

        assert result.total_tasks == 3
        assert result.successful_tasks == 3
        successful_results = result.get_successful_results()
        assert 2 in successful_results
        assert 4 in successful_results
        assert 6 in successful_results

    def test_task_id_function(self) -> None:
        """Should use custom task ID function."""
        config = ParallelConfig(strategy=ParallelStrategy.SEQUENTIAL)

        tasks = [{"name": "a"}, {"name": "b"}]

        with ParallelExecutor(config) as executor:
            result = executor.execute(
                tasks,
                lambda t: t["name"],
                task_id_fn=lambda t: t["name"],
            )

        task_ids = [r.task_id for r in result.results]
        assert "a" in task_ids
        assert "b" in task_ids

    def test_handles_exceptions(self) -> None:
        """Should handle task exceptions."""
        config = ParallelConfig(
            strategy=ParallelStrategy.SEQUENTIAL,
            retry_on_failure=False,
        )

        def failing_task(x: int) -> int:
            if x == 2:
                raise ValueError("Task failed")
            return x

        with ParallelExecutor(config) as executor:
            result = executor.execute([1, 2, 3], failing_task)

        assert result.total_tasks == 3
        assert result.successful_tasks == 2
        assert result.failed_tasks == 1

    def test_retry_logic(self) -> None:
        """Should retry failed tasks."""
        config = ParallelConfig(
            strategy=ParallelStrategy.SEQUENTIAL,
            retry_on_failure=True,
            max_retries=2,
        )

        call_count = [0]

        def sometimes_fails(x: int) -> int:
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ValueError("Transient error")
            return x

        with ParallelExecutor(config) as executor:
            result = executor.execute([1], sometimes_fails)

        # Should succeed after retries
        assert result.successful_tasks == 1
        assert result.results[0].retries >= 1

    def test_fail_fast(self) -> None:
        """Should stop on first failure when fail_fast is True."""
        config = ParallelConfig(
            strategy=ParallelStrategy.SEQUENTIAL,
            fail_fast=True,
            retry_on_failure=False,
        )

        def failing_task(x: int) -> int:
            if x >= 2:
                raise ValueError("Failed")
            return x

        with ParallelExecutor(config) as executor:
            result = executor.execute([1, 2, 3, 4], failing_task)

        # Should stop at first failure (task 2)
        assert result.completed_tasks == 2
        assert result.successful_tasks == 1
        assert result.failed_tasks == 1


# =============================================================================
# ModelEvaluator Tests
# =============================================================================


@pytest.mark.unit
class TestModelEvaluator:
    """Tests for ModelEvaluator class."""

    def test_initialization(self) -> None:
        """Should initialize with models and benchmarks."""
        evaluator = ModelEvaluator(
            models=["llama3.2:3b", "mistral:7b"],
            benchmarks=["humaneval", "mbpp"],
        )
        assert len(evaluator.models) == 2
        assert len(evaluator.benchmarks) == 2

    def test_evaluate_all_parallel(self) -> None:
        """Should evaluate all combinations in parallel."""
        evaluator = ModelEvaluator(
            models=["model_a", "model_b"],
            benchmarks=["bench_1", "bench_2"],
            config=ParallelConfig(strategy=ParallelStrategy.SEQUENTIAL),
        )

        def mock_eval(model: str, benchmark: str) -> dict:
            return {"model": model, "benchmark": benchmark, "score": 0.8}

        results = evaluator.evaluate_all(mock_eval, parallel_models=True)

        assert "model_a" in results
        assert "model_b" in results
        assert "bench_1" in results["model_a"]
        assert "bench_2" in results["model_a"]
        assert results["model_a"]["bench_1"]["score"] == 0.8

    def test_evaluate_sequential_models_parallel_benchmarks(self) -> None:
        """Should evaluate models sequentially with parallel benchmarks."""
        evaluator = ModelEvaluator(
            models=["model_a"],
            benchmarks=["bench_1", "bench_2"],
            config=ParallelConfig(strategy=ParallelStrategy.SEQUENTIAL),
        )

        def mock_eval(model: str, benchmark: str) -> dict:
            return {"model": model, "benchmark": benchmark}

        results = evaluator.evaluate_all(
            mock_eval,
            parallel_models=False,
            parallel_benchmarks=True,
        )

        assert "model_a" in results
        assert "bench_1" in results["model_a"]
        assert "bench_2" in results["model_a"]

    def test_handles_eval_errors(self) -> None:
        """Should handle evaluation errors gracefully."""
        evaluator = ModelEvaluator(
            models=["model_a"],
            benchmarks=["bench_1"],
            config=ParallelConfig(
                strategy=ParallelStrategy.SEQUENTIAL,
                retry_on_failure=False,
            ),
        )

        def failing_eval(model: str, benchmark: str) -> dict:
            raise RuntimeError("Eval failed")

        results = evaluator.evaluate_all(failing_eval, parallel_models=True)

        assert "model_a" in results
        assert "error" in results["model_a"]["bench_1"]

    def test_get_results(self) -> None:
        """Should return stored results."""
        evaluator = ModelEvaluator(
            models=["model_a"],
            benchmarks=["bench_1"],
            config=ParallelConfig(strategy=ParallelStrategy.SEQUENTIAL),
        )

        def mock_eval(model: str, benchmark: str) -> dict:
            return {"result": "success"}

        evaluator.evaluate_all(mock_eval)
        results = evaluator.get_results()

        assert results["model_a"]["bench_1"]["result"] == "success"


# =============================================================================
# run_parallel_eval Tests
# =============================================================================


@pytest.mark.unit
class TestRunParallelEval:
    """Tests for run_parallel_eval convenience function."""

    def test_basic_usage(self) -> None:
        """Should run parallel evaluation."""
        def mock_eval(model: str, benchmark: str) -> dict:
            return {"score": 0.9}

        results = run_parallel_eval(
            models=["model_a", "model_b"],
            benchmarks=["bench_1"],
            eval_fn=mock_eval,
            max_workers=2,
            strategy="sequential",
        )

        assert "model_a" in results
        assert "model_b" in results
        assert results["model_a"]["bench_1"]["score"] == 0.9

    def test_different_strategies(self) -> None:
        """Should support different strategies."""
        def mock_eval(model: str, benchmark: str) -> dict:
            return {"ok": True}

        for strategy in ["sequential", "thread", "async"]:
            results = run_parallel_eval(
                models=["m1"],
                benchmarks=["b1"],
                eval_fn=mock_eval,
                strategy=strategy,
            )
            assert results["m1"]["b1"]["ok"] is True


# =============================================================================
# Performance Tests
# =============================================================================


@pytest.mark.unit
class TestParallelPerformance:
    """Tests for parallel execution performance."""

    def test_parallel_faster_than_sequential(self) -> None:
        """Parallel execution should be faster for I/O-bound tasks."""
        def slow_task(x: int) -> int:
            time.sleep(0.05)
            return x

        tasks = list(range(4))

        # Sequential
        seq_config = ParallelConfig(strategy=ParallelStrategy.SEQUENTIAL)
        with ParallelExecutor(seq_config) as executor:
            seq_result = executor.execute(tasks, slow_task)

        # Threaded
        thread_config = ParallelConfig(strategy=ParallelStrategy.THREAD, max_workers=4)
        with ParallelExecutor(thread_config) as executor:
            thread_result = executor.execute(tasks, slow_task)

        # Threaded should be faster (or at least not significantly slower)
        # Allow for some overhead
        assert thread_result.total_duration_seconds <= seq_result.total_duration_seconds + 0.1
