"""
Tests for EvaluationEngine (matric_eval.core.engine).

Covers:
- Engine initialization
- Single benchmark execution
- Multi-benchmark execution
- Error handling and recovery
- Checkpoint support
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from matric_eval.core import EvaluationEngine


@pytest.mark.unit
class TestEngineInitialization:
    """Tests for EvaluationEngine initialization."""

    def test_init_with_defaults(self, tmp_path: Path) -> None:
        """Should initialize with default parameters."""
        engine = EvaluationEngine(
            model="ollama/llama3.2:3b",
            log_dir=tmp_path,
        )

        assert engine.model == "ollama/llama3.2:3b"
        assert engine.tier == "smoke"
        assert engine.log_dir == tmp_path
        assert engine.tier_config.humaneval == 5

    def test_init_with_custom_tier(self, tmp_path: Path) -> None:
        """Should initialize with custom tier."""
        engine = EvaluationEngine(
            model="ollama/qwen2.5:7b",
            tier="quick",
            log_dir=tmp_path,
        )

        assert engine.tier == "quick"
        assert engine.tier_config.humaneval == 75

    def test_creates_log_directory(self, tmp_path: Path) -> None:
        """Should create log directory if it doesn't exist."""
        log_dir = tmp_path / "new_logs"
        assert not log_dir.exists()

        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=log_dir,
        )

        assert log_dir.exists()
        assert log_dir.is_dir()


@pytest.mark.unit
class TestRunBenchmark:
    """Tests for run_benchmark() method."""

    def test_successful_benchmark(
        self,
        tmp_path: Path,
        mock_eval_log: MagicMock,
    ) -> None:
        """Should run benchmark successfully and return results."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
        )

        with patch("matric_eval.core.engine.eval") as mock_eval:
            mock_eval.return_value = [mock_eval_log]

            result = engine.run_benchmark(
                "humaneval",
                task=Mock(),  # Provide a mock task to skip loading
            )

            assert result["status"] == "success"
            assert result["benchmark"] == "humaneval"
            assert result["model"] == "ollama/test"
            assert result["score"] == 0.8
            assert result["samples"] == 5

    def test_benchmark_with_error(self, tmp_path: Path) -> None:
        """Should handle evaluation errors gracefully."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
        )

        with patch("matric_eval.core.engine.eval") as mock_eval:
            mock_eval.side_effect = Exception("Model timeout")

            result = engine.run_benchmark(
                "humaneval",
                task=Mock(),
            )

            assert result["status"] == "error"
            assert "Model timeout" in result["error"]
            assert result["score"] == 0.0

    def test_benchmark_no_logs_returned(self, tmp_path: Path) -> None:
        """Should handle case when eval() returns empty log list."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
        )

        with patch("matric_eval.core.engine.eval") as mock_eval:
            mock_eval.return_value = []

            result = engine.run_benchmark(
                "humaneval",
                task=Mock(),
            )

            assert result["status"] == "error"
            assert "No evaluation logs" in result["error"]


@pytest.mark.unit
class TestRunAll:
    """Tests for run_all() method."""

    def test_run_all_benchmarks_success(
        self,
        tmp_path: Path,
    ) -> None:
        """Should run all benchmarks and calculate overall score."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
        )

        # Mock run_benchmark to avoid actual eval calls
        def mock_run_benchmark(benchmark: str, **kwargs):
            scores = {"humaneval": 0.8, "mbpp": 0.7, "gsm8k": 0.6}
            return {
                "benchmark": benchmark,
                "status": "success",
                "score": scores.get(benchmark, 0.0),
                "samples": 5,
            }

        with patch.object(engine, "run_benchmark", side_effect=mock_run_benchmark):
            result = engine.run_all(["humaneval", "mbpp", "gsm8k"])

            assert result["status"] == "success"
            assert result["model"] == "ollama/test"
            assert len(result["benchmarks"]) == 3
            assert result["overall_score"] == pytest.approx(0.7)  # (0.8 + 0.7 + 0.6) / 3

    def test_run_all_with_failures(
        self,
        tmp_path: Path,
    ) -> None:
        """Should handle partial failures and calculate score from successful benchmarks only."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
        )

        def mock_run_benchmark(benchmark: str, **kwargs):
            if benchmark == "mbpp":
                return {
                    "benchmark": benchmark,
                    "status": "error",
                    "error": "Model timeout",
                    "score": 0.0,
                }
            return {
                "benchmark": benchmark,
                "status": "success",
                "score": 0.75,
                "samples": 5,
            }

        with patch.object(engine, "run_benchmark", side_effect=mock_run_benchmark):
            result = engine.run_all(["humaneval", "mbpp", "gsm8k"])

            assert result["status"] == "success"
            assert result["benchmarks"]["humaneval"]["status"] == "success"
            assert result["benchmarks"]["mbpp"]["status"] == "error"
            assert result["benchmarks"]["gsm8k"]["status"] == "success"
            # Score should average only successful benchmarks
            assert result["overall_score"] == pytest.approx(0.75)

    def test_run_all_complete_failure(
        self,
        tmp_path: Path,
    ) -> None:
        """Should set status to error when all benchmarks fail."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
        )

        def mock_run_benchmark(benchmark: str, **kwargs):
            return {
                "benchmark": benchmark,
                "status": "error",
                "error": "Connection refused",
                "score": 0.0,
            }

        with patch.object(engine, "run_benchmark", side_effect=mock_run_benchmark):
            result = engine.run_all(["humaneval", "mbpp", "gsm8k"])

            assert result["status"] == "error"
            assert result["overall_score"] == 0.0


@pytest.mark.unit
class TestLoadTask:
    """Tests for _load_task() method."""

    def test_load_known_task(self, tmp_path: Path) -> None:
        """Should load tier-aware task from matric_eval.tasks module."""
        engine = EvaluationEngine(
            model="ollama/test",
            tier="smoke",
            log_dir=tmp_path,
        )

        with patch("importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_task_fn = Mock(return_value=Mock())
            mock_module.humaneval = mock_task_fn
            mock_import.return_value = mock_module

            task = engine._load_task("humaneval")

            assert task is not None
            mock_import.assert_called_once_with("matric_eval.tasks.humaneval")
            mock_task_fn.assert_called_once_with(tier="smoke")

    def test_load_all_benchmark_types(self, tmp_path: Path) -> None:
        """Should support loading all registered benchmark types."""
        engine = EvaluationEngine(
            model="ollama/test",
            tier="quick",
            log_dir=tmp_path,
        )

        expected_benchmarks = [
            "humaneval", "mbpp", "gsm8k", "arc", "ifeval",
            "ds1000", "livecodebench", "mtbench", "tool_calling",
        ]

        for benchmark in expected_benchmarks:
            with patch("importlib.import_module") as mock_import:
                mock_module = Mock()
                mock_task_fn = Mock(return_value=Mock())
                setattr(mock_module, benchmark, mock_task_fn)
                mock_import.return_value = mock_module

                task = engine._load_task(benchmark)

                assert task is not None
                mock_task_fn.assert_called_once_with(tier="quick")

    def test_load_unknown_task(self, tmp_path: Path) -> None:
        """Should raise ValueError for unknown benchmark."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
        )

        with pytest.raises(ValueError, match="Unknown benchmark"):
            engine._load_task("unknown_benchmark")


@pytest.mark.unit
class TestEngineIntegration:
    """Integration tests for EvaluationEngine workflows."""

    def test_full_evaluation_workflow(
        self,
        tmp_path: Path,
        mock_eval_log: MagicMock,
    ) -> None:
        """Should execute complete evaluation workflow."""
        engine = EvaluationEngine(
            model="ollama/llama3.2:3b",
            tier="smoke",
            log_dir=tmp_path,
        )

        with patch("matric_eval.core.engine.eval") as mock_eval:
            mock_eval.return_value = [mock_eval_log]

            # Run multiple benchmarks
            results = engine.run_all(
                ["humaneval", "mbpp", "gsm8k"],
                checkpoint=True,
            )

            assert results["status"] == "success"
            assert results["model"] == "ollama/llama3.2:3b"
            assert results["tier"] == "smoke"
            assert len(results["benchmarks"]) == 3

            # Verify eval was called for each benchmark
            assert mock_eval.call_count == 3

            # Verify log_dir was passed
            for call in mock_eval.call_args_list:
                assert call.kwargs["log_dir"] == str(tmp_path)
