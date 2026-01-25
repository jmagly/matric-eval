"""
Tests for state management functionality.

Verifies checkpoint/resume state management with atomic updates.
"""

import json
from pathlib import Path

import pytest

from matric_eval.state import StateManager
from matric_eval.state.manager import BenchmarkState, ModelState, RunState, Status


class TestStateManager:
    """Test StateManager for checkpoint/resume functionality."""

    @pytest.fixture
    def temp_run_dir(self, tmp_path: Path) -> Path:
        """Create temporary run directory."""
        run_dir = tmp_path / "run-test"
        run_dir.mkdir()
        return run_dir

    @pytest.fixture
    def state_manager(self, temp_run_dir: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(temp_run_dir)

    def test_initialize_run(self, state_manager: StateManager) -> None:
        """Test initializing a new evaluation run."""
        run_state = state_manager.initialize_run(
            run_id="run-test-001",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b", "codestral:22b"],
            benchmarks=["humaneval", "mbpp"],
        )

        assert run_state.run_id == "run-test-001"
        assert run_state.tier == "smoke"
        assert run_state.seed == 42
        assert run_state.models == ["llama3.2:3b", "codestral:22b"]
        assert run_state.benchmarks == ["humaneval", "mbpp"]
        assert run_state.status == Status.RUNNING

    def test_initialize_run_creates_files(self, state_manager: StateManager) -> None:
        """Test that initialization creates required files."""
        state_manager.initialize_run(
            run_id="run-test-002",
            tier="quick",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        assert state_manager.meta_file.exists()
        assert state_manager.state_file.exists()
        assert state_manager.lock_file.exists()

    def test_initialize_run_writes_meta_json(self, state_manager: StateManager) -> None:
        """Test that meta.json contains correct run configuration."""
        state_manager.initialize_run(
            run_id="run-test-003",
            tier="full",
            seed=123,
            models=["model-a", "model-b"],
            benchmarks=["bench-a", "bench-b"],
        )

        with open(state_manager.meta_file) as f:
            meta = json.load(f)

        assert meta["run_id"] == "run-test-003"
        assert meta["tier"] == "full"
        assert meta["seed"] == 123
        assert meta["models"] == ["model-a", "model-b"]
        assert meta["benchmarks"] == ["bench-a", "bench-b"]

    def test_load_run_state(self, state_manager: StateManager) -> None:
        """Test loading existing run state."""
        original = state_manager.initialize_run(
            run_id="run-test-004",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        loaded = state_manager.load_run_state()

        assert loaded.run_id == original.run_id
        assert loaded.tier == original.tier
        assert loaded.seed == original.seed
        assert loaded.models == original.models
        assert loaded.benchmarks == original.benchmarks

    def test_load_run_state_not_found(self, state_manager: StateManager) -> None:
        """Test loading run state when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            state_manager.load_run_state()

    def test_update_run_state(self, state_manager: StateManager) -> None:
        """Test updating run state."""
        run_state = state_manager.initialize_run(
            run_id="run-test-005",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        run_state.status = Status.COMPLETED
        run_state.current_model = "llama3.2:3b"
        state_manager.update_run_state(run_state)

        loaded = state_manager.load_run_state()
        assert loaded.status == Status.COMPLETED
        assert loaded.current_model == "llama3.2:3b"

    def test_lock_file_operations(self, state_manager: StateManager) -> None:
        """Test lock file acquire and release."""
        assert not state_manager.is_locked()

        state_manager.acquire_lock()
        assert state_manager.is_locked()

        state_manager.release_lock()
        assert not state_manager.is_locked()

    def test_get_model_dir(self, state_manager: StateManager) -> None:
        """Test getting model directory with sanitized name."""
        model_dir = state_manager.get_model_dir("llama3.2:3b")
        assert model_dir.name == "llama3.2_3b"

        model_dir = state_manager.get_model_dir("codestral/22b")
        assert model_dir.name == "codestral_22b"

    def test_load_model_state_not_found(self, state_manager: StateManager) -> None:
        """Test loading model state when it doesn't exist."""
        model_state = state_manager.load_model_state("llama3.2:3b")
        assert model_state is None

    def test_update_model_state(self, state_manager: StateManager) -> None:
        """Test updating model state."""
        model_state = ModelState(model="llama3.2:3b", status=Status.RUNNING)

        state_manager.update_model_state("llama3.2:3b", model_state)

        loaded = state_manager.load_model_state("llama3.2:3b")
        assert loaded is not None
        assert loaded.model == "llama3.2:3b"
        assert loaded.status == Status.RUNNING

    def test_update_model_state_creates_directory(
        self, state_manager: StateManager
    ) -> None:
        """Test that updating model state creates directory."""
        model_state = ModelState(model="llama3.2:3b")

        state_manager.update_model_state("llama3.2:3b", model_state)

        model_dir = state_manager.get_model_dir("llama3.2:3b")
        assert model_dir.exists()
        assert model_dir.is_dir()

    def test_atomic_writes(self, state_manager: StateManager) -> None:
        """Test that state writes are atomic."""
        run_state = state_manager.initialize_run(
            run_id="run-test-006",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Verify no .tmp files left behind
        tmp_files = list(state_manager.run_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestRunState:
    """Test RunState data model."""

    def test_run_state_creation(self) -> None:
        """Test creating a RunState instance."""
        run_state = RunState(
            run_id="run-001",
            tier="smoke",
            seed=42,
            models=["model-a"],
            benchmarks=["bench-a"],
        )

        assert run_state.run_id == "run-001"
        assert run_state.tier == "smoke"
        assert run_state.seed == 42
        assert run_state.status == Status.RUNNING
        assert run_state.current_model is None
        assert run_state.completed_models == []


class TestModelState:
    """Test ModelState data model."""

    def test_model_state_creation(self) -> None:
        """Test creating a ModelState instance."""
        model_state = ModelState(model="llama3.2:3b")

        assert model_state.model == "llama3.2:3b"
        assert model_state.status == Status.PENDING
        assert model_state.benchmarks == {}
        assert model_state.overall_score is None


class TestBenchmarkState:
    """Test BenchmarkState data model."""

    def test_benchmark_state_creation(self) -> None:
        """Test creating a BenchmarkState instance."""
        benchmark_state = BenchmarkState(benchmark="humaneval")

        assert benchmark_state.benchmark == "humaneval"
        assert benchmark_state.status == Status.PENDING
        assert benchmark_state.problems == {}
        assert benchmark_state.score is None
        assert benchmark_state.total_problems == 0
        assert benchmark_state.completed_problems == 0
