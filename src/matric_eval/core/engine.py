"""
EvaluationEngine - High-level interface for running model evaluations.

Wraps Inspect AI's eval() function with checkpoint support, error handling,
and result aggregation. Supports multiple inference providers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from inspect_ai import eval, Task
from inspect_ai.log import EvalLog
from inspect_ai.model import GenerateConfig

from matric_eval.config import get_tier


class EvaluationEngine:
    """
    High-level evaluation engine for running benchmarks against models.

    Features:
    - Checkpoint support for resuming interrupted evaluations
    - Error handling and recovery
    - Result aggregation across benchmarks
    - Progress tracking and logging
    - Thinking mode support for thinking-capable models
    - Multi-provider support (Ollama, vLLM, llama.cpp, OpenRouter, Chutes)

    Example:
        >>> engine = EvaluationEngine("ollama/llama3.2:3b", tier="smoke")
        >>> result = engine.run_benchmark("humaneval")
        >>> results = engine.run_all(["humaneval", "mbpp", "gsm8k"])

        >>> # With a specific provider
        >>> from matric_eval.providers import get_provider
        >>> provider = get_provider("vllm")
        >>> engine = EvaluationEngine("mistral:7b", tier="smoke", provider=provider)

        >>> # Thinking model with thinking disabled
        >>> engine = EvaluationEngine("ollama/qwen3:14b", tier="smoke", thinking_mode="off")
        >>> result = engine.run_benchmark("humaneval")
    """

    def __init__(
        self,
        model: str,
        tier: str = "smoke",
        log_dir: Optional[Path | str] = None,
        thinking_mode: Optional[str] = None,
        provider: Any = None,
    ):
        """
        Initialize the evaluation engine.

        Args:
            model: Model identifier (e.g., "ollama/llama3.2:3b" or "llama3.2:3b")
            tier: Evaluation tier ("smoke", "quick", or "full")
            log_dir: Directory for storing evaluation logs (default: "./logs")
            thinking_mode: Thinking mode for thinking-capable models:
                - None: Standard mode (no thinking control)
                - "on": Enable thinking (extended reasoning)
                - "off": Disable thinking (direct response)
            provider: Optional Provider instance. If provided, the model string
                is formatted through the provider and provider-specific eval
                kwargs are applied. If None, model string is used as-is
                (backwards-compatible with existing ollama/ prefix behavior).
        """
        self.provider = provider
        self.tier = tier
        self.tier_config = get_tier(tier)
        self.thinking_mode = thinking_mode
        self.log_dir = Path(log_dir) if log_dir else Path("./logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Format model ID through provider if available
        if provider is not None:
            self.model = provider.format_model_id(model)
            self._raw_model = model
        else:
            self.model = model
            self._raw_model = model

    def _get_provider_name(self) -> str:
        """Get the provider name for metadata."""
        if self.provider is not None:
            return self.provider.name
        # Infer from model string prefix
        if self.model.startswith("ollama/"):
            return "ollama"
        if self.model.startswith("openai/"):
            return "openai"
        return "unknown"

    def _get_model_log_dir(self) -> Path:
        """
        Get the model-specific log directory.

        For thinking-capable models with thinking_mode set, creates
        subdirectories for thinking-on and thinking-off results.

        Returns:
            Path to model-specific log directory
        """
        # Extract model name (remove provider prefix)
        model_name = self.model
        for prefix in ("ollama/", "openai/"):
            model_name = model_name.replace(prefix, "")
        model_name = model_name.replace(":", "_").replace("/", "_")

        if self.thinking_mode in ("on", "off"):
            # Include thinking mode in directory structure
            return self.log_dir / model_name / f"thinking-{self.thinking_mode}"
        else:
            # Standard directory structure
            return self.log_dir / model_name

    def _get_eval_kwargs(self) -> dict[str, Any]:
        """
        Get evaluation kwargs including thinking mode configuration.

        Returns:
            Dictionary of kwargs to pass to inspect_ai.eval()
        """
        kwargs: dict[str, Any] = {}

        if self.thinking_mode == "off":
            # Disable thinking via generate config
            kwargs["generate_config"] = GenerateConfig(
                extra_body={"enable_thinking": False}
            )
        elif self.thinking_mode == "on":
            # Enable thinking (may be default for some models)
            kwargs["generate_config"] = GenerateConfig(
                extra_body={"enable_thinking": True}
            )

        return kwargs

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
            - thinking_mode: Thinking mode used (if applicable)

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

        # Include thinking mode in result if set
        if self.thinking_mode:
            result["thinking_mode"] = self.thinking_mode

        # Get model-specific log directory
        model_log_dir = self._get_model_log_dir()
        model_log_dir.mkdir(parents=True, exist_ok=True)

        # Merge thinking mode config with provider kwargs and user overrides
        default_kwargs = self._get_eval_kwargs()
        if self.provider is not None:
            provider_kwargs = self.provider.get_eval_kwargs(self._raw_model)
            default_kwargs = {**provider_kwargs, **default_kwargs}
        merged_kwargs = {**default_kwargs, **eval_kwargs}

        try:
            # Run evaluation with Inspect AI (synchronous - manages its own event loop)
            logs: list[EvalLog] = eval(
                task,
                model=self.model,
                log_dir=str(model_log_dir),
                **merged_kwargs,
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
            - thinking_mode: Thinking mode used (if applicable)
        """
        results = {
            "model": self.model,
            "tier": self.tier,
            "provider": self._get_provider_name(),
            "benchmarks": {},
            "status": "pending",
        }

        # Include thinking mode if set
        if self.thinking_mode:
            results["thinking_mode"] = self.thinking_mode

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
        # Application-specific benchmarks
        "matric_cli": "matric_eval.tasks.matric_cli.matric_cli",
        "matric_memory": "matric_eval.tasks.matric_memory.matric_memory",
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
