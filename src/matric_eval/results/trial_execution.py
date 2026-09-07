"""Freeze a task once and execute explicitly declared outer generation trials."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from typing import TYPE_CHECKING, Any

from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset

from matric_eval.config import get_seed
from matric_eval.results.contract import BenchmarkResult, MetricDescriptor, Selection
from matric_eval.results.inspect_adapter import sample_identity
from matric_eval.results.trials import (
    GenerationEvidence,
    PassPredicate,
    TrialProtocol,
    TrialRecord,
    evaluate_trials,
)
from matric_eval.scorers.pass_k import pass_at_k

if TYPE_CHECKING:
    from matric_eval.core.engine import EvaluationEngine


def generation_seed_schedule(root: int, n: int) -> list[int]:
    """Version 1 deterministic, collision-resolved 31-bit generation seeds."""
    if isinstance(root, bool) or not isinstance(root, int) or not 0 <= root <= 9007199254740991:
        raise ValueError("generation root seed must be a nonnegative safe integer")
    pass_at_k(n, 0, 1)
    if n > 2**31:
        raise ValueError("trial count exceeds distinct generation seed space")
    used: set[int] = set()
    result = []
    for index in range(n):
        nonce = 0
        while True:
            payload = f"generation-seed/1:{root}:{index}:{nonce}"
            seed = int.from_bytes(hashlib.sha256(payload.encode()).digest()[:4], "big") % 2**31
            if seed not in used:
                break
            nonce += 1
        used.add(seed)
        result.append(seed)
    return result


def run_trials(
    engine: EvaluationEngine,
    benchmark: str,
    *,
    n: int,
    k: int,
    predicate: PassPredicate,
    task: Task | None = None,
    metric_id: str | None = None,
    metric_descriptors: dict[str, MetricDescriptor] | None = None,
    root_generation_seed: int = 42,
    selection_seed: int | None = None,
    **eval_kwargs: Any,
) -> dict[str, Any]:
    """Retain missing trials and seed limitations without inferring independence."""
    pass_at_k(n, 0, k)  # Validate before loading data or invoking any model.
    predicate = PassPredicate.model_validate(predicate.model_dump())
    forbidden = {
        "seed",
        "epochs",
        "sample_shuffle",
        "sample_id",
        "limit",
        "result_format",
        "primary_metric_id",
        "checkpoint",
    } & eval_kwargs.keys()
    if forbidden:
        raise ValueError(f"trial protocol owns these execution options: {sorted(forbidden)}")
    from matric_eval.tasks.registry import get_registry

    metadata = get_registry().get(benchmark)
    if metric_id is None and metric_descriptors is None and metadata is not None:
        metric_id = metadata.primary_metric_id
        metric_descriptors = {item.metric_id: item for item in metadata.metric_descriptors}
    descriptor = (metric_descriptors or {}).get(metric_id or "")
    if descriptor is None or descriptor.units != predicate.units:
        raise ValueError("trial metric and predicate require matching declared units")
    if selection_seed is None:
        selection_seed = get_seed()
    if (
        isinstance(selection_seed, bool)
        or not isinstance(selection_seed, int)
        or not 0 <= selection_seed <= 9007199254740991
    ):
        raise ValueError("selection seed must be a nonnegative safe integer")
    if task is None:
        if selection_seed != get_seed():
            raise ValueError(
                "builtin task selection uses configured seed; supply a preselected Task for another seed"
            )
        task = engine._load_task(benchmark)
    if task.sample_source is not None:
        raise ValueError("dynamic sample sources cannot establish a frozen trial manifest")
    frozen = copy.deepcopy(task)
    samples = copy.deepcopy(list(frozen.dataset))
    if not samples or any(
        isinstance(item.id, bool) or not isinstance(item.id, (str, int)) for item in samples
    ):
        raise ValueError("trials require nonempty samples with explicit integer or string IDs")
    identities = []
    for item in samples:
        assert isinstance(item.id, (str, int))
        identities.append(sample_identity(item.id))
    if len(set(identities)) != len(identities):
        raise ValueError("trial sample identities must be unique")
    content = json.dumps(
        [item.model_dump(mode="json") for item in samples],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    seeds = generation_seed_schedule(root_generation_seed, n)
    protocol = TrialProtocol(
        version="1",
        n=n,
        k=k,
        metric_id=descriptor.metric_id,
        metric_version=descriptor.version,
        predicate=predicate,
        generation_seeds=seeds,
        root_generation_seed=root_generation_seed,
        selection_seed=selection_seed,
        independence="unverified",
        task_content_sha256=hashlib.sha256(content.encode()).hexdigest(),
    )
    manifest = [
        Selection.model_validate(
            {
                "allocation_id": benchmark,
                "sample_id": sid,
                "trial_id": "selected",
                "data": {
                    "partition_schema_version": "1",
                    "role": "unknown",
                    "row_id": sid,
                    "source_id": frozen.dataset.name or benchmark,
                    "independent_unit_id": sid,
                },
            }
        )
        for sid in identities
    ]
    # Each invocation is a fresh evaluation, even when the engine is reused.
    run_id = str(uuid.uuid4())
    records = []
    for index, seed in enumerate(seeds):
        trial_id = f"trial-{index}"
        instance = copy.deepcopy(frozen)
        instance.dataset = MemoryDataset(
            copy.deepcopy(samples),
            name=frozen.dataset.name or benchmark,
            location=frozen.dataset.location,
        )
        instance.epochs = 1
        instance.epochs_reducer = None
        instance.config = instance.config.model_copy(update={"seed": seed})
        result = engine.run_benchmark(
            benchmark,
            task=instance,
            primary_metric_id=descriptor.metric_id,
            metric_descriptors=metric_descriptors,
            seed=seed,
            epochs=1,
            sample_shuffle=False,
            **eval_kwargs,
        )
        measured = None
        reason = None
        if "observation_result" not in result:
            reason = "trial_projection_unavailable"
        else:
            measured = BenchmarkResult.model_validate(result["observation_result"])
            actual = [(row.allocation_id, row.sample_id) for row in measured.selection]
            expected = [(row.allocation_id, row.sample_id) for row in manifest]
            if actual != expected or any(row.trial_id != "epoch-1" for row in measured.selection):
                raise ValueError("native trial manifest differs from frozen selected task order")
            for selected in measured.selection:
                selected.trial_id = trial_id
            for row in measured.observations:
                row.identity.run_id = run_id
                row.identity.trial_id = trial_id
                row.observation_id = row.identity.logical_id()
            measured = BenchmarkResult.model_validate(measured.model_dump())
        recorded = result.get("generation_config", {})
        recorded_seed = recorded.get("seed")
        temperature = recorded.get("temperature")
        limitations = ["provider_seed_honoring_unverified", "trial_independence_unverified"]
        if temperature == 0:
            limitations.append("deterministic_generation_may_repeat_outputs")
        elif temperature is None:
            limitations.append("effective_temperature_unverified")
        records.append(
            TrialRecord(
                trial_id=trial_id,
                generation_seed=seed,
                benchmark=measured,
                unavailable_reason=reason,
                native_trial_id="epoch-1",
                artifacts=result.get("native_logs", measured.artifacts if measured else []),
                failure_code=result.get("error_type")
                or (
                    f"inspect_{measured.execution}"
                    if measured is not None and measured.execution != "completed"
                    else "trial_projection_unavailable"
                    if measured is None
                    else None
                ),
                generation_evidence=GenerationEvidence(
                    requested_seed=seed,
                    recorded_seed=recorded_seed,
                    temperature=temperature,
                    provider_id=engine._get_provider_name(),
                    forwarding="recorded" if recorded_seed == seed else "unverified",
                    honored="unverified",
                    limitations=limitations,
                ),
            )
        )
    return evaluate_trials(
        records,
        manifest,
        run_id=run_id,
        model_id=engine.model,
        benchmark_id=benchmark,
        protocol=protocol,
    ).model_dump()
