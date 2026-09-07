"""Reviewed declarations for scalar metrics emitted by repository task scorers.

Keys refer to native Inspect scorer/metric names, never position or a generic
``score`` alias. Bounds describe each sample value; a binary input can produce a
fractional aggregate. These declarations do not establish comparability between
benchmarks, judge qualification, or permission to average suite scores.

Grouped, dictionary-valued, external, and unreviewed scorers remain undeclared.
Their native measurements can still be retained by the result adapter. In
particular, EvalPlus and InjecAgent produce dictionary grades; MMLU-Pro and
MMMU-Pro use grouped reducers; VideoMME's official headline is grouped nonlinear
rating alongside raw accuracy. No scalar default substitutes for those protocols.
GAIA, SWE-bench Lite/Verified, and delegated upstream tasks need a separate review
of their pinned external evaluators. Placeholder tasks have no scorer declaration.

MatricMemory's mixed title/similarity rubric has no finite lower bound: its
current dissimilar-pair formula accepts unrestricted numeric response ratings.
Refusal-prefix metrics are explicitly diagnostic and do not qualify a publication
judge. Declaring a metric does not change a benchmark's access or lifecycle gate.
"""

from typing import Literal

from matric_eval.results.contract import MetricDescriptor

# (scorer, native metric, input kind, semantic unit). Source of each declaration
# is the correspondingly named task module and its configured scorer.
_DECLARATIONS: dict[str, tuple[str, str, Literal["binary", "continuous"], str]] = {
    "humaneval": ("code_execution_scorer", "mean", "binary", "all-tests-passed"),
    "mbpp": ("code_execution_scorer", "mean", "binary", "all-tests-passed"),
    "gsm8k": ("gsm8k_scorer", "mean", "binary", "numeric-answer-correct"),
    "arc": ("match", "accuracy", "binary", "multiple-choice-answer-correct"),
    "mmlu": ("match", "accuracy", "binary", "multiple-choice-answer-correct"),
    "gpqa": ("match", "accuracy", "binary", "multiple-choice-answer-correct"),
    "ifeval": ("ifeval_scorer", "mean", "continuous", "satisfied-constraint-fraction"),
    "tool_calling": ("tool_call_scorer", "mean", "continuous", "function-call-rubric-credit"),
    "mtbench": ("llm_judge_scorer", "mean", "continuous", "normalized-judge-rating"),
    "livecodebench": ("io_execution_scorer", "mean", "continuous", "passed-test-fraction"),
    "ds1000": ("ds1000_scorer", "mean", "binary", "all-tests-passed"),
    "mmmu": ("mmmu_scorer", "accuracy", "binary", "multimodal-answer-correct"),
    "realworldqa": ("realworldqa_scorer", "mean", "binary", "visual-answer-correct"),
    "locomo": ("match", "accuracy", "binary", "memory-answer-match"),
    "longmemeval": ("match", "accuracy", "binary", "memory-answer-match"),
    "memoryagentbench": ("match", "accuracy", "binary", "memory-answer-match"),
    "babilong": ("babilong_scorer", "accuracy", "binary", "reasoning-answer-correct"),
    "swebench_pro": ("swebench_pro_scorer", "mean", "binary", "required-tests-resolved"),
    "matric_cli": (
        "matric_cli_scorer",
        "accuracy",
        "continuous",
        "required-pattern-check-fraction",
    ),
    "matric_memory": (
        "title_quality_scorer",
        "accuracy",
        "continuous",
        "title-similarity-rubric-credit",
    ),
    "xstest_safe": (
        "refusal_prefix_diagnostic_scorer",
        "accuracy",
        "binary",
        "diagnostic-expected-behavior-match",
    ),
    "xstest_unsafe": (
        "refusal_prefix_diagnostic_scorer",
        "accuracy",
        "binary",
        "diagnostic-expected-behavior-match",
    ),
    "or_bench_hard": (
        "refusal_prefix_diagnostic_scorer",
        "accuracy",
        "binary",
        "diagnostic-expected-behavior-match",
    ),
    "strongreject": (
        "refusal_prefix_diagnostic_scorer",
        "accuracy",
        "binary",
        "diagnostic-expected-behavior-match",
    ),
    "nl2repo": ("nl2repo_scorer", "mean", "continuous", "canonical-test-pass-fraction"),
    "terminalbench": ("terminal_task_scorer", "mean", "binary", "harbor-verifier-success"),
}


def benchmark_metric_declarations(
    name: str,
) -> tuple[str | None, tuple[MetricDescriptor, ...]]:
    """Return explicit defaults; unknown benchmarks have no primary metric.

    Return fresh descriptors so a caller cannot mutate shared catalog state.
    Missingness requires every selected sample to have an accepted observation.
    Timeout values are intentionally undeclared: execution timeout classification
    is separate from any scorer's ordinary observed incorrect response.
    """
    declaration = _DECLARATIONS.get(name)
    if declaration is None:
        return None, ()
    scorer, reducer, value_kind, units = declaration
    metric_id = f"{scorer}/{reducer}"
    descriptor = MetricDescriptor(
        metric_id=metric_id,
        version=f"matric/{name}/1",
        scorer_id=scorer,
        value_kind=value_kind,
        units=units,
        direction="higher",
        minimum=None if name == "matric_memory" else 0.0,
        maximum=1.0,
        independent_unit="task",
        missingness_policy="require-complete/1",
        aggregation_id=f"{reducer}/1",
        timeout_value=None,
    )
    return metric_id, (descriptor,)
