"""
Parallel model evaluation for matric-eval.

Provides concurrent execution of evaluations across:
- Multiple models (e.g., llama3.2:3b, mistral:7b, etc.)
- Multiple benchmarks (e.g., humaneval, mbpp, gsm8k, etc.)
- Multiple samples within a benchmark

Supports both process-based and async parallelism.
"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar

from matric_eval.logging import EvalMetrics, configure_logging, get_logger, set_context

T = TypeVar("T")
R = TypeVar("R")

logger = get_logger("parallel")


class ParallelStrategy(str, Enum):
    """Parallelization strategy."""

    SEQUENTIAL = "sequential"
    THREAD = "thread"
    PROCESS = "process"
    ASYNC = "async"


@dataclass
class ParallelConfig:
    """Configuration for parallel execution."""

    strategy: ParallelStrategy = ParallelStrategy.THREAD
    max_workers: int = 4
    timeout: float = 300.0  # 5 minutes per task
    retry_on_failure: bool = True
    max_retries: int = 3
    fail_fast: bool = False  # Stop all on first failure

    def __post_init__(self) -> None:
        """Validate and adjust configuration."""
        if self.max_workers < 1:
            self.max_workers = 1

        # Limit process workers to CPU count
        cpu_count = os.cpu_count() or 4
        if self.strategy == ParallelStrategy.PROCESS:
            self.max_workers = min(self.max_workers, cpu_count)


@dataclass
class TaskResult(Generic[R]):
    """Result of a parallel task."""

    task_id: str
    success: bool
    result: Optional[R] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    retries: int = 0


@dataclass
class ParallelResult(Generic[R]):
    """Aggregated result of parallel execution."""

    total_tasks: int = 0
    completed_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    results: list[TaskResult[R]] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Return success percentage."""
        if self.completed_tasks == 0:
            return 0.0
        return (self.successful_tasks / self.completed_tasks) * 100

    def get_successful_results(self) -> list[R]:
        """Return list of successful results."""
        return [r.result for r in self.results if r.success and r.result is not None]

    def get_errors(self) -> list[tuple[str, str]]:
        """Return list of (task_id, error) for failed tasks."""
        return [(r.task_id, r.error or "Unknown error") for r in self.results if not r.success]


@dataclass
class EvalTask:
    """Evaluation task definition."""

    task_id: str
    model: str
    benchmark: str
    samples: list[dict[str, Any]]
    config: dict[str, Any] = field(default_factory=dict)


class ParallelExecutor:
    """
    Parallel executor for evaluation tasks.

    Supports multiple parallelization strategies:
    - Sequential: No parallelism, useful for debugging
    - Thread: Thread pool for I/O-bound tasks
    - Process: Process pool for CPU-bound tasks
    - Async: Asyncio for cooperative multitasking
    """

    def __init__(self, config: Optional[ParallelConfig] = None) -> None:
        """Initialize executor."""
        self.config = config or ParallelConfig()
        self._executor: Optional[ProcessPoolExecutor | ThreadPoolExecutor] = None
        self._shutdown = False

    def __enter__(self) -> ParallelExecutor:
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        self.shutdown()

    def shutdown(self) -> None:
        """Shutdown executor."""
        self._shutdown = True
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None

    def execute(
        self,
        tasks: list[T],
        task_fn: Callable[[T], R],
        task_id_fn: Optional[Callable[[T], str]] = None,
    ) -> ParallelResult[R]:
        """
        Execute tasks in parallel.

        Args:
            tasks: List of tasks to execute
            task_fn: Function to execute for each task
            task_id_fn: Optional function to extract task ID

        Returns:
            ParallelResult containing all task results
        """
        if not tasks:
            return ParallelResult()

        result = ParallelResult(total_tasks=len(tasks))

        strategy = self.config.strategy
        if strategy == ParallelStrategy.SEQUENTIAL:
            result = self._execute_sequential(tasks, task_fn, task_id_fn)
        elif strategy == ParallelStrategy.THREAD:
            result = self._execute_threaded(tasks, task_fn, task_id_fn)
        elif strategy == ParallelStrategy.PROCESS:
            result = self._execute_process(tasks, task_fn, task_id_fn)
        elif strategy == ParallelStrategy.ASYNC:
            result = asyncio.run(self._execute_async(tasks, task_fn, task_id_fn))

        return result

    def _execute_sequential(
        self,
        tasks: list[T],
        task_fn: Callable[[T], R],
        task_id_fn: Optional[Callable[[T], str]] = None,
    ) -> ParallelResult[R]:
        """Execute tasks sequentially."""
        import time

        result = ParallelResult(total_tasks=len(tasks))
        start_time = time.time()

        for i, task in enumerate(tasks):
            if self._shutdown:
                break

            task_id = task_id_fn(task) if task_id_fn else str(i)
            task_start = time.time()

            try:
                task_result = self._execute_with_retry(task, task_fn, task_id)
                result.results.append(task_result)
                result.completed_tasks += 1

                if task_result.success:
                    result.successful_tasks += 1
                else:
                    result.failed_tasks += 1
                    if self.config.fail_fast:
                        break

            except Exception as e:
                task_result = TaskResult(
                    task_id=task_id,
                    success=False,
                    error=str(e),
                    duration_seconds=time.time() - task_start,
                )
                result.results.append(task_result)
                result.completed_tasks += 1
                result.failed_tasks += 1

                if self.config.fail_fast:
                    break

        result.total_duration_seconds = time.time() - start_time
        return result

    def _execute_threaded(
        self,
        tasks: list[T],
        task_fn: Callable[[T], R],
        task_id_fn: Optional[Callable[[T], str]] = None,
    ) -> ParallelResult[R]:
        """Execute tasks using thread pool."""
        import time

        result = ParallelResult(total_tasks=len(tasks))
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            self._executor = executor
            futures = {}

            for i, task in enumerate(tasks):
                task_id = task_id_fn(task) if task_id_fn else str(i)
                future = executor.submit(self._execute_with_retry, task, task_fn, task_id)
                futures[future] = (task_id, time.time())

            for future in as_completed(futures):
                if self._shutdown:
                    break

                task_id, task_start = futures[future]

                try:
                    task_result = future.result(timeout=self.config.timeout)
                    result.results.append(task_result)
                    result.completed_tasks += 1

                    if task_result.success:
                        result.successful_tasks += 1
                    else:
                        result.failed_tasks += 1
                        if self.config.fail_fast:
                            self._shutdown = True

                except TimeoutError:
                    task_result = TaskResult(
                        task_id=task_id,
                        success=False,
                        error="Task timed out",
                        duration_seconds=self.config.timeout,
                    )
                    result.results.append(task_result)
                    result.completed_tasks += 1
                    result.failed_tasks += 1

                except Exception as e:
                    task_result = TaskResult(
                        task_id=task_id,
                        success=False,
                        error=str(e),
                        duration_seconds=time.time() - task_start,
                    )
                    result.results.append(task_result)
                    result.completed_tasks += 1
                    result.failed_tasks += 1

        result.total_duration_seconds = time.time() - start_time
        return result

    def _execute_process(
        self,
        tasks: list[T],
        task_fn: Callable[[T], R],
        task_id_fn: Optional[Callable[[T], str]] = None,
    ) -> ParallelResult[R]:
        """Execute tasks using process pool."""
        import time

        result = ParallelResult(total_tasks=len(tasks))
        start_time = time.time()

        # Note: Process pool requires picklable functions and data
        # For complex tasks, consider using thread pool or async
        with ProcessPoolExecutor(max_workers=self.config.max_workers) as executor:
            self._executor = executor
            futures = {}

            for i, task in enumerate(tasks):
                task_id = task_id_fn(task) if task_id_fn else str(i)
                # Wrap in simple tuple for pickling
                future = executor.submit(_process_worker, task, task_fn, task_id)
                futures[future] = (task_id, time.time())

            for future in as_completed(futures):
                if self._shutdown:
                    break

                task_id, task_start = futures[future]

                try:
                    task_result = future.result(timeout=self.config.timeout)
                    result.results.append(task_result)
                    result.completed_tasks += 1

                    if task_result.success:
                        result.successful_tasks += 1
                    else:
                        result.failed_tasks += 1

                except TimeoutError:
                    task_result = TaskResult(
                        task_id=task_id,
                        success=False,
                        error="Process timed out",
                        duration_seconds=self.config.timeout,
                    )
                    result.results.append(task_result)
                    result.completed_tasks += 1
                    result.failed_tasks += 1

                except Exception as e:
                    task_result = TaskResult(
                        task_id=task_id,
                        success=False,
                        error=str(e),
                        duration_seconds=time.time() - task_start,
                    )
                    result.results.append(task_result)
                    result.completed_tasks += 1
                    result.failed_tasks += 1

        result.total_duration_seconds = time.time() - start_time
        return result

    async def _execute_async(
        self,
        tasks: list[T],
        task_fn: Callable[[T], R],
        task_id_fn: Optional[Callable[[T], str]] = None,
    ) -> ParallelResult[R]:
        """Execute tasks using asyncio."""
        import time

        result = ParallelResult(total_tasks=len(tasks))
        start_time = time.time()

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.config.max_workers)

        async def run_task(task: T, task_id: str) -> TaskResult[R]:
            async with semaphore:
                task_start = time.time()
                try:
                    # Run sync function in executor
                    loop = asyncio.get_event_loop()
                    task_result = await asyncio.wait_for(
                        loop.run_in_executor(None, task_fn, task),
                        timeout=self.config.timeout,
                    )
                    return TaskResult(
                        task_id=task_id,
                        success=True,
                        result=task_result,
                        duration_seconds=time.time() - task_start,
                    )
                except asyncio.TimeoutError:
                    return TaskResult(
                        task_id=task_id,
                        success=False,
                        error="Task timed out",
                        duration_seconds=self.config.timeout,
                    )
                except Exception as e:
                    return TaskResult(
                        task_id=task_id,
                        success=False,
                        error=str(e),
                        duration_seconds=time.time() - task_start,
                    )

        # Create all tasks
        async_tasks = []
        for i, task in enumerate(tasks):
            task_id = task_id_fn(task) if task_id_fn else str(i)
            async_tasks.append(run_task(task, task_id))

        # Run all tasks
        task_results = await asyncio.gather(*async_tasks, return_exceptions=True)

        for task_result in task_results:
            if isinstance(task_result, TaskResult):
                result.results.append(task_result)
                result.completed_tasks += 1
                if task_result.success:
                    result.successful_tasks += 1
                else:
                    result.failed_tasks += 1
            else:
                # Exception
                result.completed_tasks += 1
                result.failed_tasks += 1

        result.total_duration_seconds = time.time() - start_time
        return result

    def _execute_with_retry(
        self,
        task: T,
        task_fn: Callable[[T], R],
        task_id: str,
    ) -> TaskResult[R]:
        """Execute task with retry logic."""
        import time

        last_error: Optional[str] = None
        retries = 0
        task_start = time.time()

        while retries <= self.config.max_retries:
            try:
                result = task_fn(task)
                return TaskResult(
                    task_id=task_id,
                    success=True,
                    result=result,
                    duration_seconds=time.time() - task_start,
                    retries=retries,
                )
            except Exception as e:
                last_error = str(e)
                retries += 1

                if not self.config.retry_on_failure or retries > self.config.max_retries:
                    break

                # Exponential backoff
                time.sleep(0.5 * (2**retries))

        return TaskResult(
            task_id=task_id,
            success=False,
            error=last_error,
            duration_seconds=time.time() - task_start,
            retries=retries,
        )


def _process_worker(task: T, task_fn: Callable[[T], R], task_id: str) -> TaskResult[R]:
    """Worker function for process pool (must be top-level for pickling)."""
    import time

    task_start = time.time()
    try:
        result = task_fn(task)
        return TaskResult(
            task_id=task_id,
            success=True,
            result=result,
            duration_seconds=time.time() - task_start,
        )
    except Exception as e:
        return TaskResult(
            task_id=task_id,
            success=False,
            error=str(e),
            duration_seconds=time.time() - task_start,
        )


class ModelEvaluator:
    """
    High-level interface for parallel model evaluation.

    Coordinates evaluation across multiple models and benchmarks.
    """

    def __init__(
        self,
        models: list[str],
        benchmarks: list[str],
        config: Optional[ParallelConfig] = None,
    ) -> None:
        """Initialize evaluator."""
        self.models = models
        self.benchmarks = benchmarks
        self.config = config or ParallelConfig()
        self._results: dict[str, dict[str, Any]] = {}

    def evaluate_all(
        self,
        eval_fn: Callable[[str, str], dict[str, Any]],
        parallel_models: bool = True,
        parallel_benchmarks: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """
        Evaluate all models across all benchmarks.

        Args:
            eval_fn: Function that takes (model, benchmark) and returns results
            parallel_models: Run models in parallel
            parallel_benchmarks: Run benchmarks in parallel (within each model)

        Returns:
            Dict mapping model -> benchmark -> results
        """
        results: dict[str, dict[str, Any]] = {}

        if parallel_models:
            # Create tasks for all model-benchmark combinations
            tasks = [(model, benchmark) for model in self.models for benchmark in self.benchmarks]

            executor = ParallelExecutor(self.config)
            parallel_result = executor.execute(
                tasks,
                lambda t: eval_fn(t[0], t[1]),
                lambda t: f"{t[0]}:{t[1]}",
            )

            # Organize results
            for task_result in parallel_result.results:
                model, benchmark = task_result.task_id.split(":", 1)
                if model not in results:
                    results[model] = {}
                results[model][benchmark] = (
                    task_result.result if task_result.success else {"error": task_result.error}
                )

            logger.info(
                f"Parallel evaluation complete: {parallel_result.successful_tasks}/"
                f"{parallel_result.total_tasks} successful in "
                f"{parallel_result.total_duration_seconds:.1f}s"
            )

        else:
            # Sequential model evaluation
            for model in self.models:
                set_context(model=model)
                results[model] = {}

                if parallel_benchmarks:
                    executor = ParallelExecutor(self.config)
                    parallel_result = executor.execute(
                        self.benchmarks,
                        lambda b: eval_fn(model, b),
                        lambda b: b,
                    )

                    for task_result in parallel_result.results:
                        results[model][task_result.task_id] = (
                            task_result.result
                            if task_result.success
                            else {"error": task_result.error}
                        )
                else:
                    # Sequential benchmark evaluation
                    for benchmark in self.benchmarks:
                        set_context(benchmark=benchmark)
                        try:
                            results[model][benchmark] = eval_fn(model, benchmark)
                        except Exception as e:
                            results[model][benchmark] = {"error": str(e)}

        self._results = results
        return results

    def get_results(self) -> dict[str, dict[str, Any]]:
        """Return stored results."""
        return self._results


def run_parallel_eval(
    models: list[str],
    benchmarks: list[str],
    eval_fn: Callable[[str, str], dict[str, Any]],
    max_workers: int = 4,
    strategy: str = "thread",
) -> dict[str, dict[str, Any]]:
    """
    Convenience function for parallel model evaluation.

    Args:
        models: List of model names
        benchmarks: List of benchmark names
        eval_fn: Evaluation function (model, benchmark) -> results
        max_workers: Maximum parallel workers
        strategy: Parallelization strategy (sequential, thread, process, async)

    Returns:
        Results dict mapping model -> benchmark -> results
    """
    config = ParallelConfig(
        strategy=ParallelStrategy(strategy),
        max_workers=max_workers,
    )

    evaluator = ModelEvaluator(models, benchmarks, config)
    return evaluator.evaluate_all(eval_fn, parallel_models=True)


__all__ = [
    "EvalTask",
    "ModelEvaluator",
    "ParallelConfig",
    "ParallelExecutor",
    "ParallelResult",
    "ParallelStrategy",
    "TaskResult",
    "run_parallel_eval",
]
