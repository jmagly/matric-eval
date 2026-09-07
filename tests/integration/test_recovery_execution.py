"""Real Inspect mockllm dispatch with journal recovery; no inference service.

On non-ext4 test hosts the private storage seam tests transaction semantics only.
The JUnit property records that distinction; it never qualifies power loss.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import match
from inspect_ai.solver import generate

from matric_eval.core import recovery_execution as execution
from matric_eval.core.engine import EvaluationEngine
from matric_eval.results.contract import MetricDescriptor
from matric_eval.state import journal as journal_module


@pytest.fixture
def recovery_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record_property: Any) -> Path:
    actual = journal_module.storage_profile(tmp_path)
    record_property("actual_storage_profile", json.dumps(actual, sort_keys=True))
    record_property(
        "qualification", "actual_ext4" if actual["supported"] else "transaction_semantics_only"
    )
    if not actual["supported"]:
        monkeypatch.setattr(
            journal_module, "storage_profile", lambda _: {**actual, "supported": True}
        )
    return tmp_path / "recovery"


def options(recovery_dir: Path) -> dict[str, Any]:
    descriptor = MetricDescriptor(
        metric_id="match/accuracy",
        version="1",
        scorer_id="match",
        value_kind="binary",
        units="proportion",
        direction="higher",
        minimum=0.0,
        maximum=1.0,
        independent_unit="sample",
        missingness_policy="exclude/1",
        aggregation_id="accuracy/1",
        timeout_value=None,
    )
    return {
        "task": Task(
            dataset=MemoryDataset(
                [
                    Sample(
                        id="correct", input="Say hello", target="Default output from mockllm/model"
                    ),
                    Sample(id="wrong", input="Say hello", target="different"),
                ],
                name="recovery-fixture",
            ),
            solver=generate(),
            scorer=match(),
        ),
        "benchmark": "fixture",
        "model": "mockllm/model",
        "recovery_dir": recovery_dir,
        "run_id": "stable-run",
        "metric_descriptors": {descriptor.metric_id: descriptor},
        "primary_metric_id": descriptor.metric_id,
        "generation_seeds": [17, 29],
    }


@pytest.mark.integration
def test_real_inspect_acceptance_and_qualified_reuse(recovery_dir: Path) -> None:
    kwargs = options(recovery_dir)
    original = execution.eval
    with patch.object(execution, "eval", wraps=original) as dispatch:
        first = execution.run_recoverable(**kwargs)
        assert first["recovery_status"] == "complete", first
        assert dispatch.call_count == 4
        second = execution.run_recoverable(**kwargs)
        assert dispatch.call_count == 4
    assert second["recovery_status"] == "complete", second
    assert [item["observations"][0]["value"] for item in first["sample_results"]] == [1, 0, 1, 0]
    ids = [item["observations"][0]["observation_id"] for item in first["sample_results"]]
    assert len(set(ids)) == 4
    for fresh, reused in zip(first["sample_results"], second["sample_results"], strict=True):
        assert fresh["acceptance_basis"] == "same_dispatch_commit_receipt"
        assert reused["acceptance_basis"] == "qualified_journal_reuse"
        assert fresh["observations"] == reused["observations"]
        assert reused["native_result"]["selection"][0]["trial_id"] == reused["trial_id"]
        assert all(row["accepted"] for row in reused["observations"])


@pytest.mark.integration
def test_interruption_leaves_intent_and_never_replays(recovery_dir: Path) -> None:
    kwargs = options(recovery_dir)
    kwargs["task"].dataset = MemoryDataset(
        [list(kwargs["task"].dataset)[0]], name="recovery-fixture"
    )
    kwargs["generation_seeds"] = [17]
    with patch.object(execution, "eval", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            execution.run_recoverable(**kwargs)
    with patch.object(execution, "eval", side_effect=RuntimeError("must not dispatch")) as dispatch:
        result = execution.run_recoverable(**kwargs)
        dispatch.assert_not_called()
    assert result["recovery_status"] == "manual_recovery_required"
    assert result["sample_results"][0]["observations"] == []
    assert "intent_without_reusable_acceptance" in result["sample_results"][0]["reasons"][0]


@pytest.mark.integration
def test_changed_plan_and_mutated_native_bytes_refuse_reuse(recovery_dir: Path) -> None:
    kwargs = options(recovery_dir)
    first = execution.run_recoverable(**kwargs)
    assert first["recovery_status"] == "complete", first
    kwargs["task"].dataset[0].target = "changed"
    with patch.object(execution, "eval") as dispatch:
        changed = execution.run_recoverable(**kwargs)
        dispatch.assert_not_called()
    assert all(item["disposition"] == "manual" for item in changed["sample_results"])
    kwargs = options(recovery_dir)
    native = Path(first["sample_results"][0]["observations"][0]["artifacts"][0]["uri"])
    native.write_bytes(native.read_bytes() + b"corruption")
    with patch.object(execution, "eval") as dispatch:
        corrupt = execution.run_recoverable(**kwargs)
        dispatch.assert_not_called()
    assert corrupt["recovery_status"] == "manual_recovery_required"
    assert corrupt["sample_results"][0]["observations"] == []


@pytest.mark.integration
def test_lost_commit_acknowledgement_recovers_accepted_terminal(recovery_dir: Path) -> None:
    kwargs = options(recovery_dir)
    original = journal_module.ObservationJournal.commit_terminal

    def lost_ack(self: Any, terminal: Any) -> Any:
        original(self, terminal)
        raise RuntimeError("lost acknowledgement")

    with patch.object(journal_module.ObservationJournal, "commit_terminal", lost_ack):
        first = execution.run_recoverable(**kwargs)
    assert first["recovery_status"] == "manual_recovery_required"
    with patch.object(execution, "eval") as dispatch:
        recovered = execution.run_recoverable(**kwargs)
        dispatch.assert_not_called()
    assert recovered["recovery_status"] == "complete", recovered
    assert all(item["disposition"] == "reused" for item in recovered["sample_results"])


@pytest.mark.integration
def test_unknown_component_first_acceptance_is_not_reuse_authorization(recovery_dir: Path) -> None:
    kwargs = options(recovery_dir)
    capture = execution.capture_execution_fingerprint

    def unknown(*args: Any, **kw: Any) -> Any:
        fingerprint = capture(*args, **kw)
        fingerprint.environment.status = "unverified"
        fingerprint.environment.unavailable_reason = "qualification_unavailable"
        return fingerprint

    with patch.object(execution, "capture_execution_fingerprint", unknown):
        first = execution.run_recoverable(**kwargs)
        assert first["recovery_status"] == "complete", first
        with patch.object(execution, "eval") as dispatch:
            second = execution.run_recoverable(**kwargs)
            dispatch.assert_not_called()
    assert all(not item["reuse_eligibility"]["eligible"] for item in first["sample_results"])
    assert second["recovery_status"] == "manual_recovery_required"


def test_engine_recovery_rejects_implicit_overrides(tmp_path: Path) -> None:
    engine = EvaluationEngine("mockllm/model", thinking_mode="on", log_dir=tmp_path)
    kwargs = options(tmp_path / "recovery")
    del kwargs["model"]
    with pytest.raises(ValueError, match="adapter overrides"):
        engine.run_recoverable_benchmark(**kwargs)


def test_multiple_direct_metrics_for_one_scorer_refused_before_dispatch(tmp_path: Path) -> None:
    kwargs = options(tmp_path / "recovery")
    descriptor = kwargs["metric_descriptors"]["match/accuracy"]
    kwargs["metric_descriptors"]["match/mean"] = descriptor.model_copy(
        update={"metric_id": "match/mean"}
    )
    with patch.object(execution, "eval") as dispatch:
        with pytest.raises(ValueError, match="one direct metric"):
            execution.run_recoverable(**kwargs)
        dispatch.assert_not_called()


@pytest.mark.integration
def test_native_applied_config_mismatch_never_accepted(recovery_dir: Path) -> None:
    kwargs = options(recovery_dir)
    original = execution.read_eval_log

    def altered(*args: Any, **kw: Any) -> Any:
        native = original(*args, **kw)
        native.eval.model_generate_config.seed = 9999
        return native

    with patch.object(execution, "read_eval_log", altered):
        result = execution.run_recoverable(**kwargs)
    assert result["recovery_status"] == "manual_recovery_required"
    assert all(item["observations"] == [] for item in result["sample_results"])
    assert all(
        "native_generation_configuration_mismatch" in item["reasons"][0]
        for item in result["sample_results"]
    )


def _kill_boundary_worker(directory: str, stage: str, ready: Any, release: Any) -> None:
    """Spawned process owns a real Inspect dispatch and pauses at one boundary."""
    path = Path(directory)
    actual = journal_module.storage_profile(path.parent)
    if not actual["supported"]:
        journal_module.storage_profile = lambda _: {**actual, "supported": True}

    def pause() -> None:
        ready.set()
        if not release.wait(120):
            raise RuntimeError("test parent did not terminate boundary worker")

    if stage == "before_intent":
        original_intent = journal_module.ObservationJournal.record_intent

        def intent(self: Any, request: Any) -> Any:
            pause()
            return original_intent(self, request)

        journal_module.ObservationJournal.record_intent = intent
    elif stage in {"before_dispatch", "after_execution"}:
        original_eval = execution.eval

        def dispatch(*args: Any, **kwargs: Any) -> Any:
            if stage == "before_dispatch":
                pause()
            logs = original_eval(*args, **kwargs)
            if stage == "after_execution":
                pause()
            return logs

        execution.eval = dispatch
    elif stage == "after_artifact":
        original_retain = execution._retain_native

        def retain(*args: Any, **kwargs: Any) -> Any:
            artifact = original_retain(*args, **kwargs)
            pause()
            return artifact

        execution._retain_native = retain
    elif stage == "between_samples":
        original_commit = journal_module.ObservationJournal.commit_terminal

        def commit(self: Any, terminal: Any) -> Any:
            receipt = original_commit(self, terminal)
            pause()
            return receipt

        journal_module.ObservationJournal.commit_terminal = commit
    else:
        raise ValueError(stage)
    execution.run_recoverable(**options(path))


@pytest.mark.integration
@pytest.mark.parametrize(
    "stage",
    ["before_intent", "before_dispatch", "after_execution", "after_artifact", "between_samples"],
)
def test_killed_inspect_controller_resumes_only_authorized_scopes(
    recovery_dir: Path, stage: str
) -> None:
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    process = context.Process(
        target=_kill_boundary_worker, args=(str(recovery_dir), stage, ready, release)
    )
    process.start()
    try:
        assert ready.wait(90), f"worker exited {process.exitcode} before {stage}"
        process.kill()
        process.join(10)
        assert not process.is_alive()
        assert process.exitcode is not None and process.exitcode < 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
    original_eval = execution.eval
    with patch.object(execution, "eval", wraps=original_eval) as dispatch:
        result = execution.run_recoverable(**options(recovery_dir))
    if stage == "before_intent":
        assert result["recovery_status"] == "complete", result
        assert dispatch.call_count == 4
    elif stage == "between_samples":
        assert result["recovery_status"] == "complete", result
        assert result["sample_results"][0]["disposition"] == "reused"
        assert dispatch.call_count == 3
    else:
        assert result["recovery_status"] == "manual_recovery_required", result
        assert result["sample_results"][0]["disposition"] == "manual"
        assert result["sample_results"][0]["observations"] == []
        assert dispatch.call_count == 3
        assert all(item["disposition"] == "executed" for item in result["sample_results"][1:])


@pytest.mark.integration
def test_provider_error_content_is_not_echoed_in_recovery_report(recovery_dir: Path) -> None:
    with patch.object(
        execution, "eval", side_effect=RuntimeError("secret prompt and credential marker")
    ):
        result = execution.run_recoverable(**options(recovery_dir))
    assert result["recovery_status"] == "manual_recovery_required"
    assert result["execution"] == "unknown"
    assert result["status"] == "error"
    assert result["journal_capture_complete"] is False
    assert result["eligibility"]["eligible"] is False
    assert "secret prompt" not in json.dumps(result)
    assert all(
        item["reasons"] == ["dispatch_or_native_evidence_unavailable"]
        for item in result["sample_results"]
    )


class _ChangingDataset(MemoryDataset):
    """Each iteration exposes a different payload under the same stable ID."""

    def __iter__(self) -> Any:
        self.iterations = getattr(self, "iterations", 0) + 1
        return iter(
            [
                Sample(
                    id="stable",
                    input=f"payload-{self.iterations}",
                    target="Default output from mockllm/model",
                )
            ]
        )


@pytest.mark.integration
def test_changing_dataset_is_materialized_once_before_capture(recovery_dir: Path) -> None:
    kwargs = options(recovery_dir)
    kwargs["task"].dataset = _ChangingDataset([], name="changing")
    original = execution.eval
    dispatched = []

    def observe(task: Task, **kw: Any) -> Any:
        dispatched.extend(sample.input for sample in task.dataset)
        return original(task, **kw)

    with patch.object(execution, "eval", observe):
        result = execution.run_recoverable(**kwargs)
    assert result["recovery_status"] == "complete", result
    assert dispatched == ["payload-1", "payload-1"]
    with journal_module.ObservationJournal(recovery_dir / "observations.sqlite") as journal:
        documents = [
            item["intent"].fingerprint.dataset.document for item in journal.list_attempts()
        ]
    assert documents[0] == documents[1]


@pytest.mark.integration
@pytest.mark.parametrize("field", ["input", "target", "choices", "metadata"])
def test_native_content_drift_refuses_acceptance(recovery_dir: Path, field: str) -> None:
    original = execution.read_eval_log

    def altered(*args: Any, **kw: Any) -> Any:
        native = original(*args, **kw)
        assert native.samples
        value = {
            "input": "changed input",
            "target": "changed target",
            "choices": ["changed"],
            "metadata": {"changed": True},
        }[field]
        setattr(native.samples[0], field, value)
        return native

    with patch.object(execution, "read_eval_log", altered):
        result = execution.run_recoverable(**options(recovery_dir))
    assert result["recovery_status"] == "manual_recovery_required"
    assert all(item["observations"] == [] for item in result["sample_results"])
    assert all(
        item["reasons"] == ["native_sample_content_mismatch"] for item in result["sample_results"]
    )
