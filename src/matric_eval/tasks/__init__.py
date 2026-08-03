"""Benchmark task definitions."""

from matric_eval.tasks.arc import arc, format_arc_prompt, load_arc
from matric_eval.tasks.babilong import babilong, load_babilong
from matric_eval.tasks.builtin import (
    smoke_gsm8k,
    smoke_humaneval,
    smoke_mbpp,
    smoke_suite,
)
from matric_eval.tasks.claweval import (
    build_claweval_command,
    claweval,
    load_claweval,
    run_claweval,
)
from matric_eval.tasks.custom import (
    CustomTestMetadata,
    CustomTestNotFoundError,
    InvalidCustomTestError,
    custom_task,
    discover_custom_tests,
    load_custom_tests,
)
from matric_eval.tasks.cyberseceval import (
    check_insecure_patterns,
    cyberseceval,
    cyberseceval_scorer,
    load_cyberseceval,
)
from matric_eval.tasks.cyberseceval import record_to_sample as cyberseceval_record_to_sample
from matric_eval.tasks.ds1000 import ds1000, load_ds1000
from matric_eval.tasks.ds1000 import record_to_sample as ds1000_record_to_sample
from matric_eval.tasks.evalplus import humaneval_plus, load_evalplus, mbpp_plus
from matric_eval.tasks.gaia import (
    gaia,
    gaia_scorer,
    load_gaia,
    normalize_answer,
)
from matric_eval.tasks.gaia import record_to_sample as gaia_record_to_sample
from matric_eval.tasks.gaia2 import (
    build_gaia2_command,
    gaia2,
    load_gaia2,
    load_gaia2_results,
    run_gaia2,
)
from matric_eval.tasks.gpqa import format_gpqa_prompt, gpqa, load_gpqa
from matric_eval.tasks.gpqa import record_to_sample as gpqa_record_to_sample
from matric_eval.tasks.gsm8k import (
    extract_answer,
    gsm8k,
    gsm8k_scorer,
    load_gsm8k,
)
from matric_eval.tasks.gsm8k import record_to_sample as gsm8k_record_to_sample
from matric_eval.tasks.helmet import build_helmet_command, helmet
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
from matric_eval.tasks.infinite_bench import create_infinite_bench_task, infinite_bench
from matric_eval.tasks.injecagent import injecagent, load_injecagent
from matric_eval.tasks.livecodebench import livecodebench, load_livecodebench
from matric_eval.tasks.livecodebench import (
    record_to_sample as livecodebench_record_to_sample,
)
from matric_eval.tasks.locomo import load_locomo, locomo
from matric_eval.tasks.locomo import record_to_sample as locomo_record_to_sample
from matric_eval.tasks.longmemeval import load_longmemeval, longmemeval
from matric_eval.tasks.longmemeval import record_to_sample as longmemeval_record_to_sample
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
from matric_eval.tasks.mbpp import (
    extract_function_name,
    extract_function_signature,
    load_mbpp,
    mbpp,
)
from matric_eval.tasks.mbpp import record_to_sample as mbpp_record_to_sample
from matric_eval.tasks.memoryagentbench import load_memoryagentbench, memoryagentbench
from matric_eval.tasks.memoryagentbench import record_to_sample as memoryagentbench_record_to_sample
from matric_eval.tasks.memorybench import build_memorybench_command, memorybench
from matric_eval.tasks.mmlu import format_mmlu_prompt, load_mmlu, mmlu
from matric_eval.tasks.mmlu import record_to_sample as mmlu_record_to_sample
from matric_eval.tasks.mmlu_pro import load_mmlu_pro, mmlu_pro
from matric_eval.tasks.mmmu import load_mmmu
from matric_eval.tasks.mmmu import mmmu as mmmu_task
from matric_eval.tasks.mmmu_pro import load_mmmu_pro, mmmu_pro
from matric_eval.tasks.mtbench import load_mtbench, mtbench
from matric_eval.tasks.mtbench import record_to_sample as mtbench_record_to_sample
from matric_eval.tasks.nl2repo import load_nl2repo, nl2repo
from matric_eval.tasks.nolima import build_nolima_command, nolima
from matric_eval.tasks.omnidocbench import (
    build_omnidocbench_command,
    load_omnidocbench,
    omnidocbench,
    run_omnidocbench,
)
from matric_eval.tasks.qwenclawbench import (
    build_qwenclawbench_command,
    load_qwenclawbench,
    qwenclawbench,
    run_qwenclawbench,
)
from matric_eval.tasks.qwenwebbench import load_qwenwebbench, qwenwebbench
from matric_eval.tasks.realworldqa import load_realworldqa, realworldqa
from matric_eval.tasks.registry import (  # noqa: F401 — registry must be importable
    BenchmarkAccess,
    BenchmarkCategory,
    BenchmarkMetadata,
    BenchmarkReleasePolicy,
    BenchmarkSourceKind,
    BenchmarkStatus,
    BenchmarkUnavailableError,
    TaskRegistry,
    get_registry,
    register_benchmark,
)
from matric_eval.tasks.ruler import build_ruler_prepare_command, ruler
from matric_eval.tasks.swebench.factory import (
    create_swebench_task,
    swebench_record_to_sample,
)
from matric_eval.tasks.swebench.multilingual import swebench_multilingual
from matric_eval.tasks.swebench.pro import swebench_pro

# Benchmark expansion (issues #38-49)
from matric_eval.tasks.swebench.verified import swebench_verified
from matric_eval.tasks.terminalbench import build_harbor_command, load_terminalbench, terminalbench
from matric_eval.tasks.tool_calling import (
    SCENARIOS as TOOL_CALLING_SCENARIOS,
)
from matric_eval.tasks.tool_calling import (
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
from matric_eval.tasks.tulving import build_tulving_command, tulving
from matric_eval.tasks.videomme import load_videomme, videomme

__all__ = [
    # Registry
    "BenchmarkAccess",
    "BenchmarkCategory",
    "BenchmarkMetadata",
    "BenchmarkReleasePolicy",
    "BenchmarkSourceKind",
    "BenchmarkStatus",
    "BenchmarkUnavailableError",
    "TaskRegistry",
    "get_registry",
    "register_benchmark",
    # Benchmarks
    "arc",
    "babilong",
    "load_babilong",
    "build_helmet_command",
    "helmet",
    "create_infinite_bench_task",
    "infinite_bench",
    "build_memorybench_command",
    "memorybench",
    "build_nolima_command",
    "nolima",
    "build_ruler_prepare_command",
    "ruler",
    "build_tulving_command",
    "tulving",
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
    "gaia2",
    "gaia_record_to_sample",
    "gaia_scorer",
    "build_gaia2_command",
    "run_gaia2",
    "gpqa",
    "gpqa_record_to_sample",
    "gsm8k",
    "gsm8k_record_to_sample",
    "gsm8k_scorer",
    "humaneval",
    "humaneval_plus",
    "humaneval_record_to_sample",
    "ifeval",
    "ifeval_record_to_sample",
    "ifeval_scorer",
    "injecagent",
    "InvalidCustomTestError",
    "livecodebench",
    "livecodebench_record_to_sample",
    "load_locomo",
    "locomo",
    "locomo_record_to_sample",
    "load_arc",
    "load_custom_tests",
    "load_cyberseceval",
    "load_ds1000",
    "load_gaia",
    "load_gaia2",
    "load_gaia2_results",
    "load_gpqa",
    "load_gsm8k",
    "load_humaneval",
    "load_ifeval",
    "load_injecagent",
    "load_livecodebench",
    "load_longmemeval",
    "load_memoryagentbench",
    "longmemeval",
    "longmemeval_record_to_sample",
    "memoryagentbench",
    "memoryagentbench_record_to_sample",
    "load_mbpp",
    "load_evalplus",
    "load_mmlu",
    "load_mmlu_pro",
    "load_mtbench",
    "mbpp",
    "mbpp_plus",
    "normalize_answer",
    "mbpp_record_to_sample",
    "mmlu",
    "mmlu_pro",
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
    "build_harbor_command",
    "load_terminalbench",
    "nl2repo",
    "load_nl2repo",
    "claweval",
    "build_claweval_command",
    "run_claweval",
    "load_claweval",
    "qwenclawbench",
    "build_qwenclawbench_command",
    "run_qwenclawbench",
    "load_qwenclawbench",
    "qwenwebbench",
    "load_qwenwebbench",
    "mmmu_task",
    "load_mmmu",
    "mmmu_pro",
    "load_mmmu_pro",
    "realworldqa",
    "load_realworldqa",
    "omnidocbench",
    "build_omnidocbench_command",
    "run_omnidocbench",
    "load_omnidocbench",
    "videomme",
    "load_videomme",
]
