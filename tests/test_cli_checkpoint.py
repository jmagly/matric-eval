"""
Tests for CLI checkpoint/resume commands.

Tests the validate command and resume flag functionality.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from matric_eval.cli import cli
from matric_eval.config import get_seed, get_settings
from matric_eval.state import StateManager
from matric_eval.state.manager import BenchmarkState, Status


class TestValidateCommand:
    """Test the validate CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_results_dir(self, tmp_path: Path) -> Path:
        """Create temporary results directory."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        return results_dir

    @pytest.fixture
    def complete_run_dir(self, temp_results_dir: Path) -> Path:
        """Create a complete run directory."""
        run_dir = temp_results_dir / "run-complete"
        run_dir.mkdir()

        # Initialize complete run
        state_manager = StateManager(run_dir)
        state_manager.initialize_run(
            run_id="run-complete",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval", "mbpp"],
        )

        # Mark all benchmarks complete
        state_manager.mark_complete(
            model="llama3.2:3b",
            benchmark="humaneval",
            score=0.8,
            total_problems=5,
        )
        state_manager.mark_complete(
            model="llama3.2:3b",
            benchmark="mbpp",
            score=0.7,
            total_problems=10,
        )

        # Release lock
        state_manager.release_lock()

        return run_dir

    @pytest.fixture
    def incomplete_run_dir(self, temp_results_dir: Path) -> Path:
        """Create an incomplete run directory."""
        run_dir = temp_results_dir / "run-incomplete"
        run_dir.mkdir()

        # Initialize incomplete run
        state_manager = StateManager(run_dir)
        state_manager.initialize_run(
            run_id="run-incomplete",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b", "qwen2.5:7b"],
            benchmarks=["humaneval", "mbpp", "gsm8k"],
        )

        # Only complete some benchmarks for first model
        state_manager.mark_complete(
            model="llama3.2:3b",
            benchmark="humaneval",
            score=0.8,
            total_problems=5,
        )

        # Create partial progress for mbpp
        model_state = state_manager.load_model_state("llama3.2:3b")
        model_state.benchmarks["mbpp"] = BenchmarkState(
            benchmark="mbpp",
            status=Status.RUNNING,
            total_problems=10,
            completed_problems=6,
        )
        state_manager.update_model_state("llama3.2:3b", model_state)

        # Release lock
        state_manager.release_lock()

        return run_dir

    def test_validate_complete_run(self, runner: CliRunner, complete_run_dir: Path) -> None:
        """Test validating a complete run."""
        result = runner.invoke(
            cli,
            ["validate", str(complete_run_dir)],
        )

        assert result.exit_code == 0
        assert "RUN VALIDATION" in result.output
        assert "complete" in result.output.lower()

    def test_validate_incomplete_run(self, runner: CliRunner, incomplete_run_dir: Path) -> None:
        """Test validating an incomplete run."""
        result = runner.invoke(
            cli,
            ["validate", str(incomplete_run_dir)],
        )

        assert result.exit_code == 0
        assert "GAPS FOUND" in result.output
        assert "incomplete" in result.output.lower()

    def test_validate_with_json_output(self, runner: CliRunner, complete_run_dir: Path) -> None:
        """Test validate command with JSON output."""
        result = runner.invoke(
            cli,
            ["validate", str(complete_run_dir), "--output-format", "json"],
        )

        assert result.exit_code == 0

        # Parse JSON output
        data = json.loads(result.output)
        assert data["run_id"] == "run-complete"
        assert data["tier"] == "smoke"
        assert data["is_complete"] is True
        assert len(data["gaps"]) == 0

    def test_validate_incomplete_with_json(
        self, runner: CliRunner, incomplete_run_dir: Path
    ) -> None:
        """Test validate incomplete run with JSON output."""
        result = runner.invoke(
            cli,
            ["validate", str(incomplete_run_dir), "--output-format", "json"],
        )

        assert result.exit_code == 0

        # Parse JSON output
        data = json.loads(result.output)
        assert data["run_id"] == "run-incomplete"
        assert data["is_complete"] is False
        assert len(data["gaps"]) > 0

        # Should have gaps for llama3.2:3b (mbpp, gsm8k)
        assert "llama3.2:3b" in data["gaps"]
        assert "mbpp" in data["gaps"]["llama3.2:3b"]
        assert "gsm8k" in data["gaps"]["llama3.2:3b"]

        # Should have gaps for qwen2.5:7b (all benchmarks)
        assert "qwen2.5:7b" in data["gaps"]

    def test_validate_force_unlock(self, runner: CliRunner, temp_results_dir: Path) -> None:
        """Test force unlock functionality."""
        run_dir = temp_results_dir / "run-locked"
        run_dir.mkdir()

        # Create locked run
        state_manager = StateManager(run_dir)
        state_manager.initialize_run(
            run_id="run-locked",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )

        # Verify locked
        assert state_manager.is_locked()

        # Force unlock via CLI
        result = runner.invoke(
            cli,
            ["validate", str(run_dir), "--force-unlock"],
        )

        assert result.exit_code == 0
        assert "Lock released" in result.output

        # Verify unlocked
        assert not state_manager.is_locked()

    def test_validate_nonexistent_run(self, runner: CliRunner, temp_results_dir: Path) -> None:
        """Test validating nonexistent run."""
        result = runner.invoke(
            cli,
            ["validate", str(temp_results_dir / "nonexistent")],
        )

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestResumeFlag:
    """Test the --resume flag functionality."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_results_dir(self, tmp_path: Path) -> Path:
        """Create temporary results directory."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        return results_dir

    @pytest.fixture
    def incomplete_run_dir(self, temp_results_dir: Path) -> Path:
        """Create an incomplete run directory."""
        run_dir = temp_results_dir / "run-resume-test"
        run_dir.mkdir()

        # Initialize incomplete run
        state_manager = StateManager(run_dir)
        state_manager.initialize_run(
            run_id="run-resume-test",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval", "mbpp"],
        )

        # Complete humaneval
        state_manager.mark_complete(
            model="llama3.2:3b",
            benchmark="humaneval",
            score=0.8,
            total_problems=5,
        )

        # Release lock
        state_manager.release_lock()

        return run_dir

    def test_resume_detects_existing_run(
        self, runner: CliRunner, incomplete_run_dir: Path, temp_results_dir: Path
    ) -> None:
        """Test that --resume detects existing run."""
        with patch("matric_eval.core.engine.EvaluationEngine.run_benchmark") as run_benchmark:
            run_benchmark.return_value = {
                "benchmark": "mbpp",
                "status": "success",
                "score": 0.7,
                "samples": 5,
            }
            result = runner.invoke(
                cli,
                [
                    "run",
                    "--resume",
                    str(incomplete_run_dir),
                    "--output",
                    str(temp_results_dir),
                ],
            )

        assert result.exit_code == 0
        assert "RESUMING RUN" in result.output

    def test_resume_with_fill_gaps(
        self, runner: CliRunner, incomplete_run_dir: Path, temp_results_dir: Path
    ) -> None:
        """Test --resume --fill-gaps shows gap information."""
        with patch("matric_eval.core.engine.EvaluationEngine.run_benchmark") as run_benchmark:
            run_benchmark.return_value = {
                "benchmark": "mbpp",
                "status": "success",
                "score": 0.7,
                "samples": 5,
            }
            result = runner.invoke(
                cli,
                [
                    "run",
                    "--resume",
                    str(incomplete_run_dir),
                    "--fill-gaps",
                    "--output",
                    str(temp_results_dir),
                ],
            )

        assert result.exit_code == 0
        assert "FILLING GAPS" in result.output
        assert "mbpp" in result.output

    def test_resume_nonexistent_run(self, runner: CliRunner, temp_results_dir: Path) -> None:
        """Test resuming nonexistent run fails."""
        result = runner.invoke(
            cli,
            [
                "run",
                "--resume",
                "nonexistent-run",
                "--output",
                str(temp_results_dir),
            ],
        )

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_resume_locked_run_fails(self, runner: CliRunner, temp_results_dir: Path) -> None:
        """Test resuming locked run fails."""
        run_dir = temp_results_dir / "run-locked"
        run_dir.mkdir()

        # Create locked run
        state_manager = StateManager(run_dir)
        state_manager.initialize_run(
            run_id="run-locked",
            tier="smoke",
            seed=42,
            models=["llama3.2:3b"],
            benchmarks=["humaneval"],
        )
        with pytest.raises(RuntimeError, match="Run is locked"):
            state_manager.acquire_lock()

        # Try to resume (should fail due to lock)
        result = runner.invoke(
            cli,
            [
                "run",
                "--resume",
                str(run_dir),
                "--output",
                str(temp_results_dir),
            ],
        )

        assert result.exit_code != 0
        assert "locked" in result.output.lower()

    def test_resume_completed_run_reports_distinct_error(
        self, runner: CliRunner, temp_results_dir: Path
    ) -> None:
        """A completed checkpoint should not be reported as corrupt."""
        run_dir = temp_results_dir / "run-complete"
        manager = StateManager(run_dir)
        manager.initialize_run("run-complete", "smoke", 42, ["model"], ["humaneval"])
        manager.mark_complete("model", "humaneval", score=1.0, total_problems=5)
        manager.release_lock()

        result = runner.invoke(cli, ["run", "--resume", str(run_dir)])

        assert result.exit_code != 0
        assert "already complete" in result.output.lower()
        assert "corrupt" not in result.output.lower()

    def test_resume_corrupt_run_reports_invalid_checkpoint(
        self, runner: CliRunner, temp_results_dir: Path
    ) -> None:
        """Malformed state should produce a deterministic corruption diagnostic."""
        run_dir = temp_results_dir / "run-corrupt"
        run_dir.mkdir()
        (run_dir / "state.json").write_text("{not-json")
        (run_dir / "meta.json").write_text("{}")

        result = runner.invoke(cli, ["run", "--resume", str(run_dir)])

        assert result.exit_code != 0
        assert "invalid checkpoint state" in result.output.lower()


class TestResumeExecution:
    """Test actual resume execution (integration-level)."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI runner."""
        return CliRunner()

    def test_fresh_run_creates_complete_unlocked_checkpoint(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Normal execution should create usable immutable checkpoint metadata."""
        results_dir = tmp_path / "results"
        with patch("matric_eval.core.engine.EvaluationEngine.run_benchmark") as run_benchmark:
            run_benchmark.return_value = {
                "benchmark": "humaneval",
                "status": "success",
                "score": 0.75,
                "samples": 5,
            }
            result = runner.invoke(
                cli,
                [
                    "run",
                    "--model",
                    "llama3.2:3b",
                    "--benchmark",
                    "humaneval",
                    "--output",
                    str(results_dir),
                ],
            )

        assert result.exit_code == 0
        run_dirs = list(results_dir.glob("run-*"))
        assert len(run_dirs) == 1
        manager = StateManager(run_dirs[0])
        assert manager.load_run_state().status == Status.COMPLETED
        assert manager.load_metadata()["checkpoint_granularity"] == "benchmark"
        assert manager.is_locked() is False

    def test_resume_executes_only_missing_benchmarks(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Resume should execute gaps and retain completed benchmark results."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()

        run_dir = results_dir / "run-test"
        run_dir.mkdir()

        # Create incomplete run
        state_manager = StateManager(run_dir)
        state_manager.initialize_run(
            run_id="run-test",
            tier="smoke",
            seed=123,
            models=["llama3.2:3b"],
            benchmarks=["humaneval", "mbpp"],
        )
        state_manager.mark_complete(
            "llama3.2:3b",
            "humaneval",
            score=0.8,
            total_problems=5,
            result={
                "benchmark": "humaneval",
                "model": "ollama/llama3.2:3b",
                "status": "success",
                "score": 0.8,
                "samples": 5,
            },
        )
        state_manager.release_lock()

        settings = get_settings()
        previous_seed = settings.seed
        settings.seed = 999

        with patch("matric_eval.core.engine.EvaluationEngine.run_benchmark") as run_benchmark:

            def complete_mbpp(benchmark: str) -> dict[str, object]:
                assert get_seed() == 123
                return {
                    "benchmark": benchmark,
                    "model": "ollama/llama3.2:3b",
                    "status": "success",
                    "score": 0.6,
                    "samples": 5,
                }

            run_benchmark.side_effect = complete_mbpp
            try:
                result = runner.invoke(
                    cli,
                    ["run", "--resume", str(run_dir), "--output", str(results_dir)],
                )
            finally:
                restored_seed = settings.seed
                settings.seed = previous_seed

        assert result.exit_code == 0
        assert restored_seed == 999
        assert "RESUMING RUN" in result.output
        run_benchmark.assert_called_once_with("mbpp")
        final_state = state_manager.load_run_state()
        assert final_state.status == Status.COMPLETED
        assert final_state.completed_models == ["llama3.2:3b"]
        assert not state_manager.is_locked()

        summary = json.loads((run_dir / "summary.json").read_text())
        resumed = summary["results"][0]
        assert resumed["benchmarks"]["humaneval"]["resumed_from_checkpoint"] is True
        assert resumed["benchmarks"]["mbpp"]["score"] == 0.6
