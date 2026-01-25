"""
Tests for state management (matric_eval.state.manager).

Covers:
- RunState, ModelState, BenchmarkState, ProblemResult
- StateManager initialization and persistence
- Checkpoint/resume functionality
- Gap detection and work resumption
- Atomic writes and lock management
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from matric_eval.state.manager import (
    BenchmarkState,
    ModelState,
    ProblemResult,
    RunState,
    StateManager,
    Status,
)


# =============================================================================
# Status Tests
# =============================================================================


@pytest.mark.unit
class TestStatus:
    """Tests for Status enum."""

    def test_all_statuses_defined(self) -> None:
        """Should have all expected status values."""
        assert Status.PENDING == "pending"
        assert Status.RUNNING == "running"
        assert Status.COMPLETED == "completed"
        assert Status.FAILED == "failed"
        assert Status.CANCELLED == "cancelled"


# =============================================================================
# ProblemResult Tests
# =============================================================================


@pytest.mark.unit
class TestProblemResult:
    """Tests for ProblemResult model."""

    def test_basic_creation(self) -> None:
        """Should create with minimal fields."""
        result = ProblemResult(problem_id="HE_001")
        assert result.problem_id == "HE_001"
        assert result.response is None
        assert result.score == 0.0
        assert result.passed is False
        assert result.error is None
        assert result.timestamp is not None

    def test_with_response(self) -> None:
        """Should store response and score."""
        result = ProblemResult(
            problem_id="HE_002",
            response="def add(a, b): return a + b",
            score=1.0,
            passed=True,
        )
        assert result.response == "def add(a, b): return a + b"
        assert result.score == 1.0
        assert result.passed is True

    def test_with_error(self) -> None:
        """Should store error information."""
        result = ProblemResult(
            problem_id="HE_003",
            error="Timeout exceeded",
            passed=False,
        )
        assert result.error == "Timeout exceeded"
        assert result.passed is False

    def test_with_artifacts(self) -> None:
        """Should store artifacts."""
        result = ProblemResult(
            problem_id="HE_004",
            artifacts={"generated_code": "print('hello')", "execution_time": 0.5},
        )
        assert result.artifacts["generated_code"] == "print('hello')"
        assert result.artifacts["execution_time"] == 0.5


# =============================================================================
# BenchmarkState Tests
# =============================================================================


@pytest.mark.unit
class TestBenchmarkState:
    """Tests for BenchmarkState model."""

    def test_default_state(self) -> None:
        """Should have sensible defaults."""
        state = BenchmarkState(benchmark="humaneval")
        assert state.benchmark == "humaneval"
        assert state.status == Status.PENDING
        assert len(state.problems) == 0
        assert state.score is None
        assert state.total_problems == 0
        assert state.completed_problems == 0

    def test_with_problems(self) -> None:
        """Should track problems."""
        state = BenchmarkState(
            benchmark="mbpp",
            status=Status.RUNNING,
            total_problems=100,
            completed_problems=50,
        )
        assert state.status == Status.RUNNING
        assert state.total_problems == 100
        assert state.completed_problems == 50

    def test_completed_state(self) -> None:
        """Should track completion."""
        state = BenchmarkState(
            benchmark="gsm8k",
            status=Status.COMPLETED,
            score=0.85,
            total_problems=200,
            completed_problems=200,
        )
        assert state.status == Status.COMPLETED
        assert state.score == 0.85


# =============================================================================
# ModelState Tests
# =============================================================================


@pytest.mark.unit
class TestModelState:
    """Tests for ModelState model."""

    def test_default_state(self) -> None:
        """Should have sensible defaults."""
        state = ModelState(model="llama3.2:3b")
        assert state.model == "llama3.2:3b"
        assert state.status == Status.PENDING
        assert len(state.benchmarks) == 0
        assert state.overall_score is None

    def test_with_benchmarks(self) -> None:
        """Should track benchmark states."""
        state = ModelState(
            model="mistral:7b",
            status=Status.RUNNING,
            benchmarks={
                "humaneval": BenchmarkState(benchmark="humaneval", status=Status.COMPLETED),
                "mbpp": BenchmarkState(benchmark="mbpp", status=Status.RUNNING),
            },
        )
        assert len(state.benchmarks) == 2
        assert state.benchmarks["humaneval"].status == Status.COMPLETED
        assert state.benchmarks["mbpp"].status == Status.RUNNING

    def test_overall_score(self) -> None:
        """Should track overall score."""
        state = ModelState(
            model="qwen:7b",
            status=Status.COMPLETED,
            overall_score=0.78,
        )
        assert state.overall_score == 0.78


# =============================================================================
# RunState Tests
# =============================================================================


@pytest.mark.unit
class TestRunState:
    """Tests for RunState model."""

    def test_default_state(self) -> None:
        """Should initialize with required fields."""
        state = RunState(
            run_id="run_001",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )
        assert state.run_id == "run_001"
        assert state.tier == "smoke"
        assert state.seed == 42
        assert state.status == Status.RUNNING
        assert state.current_model is None
        assert state.current_benchmark is None
        assert len(state.completed_models) == 0

    def test_with_progress(self) -> None:
        """Should track progress."""
        state = RunState(
            run_id="run_002",
            tier="quick",
            seed=123,
            models=["m1", "m2", "m3"],
            benchmarks=["b1", "b2"],
            current_model="m2",
            current_benchmark="b1",
            completed_models=["m1"],
        )
        assert state.current_model == "m2"
        assert state.current_benchmark == "b1"
        assert "m1" in state.completed_models


# =============================================================================
# StateManager Tests
# =============================================================================


@pytest.mark.unit
class TestStateManager:
    """Tests for StateManager class."""

    @pytest.fixture
    def run_dir(self, tmp_path: Path) -> Path:
        """Create temporary run directory."""
        return tmp_path / "eval_run"

    @pytest.fixture
    def manager(self, run_dir: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(run_dir)

    def test_initialization(self, manager: StateManager, run_dir: Path) -> None:
        """Should initialize with correct paths."""
        assert manager.run_dir == run_dir
        assert manager.state_file == run_dir / "state.json"
        assert manager.meta_file == run_dir / "meta.json"
        assert manager.lock_file == run_dir / "lock"

    def test_initialize_run(self, manager: StateManager) -> None:
        """Should initialize a new run."""
        run_state = manager.initialize_run(
            run_id="run_001",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b", "mistral:7b"],
            benchmarks=["humaneval", "mbpp"],
        )

        assert run_state.run_id == "run_001"
        assert run_state.tier == "smoke"
        assert run_state.seed == 42
        assert len(run_state.models) == 2
        assert len(run_state.benchmarks) == 2
        assert manager.state_file.exists()
        assert manager.meta_file.exists()
        assert manager.lock_file.exists()

    def test_load_run_state(self, manager: StateManager) -> None:
        """Should load existing run state."""
        # Initialize first
        original = manager.initialize_run(
            run_id="run_002",
            tier="quick",
            seed=123,
            models=["m1"],
            benchmarks=["b1"],
        )

        # Load and verify
        loaded = manager.load_run_state()
        assert loaded.run_id == original.run_id
        assert loaded.tier == original.tier
        assert loaded.seed == original.seed

    def test_load_nonexistent_state_raises(self, manager: StateManager) -> None:
        """Should raise FileNotFoundError for missing state."""
        with pytest.raises(FileNotFoundError):
            manager.load_run_state()

    def test_update_run_state(self, manager: StateManager) -> None:
        """Should update run state atomically."""
        run_state = manager.initialize_run(
            run_id="run_003",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        # Update
        run_state.current_model = "m1"
        run_state.current_benchmark = "b1"
        manager.update_run_state(run_state)

        # Verify
        loaded = manager.load_run_state()
        assert loaded.current_model == "m1"
        assert loaded.current_benchmark == "b1"

    def test_lock_management(self, manager: StateManager) -> None:
        """Should manage lock file."""
        manager.initialize_run(
            run_id="run_004",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        assert manager.is_locked() is True

        manager.release_lock()
        assert manager.is_locked() is False

        manager.acquire_lock()
        assert manager.is_locked() is True

    def test_get_model_dir(self, manager: StateManager) -> None:
        """Should create safe model directory names."""
        # Normal model name
        assert manager.get_model_dir("llama3.2") == manager.run_dir / "llama3.2"

        # Model with colon
        assert manager.get_model_dir("llama3.2:3b") == manager.run_dir / "llama3.2_3b"

        # Model with slash
        assert manager.get_model_dir("meta/llama3") == manager.run_dir / "meta_llama3"

    def test_model_state_persistence(self, manager: StateManager) -> None:
        """Should persist and load model state."""
        manager.initialize_run(
            run_id="run_005",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        # Initially no model state
        assert manager.load_model_state("m1") is None

        # Create and save model state
        model_state = ModelState(model="m1", status=Status.RUNNING)
        manager.update_model_state("m1", model_state)

        # Load and verify
        loaded = manager.load_model_state("m1")
        assert loaded is not None
        assert loaded.model == "m1"
        assert loaded.status == Status.RUNNING

    def test_can_resume_new_run(self, manager: StateManager) -> None:
        """Should not resume non-existent run."""
        assert manager.can_resume() is False

    def test_can_resume_incomplete_run(self, manager: StateManager) -> None:
        """Should resume incomplete run."""
        manager.initialize_run(
            run_id="run_006",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )
        manager.release_lock()

        assert manager.can_resume() is True

    def test_can_resume_completed_run(self, manager: StateManager) -> None:
        """Should not resume completed run."""
        run_state = manager.initialize_run(
            run_id="run_007",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )
        run_state.status = Status.COMPLETED
        manager.update_run_state(run_state)
        manager.release_lock()

        assert manager.can_resume() is False

    def test_find_gaps_empty_run(self, manager: StateManager) -> None:
        """Should find all benchmarks as gaps in empty run."""
        manager.initialize_run(
            run_id="run_008",
            tier="smoke",
            seed=42,
            models=["m1", "m2"],
            benchmarks=["b1", "b2"],
        )

        gaps = manager.find_gaps()

        assert "m1" in gaps
        assert "m2" in gaps
        assert "b1" in gaps["m1"]
        assert "b2" in gaps["m1"]
        assert gaps["m1"]["b1"]["status"] == "not_started"

    def test_find_gaps_partial_run(self, manager: StateManager) -> None:
        """Should find remaining work in partial run."""
        manager.initialize_run(
            run_id="run_009",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1", "b2"],
        )

        # Complete one benchmark
        manager.mark_complete("m1", "b1", score=0.8, total_problems=10)

        gaps = manager.find_gaps()

        assert "m1" in gaps
        assert "b1" not in gaps["m1"]  # Completed
        assert "b2" in gaps["m1"]  # Not started

    def test_get_resume_work(self, manager: StateManager) -> None:
        """Should return work items for resume."""
        manager.initialize_run(
            run_id="run_010",
            tier="smoke",
            seed=42,
            models=["m1", "m2"],
            benchmarks=["b1", "b2"],
        )

        # Complete some work
        manager.mark_complete("m1", "b1", score=0.8, total_problems=10)

        work = manager.get_resume_work()

        assert "m1" in work
        assert "m2" in work
        assert "b2" in work["m1"]  # Remaining for m1
        assert "b1" in work["m2"]  # All benchmarks for m2
        assert "b2" in work["m2"]

    def test_mark_complete(self, manager: StateManager) -> None:
        """Should mark benchmark as complete."""
        manager.initialize_run(
            run_id="run_011",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        manager.mark_complete("m1", "b1", score=0.85, total_problems=100)

        model_state = manager.load_model_state("m1")
        assert model_state is not None
        assert "b1" in model_state.benchmarks
        assert model_state.benchmarks["b1"].status == Status.COMPLETED
        assert model_state.benchmarks["b1"].score == 0.85

    def test_mark_complete_updates_overall(self, manager: StateManager) -> None:
        """Should update overall score when all benchmarks complete."""
        manager.initialize_run(
            run_id="run_012",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1", "b2"],
        )

        manager.mark_complete("m1", "b1", score=0.8, total_problems=10)
        manager.mark_complete("m1", "b2", score=0.6, total_problems=10)

        model_state = manager.load_model_state("m1")
        assert model_state is not None
        assert model_state.status == Status.COMPLETED
        assert model_state.overall_score == 0.7  # (0.8 + 0.6) / 2

    def test_should_skip_incomplete(self, manager: StateManager) -> None:
        """Should not skip incomplete benchmarks."""
        manager.initialize_run(
            run_id="run_013",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        assert manager.should_skip("m1", "b1") is False

    def test_should_skip_completed(self, manager: StateManager) -> None:
        """Should skip completed benchmarks."""
        manager.initialize_run(
            run_id="run_014",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        manager.mark_complete("m1", "b1", score=0.9, total_problems=10)

        assert manager.should_skip("m1", "b1") is True

    def test_get_remaining_problems_not_started(self, manager: StateManager) -> None:
        """Should return None for not started benchmark."""
        manager.initialize_run(
            run_id="run_015",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        remaining = manager.get_remaining_problems("m1", "b1")
        assert remaining is None

    def test_get_remaining_problems_partial(self, manager: StateManager) -> None:
        """Should return remaining count for partial benchmark."""
        manager.initialize_run(
            run_id="run_016",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        # Create partial state
        model_state = ModelState(model="m1")
        model_state.benchmarks["b1"] = BenchmarkState(
            benchmark="b1",
            status=Status.RUNNING,
            total_problems=100,
            completed_problems=40,
        )
        manager.update_model_state("m1", model_state)

        remaining = manager.get_remaining_problems("m1", "b1")
        assert remaining is not None
        assert remaining["total"] == 100
        assert remaining["completed"] == 40
        assert remaining["remaining"] == 60

    def test_atomic_write(self, manager: StateManager) -> None:
        """Should write files atomically."""
        manager.run_dir.mkdir(parents=True, exist_ok=True)

        test_file = manager.run_dir / "test.json"
        data = {"key": "value", "count": 42}

        manager._write_atomic(test_file, data)

        assert test_file.exists()
        with open(test_file) as f:
            loaded = json.load(f)
        assert loaded == data

        # Temp file should be cleaned up
        assert not test_file.with_suffix(".tmp").exists()

    def test_resume_locked_run_raises(self, manager: StateManager) -> None:
        """Should raise when trying to resume locked run."""
        manager.initialize_run(
            run_id="run_017",
            tier="smoke",
            seed=42,
            models=["m1"],
            benchmarks=["b1"],
        )

        with pytest.raises(RuntimeError, match="already running"):
            manager.resume_locked_run()


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
class TestStateManagerIntegration:
    """Integration tests for StateManager."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(tmp_path / "integration_test")

    def test_full_evaluation_workflow(self, manager: StateManager) -> None:
        """Should handle complete evaluation workflow."""
        # Initialize
        run_state = manager.initialize_run(
            run_id="full_test",
            tier="quick",
            seed=42,
            models=["llama3.2:3b", "mistral:7b"],
            benchmarks=["humaneval", "mbpp", "gsm8k"],
        )

        # Simulate evaluation progress
        for model in run_state.models:
            run_state.current_model = model
            manager.update_run_state(run_state)

            for benchmark in run_state.benchmarks:
                run_state.current_benchmark = benchmark
                manager.update_run_state(run_state)

                # Simulate evaluation
                score = 0.8 if model == "llama3.2:3b" else 0.7
                manager.mark_complete(model, benchmark, score=score, total_problems=50)

            run_state.completed_models.append(model)

        run_state.status = Status.COMPLETED
        manager.update_run_state(run_state)

        # Verify final state
        final_state = manager.load_run_state()
        assert final_state.status == Status.COMPLETED
        assert len(final_state.completed_models) == 2

        # Verify model scores
        llama_state = manager.load_model_state("llama3.2:3b")
        assert llama_state is not None
        assert llama_state.overall_score is not None
        assert abs(llama_state.overall_score - 0.8) < 0.001

        mistral_state = manager.load_model_state("mistral:7b")
        assert mistral_state is not None
        assert mistral_state.overall_score is not None
        assert abs(mistral_state.overall_score - 0.7) < 0.001

    def test_resume_interrupted_run(self, manager: StateManager) -> None:
        """Should resume from interruption point."""
        # Initialize and partially complete
        manager.initialize_run(
            run_id="interrupted",
            tier="smoke",
            seed=42,
            models=["m1", "m2"],
            benchmarks=["b1", "b2"],
        )

        # Complete some work
        manager.mark_complete("m1", "b1", score=0.9, total_problems=10)
        manager.release_lock()

        # "Resume" - verify we can detect remaining work
        assert manager.can_resume() is True

        work = manager.get_resume_work()
        assert "m1" in work
        assert "b2" in work["m1"]
        assert "b1" not in work["m1"]  # Already done
        assert "m2" in work
        assert len(work["m2"]) == 2  # All benchmarks for m2
