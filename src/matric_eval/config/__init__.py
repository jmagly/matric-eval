"""Configuration management for matric-eval."""

from .settings import TIERS, Settings, TierConfig, get_settings

# Legacy compatibility functions for existing code
DEFAULT_SEED = 42
MAX_MODEL_SIZE_GB = 15.0


def get_seed() -> int:
    """Get evaluation seed (legacy compatibility function)."""
    return get_settings().seed


def get_tier(name: str = "smoke") -> TierConfig:
    """Get tier configuration by name (legacy compatibility function)."""
    return get_settings().get_tier_config(name)


def get_sample_count(benchmark: str, tier: str = "smoke") -> int:
    """Get sample count for benchmark (legacy compatibility function)."""
    return get_settings().get_sample_count(benchmark, tier)


__all__ = [
    "Settings",
    "TierConfig",
    "get_settings",
    "TIERS",
    "DEFAULT_SEED",
    "MAX_MODEL_SIZE_GB",
    "get_seed",
    "get_tier",
    "get_sample_count",
]
