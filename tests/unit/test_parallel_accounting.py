"""Model caller parity preserves domain outcomes and opaque model identities."""

from copy import deepcopy
from typing import Any

import pytest

from matric_eval.parallel import ModelEvaluator, ParallelConfig, ParallelStrategy

MODELS = ["ollama/qwen:7b", "ollama/qwen:14b", "custom:backend/model:revision"]
OUTCOMES: dict[str, dict[str, Any]] = {
    "correct": {
        "status": "success",
        "execution": "completed",
        "score": 1.0,
        "samples": 2,
        "eligible": True,
        "eligibility_reasons": [],
    },
    "all-wrong": {
        "status": "success",
        "execution": "completed",
        "score": 0.0,
        "samples": 2,
        "eligible": True,
        "eligibility_reasons": [],
    },
    "judge:unscored": {
        "status": "success",
        "execution": "completed",
        "score": None,
        "samples": 2,
        "eligible": False,
        "eligibility_reasons": ["grader_failed"],
        "coverage": {"requested": 2, "completed": 2, "scored": 0},
    },
    "native-error": {
        "status": "error",
        "execution": "failed",
        "score": None,
        "samples": 1,
        "eligible": False,
        "eligibility_reasons": ["native_error"],
        "error": "provider unavailable",
    },
    "cancelled": {
        "status": "cancelled",
        "execution": "cancelled",
        "score": None,
        "samples": 1,
        "eligible": False,
        "eligibility_reasons": ["operator_cancelled"],
    },
}


def evaluate(model: str, benchmark: str) -> dict[str, Any]:
    if benchmark == "raises":
        raise RuntimeError(f"backend failed for {model}")
    return {"model": model, "benchmark": benchmark, **deepcopy(OUTCOMES[benchmark])}


@pytest.mark.parametrize(
    ("strategy", "parallel_models", "parallel_benchmarks"),
    [
        (ParallelStrategy.SEQUENTIAL, True, False),
        (ParallelStrategy.THREAD, True, False),
        (ParallelStrategy.THREAD, False, True),
        (ParallelStrategy.SEQUENTIAL, False, False),
    ],
)
def test_model_callers_preserve_complete_results_and_tagged_names(
    strategy: ParallelStrategy, parallel_models: bool, parallel_benchmarks: bool
) -> None:
    benchmarks = [*OUTCOMES, "raises"]
    expected = {
        model: {
            **{benchmark: evaluate(model, benchmark) for benchmark in OUTCOMES},
            "raises": {
                "status": "error",
                "execution": "failed",
                "score": None,
                "samples": 0,
                "error": f"backend failed for {model}",
                "eligible": False,
                "eligibility_reasons": ["execution_failed"],
            },
        }
        for model in MODELS
    }
    evaluator = ModelEvaluator(
        MODELS,
        benchmarks,
        ParallelConfig(strategy=strategy, max_workers=3, retry_on_failure=False),
    )
    result = evaluator.evaluate_all(
        evaluate, parallel_models=parallel_models, parallel_benchmarks=parallel_benchmarks
    )
    assert result == expected
    assert evaluator.get_results() == expected
    assert set(result) == set(MODELS)
    assert all(set(rows) == set(benchmarks) for rows in result.values())
