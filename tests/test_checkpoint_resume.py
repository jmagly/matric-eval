"""
Tests for checkpoint/resume functionality.

Comprehensive tests for state management including:
- Checkpoint save/load cycle
- Atomic writes with crash simulation
- Gap detection
- Resume functionality
- Lock file handling
"""

import json
import os
import signal
from pathlib import Path
from unittest.mock import patch

import pytest

from matric_eval.state import RecoveryEngine, StateManager
from matric_eval.state.manager import BenchmarkState, ModelState, ProblemResult, RunState, Status


class TestCheckpointSaveLoad:
    """Test checkpoint save and load operations."""

    @pytest.fixture
    def temp_run_dir(self, tmp_path: Path) -> Path:
        """Create temporary run directory."""
        run_dir = tmp_path / "run-checkpoint-test"
        run_dir.mkdir()
        return run_dir

    @pytest.fixture
    def state_manager(self, temp_run_dir: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(temp_run_dir)

    def test_save_checkpoint_creates_benchmark_results(
        self, state_manager: StateManager
    ) -> None:
        """Test saving checkpoint with benchmark progress."""
        # Initialize run
        state_manager.initialize_run(
            run_id="run-001",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval", "mbpp"],
        )

        # Create model state with benchmark progress
        model_state = ModelState(model="llama3.2:3b", status=Status.RUNNING)

        # Add humaneval benchmark with some completed problems
        humaneval_state = BenchmarkState(
            benchmark="humaneval",
            status=Status.RUNNING,
            total_problems=5,
            completed_problems=3,
        )
        humaneval_state.problems["problem_1"] = ProblemResult(
            problem_id="problem_1",
            response="def solution(): pass",
            score=1.0,
            passed=True,
        )
        humaneval_state.problems["problem_2"] = ProblemResult(
            problem_id="problem_2",
            response="def solution(): return 42",
            score=1.0,
            passed=True,
        )
        humaneval_state.problems["problem_3"] = ProblemResult(
            problem_id="problem_3",
            response="invalid code",
            score=0.0,
            passed=False,
            error="Syntax error",
        )
        model_state.benchmarks["humaneval"] = humaneval_state

        # Save checkpoint
        state_manager.update_model_state("llama3.2:3b", model_state)

        # Verify checkpoint was saved
        saved_state = state_manager.load_model_state("llama3.2:3b")
        assert saved_state is not None
        assert saved_state.model == "llama3.2:3b"
        assert "humaneval" in saved_state.benchmarks
        assert saved_state.benchmarks["humaneval"].completed_problems == 3
        assert len(saved_state.benchmarks["humaneval"].problems) == 3

    def test_load_checkpoint_restores_exact_state(
        self, state_manager: StateManager
    ) -> None:
        """Test that loading checkpoint restores exact state."""
        # Initialize and create complex state
        state_manager.initialize_run(
            run_id="run-002",
            tier="quick",
            seed=123,
            models=["model-a", "model-b"],
            benchmarks=["humaneval", "mbpp", "gsm8k"],
        )

        # Create detailed model state
        model_state = ModelState(model="model-a", status=Status.RUNNING)

        # Add multiple benchmarks in different states
        model_state.benchmarks["humaneval"] = BenchmarkState(
            benchmark="humaneval",
            status=Status.COMPLETED,
            total_problems=10,
            completed_problems=10,
            score=0.8,
        )

        model_state.benchmarks["mbpp"] = BenchmarkState(
            benchmark="mbpp",
            status=Status.RUNNING,
            total_problems=20,
            completed_problems=12,
        )

        model_state.benchmarks["gsm8k"] = BenchmarkState(
            benchmark="gsm8k",
            status=Status.PENDING,
            total_problems=15,
            completed_problems=0,
        )

        # Save checkpoint
        state_manager.update_model_state("model-a", model_state)

        # Load and verify exact match
        loaded_state = state_manager.load_model_state("model-a")
        assert loaded_state is not None
        assert loaded_state.model == model_state.model
        assert loaded_state.status == model_state.status
        assert len(loaded_state.benchmarks) == 3

        # Verify humaneval (completed)
        assert loaded_state.benchmarks["humaneval"].status == Status.COMPLETED
        assert loaded_state.benchmarks["humaneval"].score == 0.8

        # Verify mbpp (running)
        assert loaded_state.benchmarks["mbpp"].status == Status.RUNNING
        assert loaded_state.benchmarks["mbpp"].completed_problems == 12

        # Verify gsm8k (pending)
        assert loaded_state.benchmarks["gsm8k"].status == Status.PENDING
        assert loaded_state.benchmarks["gsm8k"].completed_problems == 0

    def test_checkpoint_persists_across_manager_instances(
        self, temp_run_dir: Path
    ) -> None:
        """Test that checkpoints persist when creating new StateManager instance."""
        # First manager - save checkpoint
        manager1 = StateManager(temp_run_dir)
        manager1.initialize_run(
            run_id="run-003",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        model_state = ModelState(model="llama3.2:3b", status=Status.RUNNING)
        model_state.benchmarks["humaneval"] = BenchmarkState(
            benchmark="humaneval",
            status=Status.RUNNING,
            completed_problems=5,
        )
        manager1.update_model_state("llama3.2:3b", model_state)

        # Second manager - load checkpoint
        manager2 = StateManager(temp_run_dir)
        loaded_state = manager2.load_model_state("llama3.2:3b")

        assert loaded_state is not None
        assert loaded_state.benchmarks["humaneval"].completed_problems == 5


class TestAtomicWrites:
    """Test atomic write operations with crash simulation."""

    @pytest.fixture
    def temp_run_dir(self, tmp_path: Path) -> Path:
        """Create temporary run directory."""
        run_dir = tmp_path / "run-atomic-test"
        run_dir.mkdir()
        return run_dir

    @pytest.fixture
    def state_manager(self, temp_run_dir: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(temp_run_dir)

    def test_atomic_write_no_partial_files(self, state_manager: StateManager) -> None:
        """Test that atomic writes don't leave partial files."""
        state_manager.initialize_run(
            run_id="run-004",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Update state multiple times
        for i in range(10):
            run_state = state_manager.load_run_state()
            run_state.current_benchmark = f"benchmark_{i}"
            state_manager.update_run_state(run_state)

        # Verify no .tmp files exist
        tmp_files = list(state_manager.run_dir.glob("**/*.tmp"))
        assert len(tmp_files) == 0

    def test_atomic_write_interrupted_during_write(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test atomic write behavior when interrupted during write."""
        state_manager.initialize_run(
            run_id="run-005",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Save initial state
        run_state = state_manager.load_run_state()
        run_state.current_model = "llama3.2:3b"
        state_manager.update_run_state(run_state)

        # Simulate interrupted write by manually creating .tmp file
        tmp_file = state_manager.state_file.with_suffix(".tmp")
        tmp_file.write_text('{"corrupted": "data"}')

        # Verify original state file still has valid data
        loaded_state = state_manager.load_run_state()
        assert loaded_state.current_model == "llama3.2:3b"

    def test_atomic_write_handles_concurrent_writes(
        self, state_manager: StateManager
    ) -> None:
        """Test that atomic writes handle concurrent access safely."""
        state_manager.initialize_run(
            run_id="run-006",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Simulate rapid concurrent updates
        run_state = state_manager.load_run_state()
        for i in range(100):
            run_state.current_benchmark = f"benchmark_{i}"
            state_manager.update_run_state(run_state)

        # Verify final state is consistent
        final_state = state_manager.load_run_state()
        assert final_state.current_benchmark == "benchmark_99"

        # Verify no corruption in JSON
        with open(state_manager.state_file) as f:
            data = json.load(f)
            assert "current_benchmark" in data


class TestGapDetection:
    """Test gap detection for incomplete runs."""

    @pytest.fixture
    def temp_run_dir(self, tmp_path: Path) -> Path:
        """Create temporary run directory."""
        run_dir = tmp_path / "run-gap-test"
        run_dir.mkdir()
        return run_dir

    @pytest.fixture
    def state_manager(self, temp_run_dir: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(temp_run_dir)

    def test_find_gaps_detects_incomplete_benchmarks(
        self, state_manager: StateManager
    ) -> None:
        """Test finding gaps in incomplete benchmark runs."""
        state_manager.initialize_run(
            run_id="run-007",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval", "mbpp", "gsm8k"],
        )

        # Create model state with only some benchmarks completed
        model_state = ModelState(model="llama3.2:3b", status=Status.RUNNING)

        # humaneval: completed
        model_state.benchmarks["humaneval"] = BenchmarkState(
            benchmark="humaneval",
            status=Status.COMPLETED,
            total_problems=5,
            completed_problems=5,
            score=0.8,
        )

        # mbpp: partially complete
        model_state.benchmarks["mbpp"] = BenchmarkState(
            benchmark="mbpp",
            status=Status.RUNNING,
            total_problems=10,
            completed_problems=6,
        )

        # gsm8k: not started (no entry)

        state_manager.update_model_state("llama3.2:3b", model_state)

        # Find gaps
        gaps = state_manager.find_gaps()

        assert "llama3.2:3b" in gaps
        model_gaps = gaps["llama3.2:3b"]

        # mbpp should be in gaps (partially complete)
        assert "mbpp" in model_gaps
        assert model_gaps["mbpp"]["status"] == "incomplete"
        assert model_gaps["mbpp"]["completed"] == 6
        assert model_gaps["mbpp"]["total"] == 10

        # gsm8k should be in gaps (not started)
        assert "gsm8k" in model_gaps
        assert model_gaps["gsm8k"]["status"] == "not_started"

    def test_find_gaps_detects_incomplete_models(
        self, state_manager: StateManager
    ) -> None:
        """Test finding gaps for models that were never started."""
        state_manager.initialize_run(
            run_id="run-008",
            tier="smoke",
            seed=42,
            models=["model-a", "model-b", "model-c"],
            benchmarks=["humaneval"],
        )

        # Only create state for model-a
        model_state = ModelState(model="model-a", status=Status.COMPLETED)
        model_state.benchmarks["humaneval"] = BenchmarkState(
            benchmark="humaneval",
            status=Status.COMPLETED,
            total_problems=5,
            completed_problems=5,
            score=0.9,
        )
        state_manager.update_model_state("model-a", model_state)

        # Find gaps
        gaps = state_manager.find_gaps()

        # model-b and model-c should have gaps
        assert "model-b" in gaps
        assert "model-c" in gaps

        # Both should show humaneval as not started
        assert "humaneval" in gaps["model-b"]
        assert gaps["model-b"]["humaneval"]["status"] == "not_started"
        assert "humaneval" in gaps["model-c"]
        assert gaps["model-c"]["humaneval"]["status"] == "not_started"

    def test_find_gaps_returns_empty_for_complete_run(
        self, state_manager: StateManager
    ) -> None:
        """Test that complete runs return no gaps."""
        state_manager.initialize_run(
            run_id="run-009",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval", "mbpp"],
        )

        # Create complete model state
        model_state = ModelState(model="llama3.2:3b", status=Status.COMPLETED)

        model_state.benchmarks["humaneval"] = BenchmarkState(
            benchmark="humaneval",
            status=Status.COMPLETED,
            total_problems=5,
            completed_problems=5,
            score=0.8,
        )

        model_state.benchmarks["mbpp"] = BenchmarkState(
            benchmark="mbpp",
            status=Status.COMPLETED,
            total_problems=10,
            completed_problems=10,
            score=0.75,
        )

        state_manager.update_model_state("llama3.2:3b", model_state)

        # Find gaps
        gaps = state_manager.find_gaps()

        # Should be empty (no gaps)
        assert len(gaps) == 0


class TestResumeFunctionality:
    """Test resume from checkpoint functionality."""

    @pytest.fixture
    def temp_run_dir(self, tmp_path: Path) -> Path:
        """Create temporary run directory."""
        run_dir = tmp_path / "run-resume-test"
        run_dir.mkdir()
        return run_dir

    @pytest.fixture
    def state_manager(self, temp_run_dir: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(temp_run_dir)

    def test_resume_detects_existing_run(self, state_manager: StateManager) -> None:
        """Test that resume can detect existing run."""
        # Create initial run
        state_manager.initialize_run(
            run_id="run-010",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Verify can detect resumable run
        assert state_manager.can_resume()

    def test_resume_fails_for_new_run(self, state_manager: StateManager) -> None:
        """Test that resume fails when no state exists."""
        assert not state_manager.can_resume()

    def test_resume_skips_completed_work(self, state_manager: StateManager) -> None:
        """Test that resume skips already completed benchmarks."""
        state_manager.initialize_run(
            run_id="run-011",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval", "mbpp", "gsm8k"],
        )

        # Mark humaneval as complete
        model_state = ModelState(model="llama3.2:3b", status=Status.RUNNING)
        model_state.benchmarks["humaneval"] = BenchmarkState(
            benchmark="humaneval",
            status=Status.COMPLETED,
            total_problems=5,
            completed_problems=5,
            score=0.8,
        )
        state_manager.update_model_state("llama3.2:3b", model_state)

        # Get work to resume
        resume_work = state_manager.get_resume_work()

        assert "llama3.2:3b" in resume_work
        # humaneval should not be in work list (already complete)
        assert "humaneval" not in resume_work["llama3.2:3b"]
        # mbpp and gsm8k should be in work list
        assert "mbpp" in resume_work["llama3.2:3b"]
        assert "gsm8k" in resume_work["llama3.2:3b"]

    def test_mark_complete_updates_status(self, state_manager: StateManager) -> None:
        """Test marking benchmark/model as complete."""
        state_manager.initialize_run(
            run_id="run-012",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Mark benchmark as complete
        state_manager.mark_complete(
            model="llama3.2:3b",
            benchmark="humaneval",
            score=0.85,
        )

        # Verify state was updated
        model_state = state_manager.load_model_state("llama3.2:3b")
        assert model_state is not None
        assert "humaneval" in model_state.benchmarks
        assert model_state.benchmarks["humaneval"].status == Status.COMPLETED
        assert model_state.benchmarks["humaneval"].score == 0.85


class TestLockFileHandling:
    """Test lock file management for concurrent run prevention."""

    @pytest.fixture
    def temp_run_dir(self, tmp_path: Path) -> Path:
        """Create temporary run directory."""
        run_dir = tmp_path / "run-lock-test"
        run_dir.mkdir()
        return run_dir

    @pytest.fixture
    def state_manager(self, temp_run_dir: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(temp_run_dir)

    def test_initialize_creates_lock(self, state_manager: StateManager) -> None:
        """Test that initializing a run creates a lock file."""
        assert not state_manager.is_locked()

        state_manager.initialize_run(
            run_id="run-013",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        assert state_manager.is_locked()

    def test_lock_prevents_concurrent_resume(
        self, temp_run_dir: Path, state_manager: StateManager
    ) -> None:
        """Test that lock prevents concurrent resume attempts."""
        # First process initializes
        state_manager.initialize_run(
            run_id="run-014",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Second process tries to resume
        manager2 = StateManager(temp_run_dir)

        # Should detect lock
        assert manager2.is_locked()

        # Should raise error when trying to resume while locked
        with pytest.raises(RuntimeError, match="already running"):
            manager2.resume_locked_run()

    def test_lock_can_be_forced_if_stale(
        self, temp_run_dir: Path, state_manager: StateManager
    ) -> None:
        """Test that stale locks can be forced (after process dies)."""
        # Create lock
        state_manager.initialize_run(
            run_id="run-015",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Simulate process death (lock remains)
        assert state_manager.is_locked()

        # Force release lock
        state_manager.release_lock(force=True)

        assert not state_manager.is_locked()

    def test_lock_cleanup_on_completion(self, state_manager: StateManager) -> None:
        """Test that lock is released on successful completion."""
        state_manager.initialize_run(
            run_id="run-016",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        assert state_manager.is_locked()

        # Mark run as complete
        run_state = state_manager.load_run_state()
        run_state.status = Status.COMPLETED
        state_manager.update_run_state(run_state)
        state_manager.release_lock()

        assert not state_manager.is_locked()


class TestIdempotentExecution:
    """Test idempotent execution of evaluations."""

    @pytest.fixture
    def temp_run_dir(self, tmp_path: Path) -> Path:
        """Create temporary run directory."""
        run_dir = tmp_path / "run-idempotent-test"
        run_dir.mkdir()
        return run_dir

    @pytest.fixture
    def state_manager(self, temp_run_dir: Path) -> StateManager:
        """Create StateManager instance."""
        return StateManager(temp_run_dir)

    def test_rerunning_completed_benchmark_skips_execution(
        self, state_manager: StateManager
    ) -> None:
        """Test that rerunning a completed benchmark is skipped."""
        state_manager.initialize_run(
            run_id="run-017",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Mark as complete
        state_manager.mark_complete(
            model="llama3.2:3b",
            benchmark="humaneval",
            score=0.8,
        )

        # Check if should skip
        assert state_manager.should_skip(
            model="llama3.2:3b",
            benchmark="humaneval",
        )

    def test_partial_benchmark_can_resume(self, state_manager: StateManager) -> None:
        """Test that partially completed benchmark can resume."""
        state_manager.initialize_run(
            run_id="run-018",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Create partial progress
        model_state = ModelState(model="llama3.2:3b", status=Status.RUNNING)
        model_state.benchmarks["humaneval"] = BenchmarkState(
            benchmark="humaneval",
            status=Status.RUNNING,
            total_problems=10,
            completed_problems=5,
        )
        state_manager.update_model_state("llama3.2:3b", model_state)

        # Should not skip (incomplete)
        assert not state_manager.should_skip(
            model="llama3.2:3b",
            benchmark="humaneval",
        )

        # Get remaining work
        remaining = state_manager.get_remaining_problems(
            model="llama3.2:3b",
            benchmark="humaneval",
        )

        # Should have 5 remaining problems
        assert remaining is not None
        assert remaining["total"] == 10
        assert remaining["completed"] == 5
        assert remaining["remaining"] == 5
