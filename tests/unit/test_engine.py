"""
Tests for EvaluationEngine (matric_eval.core.engine).

Covers:
- Engine initialization
- Single benchmark execution
- Multi-benchmark execution
- Error handling and recovery
- Checkpoint support
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from inspect_ai.log import EvalLog

from matric_eval.core import EvaluationEngine
from matric_eval.state import StateManager
from matric_eval.state.manager import Status
from tests.metric_checkpoint import completed_metric_checkpoint


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

        EvaluationEngine(
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
        mock_eval_log: EvalLog,
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
            assert result["score"] is None
            assert result["execution"] == "completed"
            assert result["eligible"] is False
            assert (
                result["observation_result"]["metrics"]["exact/accuracy"]["estimate"]["value"]
                == 0.8
            )
            assert result["samples"] == 5
            assert result["provenance"]["schema_version"] == "1"
            assert result["provenance"]["framework"]["inspect_ai"] == "0.3.263"
            assert result["provenance"]["benchmark"]["name"] == "humaneval"
            assert "dataset_revision" in result["provenance"]["benchmark"]

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
            assert result["score"] is None
            assert result["execution"] == "failed"
            assert result["eligible"] is False
            assert result["provenance"]["benchmark"]["name"] == "humaneval"

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
            assert result["score"] is None
            assert result["execution"] == "failed"

    def test_thinking_config_is_expanded_into_inspect_eval_kwargs(
        self,
        tmp_path: Path,
        mock_eval_log: EvalLog,
    ) -> None:
        """Inspect eval rejects a nested generate_config keyword."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
            thinking_mode="off",
        )

        with patch("matric_eval.core.engine.eval", return_value=[mock_eval_log]) as mock_eval:
            result = engine.run_benchmark("humaneval", task=Mock())

        assert result["status"] == "success"
        assert mock_eval.call_args.kwargs["extra_body"] == {"enable_thinking": False}
        assert "generate_config" not in mock_eval.call_args.kwargs


@pytest.mark.unit
class TestRunAll:
    """Tests for run_all() method."""

    def test_run_all_benchmarks_success(
        self,
        tmp_path: Path,
    ) -> None:
        """Complete benchmarks retain scores without an undeclared overall aggregate."""
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
                "execution": "completed",
                "score": scores.get(benchmark, 0.0),
                "samples": 5,
            }

        with patch.object(engine, "run_benchmark", side_effect=mock_run_benchmark):
            result = engine.run_all(["humaneval", "mbpp", "gsm8k"])

            assert result["status"] == "success"
            assert result["model"] == "ollama/test"
            assert len(result["benchmarks"]) == 3
            assert result["overall_score"] is None
            assert result["aggregation_reason"] == "aggregation_undeclared"
            assert result["provenance"]["framework"]["inspect_evals"] == "0.19.0"

    def test_run_all_with_failures(
        self,
        tmp_path: Path,
    ) -> None:
        """A partial suite cannot masquerade as successful full-suite performance."""
        engine = EvaluationEngine(
            model="ollama/test",
            log_dir=tmp_path,
        )

        def mock_run_benchmark(benchmark: str, **kwargs):
            if benchmark == "mbpp":
                return {
                    "benchmark": benchmark,
                    "status": "error",
                    "execution": "failed",
                    "error": "Model timeout",
                    "score": None,
                }
            return {
                "benchmark": benchmark,
                "status": "success",
                "execution": "completed",
                "score": 0.75,
                "samples": 5,
            }

        with patch.object(engine, "run_benchmark", side_effect=mock_run_benchmark):
            result = engine.run_all(["humaneval", "mbpp", "gsm8k"])

            assert result["status"] == "partial"
            assert result["benchmarks"]["humaneval"]["status"] == "success"
            assert result["benchmarks"]["mbpp"]["status"] == "error"
            assert result["benchmarks"]["gsm8k"]["status"] == "success"
            assert result["overall_score"] is None
            assert result["suite_scope"] == {"requested": 3, "completed": 2, "scored": 2}

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
                "execution": "failed",
                "error": "Connection refused",
                "score": None,
            }

        with patch.object(engine, "run_benchmark", side_effect=mock_run_benchmark):
            result = engine.run_all(["humaneval", "mbpp", "gsm8k"])

            assert result["status"] == "error"
            assert result["overall_score"] is None
            assert result["execution"] == "failed"

    def test_run_all_persists_and_reuses_completed_benchmarks(
        self,
        tmp_path: Path,
        mock_eval_log: EvalLog,
    ) -> None:
        """Historical results remain diagnostic and cannot become accepted observations."""
        manager = StateManager(tmp_path / "run")
        manager.initialize_run(
            run_id="run",
            tier="smoke",
            seed=42,
            models=["test"],
            benchmarks=["humaneval", "mbpp"],
        )
        manager.mark_complete(
            "test",
            "humaneval",
            score=0.8,
            total_problems=5,
            result=completed_metric_checkpoint(
                mock_eval_log,
                benchmark="humaneval",
                run_id="run",
                model="ollama/test",
                correct=4,
            ),
        )

        original_state = (manager.get_model_dir("test") / "state.json").read_bytes()
        original_run_state = manager.state_file.read_bytes()
        engine = EvaluationEngine(model="ollama/test", log_dir=tmp_path / "logs")
        with patch.object(engine, "run_benchmark") as run_benchmark:
            run_benchmark.return_value = completed_metric_checkpoint(
                mock_eval_log,
                benchmark="mbpp",
                run_id="run",
                model="ollama/test",
                correct=3,
            )
            result = engine.run_all(
                ["humaneval", "mbpp"],
                state_manager=manager,
                checkpoint_model="test",
            )

        run_benchmark.assert_called_once_with("mbpp")
        retained = [
            Path(item["artifact"]["uri"]).read_bytes()
            for item in result["legacy_checkpoint_artifacts"]
        ]
        assert original_state in retained
        assert original_run_state in retained
        assert result["benchmarks"]["humaneval"]["status"] == "legacy_unverified"
        assert result["benchmarks"]["humaneval"]["score"] is None
        assert result["benchmarks"]["humaneval"]["eligible"] is False
        assert result["overall_score"] is None
        assert result["aggregation_reason"] == "aggregation_undeclared"
        assert manager.load_run_state().status == Status.COMPLETED

    def test_interrupted_run_retries_only_interrupted_benchmark(
        self,
        tmp_path: Path,
        mock_eval_log: EvalLog,
    ) -> None:
        """An interrupted coarse checkpoint requires manual recovery without replay."""
        manager = StateManager(tmp_path / "run")
        manager.initialize_run(
            run_id="run",
            tier="smoke",
            seed=42,
            models=["test"],
            benchmarks=["humaneval", "mbpp"],
        )
        engine = EvaluationEngine(model="ollama/test", log_dir=tmp_path / "logs")

        completed = completed_metric_checkpoint(
            mock_eval_log,
            benchmark="humaneval",
            run_id="run",
            model="ollama/test",
            correct=4,
        )
        with patch.object(
            engine,
            "run_benchmark",
            side_effect=[completed, KeyboardInterrupt()],
        ):
            with pytest.raises(KeyboardInterrupt):
                engine.run_all(
                    ["humaneval", "mbpp"],
                    state_manager=manager,
                    checkpoint_model="test",
                )

        assert manager.should_skip("test", "humaneval") is True
        assert manager.should_skip("test", "mbpp") is False
        assert manager.get_resume_work() == {"test": ["mbpp"]}

        resumed = completed_metric_checkpoint(
            mock_eval_log,
            benchmark="mbpp",
            run_id="run",
            model="ollama/test",
            correct=3,
        )
        with patch.object(engine, "run_benchmark", return_value=resumed) as run_benchmark:
            result = engine.run_all(
                ["humaneval", "mbpp"],
                state_manager=manager,
                checkpoint_model="test",
            )

        run_benchmark.assert_not_called()
        assert result["overall_score"] is None
        assert result["aggregation_reason"] == "aggregation_undeclared"
        assert manager.load_run_state().status != Status.COMPLETED
        assert all(item["status"] == "legacy_unverified" for item in result["benchmarks"].values())


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
            "humaneval",
            "mbpp",
            "gsm8k",
            "arc",
            "ifeval",
            "ds1000",
            "livecodebench",
            "mtbench",
            "tool_calling",
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
        mock_eval_log: EvalLog,
    ) -> None:
        """Should execute complete evaluation workflow."""
        engine = EvaluationEngine(
            model="ollama/llama3.2:3b",
            tier="smoke",
            log_dir=tmp_path,
        )

        with (
            patch("matric_eval.core.engine.eval") as mock_eval,
            patch.object(engine, "_load_task", return_value=Mock()),
        ):
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

            # Verify log_dir was passed (should include model name subdirectory)
            for call in mock_eval.call_args_list:
                assert call.kwargs["log_dir"].startswith(str(tmp_path))
                assert "llama3.2_3b" in call.kwargs["log_dir"]


@pytest.mark.unit
class TestRunPassKMigration:
    """Legacy spelling requires an explicit task predicate and delegates intact."""

    def test_missing_predicate_fails_before_execution(self, tmp_path: Path) -> None:
        runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
        with (
            patch.object(runner, "_load_task") as load,
            patch("matric_eval.core.engine.eval") as evaluate,
        ):
            with pytest.warns(DeprecationWarning), pytest.raises(ValueError, match="explicit"):
                runner.run_pass_k_benchmark("humaneval", k=2)
        load.assert_not_called()
        evaluate.assert_not_called()

    def test_legacy_spelling_delegates_explicit_n_and_predicate(self, tmp_path: Path) -> None:
        from matric_eval.results.trials import PassPredicate

        runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
        predicate = PassPredicate(
            version="1", kind="equals", threshold=1.0, units="all-tests-passed"
        )
        with patch.object(
            runner, "run_trial_benchmark", return_value={"trial_schema_version": "1"}
        ) as run:
            with pytest.warns(DeprecationWarning):
                result = runner.run_pass_k_benchmark("humaneval", k=2, n=5, predicate=predicate)
        run.assert_called_once_with("humaneval", n=5, k=2, predicate=predicate)
        assert result == {"trial_schema_version": "1"}


def test_direct_engine_missing_attempted_model_state_is_manual(tmp_path: Path) -> None:
    manager = StateManager(tmp_path / "missing-model")
    manager.initialize_run("missing-model", "smoke", 42, ["m"], ["b"])
    manager.mark_running("m", "b")
    (manager.get_model_dir("m") / "state.json").unlink()
    manager.release_lock()
    before = {
        path.relative_to(manager.run_dir): path.read_bytes()
        for path in manager.run_dir.rglob("*")
        if path.is_file()
    }
    engine = EvaluationEngine("m", log_dir=tmp_path / "logs")
    with patch.object(engine, "run_benchmark") as dispatch:
        result = engine.run_all(["b"], state_manager=manager)
    dispatch.assert_not_called()
    assert result["benchmarks"]["b"]["status"] == "legacy_unverified"
    assert result["benchmarks"]["b"]["score"] is None
    assert result["eligible"] is False
    assert {
        path.relative_to(manager.run_dir): path.read_bytes()
        for path in manager.run_dir.rglob("*")
        if path.is_file()
    } == before
