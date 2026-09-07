"""Engine/checkpoint integration preserves native execution and unscored outcomes."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score

from matric_eval.core.engine import EvaluationEngine
from matric_eval.results.contract import read_result
from matric_eval.state import StateManager
from tests.unit.test_inspect_result_adapter import descriptor, native_log, sample


def engine(tmp_path: Path) -> EvaluationEngine:
    return EvaluationEngine("ollama/model:7b", log_dir=tmp_path / "logs")


def task() -> Task:
    return Task(dataset=[Sample(id="a", input="synthetic", target="synthetic")])


@pytest.mark.parametrize(
    ("native", "status"),
    [
        ("success", "success"),
        ("error", "error"),
        ("cancelled", "cancelled"),
        ("started", "partial"),
    ],
)
def test_returned_native_status_controls_engine_result(
    tmp_path: Path, native: str, status: str
) -> None:
    runner = engine(tmp_path)
    with patch(
        "matric_eval.core.engine.eval", return_value=[native_log([sample("a")], status=native)]
    ):
        result = runner.run_benchmark(
            "synthetic",
            task=task(),
            primary_metric_id="exact/accuracy",
            metric_descriptors={"exact/accuracy": descriptor()},
        )
    assert result["status"] == status
    assert result["eligible"] is (native == "success")
    assert result["counts"]["requested"] == 1
    assert result["observation_result"]["observations"][0]["value"] == 1


@pytest.mark.parametrize("count", [0, 2])
def test_empty_and_multiple_logs_fail_explicitly(tmp_path: Path, count: int) -> None:
    runner = engine(tmp_path)
    logs = [native_log([sample("a")]) for _ in range(count)]
    with patch("matric_eval.core.engine.eval", return_value=logs):
        result = runner.run_benchmark("synthetic", task=task())
        assert result["status"] == "error"
        assert result["score"] is None
        assert not result["eligible"]
        assert len(result["native_logs"]) == count
        with pytest.raises(ValueError, match="v2 projection unavailable"):
            runner.run_benchmark("synthetic", task=task(), result_format="v2")


def test_all_unscored_terminal_work_is_checkpointed_without_score_imputation(
    tmp_path: Path,
) -> None:
    runner = engine(tmp_path)
    manager = StateManager(tmp_path / "state")
    manager.initialize_run("stable-run", "smoke", 42, ["ollama/model:7b"], ["synthetic"])
    log = native_log([sample("a", Score.unscored(reason="grader_failed"))], value=float("nan"))
    with (
        patch.object(runner, "_load_task", return_value=task()),
        patch("matric_eval.core.engine.eval", return_value=[log]) as evaluate,
    ):
        first = runner.run_all(
            ["synthetic"],
            state_manager=manager,
            primary_metric_id="exact/accuracy",
            metric_descriptors={"exact/accuracy": descriptor()},
        )
        second = runner.run_all(
            ["synthetic"],
            state_manager=manager,
            primary_metric_id="exact/accuracy",
            metric_descriptors={"exact/accuracy": descriptor()},
        )
        assert evaluate.call_count == 1
        with pytest.raises(ValueError, match="no verified observation manifest"):
            runner.run_all(
                ["synthetic"],
                state_manager=manager,
                result_format="v2",
                primary_metric_id="exact/accuracy",
                metric_descriptors={"exact/accuracy": descriptor()},
            )
        assert evaluate.call_count == 1
        # Preserve truthful all-unscored v2 projection coverage through a fresh
        # dispatch, rather than promoting an unverified coarse checkpoint.
        fresh_runner = engine(tmp_path / "fresh")
        v2 = fresh_runner.run_all(
            ["synthetic"],
            checkpoint=False,
            task=task(),
            result_format="v2",
            primary_metric_id="exact/accuracy",
            metric_descriptors={"exact/accuracy": descriptor()},
        )
        assert evaluate.call_count == 2
    assert first["status"] == "success"
    assert first["execution"] == "completed"
    assert second["status"] == "error"
    historical = second["benchmarks"]["synthetic"]
    assert historical["status"] == "legacy_unverified"
    assert historical["execution"] == "unknown"
    assert historical["score"] is None
    assert historical["historical_result"] == first["benchmarks"]["synthetic"]
    assert first["overall_score"] is second["overall_score"] is None
    assert not first["eligible"] and not second["eligible"]
    assert manager.get_benchmark_result("ollama/model:7b", "synthetic")["score"] is None
    measured = read_result(json.dumps(v2, allow_nan=False)).benchmarks[0]
    assert measured.execution == "completed"
    assert measured.primary_estimate.value is None
    assert not measured.eligibility.eligible
    assert [(row.outcome, row.value) for row in measured.observations] == [("grader_failed", None)]


def test_error_log_requires_manual_recovery_and_preserves_history(tmp_path: Path) -> None:
    runner = engine(tmp_path)
    manager = StateManager(tmp_path / "state")
    manager.initialize_run("run", "smoke", 42, ["ollama/model:7b"], ["synthetic"])
    with (
        patch.object(runner, "_load_task", return_value=task()),
        patch(
            "matric_eval.core.engine.eval", return_value=[native_log([sample("a")], status="error")]
        ) as evaluate,
    ):
        first = runner.run_all(["synthetic"], state_manager=manager)
        original = {
            path: path.read_bytes() for path in manager.run_dir.rglob("*") if path.is_file()
        }
        second = runner.run_all(["synthetic"], state_manager=manager)
    assert evaluate.call_count == 1
    assert first["benchmarks"]["synthetic"]["execution"] == "failed"
    manual = second["benchmarks"]["synthetic"]
    assert manual["status"] == "legacy_unverified"
    assert manual["recovery_action"] == "manual"
    assert manual["execution"] == "unknown"
    assert manual["score"] is None
    assert not manual["eligible"]
    assert manual["historical_result"] == first["benchmarks"]["synthetic"]
    assert all(path.read_bytes() == payload for path, payload in original.items())
    for reference in second["legacy_checkpoint_artifacts"]:
        source = Path(reference["source_uri"])
        assert Path(reference["artifact"]["uri"]).read_bytes() == original[source]
    assert manager.get_benchmark_result("ollama/model:7b", "synthetic") is None


def test_checkpoint_rejects_failure_and_labels_legacy_evidence(tmp_path: Path) -> None:
    manager = StateManager(tmp_path / "state")
    manager.initialize_run("run", "smoke", 42, ["model"], ["synthetic"])
    with pytest.raises(ValueError, match="completed execution"):
        manager.mark_complete("model", "synthetic", None, result={"execution": "failed"})
    manager.mark_complete("model", "synthetic", 0.8)
    legacy = manager.get_benchmark_result("model", "synthetic")
    assert legacy["execution"] == "unknown"
    assert not legacy["eligible"]
    assert not manager.should_skip("model", "synthetic")
    assert manager.build_model_result("model")["status"] == "error"


@pytest.mark.parametrize("reason", ["refusal", "invalid_response_format", "no_response"])
def test_scored_model_failure_reason_remains_measured(tmp_path: Path, reason: str) -> None:
    runner = engine(tmp_path)
    log = native_log([sample("a", Score(value="I", reason=reason))], value=0.0)
    with patch("matric_eval.core.engine.eval", return_value=[log]):
        result = runner.run_benchmark(
            "synthetic",
            task=task(),
            primary_metric_id="exact/accuracy",
            metric_descriptors={"exact/accuracy": descriptor()},
        )
    assert result["score"] == 0.0
    assert result["eligible"]
    row = result["observation_result"]["observations"][0]
    assert row["outcome"] == "observed"
    assert row["native_status"] == reason


def test_failed_log_without_summary_keeps_existing_sample_grades(tmp_path: Path) -> None:
    runner = engine(tmp_path)
    log = native_log(
        [sample("a", "I"), sample("b", Score.unscored(reason="grader_failed"))], status="error"
    )
    log.results = None
    with patch("matric_eval.core.engine.eval", return_value=[log]):
        result = runner.run_benchmark("synthetic", task=task())
    rows = result["observation_result"]["observations"]
    assert [(row["outcome"], row["value"]) for row in rows] == [
        ("observed", 0.0),
        ("grader_failed", None),
    ]
    assert result["status"] == "error"
    assert result["score"] is None
