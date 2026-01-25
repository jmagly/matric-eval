"""
Tests for configuration legacy compatibility functions.

Verifies backward compatibility with old config.py API.
"""

import pytest

from matric_eval.config import (
    DEFAULT_SEED,
    MAX_MODEL_SIZE_GB,
    TIERS,
    get_sample_count,
    get_seed,
    get_tier,
)


class TestLegacyConfigAPI:
    """Test legacy configuration API for backward compatibility."""

    def test_default_seed_constant(self) -> None:
        """Test DEFAULT_SEED constant is available."""
        assert DEFAULT_SEED == 42

    def test_max_model_size_constant(self) -> None:
        """Test MAX_MODEL_SIZE_GB constant is available."""
        assert MAX_MODEL_SIZE_GB == 15.0

    def test_get_seed_function(self) -> None:
        """Test get_seed() legacy function."""
        seed = get_seed()
        assert isinstance(seed, int)
        assert seed == 42

    def test_get_tier_smoke(self) -> None:
        """Test get_tier() legacy function for smoke tier."""
        tier = get_tier("smoke")
        assert tier.humaneval == 5
        assert tier.mbpp == 5

    def test_get_tier_quick(self) -> None:
        """Test get_tier() legacy function for quick tier."""
        tier = get_tier("quick")
        assert tier.humaneval == 75
        assert tier.mbpp == 75

    def test_get_tier_default(self) -> None:
        """Test get_tier() defaults to smoke."""
        tier = get_tier()
        assert tier.humaneval == 5

    def test_get_sample_count_smoke(self) -> None:
        """Test get_sample_count() for smoke tier."""
        count = get_sample_count("humaneval", "smoke")
        assert count == 5

    def test_get_sample_count_quick(self) -> None:
        """Test get_sample_count() for quick tier."""
        count = get_sample_count("mbpp", "quick")
        assert count == 75

    def test_get_sample_count_default_tier(self) -> None:
        """Test get_sample_count() with default tier."""
        count = get_sample_count("humaneval")
        assert count == 5  # smoke tier default

    def test_tiers_dict_available(self) -> None:
        """Test TIERS dictionary is available."""
        assert "smoke" in TIERS
        assert "quick" in TIERS
        assert "full" in TIERS
