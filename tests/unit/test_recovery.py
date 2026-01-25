"""
Tests for recovery engine (matric_eval.state.recovery).

Covers:
- Error classification
- Retry logic
- Error type enum
"""

import pytest

from matric_eval.state.recovery import ErrorType, RecoveryEngine


# =============================================================================
# ErrorType Tests
# =============================================================================


@pytest.mark.unit
class TestErrorType:
    """Tests for ErrorType enum."""

    def test_all_types_defined(self) -> None:
        """Should have all error types."""
        assert ErrorType.TRANSIENT.value == "transient"
        assert ErrorType.MODEL_ERROR.value == "model"
        assert ErrorType.FATAL.value == "fatal"


# =============================================================================
# RecoveryEngine Tests
# =============================================================================


@pytest.mark.unit
class TestRecoveryEngine:
    """Tests for RecoveryEngine class."""

    @pytest.fixture
    def engine(self) -> RecoveryEngine:
        """Create recovery engine."""
        return RecoveryEngine(max_retries=3)

    def test_default_max_retries(self) -> None:
        """Should have default max retries."""
        engine = RecoveryEngine()
        assert engine.max_retries == 3

    def test_custom_max_retries(self) -> None:
        """Should accept custom max retries."""
        engine = RecoveryEngine(max_retries=5)
        assert engine.max_retries == 5


# =============================================================================
# Error Classification Tests
# =============================================================================


@pytest.mark.unit
class TestClassifyError:
    """Tests for error classification."""

    @pytest.fixture
    def engine(self) -> RecoveryEngine:
        """Create recovery engine."""
        return RecoveryEngine()

    # Transient errors
    def test_timeout_is_transient(self, engine: RecoveryEngine) -> None:
        """Should classify timeout as transient."""
        error = Exception("Connection timeout after 30s")
        assert engine.classify_error(error) == ErrorType.TRANSIENT

    def test_connection_reset_is_transient(self, engine: RecoveryEngine) -> None:
        """Should classify connection reset as transient."""
        error = Exception("Connection reset by peer")
        assert engine.classify_error(error) == ErrorType.TRANSIENT

    def test_broken_pipe_is_transient(self, engine: RecoveryEngine) -> None:
        """Should classify broken pipe as transient."""
        error = Exception("Broken pipe")
        assert engine.classify_error(error) == ErrorType.TRANSIENT

    def test_epipe_is_transient(self, engine: RecoveryEngine) -> None:
        """Should classify EPIPE as transient."""
        error = Exception("EPIPE error")
        assert engine.classify_error(error) == ErrorType.TRANSIENT

    def test_connection_refused_is_transient(self, engine: RecoveryEngine) -> None:
        """Should classify connection refused as transient."""
        error = Exception("Connection refused")
        assert engine.classify_error(error) == ErrorType.TRANSIENT

    def test_temporarily_unavailable_is_transient(self, engine: RecoveryEngine) -> None:
        """Should classify temporarily unavailable as transient."""
        error = Exception("Service temporarily unavailable")
        assert engine.classify_error(error) == ErrorType.TRANSIENT

    # Model errors
    def test_oom_is_model_error(self, engine: RecoveryEngine) -> None:
        """Should classify OOM as model error."""
        error = Exception("Out of memory")
        assert engine.classify_error(error) == ErrorType.MODEL_ERROR

    def test_oom_abbreviated_is_model_error(self, engine: RecoveryEngine) -> None:
        """Should classify OOM abbreviation as model error."""
        error = Exception("OOM killed")
        assert engine.classify_error(error) == ErrorType.MODEL_ERROR

    def test_model_not_found_is_model_error(self, engine: RecoveryEngine) -> None:
        """Should classify model not found as model error."""
        error = Exception("Model not found: llama3.2:3b")
        assert engine.classify_error(error) == ErrorType.MODEL_ERROR

    def test_invalid_response_is_model_error(self, engine: RecoveryEngine) -> None:
        """Should classify invalid response as model error."""
        error = Exception("Invalid response from model")
        assert engine.classify_error(error) == ErrorType.MODEL_ERROR

    def test_model_crash_is_model_error(self, engine: RecoveryEngine) -> None:
        """Should classify model crash as model error."""
        error = Exception("Model crash during inference")
        assert engine.classify_error(error) == ErrorType.MODEL_ERROR

    # Fatal errors
    def test_disk_full_is_fatal(self, engine: RecoveryEngine) -> None:
        """Should classify disk full as fatal."""
        error = Exception("Disk full")
        assert engine.classify_error(error) == ErrorType.FATAL

    def test_no_space_is_fatal(self, engine: RecoveryEngine) -> None:
        """Should classify no space as fatal."""
        error = Exception("No space left on device")
        assert engine.classify_error(error) == ErrorType.FATAL

    def test_permission_denied_is_fatal(self, engine: RecoveryEngine) -> None:
        """Should classify permission denied as fatal."""
        error = Exception("Permission denied: /path/to/file")
        assert engine.classify_error(error) == ErrorType.FATAL

    def test_config_error_is_fatal(self, engine: RecoveryEngine) -> None:
        """Should classify configuration error as fatal."""
        error = Exception("Configuration error: missing API key")
        assert engine.classify_error(error) == ErrorType.FATAL

    # Unknown errors default to model error
    def test_unknown_error_defaults_to_model(self, engine: RecoveryEngine) -> None:
        """Should default unknown errors to model error."""
        error = Exception("Some random error")
        assert engine.classify_error(error) == ErrorType.MODEL_ERROR


# =============================================================================
# Retry Logic Tests
# =============================================================================


@pytest.mark.unit
class TestShouldRetry:
    """Tests for retry logic."""

    @pytest.fixture
    def engine(self) -> RecoveryEngine:
        """Create recovery engine with max 3 retries."""
        return RecoveryEngine(max_retries=3)

    def test_transient_should_retry_first_attempt(self, engine: RecoveryEngine) -> None:
        """Should retry transient error on first attempt."""
        assert engine.should_retry(ErrorType.TRANSIENT, attempt=0) is True

    def test_transient_should_retry_second_attempt(self, engine: RecoveryEngine) -> None:
        """Should retry transient error on second attempt."""
        assert engine.should_retry(ErrorType.TRANSIENT, attempt=1) is True

    def test_transient_should_retry_third_attempt(self, engine: RecoveryEngine) -> None:
        """Should retry transient error on third attempt."""
        assert engine.should_retry(ErrorType.TRANSIENT, attempt=2) is True

    def test_transient_should_not_retry_fourth_attempt(self, engine: RecoveryEngine) -> None:
        """Should not retry transient error beyond max retries."""
        assert engine.should_retry(ErrorType.TRANSIENT, attempt=3) is False

    def test_model_error_should_not_retry(self, engine: RecoveryEngine) -> None:
        """Should not retry model errors."""
        assert engine.should_retry(ErrorType.MODEL_ERROR, attempt=0) is False

    def test_fatal_error_should_not_retry(self, engine: RecoveryEngine) -> None:
        """Should not retry fatal errors."""
        assert engine.should_retry(ErrorType.FATAL, attempt=0) is False

    def test_custom_max_retries(self) -> None:
        """Should respect custom max retries."""
        engine = RecoveryEngine(max_retries=5)
        assert engine.should_retry(ErrorType.TRANSIENT, attempt=4) is True
        assert engine.should_retry(ErrorType.TRANSIENT, attempt=5) is False


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
class TestRecoveryIntegration:
    """Integration tests for recovery engine."""

    def test_error_handling_workflow(self) -> None:
        """Should handle error classification and retry workflow."""
        engine = RecoveryEngine(max_retries=3)

        # Simulate transient error workflow
        transient_error = Exception("Connection timeout")
        error_type = engine.classify_error(transient_error)

        attempts = 0
        while engine.should_retry(error_type, attempts):
            attempts += 1
            # Simulate retry attempt
            if attempts == 2:
                # Success on third attempt
                break

        assert attempts == 2
        assert error_type == ErrorType.TRANSIENT

    def test_model_error_skips_immediately(self) -> None:
        """Should not retry model errors."""
        engine = RecoveryEngine(max_retries=3)

        oom_error = Exception("Out of memory during inference")
        error_type = engine.classify_error(oom_error)

        # Should not retry
        assert engine.should_retry(error_type, 0) is False
        assert error_type == ErrorType.MODEL_ERROR

    def test_fatal_error_stops_immediately(self) -> None:
        """Should not retry fatal errors."""
        engine = RecoveryEngine(max_retries=3)

        disk_error = Exception("No space left on device")
        error_type = engine.classify_error(disk_error)

        # Should not retry
        assert engine.should_retry(error_type, 0) is False
        assert error_type == ErrorType.FATAL
