"""
Configuration for matric-eval tiers and reproducible sampling.

Based on matric-cli's tier system with seeded random sampling.
"""

import os
from dataclasses import dataclass


@dataclass
class TierConfig:
    """Configuration for an evaluation tier."""
    humaneval: int
    mbpp: int
    gsm8k: int
    arc: int = 0
    ifeval: int = 0
    ds1000: int = 0
    livecodebench: int = 0
    mtbench: int = 0
    # Application-specific benchmarks
    matric_cli: int = 0
    matric_memory: int = 0


# Tier definitions matching matric-cli
TIERS = {
    "smoke": TierConfig(
        humaneval=5,
        mbpp=5,
        gsm8k=5,
        arc=5,
        ifeval=10,
        ds1000=5,
        livecodebench=5,
        matric_cli=6,       # Half of scenarios
        matric_memory=10,   # Sample of title cases
    ),
    "quick": TierConfig(
        humaneval=75,
        mbpp=75,
        gsm8k=75,
        arc=75,
        ifeval=100,
        ds1000=50,
        livecodebench=50,
        matric_cli=12,      # All scenarios
        matric_memory=20,   # Most title cases
    ),
    "full": TierConfig(
        humaneval=164,      # All
        mbpp=974,           # All
        gsm8k=1319,         # All
        arc=2590,           # All
        ifeval=541,         # All
        ds1000=1000,        # All
        livecodebench=1055, # All (release_v6)
        mtbench=80,         # All
        matric_cli=12,      # All scenarios
        matric_memory=30,   # All title cases + similarity
    ),
}

# Default seed for reproducible sampling
# Can be overridden via EVAL_SEED environment variable
DEFAULT_SEED = 42

def get_seed() -> int:
    """Get evaluation seed from environment or default."""
    return int(os.environ.get("EVAL_SEED", DEFAULT_SEED))

def get_tier(name: str = "smoke") -> TierConfig:
    """Get tier configuration by name."""
    return TIERS.get(name, TIERS["smoke"])

# Environment variable overrides (like matric-cli)
def get_sample_count(benchmark: str, tier: str = "smoke") -> int:
    """
    Get sample count for a benchmark, respecting environment overrides.

    Environment variables:
        EVAL_HUMANEVAL_SAMPLES=100
        EVAL_MBPP_SAMPLES=50
        etc.
    """
    env_key = f"EVAL_{benchmark.upper()}_SAMPLES"
    if env_key in os.environ:
        return int(os.environ[env_key])

    tier_config = get_tier(tier)
    return getattr(tier_config, benchmark.lower(), 0)

# Model size filtering (read from environment each time it's accessed)
def get_max_model_size_gb() -> float:
    """Get maximum model size from environment or default."""
    return float(os.environ.get("MAX_MODEL_SIZE_GB", "15.0"))

# For backwards compatibility
MAX_MODEL_SIZE_GB = get_max_model_size_gb()
