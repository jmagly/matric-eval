"""
Configuration management for matric-eval using Pydantic.

Provides environment-based configuration with sensible defaults.
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TierConfig(BaseSettings):
    """Configuration for an evaluation tier."""

    humaneval: int = 0
    mbpp: int = 0
    gsm8k: int = 0
    arc: int = 0
    ifeval: int = 0
    ds1000: int = 0
    livecodebench: int = 0
    mtbench: int = 0
    tool_calling: int = 0
    custom: int = 0


# Tier definitions matching matric-cli
TIERS: dict[str, TierConfig] = {
    "smoke": TierConfig(
        humaneval=5,
        mbpp=5,
        gsm8k=5,
        arc=5,
        ifeval=10,
        ds1000=5,
        livecodebench=5,
        mtbench=5,
        tool_calling=5,
        custom=5,
    ),
    "quick": TierConfig(
        humaneval=75,
        mbpp=75,
        gsm8k=75,
        arc=75,
        ifeval=100,
        ds1000=50,
        livecodebench=50,
        mtbench=30,
        tool_calling=30,
        custom=50,
    ),
    "full": TierConfig(
        humaneval=164,  # All
        mbpp=974,  # All
        gsm8k=1319,  # All
        arc=1172,  # All (ARC-Challenge only)
        ifeval=541,  # All
        ds1000=1000,  # All
        livecodebench=880,  # All
        mtbench=80,  # All
        tool_calling=100,  # All synthetic
        custom=1000,  # All custom tests
    ),
}


class Settings(BaseSettings):
    """
    Main configuration for matric-eval.

    Loads from environment variables with EVAL_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="EVAL_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Reproducibility
    seed: int = Field(default=42, description="Random seed for reproducible sampling")

    # Model filtering
    max_model_size_gb: float = Field(
        default=15.0, description="Maximum model size in GB to evaluate"
    )

    # Ollama configuration
    ollama_base_url: str = Field(
        default="http://localhost:11434", description="Ollama API endpoint"
    )

    # Evaluation tier
    tier: Literal["smoke", "quick", "full"] = Field(
        default="smoke", description="Evaluation tier"
    )

    # Output configuration
    output_dir: str = Field(default="results", description="Output directory for results")

    # Problem timeouts (seconds)
    timeout_humaneval: int = Field(default=60, description="Timeout for HumanEval problems")
    timeout_mbpp: int = Field(default=60, description="Timeout for MBPP problems")
    timeout_gsm8k: int = Field(default=30, description="Timeout for GSM8K problems")
    timeout_arc: int = Field(default=30, description="Timeout for ARC problems")
    timeout_default: int = Field(default=60, description="Default problem timeout")

    # Sample count overrides (optional)
    humaneval_samples: int | None = Field(default=None, description="Override HumanEval samples")
    mbpp_samples: int | None = Field(default=None, description="Override MBPP samples")
    gsm8k_samples: int | None = Field(default=None, description="Override GSM8K samples")
    arc_samples: int | None = Field(default=None, description="Override ARC samples")
    ifeval_samples: int | None = Field(default=None, description="Override IFEval samples")
    ds1000_samples: int | None = Field(default=None, description="Override DS-1000 samples")
    livecodebench_samples: int | None = Field(
        default=None, description="Override LiveCodeBench samples"
    )
    mtbench_samples: int | None = Field(default=None, description="Override MTBench samples")

    def get_tier_config(self, tier_name: str | None = None) -> TierConfig:
        """Get tier configuration by name."""
        tier = tier_name or self.tier
        return TIERS.get(tier, TIERS["smoke"])

    def get_sample_count(self, benchmark: str, tier_name: str | None = None) -> int:
        """
        Get sample count for a benchmark, respecting environment overrides.

        Args:
            benchmark: Benchmark name (e.g., "humaneval")
            tier_name: Optional tier override

        Returns:
            Number of samples to evaluate
        """
        # Check for explicit override
        override_attr = f"{benchmark.lower()}_samples"
        if hasattr(self, override_attr):
            override_value = getattr(self, override_attr)
            if override_value is not None:
                return override_value

        # Fall back to tier configuration
        tier_config = self.get_tier_config(tier_name)
        return getattr(tier_config, benchmark.lower(), 0)

    def get_timeout(self, benchmark: str) -> int:
        """
        Get timeout for a benchmark.

        Args:
            benchmark: Benchmark name (e.g., "humaneval")

        Returns:
            Timeout in seconds
        """
        timeout_attr = f"timeout_{benchmark.lower()}"
        if hasattr(self, timeout_attr):
            return getattr(self, timeout_attr)
        return self.timeout_default


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
