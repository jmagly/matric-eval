"""Qualify pinned Inspect hook behavior with real evaluations and no providers.

These tests establish callback ordering and identity, not disk/power-loss durability.
Private instrumentation observes log_sample completion; hook registration is public.
"""

import copy
import importlib
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import uuid4

import anyio
import pytest
from inspect_ai import Task, eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.hooks import Hooks, SampleAttemptEnd, SampleAttemptStart, SampleEnd, hooks
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import exact
from inspect_ai.solver import generate

pytestmark = pytest.mark.integration


@pytest.fixture
def observer(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    assert version("inspect_ai") == "0.3.263", (
        "Requalify hook ordering for a changed Inspect version"
    )
    hook_module = importlib.import_module("inspect_ai.hooks._hooks")
    registry = importlib.import_module("inspect_ai._util.registry")
    run_module = importlib.import_module("inspect_ai._eval.task.run")
    instances: list[Any] = []

    @hooks(name=f"recovery-qualification-{uuid4().hex}", description="Controlled recovery fixture")
    class Observer(Hooks):
        def __init__(self) -> None:
            self.ends: list[SampleEnd] = []
            self.starts: list[SampleAttemptStart] = []
            self.attempt_ends: list[SampleAttemptEnd] = []
            self.order: list[tuple[str, str | None]] = []
            self.original_samples: list[Any] = []
            self.fail_writes = False
            self.failed_evaluations: set[tuple[str, str]] = set()
            instances.append(self)

        async def on_sample_attempt_start(self, data: SampleAttemptStart) -> None:
            self.starts.append(copy.deepcopy(data))
            self.order.append(("attempt_start", data.sample_id))

        async def on_sample_attempt_end(self, data: SampleAttemptEnd) -> None:
            self.attempt_ends.append(copy.deepcopy(data))
            self.order.append(("attempt_end", data.sample_id))

        async def on_sample_end(self, data: SampleEnd) -> None:
            self.original_samples.append(data.sample)
            self.ends.append(copy.deepcopy(data))
            self.order.append(("sample_end", data.sample_id))
            if self.fail_writes:
                self.failed_evaluations.add((data.run_id, data.eval_id))
                raise OSError("controlled journal write failure")

    instance = instances[0]
    original_log_sample = run_module.log_sample

    async def logged_sample(*args: Any, **kwargs: Any) -> Any:
        sample = await original_log_sample(*args, **kwargs)
        instance.order.append(("log_sample_returned", sample.uuid))
        return sample

    monkeypatch.setattr(run_module, "log_sample", logged_sample)
    try:
        yield instance
    finally:
        # Remove only this public registration; preserve lazy registrations from
        # real evaluations. Invalidate cached singletons so no fixture survives.
        for key, value in list(registry._registry.items()):
            if value is instance:
                del registry._registry[key]
        hook_module._hooks_cache = []
        hook_module._hooks_cache_state = (-1, -1)


def task(name: str = "recovery-hook-task") -> Task:
    return Task(
        name=name,
        dataset=MemoryDataset([Sample(id="shared-id", input="Reply OK", target="OK")]),
        solver=generate(),
        scorer=exact(),
    )


def model() -> Any:
    return get_model(
        "mockllm/model",
        custom_outputs=lambda *args: ModelOutput.from_content("mockllm/model", "OK"),
    )


def test_full_sample_once_per_epoch_after_native_sample_logging(
    observer: Any, tmp_path: Path
) -> None:
    logs = eval(task(), model=model(), epochs=2, log_dir=str(tmp_path), display="none")
    assert len(logs) == 1 and logs[0].status == "success"
    assert len(observer.ends) == 2
    assert {event.sample.epoch for event in observer.ends} == {1, 2}
    assert len({event.sample_id for event in observer.ends}) == 2
    assert len(observer.starts) == len(observer.attempt_ends) == 2
    assert [event.attempt for event in observer.starts] == [1, 1]
    for event, original in zip(observer.ends, observer.original_samples, strict=True):
        assert event.sample is not original
        assert event.sample.scores is not original.scores
        assert event.sample.model_dump() == original.model_dump()
        assert event.sample.id == "shared-id"
        assert event.sample.output.completion == "OK"
        assert event.sample.scores and event.sample.scores["exact"].value == "C"
        assert event.run_id == logs[0].eval.run_id
        assert event.eval_id == logs[0].eval.eval_id
        assert event.sample_id == event.sample.uuid
        order = [kind for kind, sample_id in observer.order if sample_id == event.sample_id]
        assert order == ["attempt_start", "log_sample_returned", "attempt_end", "sample_end"]
    assert logs[0].samples is not None
    assert {sample.uuid for sample in logs[0].samples} == {
        event.sample_id for event in observer.ends
    }
    # No assertion equates log_sample returning with a stable final archive hash.


def test_sample_retry_lineage_has_two_attempts_and_one_terminal_sample(
    observer: Any, tmp_path: Path
) -> None:
    calls = 0

    def fail_once(*args: Any) -> ModelOutput:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("controlled first-attempt provider failure")
        return ModelOutput.from_content("mockllm/model", "OK")

    logs = eval(
        task(),
        model=get_model("mockllm/model", custom_outputs=fail_once),
        retry_on_error=1,
        fail_on_error=False,
        log_dir=str(tmp_path),
        display="none",
    )
    assert calls == 2
    assert logs[0].status == "success"
    assert [event.attempt for event in observer.starts] == [1, 2]
    assert [event.attempt for event in observer.attempt_ends] == [1, 2]
    assert [event.will_retry for event in observer.attempt_ends] == [True, False]
    assert observer.attempt_ends[0].error is not None
    assert observer.attempt_ends[1].error is None
    assert len(observer.ends) == 1
    terminal = observer.ends[0]
    assert terminal.sample.error is None
    assert terminal.sample.error_retries and len(terminal.sample.error_retries) == 1
    assert {event.sample_id for event in observer.starts} == {terminal.sample_id}
    assert {event.eval_id for event in observer.starts} == {terminal.eval_id}


def test_swallowed_hook_failure_requires_independent_failure_latch(
    observer: Any, tmp_path: Path
) -> None:
    observer.fail_writes = True
    logs = eval(task(), model=model(), log_dir=str(tmp_path), display="none")
    assert logs[0].status == "success"
    assert len(observer.ends) == 1
    assert observer.failed_evaluations == {(logs[0].eval.run_id, logs[0].eval.eval_id)}
    assert logs[0].samples and logs[0].samples[0].scores
    # Native success remains true despite the raised persistence error; an engine
    # must consult its own receipt/failure state before claiming recovery coverage.


def test_concurrent_tasks_route_same_native_sample_id_by_evaluation(
    observer: Any, tmp_path: Path
) -> None:
    active = 0
    peak = 0

    async def overlap(*args: Any) -> ModelOutput:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await anyio.sleep(0.1)
            return ModelOutput.from_content("mockllm/model", "OK")
        finally:
            active -= 1

    logs = eval(
        [task("left"), task("right")],
        model=get_model("mockllm/model", custom_outputs=overlap),
        max_tasks=2,
        max_samples=2,
        log_dir=str(tmp_path),
        display="none",
    )
    assert peak == 2, "Fixture must exercise overlapping executions"
    assert len(logs) == len(observer.ends) == 2
    expected = {(log.eval.run_id, log.eval.eval_id): log for log in logs}
    assert len(expected) == 2
    assert {(event.run_id, event.eval_id) for event in observer.ends} == set(expected)
    assert len({event.sample_id for event in observer.ends}) == 2
    for event in observer.ends:
        log = expected[(event.run_id, event.eval_id)]
        assert log.status == "success" and log.samples
        assert event.sample.id == log.samples[0].id == "shared-id"
        assert event.sample_id == log.samples[0].uuid
