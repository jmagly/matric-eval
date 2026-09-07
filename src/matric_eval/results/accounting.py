"""Shared execution summary for fresh, threaded and checkpointed benchmark results."""

from typing import Any


def summarize_benchmarks(
    results: dict[str, dict[str, Any]], requested: list[str]
) -> dict[str, Any]:
    completed = sum(results.get(name, {}).get("execution") == "completed" for name in requested)
    scored = sum(results.get(name, {}).get("score") is not None for name in requested)
    eligible = bool(requested) and all(
        results.get(name, {}).get("eligible") is True for name in requested
    )
    full = bool(requested) and completed == len(requested)
    return {
        "status": "success" if full else "partial" if completed else "error",
        "execution": "completed" if full else "partial" if completed else "failed",
        "overall_score": None,
        "aggregation_reason": "aggregation_undeclared",
        "eligible": eligible,
        "eligibility_reasons": [] if eligible else ["benchmark_scope_ineligible"],
        "suite_scope": {"requested": len(requested), "completed": completed, "scored": scored},
    }
