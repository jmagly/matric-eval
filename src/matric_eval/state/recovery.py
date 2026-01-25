"""
Recovery engine for error handling and gap detection.

Classifies errors, implements retry logic, and detects incomplete evaluations.
"""

from enum import Enum


class ErrorType(Enum):
    """Classification of errors for recovery strategy."""

    TRANSIENT = "transient"  # Retry: timeout, EPIPE, connection reset
    MODEL_ERROR = "model"  # Skip model: crash, OOM, invalid response
    FATAL = "fatal"  # Stop: disk full, config error


class RecoveryEngine:
    """
    Handles error recovery and gap detection.

    Provides error classification, retry logic, and incomplete evaluation detection.
    """

    def __init__(self, max_retries: int = 3):
        """
        Initialize recovery engine.

        Args:
            max_retries: Maximum retry attempts for transient errors
        """
        self.max_retries = max_retries

    def classify_error(self, error: Exception) -> ErrorType:
        """
        Classify error for recovery strategy.

        Args:
            error: Exception to classify

        Returns:
            ErrorType indicating recovery strategy
        """
        error_str = str(error).lower()

        # Transient errors (network, timeout)
        transient_patterns = [
            "timeout",
            "connection reset",
            "broken pipe",
            "epipe",
            "connection refused",
            "temporarily unavailable",
        ]

        if any(pattern in error_str for pattern in transient_patterns):
            return ErrorType.TRANSIENT

        # Model errors (model-specific issues)
        model_patterns = [
            "out of memory",
            "oom",
            "model not found",
            "invalid response",
            "model crash",
        ]

        if any(pattern in error_str for pattern in model_patterns):
            return ErrorType.MODEL_ERROR

        # Fatal errors (system issues)
        fatal_patterns = [
            "disk full",
            "no space left",
            "permission denied",
            "configuration error",
        ]

        if any(pattern in error_str for pattern in fatal_patterns):
            return ErrorType.FATAL

        # Default to model error (skip model, continue with others)
        return ErrorType.MODEL_ERROR

    def should_retry(self, error_type: ErrorType, attempt: int) -> bool:
        """
        Determine if operation should be retried.

        Args:
            error_type: Type of error encountered
            attempt: Current attempt number (0-indexed)

        Returns:
            True if should retry, False otherwise
        """
        if error_type != ErrorType.TRANSIENT:
            return False

        return attempt < self.max_retries
