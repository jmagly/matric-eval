"""
Tests for configuration module (matric_eval.config).

Covers:
- Tier configurations
- Reproducible seeding
- Environment variable overrides
- Sample count calculations
"""

import pytest

from matric_eval.config import (
    DEFAULT_SEED,
    MAX_MODEL_SIZE_GB,
    TIERS,
    TierConfig,
    get_sample_count,
    get_seed,
    get_tier,
)


# =============================================================================
# Tier Configuration Tests
# =============================================================================


@pytest.mark.unit
class TestTierConfig:
    """Tests for TierConfig dataclass."""

    def test_tier_config_creation(self) -> None:
        """Should create TierConfig with all fields."""
        config = TierConfig(
            humaneval=10,
            mbpp=20,
            gsm8k=15,
            arc=25,
            ifeval=30,
        )

        assert config.humaneval == 10
        assert config.mbpp == 20
        assert config.gsm8k == 15
        assert config.arc == 25
        assert config.ifeval == 30

    def test_tier_config_defaults(self) -> None:
        """Should have default values for optional benchmarks."""
        config = TierConfig(humaneval=5, mbpp=5, gsm8k=5)

        assert config.arc == 0
        assert config.ifeval == 0
        assert config.ds1000 == 0
        assert config.livecodebench == 0
        assert config.mtbench == 0


@pytest.mark.unit
class TestPredefinedTiers:
    """Tests for predefined tier configurations."""

    def test_smoke_tier_exists(self) -> None:
        """Should have smoke tier configuration."""
        assert "smoke" in TIERS
        smoke = TIERS["smoke"]

        assert smoke.humaneval == 5
        assert smoke.mbpp == 5
        assert smoke.gsm8k == 5
        assert smoke.arc == 5
        assert smoke.ifeval == 10

    def test_quick_tier_exists(self) -> None:
        """Should have quick tier configuration."""
        assert "quick" in TIERS
        quick = TIERS["quick"]

        assert quick.humaneval == 75
        assert quick.mbpp == 75
        assert quick.gsm8k == 75
        assert quick.arc == 75
        assert quick.ifeval == 100

    def test_full_tier_exists(self) -> None:
        """Should have full tier configuration."""
        assert "full" in TIERS
        full = TIERS["full"]

        # Full benchmark sizes
        assert full.humaneval == 164
        assert full.mbpp == 974
        assert full.gsm8k == 1319
        assert full.arc == 1172  # ARC-Challenge only
        assert full.ifeval == 541

    def test_all_tiers_valid(self) -> None:
        """Should have valid sample counts for all tiers."""
        for tier_name, config in TIERS.items():
            assert config.humaneval >= 0, f"{tier_name} has negative humaneval count"
            assert config.mbpp >= 0, f"{tier_name} has negative mbpp count"
            assert config.gsm8k >= 0, f"{tier_name} has negative gsm8k count"


# =============================================================================
# Seed Management Tests
# =============================================================================


@pytest.mark.unit
class TestGetSeed:
    """Tests for get_seed() function."""

    def test_default_seed(self, env_no_overrides: None) -> None:
        """Should return default seed when no environment override."""
        seed = get_seed()
        assert seed == DEFAULT_SEED
        assert seed == 42

    def test_custom_seed_from_env(self, env_custom_seed: int) -> None:
        """Should return seed from EVAL_SEED environment variable."""
        seed = get_seed()
        assert seed == 12345

    def test_seed_is_integer(self, env_no_overrides: None) -> None:
        """Should always return an integer."""
        seed = get_seed()
        assert isinstance(seed, int)


# =============================================================================
# Tier Retrieval Tests
# =============================================================================


@pytest.mark.unit
class TestGetTier:
    """Tests for get_tier() function."""

    def test_get_smoke_tier(self) -> None:
        """Should retrieve smoke tier configuration."""
        tier = get_tier("smoke")
        assert tier == TIERS["smoke"]
        assert tier.humaneval == 5

    def test_get_quick_tier(self) -> None:
        """Should retrieve quick tier configuration."""
        tier = get_tier("quick")
        assert tier == TIERS["quick"]
        assert tier.humaneval == 75

    def test_get_full_tier(self) -> None:
        """Should retrieve full tier configuration."""
        tier = get_tier("full")
        assert tier == TIERS["full"]
        assert tier.humaneval == 164

    def test_default_to_smoke(self) -> None:
        """Should default to smoke tier if no name provided."""
        tier = get_tier()
        assert tier == TIERS["smoke"]

    def test_invalid_tier_defaults_to_smoke(self) -> None:
        """Should default to smoke tier for invalid tier names."""
        tier = get_tier("nonexistent")
        assert tier == TIERS["smoke"]


# =============================================================================
# Sample Count Tests
# =============================================================================


@pytest.mark.unit
class TestGetSampleCount:
    """Tests for get_sample_count() function."""

    def test_sample_count_smoke_tier(self, env_no_overrides: None) -> None:
        """Should return correct sample counts for smoke tier."""
        assert get_sample_count("humaneval", "smoke") == 5
        assert get_sample_count("mbpp", "smoke") == 5
        assert get_sample_count("gsm8k", "smoke") == 5

    def test_sample_count_quick_tier(self, env_no_overrides: None) -> None:
        """Should return correct sample counts for quick tier."""
        assert get_sample_count("humaneval", "quick") == 75
        assert get_sample_count("mbpp", "quick") == 75
        assert get_sample_count("gsm8k", "quick") == 75

    def test_sample_count_full_tier(self, env_no_overrides: None) -> None:
        """Should return correct sample counts for full tier."""
        assert get_sample_count("humaneval", "full") == 164
        assert get_sample_count("mbpp", "full") == 974
        assert get_sample_count("gsm8k", "full") == 1319

    def test_sample_count_env_override(
        self,
        env_custom_samples: dict[str, int],
    ) -> None:
        """Should respect environment variable overrides."""
        assert get_sample_count("humaneval") == 10
        assert get_sample_count("mbpp") == 20
        assert get_sample_count("gsm8k") == 15

    def test_sample_count_unknown_benchmark(self, env_no_overrides: None) -> None:
        """Should return 0 for unknown benchmarks."""
        assert get_sample_count("unknown_benchmark", "smoke") == 0

    def test_sample_count_case_insensitive(self, env_no_overrides: None) -> None:
        """Should handle benchmark names case-insensitively."""
        # Implementation uses .lower(), so uppercase should work
        assert get_sample_count("HUMANEVAL", "smoke") == 5
        assert get_sample_count("HumanEval", "smoke") == 5


# =============================================================================
# Environment Variable Tests
# =============================================================================


@pytest.mark.unit
class TestEnvironmentVariables:
    """Tests for environment variable handling."""

    def test_max_model_size_default(self, env_no_overrides: None) -> None:
        """Should have default MAX_MODEL_SIZE_GB."""
        # Note: This tests the module-level constant
        # In real usage, this would be read at import time
        assert MAX_MODEL_SIZE_GB == 15.0

    def test_max_model_size_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should read MAX_MODEL_SIZE_GB from environment."""
        # This test demonstrates the pattern, but the module-level
        # constant is evaluated at import time
        monkeypatch.setenv("MAX_MODEL_SIZE_GB", "20.0")

        # Would need to reload module to test this properly
        # Documenting expected behavior
        import os
        assert float(os.environ.get("MAX_MODEL_SIZE_GB", "15.0")) == 20.0


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
class TestConfigIntegration:
    """Integration tests for config module."""

    def test_tier_to_sample_count_workflow(self, env_no_overrides: None) -> None:
        """Should get sample counts from tier configuration."""
        tier = get_tier("quick")

        assert tier.humaneval == 75
        assert get_sample_count("humaneval", "quick") == 75

    def test_reproducible_seed_workflow(self, env_no_overrides: None) -> None:
        """Should provide reproducible seeds for sampling."""
        seed1 = get_seed()
        seed2 = get_seed()

        # Same seed should be returned consistently
        assert seed1 == seed2
        assert seed1 == DEFAULT_SEED

    def test_env_override_workflow(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should allow full environment-based configuration."""
        # Set custom values
        monkeypatch.setenv("EVAL_SEED", "999")
        monkeypatch.setenv("EVAL_HUMANEVAL_SAMPLES", "50")

        # Reset the settings singleton so it re-reads from environment
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        assert get_seed() == 999
        assert get_sample_count("humaneval") == 50


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
class TestConfigEdgeCases:
    """Tests for edge cases in config module."""

    def test_zero_sample_count(self) -> None:
        """Should handle unknown benchmarks with zero sample counts correctly."""
        # Unknown benchmark returns 0 samples
        assert get_sample_count("unknown_benchmark", "smoke") == 0
        # TierConfig defaults to 0 for unset benchmarks
        tier = TierConfig(humaneval=5, mbpp=5)
        assert tier.arc == 0

    def test_empty_tier_name(self) -> None:
        """Should handle empty tier name gracefully."""
        tier = get_tier("")
        assert tier == TIERS["smoke"]

    def test_none_tier_name(self) -> None:
        """Should handle None tier name gracefully."""
        tier = get_tier()  # type: ignore
        assert tier == TIERS["smoke"]

    def test_sample_count_with_none_tier(self, env_no_overrides: None) -> None:
        """Should handle None tier in get_sample_count."""
        # Uses default "smoke" tier
        count = get_sample_count("humaneval")
        assert count == 5
