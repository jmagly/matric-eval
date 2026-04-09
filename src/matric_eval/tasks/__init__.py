"""Benchmark task definitions."""

from matric_eval.tasks.registry import (  # noqa: F401 — registry must be importable
    BenchmarkCategory,
    BenchmarkMetadata,
    TaskRegistry,
    get_registry,
    register_benchmark,
)

from matric_eval.tasks.arc import arc, format_arc_prompt, load_arc
from matric_eval.tasks.custom import (
    CustomTestMetadata,
    CustomTestNotFoundError,
    InvalidCustomTestError,
    custom_task,
    discover_custom_tests,
    load_custom_tests,
)
from matric_eval.tasks.ds1000 import ds1000, load_ds1000
from matric_eval.tasks.ds1000 import record_to_sample as ds1000_record_to_sample
from matric_eval.tasks.gsm8k import (
    extract_answer,
    gsm8k,
    gsm8k_scorer,
    load_gsm8k,
)
from matric_eval.tasks.gsm8k import record_to_sample as gsm8k_record_to_sample
from matric_eval.tasks.humaneval import humaneval, load_humaneval
from matric_eval.tasks.humaneval import (
    record_to_sample as humaneval_record_to_sample,
)
from matric_eval.tasks.ifeval import (
    check_constraint,
    ifeval,
    ifeval_scorer,
    load_ifeval,
)
from matric_eval.tasks.ifeval import record_to_sample as ifeval_record_to_sample
from matric_eval.tasks.livecodebench import livecodebench, load_livecodebench
from matric_eval.tasks.livecodebench import (
    record_to_sample as livecodebench_record_to_sample,
)
from matric_eval.tasks.mbpp import (
    extract_function_name,
    extract_function_signature,
    load_mbpp,
    mbpp,
)
from matric_eval.tasks.mbpp import record_to_sample as mbpp_record_to_sample
from matric_eval.tasks.cyberseceval import (
    cyberseceval,
    cyberseceval_scorer,
    check_insecure_patterns,
    load_cyberseceval,
)
from matric_eval.tasks.cyberseceval import record_to_sample as cyberseceval_record_to_sample
from matric_eval.tasks.gaia import (
    gaia,
    gaia_scorer,
    load_gaia,
    normalize_answer,
)
from matric_eval.tasks.gaia import record_to_sample as gaia_record_to_sample
from matric_eval.tasks.gpqa import gpqa, load_gpqa, format_gpqa_prompt
from matric_eval.tasks.gpqa import record_to_sample as gpqa_record_to_sample
from matric_eval.tasks.mmlu import mmlu, load_mmlu, format_mmlu_prompt
from matric_eval.tasks.mmlu import record_to_sample as mmlu_record_to_sample
from matric_eval.tasks.mtbench import mtbench, load_mtbench
from matric_eval.tasks.mtbench import record_to_sample as mtbench_record_to_sample
from matric_eval.tasks.builtin import (
    smoke_gsm8k,
    smoke_humaneval,
    smoke_mbpp,
    smoke_suite,
)
from matric_eval.tasks.tool_calling import (
    SCENARIOS as TOOL_CALLING_SCENARIOS,
    ScenarioType,
    calculate_function_call_score,
    calculate_param_match,
    extract_function_call,
    load_tool_calling,
    tool_call_scorer,
    tool_calling,
)
from matric_eval.tasks.tool_calling import (
    record_to_sample as tool_calling_record_to_sample,
)
from matric_eval.tasks.matric_cli import (
    load_matric_cli,
    matric_cli,
    matric_cli_scorer,
)
from matric_eval.tasks.matric_memory import (
    load_matric_memory,
    matric_memory,
    title_quality_scorer,
)

# Benchmark expansion (issues #38-49)
from matric_eval.tasks.swebench.verified import swebench_verified
from matric_eval.tasks.swebench.pro import swebench_pro
from matric_eval.tasks.swebench.multilingual import swebench_multilingual
from matric_eval.tasks.swebench.factory import (
    create_swebench_task,
    swebench_record_to_sample,
)
from matric_eval.tasks.terminalbench import terminalbench, load_terminalbench
from matric_eval.tasks.nl2repo import nl2repo, load_nl2repo
from matric_eval.tasks.claweval import claweval, load_claweval
from matric_eval.tasks.qwenclawbench import qwenclawbench, load_qwenclawbench
from matric_eval.tasks.qwenwebbench import qwenwebbench, load_qwenwebbench
from matric_eval.tasks.mmmu import mmmu as mmmu_task
from matric_eval.tasks.mmmu import load_mmmu
from matric_eval.tasks.realworldqa import realworldqa, load_realworldqa
from matric_eval.tasks.omnidocbench import omnidocbench, load_omnidocbench
from matric_eval.tasks.videomme import videomme, load_videomme

__all__ = [
    # Registry
    "BenchmarkCategory",
    "BenchmarkMetadata",
    "TaskRegistry",
    "get_registry",
    "register_benchmark",
    # Benchmarks
    "arc",
    "check_constraint",
    "check_insecure_patterns",
    "cyberseceval",
    "cyberseceval_record_to_sample",
    "cyberseceval_scorer",
    "custom_task",
    "CustomTestMetadata",
    "CustomTestNotFoundError",
    "discover_custom_tests",
    "ds1000",
    "ds1000_record_to_sample",
    "extract_answer",
    "extract_function_name",
    "extract_function_signature",
    "format_arc_prompt",
    "format_gpqa_prompt",
    "gaia",
    "gaia_record_to_sample",
    "gaia_scorer",
    "gpqa",
    "gpqa_record_to_sample",
    "gsm8k",
    "gsm8k_record_to_sample",
    "gsm8k_scorer",
    "humaneval",
    "humaneval_record_to_sample",
    "ifeval",
    "ifeval_record_to_sample",
    "ifeval_scorer",
    "InvalidCustomTestError",
    "livecodebench",
    "livecodebench_record_to_sample",
    "load_arc",
    "load_custom_tests",
    "load_cyberseceval",
    "load_ds1000",
    "load_gaia",
    "load_gpqa",
    "load_gsm8k",
    "load_humaneval",
    "load_ifeval",
    "load_livecodebench",
    "load_mbpp",
    "load_mmlu",
    "load_mtbench",
    "mbpp",
    "normalize_answer",
    "mbpp_record_to_sample",
    "mmlu",
    "mmlu_record_to_sample",
    "format_mmlu_prompt",
    "mtbench",
    "mtbench_record_to_sample",
    "smoke_gsm8k",
    "smoke_humaneval",
    "smoke_mbpp",
    "smoke_suite",
    "calculate_function_call_score",
    "calculate_param_match",
    "extract_function_call",
    "load_tool_calling",
    "ScenarioType",
    "tool_call_scorer",
    "tool_calling",
    "tool_calling_record_to_sample",
    "TOOL_CALLING_SCENARIOS",
    # Application-specific tasks
    "load_matric_cli",
    "matric_cli",
    "matric_cli_scorer",
    "load_matric_memory",
    "matric_memory",
    "title_quality_scorer",
    # Benchmark expansion
    "swebench_verified",
    "swebench_pro",
    "swebench_multilingual",
    "create_swebench_task",
    "swebench_record_to_sample",
    "terminalbench",
    "load_terminalbench",
    "nl2repo",
    "load_nl2repo",
    "claweval",
    "load_claweval",
    "qwenclawbench",
    "load_qwenclawbench",
    "qwenwebbench",
    "load_qwenwebbench",
    "mmmu_task",
    "load_mmmu",
    "realworldqa",
    "load_realworldqa",
    "omnidocbench",
    "load_omnidocbench",
    "videomme",
    "load_videomme",
]
