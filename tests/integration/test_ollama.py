"""
Integration tests for Ollama model interactions.

These tests require:
- Ollama installed and running
- At least one small model available (e.g., llama3.2:3b)

Mark tests with @pytest.mark.integration and skip if Ollama unavailable.
"""

import subprocess

import pytest

from matric_eval.cli import filter_models, get_ollama_models


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def ollama_available() -> bool:
    """Check if Ollama is available and running."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


@pytest.fixture
def skip_if_no_ollama(ollama_available: bool) -> None:
    """Skip test if Ollama is not available."""
    if not ollama_available:
        pytest.skip("Ollama not available")


# =============================================================================
# Ollama Discovery Integration Tests
# =============================================================================


@pytest.mark.integration
class TestOllamaIntegration:
    """Integration tests with real Ollama installation."""

    def test_get_ollama_models_real(self, skip_if_no_ollama: None) -> None:
        """Should retrieve real models from Ollama."""
        models = get_ollama_models(max_size_gb=50.0)

        # Should get at least some models (if any installed)
        assert isinstance(models, list)

        for model in models:
            assert "name" in model
            assert "size_gb" in model
            assert "size_str" in model
            assert model["size_gb"] > 0

    def test_filter_real_models(self, skip_if_no_ollama: None) -> None:
        """Should filter real Ollama models correctly."""
        all_models = get_ollama_models(max_size_gb=50.0)
        filtered = filter_models(all_models)

        # Filtered list should be <= original
        assert len(filtered) <= len(all_models)

        # No embedding models should remain
        for model in filtered:
            name_lower = model["name"].lower()
            assert "embed" not in name_lower
            assert "snowflake" not in name_lower

    def test_size_filtering_real(self, skip_if_no_ollama: None) -> None:
        """Should respect size threshold with real models."""
        small_models = get_ollama_models(max_size_gb=5.0)
        all_models = get_ollama_models(max_size_gb=100.0)

        # Small threshold should give fewer models
        assert len(small_models) <= len(all_models)

        # All small models should be under threshold
        for model in small_models:
            assert model["size_gb"] <= 5.0


# =============================================================================
# Placeholder for Future Evaluation Integration Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skip(reason="Requires model inference - very slow")
class TestEvaluationIntegration:
    """Placeholder for full evaluation integration tests."""

    def test_run_smoke_eval_real_model(self) -> None:
        """Should run smoke evaluation on real model."""
        # TODO: Implement when ready to test against real models
        # This will be slow (minutes per model)
        pass

    def test_full_evaluation_pipeline(self) -> None:
        """Should run complete evaluation pipeline."""
        # TODO: Implement full pipeline test
        pass


# =============================================================================
# Environment Tests
# =============================================================================


@pytest.mark.integration
class TestEnvironment:
    """Tests for environment setup and dependencies."""

    def test_inspect_ai_available(self) -> None:
        """Should have Inspect AI installed."""
        try:
            import inspect_ai
            assert inspect_ai is not None
        except ImportError:
            pytest.fail("inspect_ai not installed")

    def test_required_packages(self) -> None:
        """Should have all required packages."""
        required = ["inspect_ai", "httpx", "pytest"]

        for package in required:
            try:
                __import__(package)
            except ImportError:
                pytest.fail(f"Required package not installed: {package}")

    def test_ollama_version(self, skip_if_no_ollama: None) -> None:
        """Should have compatible Ollama version."""
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )

        # Just verify it has a version
        assert result.stdout.strip() != ""
