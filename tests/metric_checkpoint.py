"""Real native-log checkpoint fixtures with registry-declared metric evidence."""

from typing import Any

from inspect_ai.log import EvalLog

from matric_eval.results.inspect_adapter import adapt_log
from matric_eval.tasks.registry import get_registry


def completed_metric_checkpoint(
    native: EvalLog,
    *,
    benchmark: str,
    run_id: str,
    model: str,
    correct: int = 4,
) -> dict[str, Any]:
    """Adapt five controlled binary outcomes using the active metric declaration."""
    metadata = get_registry().get_or_raise(benchmark)
    primary = metadata.primary_metric_id
    assert primary is not None
    descriptors = {item.metric_id: item for item in metadata.metric_descriptors}
    descriptor = descriptors[primary]
    scorer_id = descriptor.scorer_id
    metric_name = primary.removeprefix(f"{scorer_id}/")
    payload = native.model_dump()
    payload["eval"]["model"] = model
    payload["eval"]["task"] = benchmark
    for index, sample in enumerate(payload["samples"]):
        sample["scores"] = {scorer_id: {"value": 1.0 if index < correct else 0.0}}
    score = correct / len(payload["samples"])
    payload["results"]["scores"] = [
        {
            "name": scorer_id,
            "scorer": scorer_id,
            "metrics": {metric_name: {"name": metric_name, "value": score}},
        }
    ]
    measured = adapt_log(
        EvalLog.model_validate(payload),
        run_id=run_id,
        model_id=model,
        benchmark_id=benchmark,
        primary_metric_id=primary,
        descriptors=descriptors,
    )
    return {
        "benchmark": benchmark,
        "model": model,
        "status": "success",
        "execution": measured.execution,
        "score": measured.primary_estimate.value,
        "samples": measured.coverage.attempted,
        "eligible": measured.eligibility.eligible,
        "counts": measured.coverage.model_dump(),
        "observation_result": measured.model_dump(),
        "metric_policy": {
            "version": "native-declarations/1",
            "primary_metric_id": primary,
            "descriptors": {mid: item.model_dump() for mid, item in sorted(descriptors.items())},
        },
    }
