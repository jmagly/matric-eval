"""matric-eval: Consolidated model evaluation framework for the matric ecosystem."""

__version__ = "0.1.0"

from .config import Settings, TierConfig, get_settings

# Legacy exports for backwards compatibility
from .config.settings import TIERS

# Logging and observability
from .logging import (
    EvalLogger,
    EvalMetrics,
    LogConfig,
    LogLevel,
    configure_logging,
    get_logger,
    set_context,
)

# Parallel execution
from .parallel import (
    ModelEvaluator,
    ParallelConfig,
    ParallelExecutor,
    ParallelResult,
    ParallelStrategy,
    TaskResult,
    run_parallel_eval,
)

# Recommendation engine
from .recommendation import (
    Capability,
    ModelScore,
    Recommendation,
    RecommendationEngine,
    RecommendationReport,
    generate_recommendations,
)

__all__ = [
    # Config
    "Settings",
    "TierConfig",
    "get_settings",
    "TIERS",
    # Logging
    "EvalLogger",
    "EvalMetrics",
    "LogConfig",
    "LogLevel",
    "configure_logging",
    "get_logger",
    "set_context",
    # Parallel
    "ModelEvaluator",
    "ParallelConfig",
    "ParallelExecutor",
    "ParallelResult",
    "ParallelStrategy",
    "TaskResult",
    "run_parallel_eval",
    # Recommendation
    "Capability",
    "ModelScore",
    "Recommendation",
    "RecommendationEngine",
    "RecommendationReport",
    "generate_recommendations",
    # Version
    "__version__",
]
