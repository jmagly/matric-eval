"""
Test package structure and imports.

This test verifies that all modules can be imported and the package
structure is correct.
"""

import pytest


class TestPackageStructure:
    """Test package structure and basic imports."""

    def test_main_package_import(self) -> None:
        """Test that main package can be imported."""
        import matric_eval

        assert hasattr(matric_eval, "__version__")
        assert matric_eval.__version__ == "0.1.0"

    def test_config_module_import(self) -> None:
        """Test that config module can be imported."""
        from matric_eval.config import Settings, TierConfig, get_settings

        assert Settings is not None
        assert TierConfig is not None
        assert callable(get_settings)

    def test_state_module_import(self) -> None:
        """Test that state module can be imported."""
        from matric_eval.state import RecoveryEngine, StateManager

        assert StateManager is not None
        assert RecoveryEngine is not None

    def test_utils_module_import(self) -> None:
        """Test that utils module can be imported."""
        from matric_eval.utils import sanitize_model_name

        assert callable(sanitize_model_name)

    def test_tasks_module_import(self) -> None:
        """Test that tasks module can be imported."""
        from matric_eval import tasks

        assert tasks is not None

    def test_scorers_module_import(self) -> None:
        """Test that scorers module can be imported."""
        from matric_eval import scorers

        assert scorers is not None

    def test_solvers_module_import(self) -> None:
        """Test that solvers module can be imported."""
        from matric_eval import solvers

        assert solvers is not None


class TestSettings:
    """Test Settings configuration."""

    def test_settings_defaults(self) -> None:
        """Test that Settings has correct default values."""
        from matric_eval.config import Settings

        settings = Settings()
        assert settings.seed == 42
        assert settings.max_model_size_gb == 15.0
        assert settings.tier == "smoke"
        assert settings.ollama_base_url == "http://localhost:11434"

    def test_tier_config_smoke(self) -> None:
        """Test smoke tier configuration."""
        from matric_eval.config import Settings

        settings = Settings()
        tier_config = settings.get_tier_config("smoke")
        assert tier_config.humaneval == 5
        assert tier_config.mbpp == 5
        assert tier_config.gsm8k == 5

    def test_tier_config_quick(self) -> None:
        """Test quick tier configuration."""
        from matric_eval.config import Settings

        settings = Settings()
        tier_config = settings.get_tier_config("quick")
        assert tier_config.humaneval == 75
        assert tier_config.mbpp == 75
        assert tier_config.gsm8k == 75

    def test_tier_config_full(self) -> None:
        """Test full tier configuration."""
        from matric_eval.config import Settings

        settings = Settings()
        tier_config = settings.get_tier_config("full")
        assert tier_config.humaneval == 164
        assert tier_config.mbpp == 974
        assert tier_config.gsm8k == 1319

    def test_get_sample_count(self) -> None:
        """Test getting sample count for a benchmark."""
        from matric_eval.config import Settings

        settings = Settings()
        count = settings.get_sample_count("humaneval", "smoke")
        assert count == 5

    def test_get_timeout(self) -> None:
        """Test getting timeout for a benchmark."""
        from matric_eval.config import Settings

        settings = Settings()
        timeout = settings.get_timeout("humaneval")
        assert timeout == 60


class TestHelpers:
    """Test utility helper functions."""

    def test_sanitize_model_name(self) -> None:
        """Test model name sanitization."""
        from matric_eval.utils import sanitize_model_name

        assert sanitize_model_name("llama3.2:3b") == "llama3.2_3b"
        assert sanitize_model_name("codestral/22b") == "codestral_22b"
        assert sanitize_model_name("qwen2.5:7b") == "qwen2.5_7b"
