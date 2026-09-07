"""Engine trial execution freezes task selection and retains native outcome evidence."""

from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score

from matric_eval.core.engine import EvaluationEngine
from matric_eval.results.trial_execution import generation_seed_schedule
from matric_eval.results.trials import PassPredicate, TrialEvaluation
from tests.unit.test_inspect_result_adapter import ERROR, descriptor, native_log, sample


def predicate():
    return PassPredicate(version="1", kind="equals", threshold=1.0, units="fraction")


def selected_task():
    return Task(
        dataset=MemoryDataset(
            [
                Sample(id="a", input="first immutable question", target="first answer"),
                Sample(id="b", input="second immutable question", target="second answer"),
            ],
            name="synthetic/1",
        )
    )


def options():
    return {
        "predicate": predicate(),
        "metric_id": "exact/accuracy",
        "metric_descriptors": {"exact/accuracy": descriptor()},
    }


def execute(runner, task, outcomes, *, retries=False, temperature=0, recorded=True):
    seen = []

    def evaluate(instance, **kwargs):
        index = len(seen)
        seen.append(([item.model_dump() for item in instance.dataset], dict(kwargs)))
        assert instance.config.seed == kwargs["seed"]
        assert kwargs["epochs"] == 1
        assert kwargs["sample_shuffle"] is False
        rows = [
            sample(sid, value, **({"error_retries": [ERROR, ERROR]} if retries else {}))
            for sid, value in zip(["a", "b"], outcomes[index], strict=True)
        ]
        log = native_log(rows, ids=["a", "b"])
        log.eval.model_generate_config.seed = kwargs["seed"] if recorded else None
        log.eval.model_generate_config.temperature = temperature
        # Inspect may mutate its Task; each outer trial must get a fresh copy.
        instance.dataset[0].input = "mutated by evaluator"
        return [log]

    with (
        patch.object(runner, "_load_task", return_value=task) as load,
        patch("matric_eval.core.engine.eval", side_effect=evaluate),
    ):
        result = runner.run_trial_benchmark("synthetic", n=len(outcomes), k=2, **options())
    load.assert_called_once_with("synthetic")
    return TrialEvaluation.model_validate(result), seen


@pytest.mark.parametrize(
    ("outcomes", "pass_value", "reliability"),
    [([[1, 0], [0, 1]], 1.0, 0.0), ([[1, 0], [1, 0]], 0.5, 0.5)],
)
def test_aligned_native_trials_distinguish_same_aggregate_scores(
    tmp_path: Path, outcomes, pass_value, reliability
):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    task = selected_task()
    original = [item.model_dump() for item in task.dataset]
    result, seen = execute(runner, task, outcomes)
    assert result.macro_pass_at_k.value == pass_value
    assert result.macro_all_n_success.value == reliability
    assert result.execution == "completed"
    assert [entry[0] for entry in seen] == [original, original]
    assert [item.model_dump() for item in task.dataset] == original
    seeds = [kwargs["seed"] for _, kwargs in seen]
    assert len(set(seeds)) == 2
    assert seeds == generation_seed_schedule(42, 2) == result.protocol.generation_seeds
    observations = [row for trial in result.trials for row in trial.benchmark.observations]
    assert len({row.observation_id for row in observations}) == 4
    assert {row.identity.trial_id for row in observations} == {"trial-0", "trial-1"}
    assert all(row.outcome == "observed" for row in observations)
    assert all(task.n_requested == task.n_observed == 2 for task in result.per_task)
    assert any(row.value == 0 for row in observations)
    for trial in result.trials:
        evidence = trial.generation_evidence
        assert evidence.forwarding == "recorded"
        assert evidence.honored == "unverified"
        assert "deterministic_generation_may_repeat_outputs" in evidence.limitations
    assert result.protocol.statistical_claim == "descriptive_only"


def test_missing_grade_keeps_requested_denominator_and_null_macro(tmp_path: Path):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    result, _ = execute(
        runner, selected_task(), [[1, 0], [Score.unscored(reason="grader_failed"), 1]]
    )
    assert [(row.n_requested, row.n_observed) for row in result.per_task] == [(2, 1), (2, 2)]
    assert result.per_task[0].pass_at_k.value is None
    assert result.per_task[1].pass_at_k.value == 1.0
    assert result.macro_pass_at_k.value is None
    assert result.macro_all_n_success.value is None
    assert not result.eligibility.eligible


def test_native_retry_attempts_do_not_become_generation_trials(tmp_path: Path):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    result, _ = execute(runner, selected_task(), [[1, 0], [0, 1]], retries=True)
    assert len(result.trials) == 2
    assert all(task.n_observed == 2 for task in result.per_task)
    assert result.macro_pass_at_k.value == 1.0
    for trial in result.trials:
        rows = trial.benchmark.observations
        assert len(rows) == 6
        assert sum(row.accepted for row in rows) == 2
        assert len({row.observation_id for row in rows}) == 2
        assert all(row.previous_attempt_id is not None for row in rows if row.accepted)


def test_unrecorded_seed_and_temperature_remain_unverified(tmp_path: Path):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    result, _ = execute(runner, selected_task(), [[1, 1], [1, 1]], temperature=None, recorded=False)
    for trial in result.trials:
        evidence = trial.generation_evidence
        assert evidence.recorded_seed is None
        assert evidence.forwarding == evidence.honored == "unverified"
        assert "effective_temperature_unverified" in evidence.limitations


@pytest.mark.parametrize(("n", "k"), [(0, 1), (2, 0), (2, 3), (-1, 1), (True, 1), (2, 1.5)])
def test_invalid_trial_counts_fail_before_loading_or_evaluation(tmp_path: Path, n, k):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    with (
        patch.object(runner, "_load_task") as load,
        patch("matric_eval.core.engine.eval") as evaluate,
    ):
        with pytest.raises((ValueError, TypeError)):
            runner.run_trial_benchmark("synthetic", n=n, k=k, **options())
    load.assert_not_called()
    evaluate.assert_not_called()


@pytest.mark.parametrize(
    "override", [{"epochs": 2}, {"limit": 1}, {"seed": 7}, {"sample_shuffle": True}]
)
def test_trial_scope_cannot_be_overridden(tmp_path: Path, override):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    with (
        patch.object(runner, "_load_task") as load,
        patch("matric_eval.core.engine.eval") as evaluate,
    ):
        with pytest.raises(ValueError, match="protocol owns"):
            runner.run_trial_benchmark("synthetic", n=2, k=2, **options(), **override)
    load.assert_not_called()
    evaluate.assert_not_called()


def test_native_reordered_manifest_is_rejected(tmp_path: Path):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    log = native_log([sample("b"), sample("a")], ids=["b", "a"])
    with patch("matric_eval.core.engine.eval", return_value=[log]) as evaluate:
        with pytest.raises(ValueError, match="manifest differs"):
            runner.run_trial_benchmark("synthetic", n=2, k=2, task=selected_task(), **options())
    assert evaluate.call_count == 1


def test_dynamic_source_is_rejected_before_evaluation(tmp_path: Path):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    task = selected_task()
    with (
        patch.object(task, "sample_source", object()),
        patch("matric_eval.core.engine.eval") as evaluate,
    ):
        with pytest.raises(ValueError, match="dynamic sample"):
            runner.run_trial_benchmark("synthetic", n=2, k=2, task=task, **options())
    evaluate.assert_not_called()


@pytest.mark.parametrize(
    "failure", ["multiple_logs", "empty_logs", "exception", "missing_manifest"]
)
def test_unprojectable_trials_retain_artifacts_and_content_free_failure(tmp_path: Path, failure):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    private_content = "synthetic-private-provider-error-content"
    expected_artifacts = []
    expected_code = "RuntimeError" if failure == "exception" else "ValueError"
    calls = 0

    def evaluate(instance, **kwargs):
        nonlocal calls
        calls += 1
        if failure == "exception":
            raise RuntimeError(private_content)
        logs = []
        count = 2 if failure == "multiple_logs" else 0 if failure == "empty_logs" else 1
        for index in range(count):
            log = native_log(
                [sample("a"), sample("b")],
                status="error" if failure == "missing_manifest" else "success",
            )
            log.eval.eval_id = f"failed-trial-{calls}-log-{index}"
            if failure == "missing_manifest":
                log.eval.dataset.sample_ids = None
                log.error.message = private_content
            logs.append(log)
        expected_artifacts.append([f"inspect:{log.eval.eval_id}" for log in logs])
        return logs

    with patch("matric_eval.core.engine.eval", side_effect=evaluate):
        result = TrialEvaluation.model_validate(
            runner.run_trial_benchmark("synthetic", n=2, k=2, task=selected_task(), **options())
        )
    assert calls == 2
    assert result.execution == "failed"
    assert result.macro_pass_at_k.value is None
    assert result.macro_all_n_success.value is None
    assert not result.eligibility.eligible
    assert [(row.n_requested, row.n_observed, row.c) for row in result.per_task] == [
        (2, 0, 0),
        (2, 0, 0),
    ]
    for index, trial in enumerate(result.trials):
        assert trial.benchmark is None
        assert trial.unavailable_reason == "trial_projection_unavailable"
        assert trial.failure_code == expected_code
        assert [artifact.uri for artifact in trial.artifacts] == (
            [] if failure == "exception" else expected_artifacts[index]
        )
        for artifact in trial.artifacts:
            assert artifact.sha256 is None
            assert artifact.unavailable_reason == "native_artifact_not_locally_hashable"
    assert private_content not in result.model_dump_json()


def test_repeated_engine_calls_allocate_distinct_observation_identity(tmp_path: Path):
    runner = EvaluationEngine("ollama/test", log_dir=tmp_path)
    original_run_id = runner.run_id
    first, _ = execute(runner, selected_task(), [[1, 0], [0, 1]])
    second, _ = execute(runner, selected_task(), [[1, 0], [0, 1]])
    assert first.run_id != second.run_id
    assert runner.run_id == original_run_id
    assert first.protocol == second.protocol
    first_ids = {
        row.observation_id for trial in first.trials for row in trial.benchmark.observations
    }
    second_ids = {
        row.observation_id for trial in second.trials for row in trial.benchmark.observations
    }
    assert first_ids.isdisjoint(second_ids)
