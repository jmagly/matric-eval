"""
Comprehensive logging and observability for matric-eval.

Provides:
- Structured logging with configurable levels
- File and console handlers
- Context-aware loggers for evaluations
- Progress tracking and metrics
- JSON formatting for log aggregation
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# Context variables for evaluation tracking
current_model: ContextVar[str] = ContextVar("current_model", default="unknown")
current_benchmark: ContextVar[str] = ContextVar("current_benchmark", default="unknown")
current_sample_id: ContextVar[str] = ContextVar("current_sample_id", default="")
current_run_id: ContextVar[str] = ContextVar("current_run_id", default="")


class LogLevel(str, Enum):
    """Log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def to_int(self) -> int:
        """Convert to logging module level."""
        return getattr(logging, self.value)


@dataclass
class EvalMetrics:
    """Metrics collected during evaluation."""

    total_samples: int = 0
    completed_samples: int = 0
    successful_samples: int = 0
    failed_samples: int = 0
    skipped_samples: int = 0
    total_tokens: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        """Return completion percentage."""
        if self.total_samples == 0:
            return 0.0
        return (self.completed_samples / self.total_samples) * 100

    @property
    def success_rate(self) -> float:
        """Return success percentage of completed samples."""
        if self.completed_samples == 0:
            return 0.0
        return (self.successful_samples / self.completed_samples) * 100

    @property
    def duration_seconds(self) -> float:
        """Return elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or datetime.now(timezone.utc)
        return (end - self.start_time).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_samples": self.total_samples,
            "completed_samples": self.completed_samples,
            "successful_samples": self.successful_samples,
            "failed_samples": self.failed_samples,
            "skipped_samples": self.skipped_samples,
            "completion_rate": round(self.completion_rate, 2),
            "success_rate": round(self.success_rate, 2),
            "total_tokens": self.total_tokens,
            "duration_seconds": round(self.duration_seconds, 2),
            "errors_count": len(self.errors),
        }


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context variables
        model = current_model.get()
        if model != "unknown":
            log_data["model"] = model

        benchmark = current_benchmark.get()
        if benchmark != "unknown":
            log_data["benchmark"] = benchmark

        sample_id = current_sample_id.get()
        if sample_id:
            log_data["sample_id"] = sample_id

        run_id = current_run_id.get()
        if run_id:
            log_data["run_id"] = run_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data

        return json.dumps(log_data)


class ColorFormatter(logging.Formatter):
    """Color formatter for console output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format with colors."""
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""

        # Build context prefix
        context_parts = []
        model = current_model.get()
        if model != "unknown":
            context_parts.append(f"model={model}")

        benchmark = current_benchmark.get()
        if benchmark != "unknown":
            context_parts.append(f"bench={benchmark}")

        context = f" [{', '.join(context_parts)}]" if context_parts else ""

        # Format timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Build message
        level = f"{color}{record.levelname:8}{reset}"
        return f"{timestamp} {level}{context} {record.getMessage()}"


@dataclass
class LogConfig:
    """Logging configuration."""

    level: LogLevel = LogLevel.INFO
    console_output: bool = True
    file_output: bool = False
    log_file: Optional[Path] = None
    json_format: bool = False
    color_output: bool = True

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.file_output and self.log_file is None:
            self.log_file = Path("matric-eval.log")


class EvalLogger:
    """
    Context-aware logger for evaluation tracking.

    Provides structured logging with automatic context injection
    and metrics collection.
    """

    _instance: Optional[EvalLogger] = None
    _initialized: bool = False

    def __new__(cls) -> EvalLogger:
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize logger."""
        if EvalLogger._initialized:
            return

        self._logger = logging.getLogger("matric_eval")
        self._metrics: dict[str, EvalMetrics] = {}
        self._config = LogConfig()
        EvalLogger._initialized = True

    def configure(self, config: LogConfig) -> None:
        """Configure logging."""
        self._config = config
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up log handlers."""
        self._logger.setLevel(self._config.level.to_int())
        self._logger.handlers.clear()

        if self._config.console_output:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(self._config.level.to_int())

            if self._config.json_format:
                console_handler.setFormatter(JsonFormatter())
            elif self._config.color_output:
                console_handler.setFormatter(ColorFormatter())
            else:
                console_handler.setFormatter(
                    logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
                )

            self._logger.addHandler(console_handler)

        if self._config.file_output and self._config.log_file:
            file_handler = logging.FileHandler(self._config.log_file)
            file_handler.setLevel(self._config.level.to_int())
            file_handler.setFormatter(JsonFormatter())
            self._logger.addHandler(file_handler)

    def get_logger(self, name: str = "matric_eval") -> logging.Logger:
        """Get a logger instance."""
        if name == "matric_eval":
            return self._logger
        return self._logger.getChild(name)

    def set_context(
        self,
        *,
        model: Optional[str] = None,
        benchmark: Optional[str] = None,
        sample_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        """Set evaluation context."""
        if model is not None:
            current_model.set(model)
        if benchmark is not None:
            current_benchmark.set(benchmark)
        if sample_id is not None:
            current_sample_id.set(sample_id)
        if run_id is not None:
            current_run_id.set(run_id)

    def clear_context(self) -> None:
        """Clear evaluation context."""
        current_model.set("unknown")
        current_benchmark.set("unknown")
        current_sample_id.set("")
        current_run_id.set("")

    def start_metrics(self, run_id: str, total_samples: int) -> EvalMetrics:
        """Start metrics collection for a run."""
        metrics = EvalMetrics(
            total_samples=total_samples,
            start_time=datetime.now(timezone.utc),
        )
        self._metrics[run_id] = metrics
        return metrics

    def get_metrics(self, run_id: str) -> Optional[EvalMetrics]:
        """Get metrics for a run."""
        return self._metrics.get(run_id)

    def record_sample_complete(
        self,
        run_id: str,
        *,
        success: bool = True,
        tokens: int = 0,
        error: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record completion of a sample."""
        metrics = self._metrics.get(run_id)
        if metrics is None:
            return

        metrics.completed_samples += 1
        metrics.total_tokens += tokens

        if success:
            metrics.successful_samples += 1
        else:
            metrics.failed_samples += 1
            if error:
                metrics.errors.append(error)

    def record_sample_skipped(self, run_id: str) -> None:
        """Record a skipped sample."""
        metrics = self._metrics.get(run_id)
        if metrics is None:
            return

        metrics.completed_samples += 1
        metrics.skipped_samples += 1

    def end_metrics(self, run_id: str) -> Optional[EvalMetrics]:
        """End metrics collection and return final metrics."""
        metrics = self._metrics.get(run_id)
        if metrics:
            metrics.end_time = datetime.now(timezone.utc)
        return metrics

    # Convenience logging methods
    def debug(self, msg: str, **extra: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, msg, extra)

    def info(self, msg: str, **extra: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, msg, extra)

    def warning(self, msg: str, **extra: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, msg, extra)

    def error(self, msg: str, **extra: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, msg, extra)

    def critical(self, msg: str, **extra: Any) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, msg, extra)

    def _log(self, level: int, msg: str, extra: dict[str, Any]) -> None:
        """Internal logging method."""
        record = self._logger.makeRecord(
            self._logger.name,
            level,
            "",
            0,
            msg,
            (),
            None,
        )
        if extra:
            record.extra_data = extra
        self._logger.handle(record)


# Singleton instance
_eval_logger: Optional[EvalLogger] = None


def get_logger(name: str = "matric_eval") -> logging.Logger:
    """Get a logger instance."""
    global _eval_logger
    if _eval_logger is None:
        _eval_logger = EvalLogger()
    return _eval_logger.get_logger(name)


def configure_logging(
    level: str = "INFO",
    console: bool = True,
    file: Optional[str] = None,
    json_format: bool = False,
    color: bool = True,
) -> EvalLogger:
    """
    Configure logging for matric-eval.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console: Enable console output
        file: Log file path (enables file logging)
        json_format: Use JSON format for logs
        color: Enable colored console output

    Returns:
        Configured EvalLogger instance
    """
    global _eval_logger
    if _eval_logger is None:
        _eval_logger = EvalLogger()

    config = LogConfig(
        level=LogLevel(level.upper()),
        console_output=console,
        file_output=file is not None,
        log_file=Path(file) if file else None,
        json_format=json_format,
        color_output=color,
    )
    _eval_logger.configure(config)
    return _eval_logger


def set_context(
    *,
    model: Optional[str] = None,
    benchmark: Optional[str] = None,
    sample_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> None:
    """Set evaluation context for logging."""
    global _eval_logger
    if _eval_logger is None:
        _eval_logger = EvalLogger()
    _eval_logger.set_context(
        model=model,
        benchmark=benchmark,
        sample_id=sample_id,
        run_id=run_id,
    )


def clear_context() -> None:
    """Clear evaluation context."""
    global _eval_logger
    if _eval_logger is not None:
        _eval_logger.clear_context()


__all__ = [
    "ColorFormatter",
    "EvalLogger",
    "EvalMetrics",
    "JsonFormatter",
    "LogConfig",
    "LogLevel",
    "clear_context",
    "configure_logging",
    "current_benchmark",
    "current_model",
    "current_run_id",
    "current_sample_id",
    "get_logger",
    "set_context",
]
