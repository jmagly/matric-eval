"""
Tests for patch_apply_scorer (matric_eval.scorers.patch_apply).

Covers:
- Path validation regex (accept valid paths, reject injection attempts)
- shlex.quote usage verification
- Scorer structure / callable interface
"""

import re
import shlex
import pytest

from matric_eval.scorers.patch_apply import (
    VALID_PATH_RE,
    patch_apply_scorer,
    validate_test_path,
)


# =============================================================================
# Path Validation Regex Tests
# =============================================================================


@pytest.mark.unit
class TestValidPathRegex:
    """Tests for VALID_PATH_RE — path safety validation."""

    def test_accepts_simple_filename(self) -> None:
        """Simple filename should pass."""
        assert re.fullmatch(VALID_PATH_RE, "test_module.py") is not None

    def test_accepts_nested_path(self) -> None:
        """Relative nested path should pass."""
        assert re.fullmatch(VALID_PATH_RE, "tests/unit/test_foo.py") is not None

    def test_accepts_path_with_dashes(self) -> None:
        """Paths with dashes should pass."""
        assert re.fullmatch(VALID_PATH_RE, "my-project/test-file.py") is not None

    def test_accepts_path_with_underscores(self) -> None:
        """Paths with underscores should pass."""
        assert re.fullmatch(VALID_PATH_RE, "my_project/test_file.py") is not None

    def test_accepts_alphanumeric(self) -> None:
        """Pure alphanumeric paths should pass."""
        assert re.fullmatch(VALID_PATH_RE, "abc123") is not None

    def test_rejects_semicolon_injection(self) -> None:
        """Shell injection via semicolon should be rejected."""
        assert re.fullmatch(VALID_PATH_RE, "tests/foo.py; rm -rf /") is None

    def test_rejects_ampersand_injection(self) -> None:
        """Shell injection via ampersand should be rejected."""
        assert re.fullmatch(VALID_PATH_RE, "tests/foo.py && evil") is None

    def test_rejects_pipe_injection(self) -> None:
        """Shell injection via pipe should be rejected."""
        assert re.fullmatch(VALID_PATH_RE, "tests/foo.py | cat /etc/passwd") is None

    def test_rejects_backtick_injection(self) -> None:
        """Backtick command substitution should be rejected."""
        assert re.fullmatch(VALID_PATH_RE, "`rm -rf /`") is None

    def test_rejects_dollar_sign(self) -> None:
        """Variable expansion via $ should be rejected."""
        assert re.fullmatch(VALID_PATH_RE, "tests/$(whoami)") is None

    def test_rejects_newline(self) -> None:
        """Newline in path should be rejected."""
        assert re.fullmatch(VALID_PATH_RE, "tests/foo.py\nrm -rf /") is None

    def test_rejects_null_byte(self) -> None:
        """Null byte in path should be rejected."""
        assert re.fullmatch(VALID_PATH_RE, "tests/foo.py\x00evil") is None

    def test_rejects_spaces(self) -> None:
        """Spaces in path should be rejected (use valid chars only)."""
        assert re.fullmatch(VALID_PATH_RE, "tests/foo bar.py") is None


# =============================================================================
# validate_test_path Tests
# =============================================================================


@pytest.mark.unit
class TestValidateTestPath:
    """Tests for validate_test_path() helper."""

    def test_valid_path_returns_true(self) -> None:
        """Valid path string returns True."""
        assert validate_test_path("tests/unit/test_foo.py") is True

    def test_injection_attempt_returns_false(self) -> None:
        """Injection attempt returns False."""
        assert validate_test_path("tests/foo.py; rm -rf /") is False

    def test_empty_path_returns_false(self) -> None:
        """Empty string returns False."""
        assert validate_test_path("") is False

    def test_none_returns_false(self) -> None:
        """None input returns False."""
        assert validate_test_path(None) is False  # type: ignore[arg-type]


# =============================================================================
# shlex.quote Usage Tests
# =============================================================================


@pytest.mark.unit
class TestShlexQuoteUsage:
    """Verify shlex.quote is used correctly for shell safety."""

    def test_shlex_quote_wraps_path(self) -> None:
        """shlex.quote should wrap paths in single quotes."""
        path = "tests/my test/foo.py"
        quoted = shlex.quote(path)
        assert quoted.startswith("'")
        assert quoted.endswith("'")

    def test_shlex_quote_escapes_single_quotes(self) -> None:
        """shlex.quote should escape single quotes in paths."""
        path = "tests/it's/foo.py"
        quoted = shlex.quote(path)
        # Quoted path should not allow single-quote escape
        assert "'" + path + "'" != quoted or "'" not in path

    def test_shlex_quote_safe_path_unchanged(self) -> None:
        """shlex.quote on a simple alphanumeric path returns the path."""
        path = "tests/foo.py"
        quoted = shlex.quote(path)
        # simple paths might not get quotes, but should be safe
        assert path in quoted


# =============================================================================
# Scorer Structure Tests
# =============================================================================


@pytest.mark.unit
class TestPatchApplyScorerStructure:
    """Tests for patch_apply_scorer() callable interface."""

    def test_scorer_is_callable(self) -> None:
        """patch_apply_scorer() should return a callable."""
        scorer_fn = patch_apply_scorer()
        assert callable(scorer_fn)

    def test_scorer_factory_callable(self) -> None:
        """patch_apply_scorer factory itself should be callable."""
        assert callable(patch_apply_scorer)

    def test_scorer_returns_on_call(self) -> None:
        """Calling the factory should not raise."""
        try:
            scorer_fn = patch_apply_scorer()
        except Exception as e:
            pytest.fail(f"patch_apply_scorer() raised unexpectedly: {e}")
