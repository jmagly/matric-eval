"""
Tests for recovery engine functionality.

Verifies error classification and retry logic.
"""

import pytest

from matric_eval.state import RecoveryEngine
from matric_eval.state.recovery import ErrorType


class TestRecoveryEngine:
    """Test RecoveryEngine for error handling."""

    @pytest.fixture
    def recovery_engine(self) -> RecoveryEngine:
        """Create RecoveryEngine instance."""
        return RecoveryEngine(max_retries=3)

    def test_classify_timeout_error(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of timeout errors as transient."""
        error = TimeoutError("Connection timeout after 60 seconds")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.TRANSIENT

    def test_classify_connection_reset(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of connection reset errors as transient."""
        error = ConnectionResetError("Connection reset by peer")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.TRANSIENT

    def test_classify_broken_pipe(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of broken pipe errors as transient."""
        error = BrokenPipeError("Broken pipe (EPIPE)")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.TRANSIENT

    def test_classify_connection_refused(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of connection refused errors as transient."""
        error = ConnectionRefusedError("Connection refused")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.TRANSIENT

    def test_classify_oom_error(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of OOM errors as model errors."""
        error = RuntimeError("Model crashed: out of memory")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.MODEL_ERROR

    def test_classify_model_not_found(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of model not found errors."""
        error = ValueError("Model not found: llama3.2:3b")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.MODEL_ERROR

    def test_classify_invalid_response(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of invalid response errors."""
        error = ValueError("Invalid response from model")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.MODEL_ERROR

    def test_classify_disk_full(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of disk full errors as fatal."""
        error = OSError("No space left on device")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.FATAL

    def test_classify_permission_denied(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of permission errors as fatal."""
        error = PermissionError("Permission denied")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.FATAL

    def test_classify_unknown_error(self, recovery_engine: RecoveryEngine) -> None:
        """Test classification of unknown errors defaults to model error."""
        error = Exception("Unknown error occurred")
        error_type = recovery_engine.classify_error(error)
        assert error_type == ErrorType.MODEL_ERROR

    def test_should_retry_transient_error(self, recovery_engine: RecoveryEngine) -> None:
        """Test retry logic for transient errors."""
        assert recovery_engine.should_retry(ErrorType.TRANSIENT, 0) is True
        assert recovery_engine.should_retry(ErrorType.TRANSIENT, 1) is True
        assert recovery_engine.should_retry(ErrorType.TRANSIENT, 2) is True
        assert recovery_engine.should_retry(ErrorType.TRANSIENT, 3) is False

    def test_should_not_retry_model_error(self, recovery_engine: RecoveryEngine) -> None:
        """Test no retry for model errors."""
        assert recovery_engine.should_retry(ErrorType.MODEL_ERROR, 0) is False
        assert recovery_engine.should_retry(ErrorType.MODEL_ERROR, 1) is False

    def test_should_not_retry_fatal_error(self, recovery_engine: RecoveryEngine) -> None:
        """Test no retry for fatal errors."""
        assert recovery_engine.should_retry(ErrorType.FATAL, 0) is False
        assert recovery_engine.should_retry(ErrorType.FATAL, 1) is False

    def test_max_retries_configuration(self) -> None:
        """Test configuring max retries."""
        engine = RecoveryEngine(max_retries=5)
        assert engine.max_retries == 5
        assert engine.should_retry(ErrorType.TRANSIENT, 4) is True
        assert engine.should_retry(ErrorType.TRANSIENT, 5) is False
