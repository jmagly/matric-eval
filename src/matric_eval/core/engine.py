"""
EvaluationEngine - High-level interface for running model evaluations.

Wraps Inspect AI's eval() function with checkpoint support, error handling,
and result aggregation. Supports multiple inference providers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from inspect_ai import Task, eval
from inspect_ai.log import EvalLog

from matric_eval.config import get_tier
from matric_eval.provenance import benchmark_provenance, framework_provenance
from matric_eval.results.accounting import summarize_benchmarks
from matric_eval.results.contract import MetricDescriptor, ResultEnvelope
from matric_eval.results.inspect_adapter import adapt_log, envelope, native_reference, unavailable

if TYPE_CHECKING:
    from matric_eval.state import StateManager


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
        judge_spec: Optional[str] = None,
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
            judge_spec: Optional judge specification string for LLM-as-judge
                evaluation (e.g., "ollama:llama3.1:8b", "openai:gpt-4o").
                When set, adds judge scoring alongside deterministic scorers.
        """
        self.provider = provider
        self.run_id = str(uuid4())
        self.tier = tier
        self.tier_config = get_tier(tier)
        self.thinking_mode = thinking_mode
        self.judge_spec = judge_spec
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
            kwargs["extra_body"] = {"enable_thinking": False}
        elif self.thinking_mode == "on":
            kwargs["extra_body"] = {"enable_thinking": True}

        return kwargs

    def run_benchmark(
        self,
        benchmark: str,
        task: Optional[Task] = None,
        result_format: str = "legacy",
        primary_metric_id: str | None = None,
        metric_descriptors: dict[str, MetricDescriptor] | None = None,
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
            - status/execution: native execution completion, failure or cancellation
            - score: Declared primary estimate, or None when unavailable
            - samples: Number of samples evaluated
            - log_path: Path to evaluation log file
            - error: Error message (if status == "error")
            - thinking_mode: Thinking mode used (if applicable)

        Raises:
            ValueError: If benchmark name is invalid
        """
        if result_format not in {"legacy", "v2"}:
            raise ValueError("result_format must be legacy or v2")
        if task is None:
            # Dynamically load task from matric_eval.tasks
            task = self._load_task(benchmark)

        result: dict[str, Any] = {
            "benchmark": benchmark,
            "model": self.model,
            "tier": self.tier,
            "status": "pending",
        }

        from matric_eval.tasks.registry import get_registry

        result["provenance"] = benchmark_provenance(benchmark, get_registry().get(benchmark))

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

            result["log_paths"] = [str(log.location) for log in logs if log.location]
            result["native_logs"] = [native_reference(log) for log in logs]
            if not logs:
                raise ValueError("No evaluation logs returned")
            if len(logs) != 1:
                raise ValueError(
                    "Multiple evaluation logs returned; benchmark execution is ambiguous"
                )
            measured = adapt_log(
                logs[0],
                run_id=self.run_id,
                model_id=self.model,
                benchmark_id=benchmark,
                primary_metric_id=primary_metric_id,
                descriptors=metric_descriptors,
            )
            if result_format == "v2":
                return envelope(measured, self.run_id, self.model).model_dump()
            result.update(
                {
                    "status": {"completed": "success", "failed": "error"}.get(
                        measured.execution, measured.execution
                    ),
                    "execution": measured.execution,
                    "score": measured.primary_estimate.value,
                    "samples": measured.coverage.attempted,
                    "log_path": str(logs[0].location) if logs[0].location else None,
                    "eligible": measured.eligibility.eligible,
                    "eligibility_reasons": measured.eligibility.reasons,
                    "counts": measured.coverage.model_dump(),
                    "observation_result": measured.model_dump(),
                }
            )
            if measured.execution != "completed":
                result["error"] = f"Inspect terminal status: {logs[0].status}"

        except Exception as e:
            result.update(
                {
                    "status": "error",
                    "error": str(e),
                    "score": None,
                    "samples": 0,
                    "execution": "failed",
                    "eligible": False,
                    "eligibility_reasons": ["execution_failed"],
                    "counts": None,
                }
            )
            if result_format == "v2":
                raise ValueError(f"v2 projection unavailable: {e}") from e

        return result

    def run_all(
        self,
        benchmarks: list[str],
        checkpoint: bool = True,
        state_manager: StateManager | None = None,
        checkpoint_model: str | None = None,
        result_format: str = "legacy",
        **eval_kwargs: Any,
    ) -> dict[str, Any]:
        """
        Run all benchmarks with checkpointing support.

        Args:
            benchmarks: List of benchmark names to run
            checkpoint: Whether to use the supplied state manager
            state_manager: Run state used to persist and reuse benchmark results
            checkpoint_model: Stable model key in the run state. Defaults to the
                unformatted model identifier.
            **eval_kwargs: Additional arguments to pass to inspect_ai.eval()

        Returns:
            Dictionary containing:
            - model: Model identifier
            - tier: Evaluation tier
            - benchmarks: Dict mapping benchmark name to results
            - overall_score: None unless a cross-benchmark aggregation is declared
            - status: "success" only if every requested benchmark completed
            - thinking_mode: Thinking mode used (if applicable)
        """
        if result_format not in {"legacy", "v2"}:
            raise ValueError("result_format must be legacy or v2")
        if checkpoint and state_manager is not None:
            self.run_id = state_manager.load_run_state().run_id
        results: dict[str, Any] = {
            "model": self.model,
            "tier": self.tier,
            "provider": self._get_provider_name(),
            "provenance": {
                "schema_version": "1",
                "framework": framework_provenance(),
            },
            "benchmarks": {},
            "status": "pending",
        }

        # Include thinking mode if set
        if self.thinking_mode:
            results["thinking_mode"] = self.thinking_mode

        # Include judge info if set
        if self.judge_spec:
            results["judge"] = self.judge_spec

        checkpoint_key = checkpoint_model or self._raw_model
        results["checkpoint_model"] = checkpoint_key

        for benchmark in benchmarks:
            if checkpoint and state_manager is not None:
                saved_result = state_manager.get_benchmark_result(checkpoint_key, benchmark)
                if saved_result is not None and saved_result.get("execution") == "completed":
                    result = {**saved_result, "resumed_from_checkpoint": True}
                    results["benchmarks"][benchmark] = result
                    continue
                state_manager.mark_running(checkpoint_key, benchmark)

            try:
                result = self.run_benchmark(benchmark, **eval_kwargs)
            except Exception as exc:
                if checkpoint and state_manager is not None:
                    state_manager.mark_failed(
                        checkpoint_key,
                        benchmark,
                        error=str(exc),
                    )
                raise
            results["benchmarks"][benchmark] = result

            if result.get("execution") == "completed":
                score = result.get("score")
                if checkpoint and state_manager is not None:
                    state_manager.mark_complete(
                        checkpoint_key,
                        benchmark,
                        score=score,
                        total_problems=int(result.get("samples", 0) or 0),
                        result=result,
                    )
            elif checkpoint and state_manager is not None:
                state_manager.mark_failed(
                    checkpoint_key,
                    benchmark,
                    error=str(result.get("error", "Evaluation failed")),
                    result=result,
                )

        results.update(summarize_benchmarks(results["benchmarks"], benchmarks))

        if result_format == "v2":
            if any("observation_result" not in value for value in results["benchmarks"].values()):
                raise ValueError(
                    "v2 projection unavailable: benchmark has no verified observation manifest"
                )
            return ResultEnvelope.model_validate(
                {
                    "result_schema_version": "2",
                    "run_id": self.run_id,
                    "model_id": self.model,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "provenance_schema_version": "1",
                    "configuration_sha256": None,
                    "execution": results["execution"],
                    "eligibility": {
                        "eligible": results["eligible"],
                        "reasons": results["eligibility_reasons"],
                    },
                    "benchmarks": [
                        value["observation_result"] for value in results["benchmarks"].values()
                    ],
                    "aggregation_id": None,
                    "overall_estimate": unavailable("aggregation_undeclared"),
                    "artifacts": [],
                }
            ).model_dump()

        return results

    def run_pass_k_benchmark(
        self,
        benchmark: str,
        k: int = 3,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run a benchmark k times and aggregate with pass^k scoring.

        Each of the k runs uses the same base random seed per NFR-REPRO-003,
        ensuring reproducible sampling across runs. The final score uses
        pass_power_k semantics: the benchmark is considered solved only if
        all k runs succeed.

        Args:
            benchmark: Benchmark name (e.g., "humaneval", "mbpp")
            k: Number of independent runs (default: 3)
            **kwargs: Additional arguments forwarded to run_benchmark()

        Returns:
            Dictionary containing:
            - benchmark: Benchmark name
            - model: Model identifier
            - tier: Evaluation tier
            - k: Number of runs performed
            - pass_power_k: 1.0 if all k runs passed, 0.0 otherwise
            - run_results: List of individual run result dicts
            - pass_rate: Fraction of runs that succeeded (c/k)
            - status: "success" if all runs completed, "partial" if some failed
              to execute (not benchmark failure), "error" if none completed
        """
        from matric_eval.scorers.pass_k import pass_power_k

        # Base seed for reproducibility (NFR-REPRO-003)
        base_seed = 42

        run_results: list[dict[str, Any]] = []
        run_pass_flags: list[bool] = []

        for i in range(k):
            # Each run uses the same seed for reproducible sampling
            run_kwargs = {"seed": base_seed, **kwargs}
            result = self.run_benchmark(benchmark, **run_kwargs)
            run_results.append(result)

            # A run "passes" if it succeeded and scored > 0
            passed = (
                result.get("status") == "success"
                and result.get("score") is not None
                and result["score"] > 0
            )
            run_pass_flags.append(passed)

        successful_runs = [r for r in run_results if r.get("status") == "success"]

        if len(successful_runs) == k:
            exec_status = "success"
        elif successful_runs:
            exec_status = "partial"
        else:
            exec_status = "error"

        pass_rate = sum(1 for f in run_pass_flags if f) / k if k > 0 else 0.0

        return {
            "benchmark": benchmark,
            "model": self.model,
            "tier": self.tier,
            "k": k,
            "pass_power_k": pass_power_k(run_pass_flags),
            "run_results": run_results,
            "pass_rate": pass_rate,
            "status": exec_status,
        }

    def _load_task(self, benchmark: str) -> Task:
        """
        Dynamically load a tier-aware task from the task registry,
        falling back to external dataset discovery.

        Each task function accepts a ``tier`` parameter and returns a Task with
        the appropriate number of samples for that tier.

        Args:
            benchmark: Benchmark name (e.g., "humaneval", "mbpp", or external dataset name)

        Returns:
            Inspect AI Task object

        Raises:
            ValueError: If benchmark is not found
        """
        from matric_eval.tasks.registry import get_registry

        registry = get_registry()

        # Check registered benchmarks first
        if benchmark in registry:
            return registry.load_task(benchmark, tier=self.tier)

        # Fallback: check external dataset registry
        from matric_eval.discovery import (
            create_external_task,
            get_external_dataset,
            get_external_datasets,
        )

        dataset = get_external_dataset(benchmark)
        if dataset is not None:
            return create_external_task(dataset, tier=self.tier)

        # Not found
        available = registry.list_names()
        external = list(get_external_datasets().keys())
        if external:
            available.extend(external)
        raise ValueError(
            f"Unknown benchmark: {benchmark}. Available benchmarks: {', '.join(available)}"
        )
