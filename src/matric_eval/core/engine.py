"""
EvaluationEngine - High-level interface for running model evaluations.

Wraps Inspect AI's eval() function with checkpoint support, error handling,
and result aggregation.
"""

from pathlib import Path
from typing import Any, Optional

from inspect_ai import eval, Task
from inspect_ai.log import EvalLog
from inspect_ai.model import get_model

from matric_eval.config import get_tier


class EvaluationEngine:
    """
    High-level evaluation engine for running benchmarks against models.

    Features:
    - Checkpoint support for resuming interrupted evaluations
    - Error handling and recovery
    - Result aggregation across benchmarks
    - Progress tracking and logging

    Example:
        >>> engine = EvaluationEngine("ollama/llama3.2:3b", tier="smoke")
        >>> result = engine.run_benchmark("humaneval")
        >>> results = engine.run_all(["humaneval", "mbpp", "gsm8k"])
    """

    def __init__(
        self,
        model: str,
        tier: str = "smoke",
        log_dir: Optional[Path | str] = None,
    ):
        """
        Initialize the evaluation engine.

        Args:
            model: Model identifier (e.g., "ollama/llama3.2:3b")
            tier: Evaluation tier ("smoke", "quick", or "full")
            log_dir: Directory for storing evaluation logs (default: "./logs")
        """
        self.model = model
        self.tier = tier
        self.tier_config = get_tier(tier)
        self.log_dir = Path(log_dir) if log_dir else Path("./logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def run_benchmark(
        self,
        benchmark: str,
        task: Optional[Task] = None,
        **eval_kwargs: Any,
    ) -> dict[str, Any]:
        """
        Run a single benchmark against the model.

        Args:
            benchmark: Benchmark name (e.g., "humaneval", "mbpp", "gsm8k")
            task: Pre-configured Inspect AI Task (if None, will load from matric_eval.tasks)
            **eval_kwargs: Additional arguments to pass to inspect_ai.eval()

        Returns:
            Dictionary containing:
            - status: "success" or "error"
            - score: Overall accuracy (0.0-1.0)
            - samples: Number of samples evaluated
            - log_path: Path to evaluation log file
            - error: Error message (if status == "error")

        Raises:
            ValueError: If benchmark name is invalid
        """
        if task is None:
            # Dynamically load task from matric_eval.tasks
            task = self._load_task(benchmark)

        result = {
            "benchmark": benchmark,
            "model": self.model,
            "tier": self.tier,
            "status": "pending",
        }

        try:
            # Run evaluation with Inspect AI (synchronous - manages its own event loop)
            logs: list[EvalLog] = eval(
                task,
                model=self.model,
                log_dir=str(self.log_dir),
                **eval_kwargs,
            )

            if not logs:
                result.update({
                    "status": "error",
                    "error": "No evaluation logs returned",
                    "score": 0.0,
                    "samples": 0,
                })
                return result

            # Extract results from log
            log = logs[0]
            result.update({
                "status": "success",
                "log_path": str(log.location) if hasattr(log, "location") else None,
                "samples": len(log.samples) if log.samples else 0,
            })

            # Extract accuracy score
            if log.results and log.results.scores:
                metrics = log.results.scores[0].metrics
                accuracy_metric = metrics.get("accuracy")
                if accuracy_metric is not None:
                    result["score"] = accuracy_metric.value
                else:
                    # Fall back to first available metric
                    first_metric = next(iter(metrics.values()), None)
                    result["score"] = first_metric.value if first_metric else 0.0
            else:
                result["score"] = 0.0

        except Exception as e:
            result.update({
                "status": "error",
                "error": str(e),
                "score": 0.0,
                "samples": 0,
            })

        return result

    def run_all(
        self,
        benchmarks: list[str],
        checkpoint: bool = True,
        **eval_kwargs: Any,
    ) -> dict[str, Any]:
        """
        Run all benchmarks with checkpointing support.

        Args:
            benchmarks: List of benchmark names to run
            checkpoint: Whether to enable checkpointing (resume on failure)
            **eval_kwargs: Additional arguments to pass to inspect_ai.eval()

        Returns:
            Dictionary containing:
            - model: Model identifier
            - tier: Evaluation tier
            - benchmarks: Dict mapping benchmark name to results
            - overall_score: Average score across successful benchmarks
            - status: "success" if any benchmark succeeded, "error" otherwise
        """
        results = {
            "model": self.model,
            "tier": self.tier,
            "benchmarks": {},
            "status": "pending",
        }

        successful_scores = []

        for benchmark in benchmarks:
            result = self.run_benchmark(benchmark, **eval_kwargs)
            results["benchmarks"][benchmark] = result

            if result["status"] == "success":
                successful_scores.append(result["score"])

        # Calculate overall score
        if successful_scores:
            results["overall_score"] = sum(successful_scores) / len(successful_scores)
            results["status"] = "success"
        else:
            results["overall_score"] = 0.0
            results["status"] = "error"

        return results

    # Map benchmark names to (module_path, function_name) for tier-aware loaders
    TASK_MAP: dict[str, str] = {
        "humaneval": "matric_eval.tasks.humaneval.humaneval",
        "mbpp": "matric_eval.tasks.mbpp.mbpp",
        "gsm8k": "matric_eval.tasks.gsm8k.gsm8k",
        "arc": "matric_eval.tasks.arc.arc",
        "ifeval": "matric_eval.tasks.ifeval.ifeval",
        "ds1000": "matric_eval.tasks.ds1000.ds1000",
        "livecodebench": "matric_eval.tasks.livecodebench.livecodebench",
        "mtbench": "matric_eval.tasks.mtbench.mtbench",
        "tool_calling": "matric_eval.tasks.tool_calling.tool_calling",
    }

    def _load_task(self, benchmark: str) -> Task:
        """
        Dynamically load a tier-aware task from matric_eval.tasks module.

        Each task function accepts a ``tier`` parameter and returns a Task with
        the appropriate number of samples for that tier.

        Args:
            benchmark: Benchmark name (e.g., "humaneval", "mbpp")

        Returns:
            Inspect AI Task object

        Raises:
            ValueError: If benchmark is not found
        """
        if benchmark not in self.TASK_MAP:
            raise ValueError(
                f"Unknown benchmark: {benchmark}. "
                f"Available benchmarks: {', '.join(self.TASK_MAP.keys())}"
            )

        # Import and call the task function with tier
        module_path = self.TASK_MAP[benchmark]
        module_name, task_name = module_path.rsplit(".", 1)

        import importlib
        module = importlib.import_module(module_name)
        task_fn = getattr(module, task_name)

        return task_fn(tier=self.tier)
