"""Declared primary selection, override validation, and scalar semantics."""

import pytest

from matric_eval.results.metric_catalog import benchmark_metric_declarations
from matric_eval.tasks import registry as registry_module
from matric_eval.tasks.registry import BenchmarkCategory, BenchmarkMetadata, TaskRegistry


@pytest.mark.parametrize(
    ("benchmark", "primary", "kind", "units"),
    [
        ("humaneval", "code_execution_scorer/mean", "binary", "all-tests-passed"),
        ("mbpp", "code_execution_scorer/mean", "binary", "all-tests-passed"),
        ("gsm8k", "gsm8k_scorer/mean", "binary", "numeric-answer-correct"),
        ("arc", "match/accuracy", "binary", "multiple-choice-answer-correct"),
        ("mmlu", "match/accuracy", "binary", "multiple-choice-answer-correct"),
        ("gpqa", "match/accuracy", "binary", "multiple-choice-answer-correct"),
        ("ifeval", "ifeval_scorer/mean", "continuous", "satisfied-constraint-fraction"),
        ("tool_calling", "tool_call_scorer/mean", "continuous", "function-call-rubric-credit"),
        ("mtbench", "llm_judge_scorer/mean", "continuous", "normalized-judge-rating"),
        ("livecodebench", "io_execution_scorer/mean", "continuous", "passed-test-fraction"),
        ("ds1000", "ds1000_scorer/mean", "binary", "all-tests-passed"),
        ("mmmu", "mmmu_scorer/accuracy", "binary", "multimodal-answer-correct"),
        ("realworldqa", "realworldqa_scorer/mean", "binary", "visual-answer-correct"),
        ("locomo", "match/accuracy", "binary", "memory-answer-match"),
        ("longmemeval", "match/accuracy", "binary", "memory-answer-match"),
        ("memoryagentbench", "match/accuracy", "binary", "memory-answer-match"),
        ("babilong", "babilong_scorer/accuracy", "binary", "reasoning-answer-correct"),
        ("swebench_pro", "swebench_pro_scorer/mean", "binary", "required-tests-resolved"),
        (
            "matric_cli",
            "matric_cli_scorer/accuracy",
            "continuous",
            "required-pattern-check-fraction",
        ),
        (
            "matric_memory",
            "title_quality_scorer/accuracy",
            "continuous",
            "title-similarity-rubric-credit",
        ),
        (
            "xstest_safe",
            "refusal_prefix_diagnostic_scorer/accuracy",
            "binary",
            "diagnostic-expected-behavior-match",
        ),
        (
            "xstest_unsafe",
            "refusal_prefix_diagnostic_scorer/accuracy",
            "binary",
            "diagnostic-expected-behavior-match",
        ),
        (
            "or_bench_hard",
            "refusal_prefix_diagnostic_scorer/accuracy",
            "binary",
            "diagnostic-expected-behavior-match",
        ),
        (
            "strongreject",
            "refusal_prefix_diagnostic_scorer/accuracy",
            "binary",
            "diagnostic-expected-behavior-match",
        ),
        ("nl2repo", "nl2repo_scorer/mean", "continuous", "canonical-test-pass-fraction"),
        ("terminalbench", "terminal_task_scorer/mean", "binary", "harbor-verifier-success"),
    ],
)
def test_reviewed_scalar_semantics(benchmark, primary, kind, units):
    selected, (descriptor,) = benchmark_metric_declarations(benchmark)
    assert selected == primary == descriptor.metric_id
    assert descriptor.value_kind == kind
    assert descriptor.units == units
    assert descriptor.version == f"matric/{benchmark}/1"
    assert descriptor.minimum == (None if benchmark == "matric_memory" else 0.0)
    assert descriptor.maximum == 1.0
    assert descriptor.missingness_policy == "require-complete/1"
    assert descriptor.aggregation_id == f"{primary.split('/')[-1]}/1"
    assert descriptor.timeout_value is None


@pytest.mark.parametrize(
    "name",
    [
        "custom",
        "mmlu_pro",
        "mmmu_pro",
        "humaneval_plus",
        "mbpp_plus",
        "injecagent",
        "videomme",
        "gaia",
        "swebench_lite",
        "swebench_verified",
        "qwenwebbench",
    ],
)
def test_unreviewed_or_structured_scorers_have_no_default(name):
    assert benchmark_metric_declarations(name) == (None, ())


def metadata(name="humaneval", **kwargs):
    return BenchmarkMetadata(
        name=name,
        description="Test benchmark",
        category=BenchmarkCategory.CODE,
        module_path="matric_eval.tasks.humaneval.humaneval",
        **kwargs,
    )


def test_registry_resolves_defaults_without_mutating_input():
    registry = TaskRegistry()
    original = metadata()
    registry.register(original)
    assert original.primary_metric_id is None
    assert registry.get_or_raise("humaneval").primary_metric_id == "code_execution_scorer/mean"


def test_explicit_descriptor_override_is_preserved_without_primary_fallback():
    registry = TaskRegistry()
    _, descriptors = benchmark_metric_declarations("ifeval")
    custom = metadata(metric_descriptors=descriptors)
    registry.register(custom)
    assert registry.get_or_raise("humaneval") is custom
    assert registry.get_or_raise("humaneval").primary_metric_id is None


def test_registry_rejects_duplicate_or_unknown_primary():
    _, (descriptor,) = benchmark_metric_declarations("humaneval")
    with pytest.raises(ValueError, match="duplicate metric IDs"):
        TaskRegistry().register(metadata(metric_descriptors=(descriptor, descriptor)))
    with pytest.raises(ValueError, match="primary metric is not declared"):
        TaskRegistry().register(metadata(primary_metric_id="absent/mean"))
    registry = TaskRegistry()
    explicit = metadata(primary_metric_id=descriptor.metric_id, metric_descriptors=(descriptor,))
    registry.register(explicit)
    assert registry.get_or_raise("humaneval") is explicit


def test_decorator_attaches_resolved_metadata_and_accepts_overrides(monkeypatch):
    registry = TaskRegistry()
    monkeypatch.setattr(registry_module, "_registry", registry)

    @registry_module.register_benchmark(name="humaneval", description="Test", category="code")
    def task():
        pass

    assert task._benchmark_metadata is registry.get_or_raise("humaneval")
    assert task._benchmark_metadata.primary_metric_id == "code_execution_scorer/mean"
    primary, descriptors = benchmark_metric_declarations("ifeval")

    @registry_module.register_benchmark(
        name="custom",
        description="Custom",
        category="instruction",
        primary_metric_id=primary,
        metric_descriptors=descriptors,
    )
    def custom():
        pass

    assert custom._benchmark_metadata.primary_metric_id == primary
    assert custom._benchmark_metadata.metric_descriptors == descriptors
