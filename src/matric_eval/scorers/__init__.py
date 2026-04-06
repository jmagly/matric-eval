"""Custom scorers for evaluation tasks."""

from matric_eval.scorers.code_execution import code_execution_scorer, extract_code, safe_execute
from matric_eval.scorers.ds1000_scorer import ds1000_scorer, execute_ds1000_test
from matric_eval.scorers.elo import EloAggregator, MatchResult
from matric_eval.scorers.io_execution import (
    compare_outputs,
    io_execute,
    io_execution_scorer,
    normalize_output,
)
from matric_eval.scorers.llm_judge import (
    JUDGE_PROMPTS,
    JudgePrompt,
    JudgeResult,
    JudgeType,
    ScoringConfig,
    agentic_judge_scorer,
    build_judge_prompt,
    get_judge_template,
    list_judge_templates,
    llm_judge_scorer,
    normalize_score,
    pairwise_judge_scorer,
    parse_judge_score,
    parse_pairwise_winner,
    reference_judge_scorer,
    register_judge_template,
)
from matric_eval.scorers.multidimensional import (
    ALL_DIMENSIONS,
    DimensionName,
    DimensionScore,
    MultidimensionalScore,
    correctness_scorer,
    extract_number,
    multidimensional_scorer,
    quality_scorer,
)
from matric_eval.scorers.pass_k import (
    aggregate_pass_k_results,
    pass_at_k,
    pass_power_k,
)
from matric_eval.scorers.patch_apply import (
    VALID_PATH_RE,
    patch_apply_scorer,
    validate_test_path,
)
from matric_eval.scorers.project import BUILD_WEIGHT, TEST_WEIGHT, project_scorer

__all__ = [
    "agentic_judge_scorer",
    "aggregate_pass_k_results",
    "ALL_DIMENSIONS",
    "build_judge_prompt",
    "BUILD_WEIGHT",
    "code_execution_scorer",
    "compare_outputs",
    "correctness_scorer",
    "DimensionName",
    "DimensionScore",
    "ds1000_scorer",
    "EloAggregator",
    "execute_ds1000_test",
    "extract_code",
    "extract_number",
    "get_judge_template",
    "io_execute",
    "io_execution_scorer",
    "JUDGE_PROMPTS",
    "JudgePrompt",
    "JudgeResult",
    "JudgeType",
    "list_judge_templates",
    "llm_judge_scorer",
    "MatchResult",
    "multidimensional_scorer",
    "MultidimensionalScore",
    "normalize_output",
    "normalize_score",
    "pairwise_judge_scorer",
    "parse_judge_score",
    "parse_pairwise_winner",
    "pass_at_k",
    "pass_power_k",
    "patch_apply_scorer",
    "project_scorer",
    "quality_scorer",
    "reference_judge_scorer",
    "register_judge_template",
    "safe_execute",
    "ScoringConfig",
    "TEST_WEIGHT",
    "VALID_PATH_RE",
    "validate_test_path",
]
