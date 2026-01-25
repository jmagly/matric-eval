"""
Tests for configuration (matric_eval.config).

Covers:
- TierConfig dataclass
- TIERS constant
- get_seed() function
- get_tier() function
- get_sample_count() function
- Settings class
- MAX_MODEL_SIZE_GB constant
"""

import os
import pytest

from matric_eval.config import (
    DEFAULT_SEED,
    MAX_MODEL_SIZE_GB,
    TIERS,
    TierConfig,
    Settings,
    get_sample_count,
    get_seed,
    get_settings,
    get_tier,
)


# =============================================================================
# TierConfig Tests
# =============================================================================


@pytest.mark.unit
class TestTierConfig:
    """Tests for TierConfig dataclass."""

    def test_basic_creation(self) -> None:
        """Should create with required fields."""
        config = TierConfig(humaneval=10, mbpp=20, gsm8k=30)
        assert config.humaneval == 10
        assert config.mbpp == 20
        assert config.gsm8k == 30

    def test_default_values(self) -> None:
        """Should have default values for optional fields."""
        config = TierConfig(humaneval=1, mbpp=1, gsm8k=1)
        assert config.arc == 0
        assert config.ifeval == 0
        assert config.ds1000 == 0
        assert config.livecodebench == 0
        assert config.mtbench == 0

    def test_all_fields(self) -> None:
        """Should accept all fields."""
        config = TierConfig(
            humaneval=100,
            mbpp=200,
            gsm8k=300,
            arc=400,
            ifeval=500,
            ds1000=600,
            livecodebench=700,
            mtbench=800,
        )
        assert config.humaneval == 100
        assert config.mbpp == 200
        assert config.gsm8k == 300
        assert config.arc == 400
        assert config.ifeval == 500
        assert config.ds1000 == 600
        assert config.livecodebench == 700
        assert config.mtbench == 800


# =============================================================================
# TIERS Tests
# =============================================================================


@pytest.mark.unit
class TestTIERS:
    """Tests for TIERS constant."""

    def test_has_three_tiers(self) -> None:
        """Should have smoke, quick, and full tiers."""
        assert "smoke" in TIERS
        assert "quick" in TIERS
        assert "full" in TIERS
        assert len(TIERS) == 3

    def test_smoke_tier_values(self) -> None:
        """Smoke tier should have small sample counts."""
        smoke = TIERS["smoke"]
        assert smoke.humaneval == 5
        assert smoke.mbpp == 5
        assert smoke.gsm8k == 5

    def test_quick_tier_values(self) -> None:
        """Quick tier should have medium sample counts."""
        quick = TIERS["quick"]
        assert quick.humaneval == 75
        assert quick.mbpp == 75
        assert quick.gsm8k == 75

    def test_full_tier_values(self) -> None:
        """Full tier should have all samples."""
        full = TIERS["full"]
        assert full.humaneval == 164
        assert full.mbpp == 974
        assert full.gsm8k == 1319


# =============================================================================
# get_seed Tests
# =============================================================================


@pytest.mark.unit
class TestGetSeed:
    """Tests for get_seed function."""

    def test_default_seed(self) -> None:
        """Should return default seed (from singleton)."""
        # get_seed uses singleton, so just verify it returns an int
        seed = get_seed()
        assert isinstance(seed, int)
        assert seed > 0

    def test_env_override_via_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use environment variable when creating fresh Settings."""
        # The get_seed() function uses a singleton, so to test env override
        # we must create a fresh Settings instance
        monkeypatch.setenv("EVAL_SEED", "123")
        settings = Settings()
        assert settings.seed == 123


# =============================================================================
# get_tier Tests
# =============================================================================


@pytest.mark.unit
class TestGetTier:
    """Tests for get_tier function."""

    def test_get_smoke_tier(self) -> None:
        """Should return smoke tier."""
        tier = get_tier("smoke")
        assert tier == TIERS["smoke"]

    def test_get_quick_tier(self) -> None:
        """Should return quick tier."""
        tier = get_tier("quick")
        assert tier == TIERS["quick"]

    def test_get_full_tier(self) -> None:
        """Should return full tier."""
        tier = get_tier("full")
        assert tier == TIERS["full"]

    def test_default_to_smoke(self) -> None:
        """Should default to smoke for unknown tier."""
        tier = get_tier("nonexistent")
        assert tier == TIERS["smoke"]

    def test_no_args_returns_smoke(self) -> None:
        """Should return smoke when called without args."""
        tier = get_tier()
        assert tier == TIERS["smoke"]


# =============================================================================
# get_sample_count Tests
# =============================================================================


@pytest.mark.unit
class TestGetSampleCount:
    """Tests for get_sample_count function."""

    def test_get_humaneval_smoke(self) -> None:
        """Should return humaneval count for smoke tier."""
        count = get_sample_count("humaneval", "smoke")
        assert count == 5

    def test_get_mbpp_quick(self) -> None:
        """Should return mbpp count for quick tier."""
        count = get_sample_count("mbpp", "quick")
        assert count == 75

    def test_env_override_via_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use environment variable via fresh Settings instance."""
        # get_sample_count uses singleton, so test env override with fresh Settings
        monkeypatch.setenv("EVAL_HUMANEVAL_SAMPLES", "100")
        settings = Settings()
        count = settings.get_sample_count("humaneval", "smoke")
        assert count == 100

    def test_unknown_benchmark(self) -> None:
        """Should return 0 for unknown benchmark."""
        count = get_sample_count("unknown", "smoke")
        assert count == 0

    def test_default_tier(self) -> None:
        """Should default to smoke tier."""
        count = get_sample_count("humaneval")
        assert count == 5


# =============================================================================
# MAX_MODEL_SIZE_GB and Settings Tests
# =============================================================================


@pytest.mark.unit
class TestMaxModelSizeGB:
    """Tests for MAX_MODEL_SIZE_GB constant and Settings.max_model_size_gb."""

    def test_constant_value(self) -> None:
        """Should have correct default constant value."""
        assert MAX_MODEL_SIZE_GB == 15.0

    def test_settings_default_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return default size from Settings when no env var."""
        monkeypatch.delenv("EVAL_MAX_MODEL_SIZE_GB", raising=False)
        settings = Settings()
        assert settings.max_model_size_gb == 15.0

    def test_settings_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use environment variable when set."""
        monkeypatch.setenv("EVAL_MAX_MODEL_SIZE_GB", "25.0")
        settings = Settings()
        assert settings.max_model_size_gb == 25.0


@pytest.mark.unit
class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        settings = Settings()
        assert settings.seed == 42
        assert settings.max_model_size_gb == 15.0
        assert settings.ollama_base_url == "http://localhost:11434"
        assert settings.tier == "smoke"
        assert settings.output_dir == "results"

    def test_get_timeout_humaneval(self) -> None:
        """Should return correct timeout for humaneval."""
        settings = Settings()
        assert settings.get_timeout("humaneval") == 60

    def test_get_timeout_gsm8k(self) -> None:
        """Should return correct timeout for gsm8k."""
        settings = Settings()
        assert settings.get_timeout("gsm8k") == 30

    def test_get_timeout_unknown(self) -> None:
        """Should return default timeout for unknown benchmark."""
        settings = Settings()
        assert settings.get_timeout("unknown") == 60

    def test_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should respect EVAL_ prefix for environment variables."""
        monkeypatch.setenv("EVAL_SEED", "123")
        monkeypatch.setenv("EVAL_TIER", "quick")
        settings = Settings()
        assert settings.seed == 123
        assert settings.tier == "quick"


@pytest.mark.unit
class TestGetSettings:
    """Tests for get_settings function."""

    def test_returns_settings(self) -> None:
        """Should return a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
class TestConfigIntegration:
    """Integration tests for configuration."""

    def test_tier_sample_counts_increase(self) -> None:
        """Tier sample counts should increase: smoke < quick < full."""
        smoke = TIERS["smoke"]
        quick = TIERS["quick"]
        full = TIERS["full"]

        # HumanEval
        assert smoke.humaneval < quick.humaneval < full.humaneval

        # MBPP
        assert smoke.mbpp < quick.mbpp < full.mbpp

        # GSM8K
        assert smoke.gsm8k < quick.gsm8k < full.gsm8k

    def test_full_tier_has_complete_datasets(self) -> None:
        """Full tier should have complete dataset sizes."""
        full = TIERS["full"]

        # Known dataset sizes
        assert full.humaneval == 164
        assert full.mbpp == 974
        assert full.gsm8k == 1319
        assert full.arc == 1172  # ARC-Challenge only
        assert full.ifeval == 541

    def test_sample_count_env_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment override should work for any tier via fresh Settings."""
        monkeypatch.setenv("EVAL_HUMANEVAL_SAMPLES", "50")

        # Create fresh Settings to pick up env var
        settings = Settings()

        # Should return env value regardless of tier
        assert settings.get_sample_count("humaneval", "smoke") == 50
        assert settings.get_sample_count("humaneval", "quick") == 50
        assert settings.get_sample_count("humaneval", "full") == 50
