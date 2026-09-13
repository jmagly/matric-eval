"""Configuration management for matric-eval."""

from pathlib import Path

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
    settings = get_settings()
    configured = settings.get_sample_count(benchmark, tier)
    normalized = benchmark.lower()

    # Preserve explicit zero overrides and legacy TierConfig zero semantics.
    override = getattr(settings, f"{normalized}_samples", None)
    if override is not None or hasattr(settings.get_tier_config(tier), normalized):
        return configured

    # Newer benchmarks define tiers in the registry rather than TierConfig.
    # Import lazily to avoid a configuration/registry import cycle.
    from matric_eval.tasks.registry import get_registry

    return get_registry().get_sample_count(benchmark, tier)


def get_datasets_dir() -> str:
    """Get configured datasets directory."""
    return get_settings().datasets_dir


def get_data_root() -> Path:
    """Root directory holding acquired benchmark corpora.

    ``EVAL_DATA_ROOT`` redirects every file-backed loader, so a dataset acquired
    into an operator-chosen destination is reachable without editing task
    modules. Task path constants derive from this at import time, so set the
    variable before importing a task module.
    """
    return Path(get_settings().data_root)


def data_path(*parts: str) -> str:
    """Path to one acquired dataset artifact beneath the resolved data root."""
    return str(get_data_root().joinpath(*parts))


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
    "get_datasets_dir",
    "get_data_root",
    "data_path",
]
