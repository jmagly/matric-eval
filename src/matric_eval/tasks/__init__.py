"""Benchmark task definitions."""

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
from matric_eval.tasks.mtbench import mtbench, load_mtbench
from matric_eval.tasks.mtbench import record_to_sample as mtbench_record_to_sample
from matric_eval.tasks.smoke import (
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

__all__ = [
    "arc",
    "check_constraint",
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
    "load_ds1000",
    "load_gsm8k",
    "load_humaneval",
    "load_ifeval",
    "load_livecodebench",
    "load_mbpp",
    "load_mtbench",
    "mbpp",
    "mbpp_record_to_sample",
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
]
