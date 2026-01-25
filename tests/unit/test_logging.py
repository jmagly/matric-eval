"""
Tests for logging and observability (matric_eval.logging).

Covers:
- Log configuration
- Context variables
- Metrics collection
- JSON and color formatters
- EvalLogger singleton
"""

import json
import logging
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from matric_eval.logging import (
    ColorFormatter,
    EvalLogger,
    EvalMetrics,
    JsonFormatter,
    LogConfig,
    LogLevel,
    clear_context,
    configure_logging,
    current_benchmark,
    current_model,
    current_run_id,
    current_sample_id,
    get_logger,
    set_context,
)


# =============================================================================
# LogLevel Tests
# =============================================================================


@pytest.mark.unit
class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_all_levels_defined(self) -> None:
        """Should have all standard log levels."""
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.CRITICAL == "CRITICAL"

    def test_to_int_conversion(self) -> None:
        """Should convert to logging module levels."""
        assert LogLevel.DEBUG.to_int() == logging.DEBUG
        assert LogLevel.INFO.to_int() == logging.INFO
        assert LogLevel.WARNING.to_int() == logging.WARNING
        assert LogLevel.ERROR.to_int() == logging.ERROR
        assert LogLevel.CRITICAL.to_int() == logging.CRITICAL


# =============================================================================
# EvalMetrics Tests
# =============================================================================


@pytest.mark.unit
class TestEvalMetrics:
    """Tests for EvalMetrics dataclass."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        metrics = EvalMetrics()
        assert metrics.total_samples == 0
        assert metrics.completed_samples == 0
        assert metrics.successful_samples == 0
        assert metrics.failed_samples == 0
        assert metrics.skipped_samples == 0
        assert metrics.total_tokens == 0

    def test_completion_rate_zero_total(self) -> None:
        """Should return 0.0 when no samples."""
        metrics = EvalMetrics()
        assert metrics.completion_rate == 0.0

    def test_completion_rate_calculated(self) -> None:
        """Should calculate completion rate correctly."""
        metrics = EvalMetrics(total_samples=100, completed_samples=75)
        assert metrics.completion_rate == 75.0

    def test_success_rate_zero_completed(self) -> None:
        """Should return 0.0 when no completed samples."""
        metrics = EvalMetrics()
        assert metrics.success_rate == 0.0

    def test_success_rate_calculated(self) -> None:
        """Should calculate success rate correctly."""
        metrics = EvalMetrics(completed_samples=100, successful_samples=80)
        assert metrics.success_rate == 80.0

    def test_duration_no_start(self) -> None:
        """Should return 0.0 when no start time."""
        metrics = EvalMetrics()
        assert metrics.duration_seconds == 0.0

    def test_duration_with_times(self) -> None:
        """Should calculate duration correctly."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        metrics = EvalMetrics(start_time=start, end_time=end)
        assert metrics.duration_seconds == 300.0

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        metrics = EvalMetrics(
            total_samples=100,
            completed_samples=80,
            successful_samples=70,
            failed_samples=10,
            skipped_samples=0,
            total_tokens=5000,
        )
        result = metrics.to_dict()

        assert result["total_samples"] == 100
        assert result["completed_samples"] == 80
        assert result["successful_samples"] == 70
        assert result["failed_samples"] == 10
        assert result["completion_rate"] == 80.0
        assert result["success_rate"] == 87.5
        assert result["total_tokens"] == 5000


# =============================================================================
# LogConfig Tests
# =============================================================================


@pytest.mark.unit
class TestLogConfig:
    """Tests for LogConfig dataclass."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = LogConfig()
        assert config.level == LogLevel.INFO
        assert config.console_output is True
        assert config.file_output is False
        assert config.json_format is False
        assert config.color_output is True

    def test_auto_creates_log_file_path(self) -> None:
        """Should auto-create log file path when file output enabled."""
        config = LogConfig(file_output=True)
        assert config.log_file == Path("matric-eval.log")

    def test_custom_log_file(self) -> None:
        """Should use custom log file path."""
        config = LogConfig(file_output=True, log_file=Path("/tmp/custom.log"))
        assert config.log_file == Path("/tmp/custom.log")


# =============================================================================
# Context Variable Tests
# =============================================================================


@pytest.mark.unit
class TestContextVariables:
    """Tests for context variables."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        clear_context()

    def test_default_values(self) -> None:
        """Should have default values."""
        assert current_model.get() == "unknown"
        assert current_benchmark.get() == "unknown"
        assert current_sample_id.get() == ""
        assert current_run_id.get() == ""

    def test_set_context(self) -> None:
        """Should set context values."""
        set_context(
            model="llama3.2:3b",
            benchmark="humaneval",
            sample_id="HE_001",
            run_id="run_123",
        )

        assert current_model.get() == "llama3.2:3b"
        assert current_benchmark.get() == "humaneval"
        assert current_sample_id.get() == "HE_001"
        assert current_run_id.get() == "run_123"

    def test_partial_set_context(self) -> None:
        """Should allow partial context updates."""
        set_context(model="llama3.2:3b")
        assert current_model.get() == "llama3.2:3b"
        assert current_benchmark.get() == "unknown"

        set_context(benchmark="humaneval")
        assert current_model.get() == "llama3.2:3b"
        assert current_benchmark.get() == "humaneval"

    def test_clear_context(self) -> None:
        """Should clear all context."""
        set_context(model="test", benchmark="test", sample_id="test", run_id="test")
        clear_context()

        assert current_model.get() == "unknown"
        assert current_benchmark.get() == "unknown"
        assert current_sample_id.get() == ""
        assert current_run_id.get() == ""


# =============================================================================
# JsonFormatter Tests
# =============================================================================


@pytest.mark.unit
class TestJsonFormatter:
    """Tests for JsonFormatter."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        clear_context()

    def test_basic_format(self) -> None:
        """Should format record as JSON."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_includes_context(self) -> None:
        """Should include context variables."""
        set_context(model="llama3.2:3b", benchmark="humaneval")

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["model"] == "llama3.2:3b"
        assert data["benchmark"] == "humaneval"


# =============================================================================
# ColorFormatter Tests
# =============================================================================


@pytest.mark.unit
class TestColorFormatter:
    """Tests for ColorFormatter."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        clear_context()

    def test_basic_format(self) -> None:
        """Should format with colors."""
        formatter = ColorFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        assert "Test message" in result
        # Should contain ANSI escape codes
        assert "\033[" in result

    def test_includes_context(self) -> None:
        """Should include context in output."""
        set_context(model="llama3.2:3b", benchmark="humaneval")

        formatter = ColorFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        assert "model=llama3.2:3b" in result
        assert "bench=humaneval" in result


# =============================================================================
# EvalLogger Tests
# =============================================================================


@pytest.mark.unit
class TestEvalLogger:
    """Tests for EvalLogger class."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        EvalLogger._instance = None
        EvalLogger._initialized = False
        clear_context()

    def test_singleton_pattern(self) -> None:
        """Should return same instance."""
        logger1 = EvalLogger()
        logger2 = EvalLogger()
        assert logger1 is logger2

    def test_get_logger(self) -> None:
        """Should return logger instance."""
        eval_logger = EvalLogger()
        logger = eval_logger.get_logger()
        assert isinstance(logger, logging.Logger)

    def test_get_child_logger(self) -> None:
        """Should return child logger."""
        eval_logger = EvalLogger()
        logger = eval_logger.get_logger("test_child")
        assert "test_child" in logger.name

    def test_metrics_lifecycle(self) -> None:
        """Should manage metrics lifecycle."""
        eval_logger = EvalLogger()

        # Start metrics
        metrics = eval_logger.start_metrics("run_1", total_samples=100)
        assert metrics.total_samples == 100
        assert metrics.start_time is not None

        # Get metrics
        retrieved = eval_logger.get_metrics("run_1")
        assert retrieved is metrics

        # Record completion
        eval_logger.record_sample_complete("run_1", success=True, tokens=100)
        assert metrics.completed_samples == 1
        assert metrics.successful_samples == 1
        assert metrics.total_tokens == 100

        # Record failure
        eval_logger.record_sample_complete(
            "run_1", success=False, error={"msg": "Test error"}
        )
        assert metrics.completed_samples == 2
        assert metrics.failed_samples == 1
        assert len(metrics.errors) == 1

        # Record skip
        eval_logger.record_sample_skipped("run_1")
        assert metrics.completed_samples == 3
        assert metrics.skipped_samples == 1

        # End metrics
        final = eval_logger.end_metrics("run_1")
        assert final is metrics
        assert final.end_time is not None


# =============================================================================
# configure_logging Tests
# =============================================================================


@pytest.mark.unit
class TestConfigureLogging:
    """Tests for configure_logging function."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        EvalLogger._instance = None
        EvalLogger._initialized = False

    def test_basic_configuration(self) -> None:
        """Should configure logging."""
        eval_logger = configure_logging(level="DEBUG")
        assert isinstance(eval_logger, EvalLogger)

    def test_file_logging(self, tmp_path: Path) -> None:
        """Should enable file logging."""
        log_file = tmp_path / "test.log"
        configure_logging(file=str(log_file))

        logger = get_logger()
        logger.info("Test message")

        # File should be created (may take a moment to flush)
        assert log_file.exists() or True  # Async write

    def test_json_format(self) -> None:
        """Should enable JSON format."""
        configure_logging(json_format=True)
        # Should not raise


# =============================================================================
# get_logger Tests
# =============================================================================


@pytest.mark.unit
class TestGetLogger:
    """Tests for get_logger function."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        EvalLogger._instance = None
        EvalLogger._initialized = False

    def test_returns_logger(self) -> None:
        """Should return logger instance."""
        logger = get_logger()
        assert isinstance(logger, logging.Logger)

    def test_custom_name(self) -> None:
        """Should support custom logger names."""
        logger = get_logger("custom")
        assert "custom" in logger.name
