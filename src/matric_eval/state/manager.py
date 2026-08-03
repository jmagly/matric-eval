"""
State manager for checkpoint/resume functionality.

Handles atomic state updates, run metadata, and progress tracking.
"""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Status(str, Enum):
    """Status of a run, model, or benchmark."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProblemResult(BaseModel):
    """Result for a single problem."""

    problem_id: str
    response: str | None = None
    score: float = 0.0
    passed: bool = False
    error: str | None = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class BenchmarkState(BaseModel):
    """State for a benchmark evaluation."""

    benchmark: str
    status: Status = Status.PENDING
    problems: dict[str, ProblemResult] = Field(default_factory=dict)
    score: float | None = None
    total_problems: int = 0
    completed_problems: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ModelState(BaseModel):
    """State for a model evaluation."""

    model: str
    status: Status = Status.PENDING
    benchmarks: dict[str, BenchmarkState] = Field(default_factory=dict)
    overall_score: float | None = None
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class RunState(BaseModel):
    """Complete run state."""

    run_id: str
    tier: str
    seed: int
    models: list[str]
    benchmarks: list[str]
    status: Status = Status.RUNNING
    current_model: str | None = None
    current_benchmark: str | None = None
    completed_models: list[str] = Field(default_factory=list)
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StateManager:
    """
    Manages checkpoint/resume state for evaluation runs.

    Provides atomic state updates, progress tracking, and lock file management.
    """

    def __init__(self, run_dir: Path):
        """
        Initialize state manager.

        Args:
            run_dir: Directory for this evaluation run
        """
        self.run_dir = run_dir
        self.state_file = run_dir / "state.json"
        self.meta_file = run_dir / "meta.json"
        self.lock_file = run_dir / "lock"

    def initialize_run(
        self,
        run_id: str,
        tier: str,
        seed: int,
        models: list[str],
        benchmarks: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> RunState:
        """
        Initialize a new evaluation run.

        Args:
            run_id: Unique run identifier
            tier: Evaluation tier (smoke/quick/full)
            seed: Random seed for reproducibility
            models: List of models to evaluate
            benchmarks: List of benchmarks to run
            metadata: Additional immutable execution configuration

        Returns:
            Initialized RunState
        """
        self.run_dir.mkdir(parents=True, exist_ok=True)

        run_state = RunState(
            run_id=run_id, tier=tier, seed=seed, models=models, benchmarks=benchmarks
        )
        self.acquire_lock()

        try:
            # Write meta.json (immutable run configuration)
            meta = {
                "run_id": run_id,
                "tier": tier,
                "seed": seed,
                "models": models,
                "benchmarks": benchmarks,
                "started_at": run_state.started_at,
                "checkpoint_granularity": "benchmark",
                "configuration": metadata or {},
            }
            self._write_atomic(self.meta_file, meta)

            # Write initial state.json
            self._write_state(run_state)
        except BaseException:
            self.release_lock(force=True)
            raise

        return run_state

    def load_metadata(self) -> dict[str, Any]:
        """Load the immutable run metadata."""
        if not self.meta_file.exists():
            raise FileNotFoundError(f"Metadata file not found: {self.meta_file}")

        with open(self.meta_file) as f:
            data: dict[str, Any] = json.load(f)
        return data

    def load_run_state(self) -> RunState:
        """
        Load existing run state.

        Returns:
            Current RunState

        Raises:
            FileNotFoundError: If state file doesn't exist
        """
        if not self.state_file.exists():
            raise FileNotFoundError(f"State file not found: {self.state_file}")

        with open(self.state_file, "r") as f:
            data = json.load(f)

        return RunState(**data)

    def update_run_state(self, run_state: RunState) -> None:
        """
        Update run state atomically.

        Args:
            run_state: Updated RunState
        """
        run_state.updated_at = datetime.now().isoformat()
        self._write_state(run_state)

    def is_locked(self) -> bool:
        """Check if run is locked by another process."""
        return self.lock_file.exists()

    def acquire_lock(self) -> None:
        """Atomically acquire the run lock or reject a competing process."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        try:
            with self.lock_file.open("x") as lock:
                lock.write(f"acquired_at={datetime.now().isoformat()}\n")
        except FileExistsError as exc:
            raise RuntimeError(f"Run is locked: {self.lock_file}") from exc

    def release_lock(self, force: bool = False) -> None:
        """
        Release lock file.

        Args:
            force: If True, release lock even if not owned by this process
        """
        if self.lock_file.exists():
            self.lock_file.unlink()

    def get_model_dir(self, model: str) -> Path:
        """Get directory for model results."""
        # Sanitize model name for filesystem
        safe_name = model.replace(":", "_").replace("/", "_")
        return self.run_dir / safe_name

    def load_model_state(self, model: str) -> ModelState | None:
        """
        Load state for a specific model.

        Args:
            model: Model name

        Returns:
            ModelState if exists, None otherwise
        """
        model_dir = self.get_model_dir(model)
        state_file = model_dir / "state.json"

        if not state_file.exists():
            return None

        with open(state_file, "r") as f:
            data = json.load(f)

        return ModelState(**data)

    def update_model_state(self, model: str, model_state: ModelState) -> None:
        """
        Update model state atomically.

        Args:
            model: Model name
            model_state: Updated ModelState
        """
        model_dir = self.get_model_dir(model)
        model_dir.mkdir(parents=True, exist_ok=True)

        model_state.updated_at = datetime.now().isoformat()
        state_file = model_dir / "state.json"
        self._write_atomic(state_file, model_state.model_dump())

    def can_resume(self) -> bool:
        """
        Check if run can be resumed.

        Returns:
            True if state file exists and run is incomplete
        """
        if not self.state_file.exists():
            return False

        try:
            run_state = self.load_run_state()
            return run_state.status != Status.COMPLETED
        except Exception:
            return False

    def resume_locked_run(self) -> None:
        """
        Attempt to resume a locked run.

        Raises:
            RuntimeError: If run is locked by another process
        """
        if self.is_locked():
            raise RuntimeError(
                f"Run is already running (lock file exists: {self.lock_file}). "
                "If the process has died, use --force to override the lock."
            )

    def find_gaps(self) -> dict[str, dict[str, dict[str, Any]]]:
        """
        Find gaps in incomplete run (missing or partial benchmarks).

        Returns:
            Dict mapping model -> benchmark -> gap info
            Gap info contains: status (not_started/incomplete), completed, total
        """
        try:
            run_state = self.load_run_state()
        except FileNotFoundError:
            return {}

        gaps: dict[str, dict[str, dict[str, Any]]] = {}

        for model in run_state.models:
            model_state = self.load_model_state(model)

            for benchmark in run_state.benchmarks:
                # Check if benchmark exists in model state
                if model_state is None:
                    # Model never started
                    if model not in gaps:
                        gaps[model] = {}
                    gaps[model][benchmark] = {
                        "status": "not_started",
                        "completed": 0,
                        "total": 0,
                    }
                elif benchmark not in model_state.benchmarks:
                    # Benchmark not started for this model
                    if model not in gaps:
                        gaps[model] = {}
                    gaps[model][benchmark] = {
                        "status": "not_started",
                        "completed": 0,
                        "total": 0,
                    }
                else:
                    # Check if benchmark is incomplete
                    bench_state = model_state.benchmarks[benchmark]
                    if bench_state.status != Status.COMPLETED:
                        if model not in gaps:
                            gaps[model] = {}
                        gaps[model][benchmark] = {
                            "status": "incomplete",
                            "completed": bench_state.completed_problems,
                            "total": bench_state.total_problems,
                        }

        return gaps

    def get_resume_work(self) -> dict[str, list[str]]:
        """
        Get work items for resuming run (incomplete/not started benchmarks).

        Returns:
            Dict mapping model -> list of benchmarks to run
        """
        gaps = self.find_gaps()
        work: dict[str, list[str]] = {}

        for model, benchmarks in gaps.items():
            work[model] = list(benchmarks.keys())

        return work

    def mark_running(self, model: str, benchmark: str) -> None:
        """Mark a benchmark as running before invoking the evaluator.

        Checkpoint recovery is benchmark-granular. Restarting an incomplete
        benchmark therefore clears any legacy sample counters rather than
        implying that Inspect AI will continue from a sample offset.
        """
        model_state = self.load_model_state(model) or ModelState(model=model)
        model_state.status = Status.RUNNING
        model_state.benchmarks[benchmark] = BenchmarkState(
            benchmark=benchmark,
            status=Status.RUNNING,
        )
        self.update_model_state(model, model_state)

        run_state = self.load_run_state()
        run_state.status = Status.RUNNING
        run_state.current_model = model
        run_state.current_benchmark = benchmark
        run_state.completed_models = [item for item in run_state.completed_models if item != model]
        self.update_run_state(run_state)

    def mark_complete(
        self,
        model: str,
        benchmark: str,
        score: float,
        total_problems: int = 0,
        result: dict[str, Any] | None = None,
    ) -> None:
        """
        Mark a benchmark as complete for a model.

        Args:
            model: Model name
            benchmark: Benchmark name
            score: Final score (0.0-1.0)
            total_problems: Total number of problems evaluated
            result: Full serializable benchmark result for idempotent resume
        """
        # Load or create model state
        model_state = self.load_model_state(model)
        if model_state is None:
            model_state = ModelState(model=model)

        # Update benchmark state
        benchmark_state = BenchmarkState(
            benchmark=benchmark,
            status=Status.COMPLETED,
            score=score,
            total_problems=total_problems,
            completed_problems=total_problems,
            result=result,
        )

        model_state.benchmarks[benchmark] = benchmark_state

        # Update overall score if all benchmarks complete
        try:
            run_state = self.load_run_state()
            if all(
                bench in model_state.benchmarks
                and model_state.benchmarks[bench].status == Status.COMPLETED
                for bench in run_state.benchmarks
            ):
                # Calculate overall score
                scores: list[float] = []
                for bench in run_state.benchmarks:
                    benchmark_score = model_state.benchmarks[bench].score
                    if benchmark_score is not None:
                        scores.append(benchmark_score)
                if scores:
                    model_state.overall_score = sum(scores) / len(scores)
                model_state.status = Status.COMPLETED
        except FileNotFoundError:
            pass

        # Save updated state
        self.update_model_state(model, model_state)
        self.refresh_run_progress()

    def mark_failed(
        self,
        model: str,
        benchmark: str,
        error: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Persist a failed benchmark so a later resume can retry it."""
        model_state = self.load_model_state(model) or ModelState(model=model)
        model_state.status = Status.FAILED
        model_state.benchmarks[benchmark] = BenchmarkState(
            benchmark=benchmark,
            status=Status.FAILED,
            score=None,
            result=result,
            error=error,
        )
        self.update_model_state(model, model_state)

        run_state = self.load_run_state()
        run_state.status = Status.RUNNING
        run_state.current_model = None
        run_state.current_benchmark = None
        run_state.completed_models = [item for item in run_state.completed_models if item != model]
        self.update_run_state(run_state)

    def get_benchmark_result(self, model: str, benchmark: str) -> dict[str, Any] | None:
        """Return a persisted completed benchmark result, if available."""
        model_state = self.load_model_state(model)
        if model_state is None:
            return None

        benchmark_state = model_state.benchmarks.get(benchmark)
        if benchmark_state is None or benchmark_state.status != Status.COMPLETED:
            return None
        if benchmark_state.result is not None:
            return benchmark_state.result

        return {
            "benchmark": benchmark,
            "model": model,
            "status": "success",
            "score": benchmark_state.score or 0.0,
            "samples": benchmark_state.completed_problems,
            "resumed_from_checkpoint": True,
        }

    def build_model_result(self, model: str, display_model: str | None = None) -> dict[str, Any]:
        """Build a complete model result from persisted benchmark checkpoints."""
        run_state = self.load_run_state()
        benchmark_results: dict[str, dict[str, Any]] = {}
        scores: list[float] = []

        for benchmark in run_state.benchmarks:
            result = self.get_benchmark_result(model, benchmark)
            if result is None:
                continue
            checkpoint_result = {**result, "resumed_from_checkpoint": True}
            benchmark_results[benchmark] = checkpoint_result
            scores.append(float(checkpoint_result.get("score", 0.0) or 0.0))

        complete = len(benchmark_results) == len(run_state.benchmarks)
        return {
            "model": display_model or model,
            "checkpoint_model": model,
            "tier": run_state.tier,
            "benchmarks": benchmark_results,
            "overall_score": sum(scores) / len(scores) if scores else 0.0,
            "status": "success" if complete else "error",
            "resumed_from_checkpoint": True,
        }

    def should_skip(self, model: str, benchmark: str) -> bool:
        """
        Check if benchmark should be skipped (already complete).

        Args:
            model: Model name
            benchmark: Benchmark name

        Returns:
            True if benchmark is complete and should be skipped
        """
        model_state = self.load_model_state(model)
        if model_state is None:
            return False

        if benchmark not in model_state.benchmarks:
            return False

        return model_state.benchmarks[benchmark].status == Status.COMPLETED

    def get_remaining_problems(self, model: str, benchmark: str) -> dict[str, int] | None:
        """
        Get remaining problems for partially completed benchmark.

        Args:
            model: Model name
            benchmark: Benchmark name

        Returns:
            Dict with total, completed, remaining counts, or None if not started
        """
        model_state = self.load_model_state(model)
        if model_state is None:
            return None

        if benchmark not in model_state.benchmarks:
            return None

        bench_state = model_state.benchmarks[benchmark]
        return {
            "total": bench_state.total_problems,
            "completed": bench_state.completed_problems,
            "remaining": bench_state.total_problems - bench_state.completed_problems,
        }

    def _write_state(self, run_state: RunState) -> None:
        """Write run state atomically."""
        self._write_atomic(self.state_file, run_state.model_dump())

    def refresh_run_progress(self) -> None:
        """Recompute completed models and terminal run status from checkpoints."""
        try:
            run_state = self.load_run_state()
        except FileNotFoundError:
            return

        completed_models: list[str] = []
        for model in run_state.models:
            model_state = self.load_model_state(model)
            if model_state is None:
                continue
            if all(
                benchmark in model_state.benchmarks
                and model_state.benchmarks[benchmark].status == Status.COMPLETED
                for benchmark in run_state.benchmarks
            ):
                completed_models.append(model)

        run_state.completed_models = completed_models
        run_state.current_model = None
        run_state.current_benchmark = None
        run_state.status = (
            Status.COMPLETED if len(completed_models) == len(run_state.models) else Status.RUNNING
        )
        self.update_run_state(run_state)

    def _write_atomic(self, path: Path, data: dict[str, Any]) -> None:
        """
        Write JSON file atomically using temp file + rename.

        Args:
            path: Target file path
            data: Data to write
        """
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        tmp_path.replace(path)
