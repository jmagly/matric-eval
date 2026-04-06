"""
Task Registry — centralized benchmark registration with metadata decorators.

Replaces the hardcoded TASK_MAP, TierConfig fields, and CLI description
dictionaries with a single source of truth for all benchmark metadata.

Usage:
    @register_benchmark(
        name="humaneval",
        description="HumanEval - Python code generation (164 problems)",
        category="code",
        tier_samples={"smoke": 5, "quick": 75, "full": 164},
    )
    @task
    def humaneval(tier: str = "smoke") -> Task:
        ...
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class BenchmarkCategory(str, Enum):
    """Categories for benchmark classification."""

    CODE = "code"
    MATH = "math"
    REASONING = "reasoning"
    INSTRUCTION = "instruction"
    KNOWLEDGE = "knowledge"
    CONVERSATION = "conversation"
    TOOL_USE = "tool_use"
    APPLICATION = "application"
    AGENTIC = "agentic"
    MULTIMODAL = "multimodal"
    DATA_SCIENCE = "data_science"


@dataclass(frozen=True)
class BenchmarkMetadata:
    """Metadata for a registered benchmark.

    Attributes:
        name: Unique benchmark identifier (e.g., "humaneval")
        description: Human-readable description for CLI display
        category: Classification category
        module_path: Fully qualified path to task function (e.g., "matric_eval.tasks.humaneval.humaneval")
        tier_samples: Sample counts per tier {"smoke": 5, "quick": 75, "full": 164}
        total_samples: Total available samples in the dataset
        requires_sandbox: Whether this benchmark needs agentic-sandbox
        requires_vision: Whether this benchmark needs multimodal/vision support
        sandbox_profile: agentic-sandbox profile to use (e.g., "agentic-dev", "basic")
        scoring_type: Scoring methodology ("standard", "pass_k", "elo", "project")
        provider_requirements: List of required provider capabilities
    """

    name: str
    description: str
    category: BenchmarkCategory
    module_path: str
    tier_samples: dict[str, int] = field(default_factory=dict)
    total_samples: int = 0
    requires_sandbox: bool = False
    requires_vision: bool = False
    sandbox_profile: Optional[str] = None
    scoring_type: str = "standard"
    provider_requirements: tuple[str, ...] = ()


class TaskRegistry:
    """Central registry for all benchmark tasks.

    Provides a single source of truth for benchmark metadata, replacing
    the hardcoded TASK_MAP, TierConfig, and CLI description dictionaries.

    Thread-safe for reads after freeze(). Not thread-safe during registration.
    """

    def __init__(self) -> None:
        self._benchmarks: dict[str, BenchmarkMetadata] = {}
        self._frozen: bool = False

    def register(self, metadata: BenchmarkMetadata) -> None:
        """Register a benchmark.

        Args:
            metadata: Benchmark metadata to register

        Raises:
            RuntimeError: If registry is frozen
            ValueError: If benchmark name is already registered
        """
        if self._frozen:
            raise RuntimeError(
                f"Cannot register '{metadata.name}': registry is frozen. "
                "Call freeze() only after all benchmarks are registered."
            )
        if metadata.name in self._benchmarks:
            raise ValueError(
                f"Benchmark '{metadata.name}' is already registered. "
                f"Existing: {self._benchmarks[metadata.name].module_path}"
            )
        self._benchmarks[metadata.name] = metadata

    def get(self, name: str) -> Optional[BenchmarkMetadata]:
        """Get benchmark metadata by name."""
        return self._benchmarks.get(name)

    def get_or_raise(self, name: str) -> BenchmarkMetadata:
        """Get benchmark metadata by name, raising if not found.

        Raises:
            KeyError: If benchmark is not registered
        """
        meta = self._benchmarks.get(name)
        if meta is None:
            raise KeyError(
                f"Unknown benchmark: '{name}'. "
                f"Available: {', '.join(sorted(self._benchmarks))}"
            )
        return meta

    def list_names(self) -> list[str]:
        """List all registered benchmark names, sorted."""
        return sorted(self._benchmarks.keys())

    def list_metadata(self) -> list[BenchmarkMetadata]:
        """List all registered benchmark metadata, sorted by name."""
        return [self._benchmarks[k] for k in sorted(self._benchmarks)]

    def filter(
        self,
        *,
        category: Optional[BenchmarkCategory] = None,
        requires_sandbox: Optional[bool] = None,
        requires_vision: Optional[bool] = None,
    ) -> list[BenchmarkMetadata]:
        """Filter benchmarks by criteria."""
        results = list(self._benchmarks.values())
        if category is not None:
            results = [m for m in results if m.category == category]
        if requires_sandbox is not None:
            results = [m for m in results if m.requires_sandbox == requires_sandbox]
        if requires_vision is not None:
            results = [m for m in results if m.requires_vision == requires_vision]
        return sorted(results, key=lambda m: m.name)

    def get_sample_count(self, name: str, tier: str) -> int:
        """Get sample count for a benchmark at a given tier.

        Returns 0 if benchmark or tier is unknown.
        """
        meta = self._benchmarks.get(name)
        if meta is None:
            return 0
        return meta.tier_samples.get(tier, 0)

    def get_descriptions(self) -> dict[str, str]:
        """Get name→description mapping for all benchmarks (for CLI)."""
        return {
            name: meta.description
            for name, meta in sorted(self._benchmarks.items())
        }

    def load_task(self, name: str, tier: str = "smoke") -> Any:
        """Dynamically load and invoke a benchmark's task function.

        Args:
            name: Benchmark name
            tier: Evaluation tier

        Returns:
            Inspect AI Task object

        Raises:
            KeyError: If benchmark is not registered
            ImportError: If module cannot be loaded
            ValueError: If module path is outside allowed namespace
        """
        meta = self.get_or_raise(name)
        module_path = meta.module_path

        # Security: restrict to matric_eval.tasks.* namespace
        if not module_path.startswith("matric_eval.tasks."):
            raise ValueError(
                f"Module path '{module_path}' is outside allowed namespace 'matric_eval.tasks.*'"
            )

        module_name, func_name = module_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        task_fn = getattr(module, func_name)
        return task_fn(tier=tier)

    def freeze(self) -> None:
        """Freeze the registry, preventing further registrations.

        Call after all benchmark modules have been imported.
        """
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        """Whether the registry is frozen."""
        return self._frozen

    def __len__(self) -> int:
        return len(self._benchmarks)

    def __contains__(self, name: str) -> bool:
        return name in self._benchmarks

    def __repr__(self) -> str:
        status = "frozen" if self._frozen else "open"
        return f"TaskRegistry({len(self._benchmarks)} benchmarks, {status})"


# ---------------------------------------------------------------------------
# Global registry singleton
# ---------------------------------------------------------------------------

_registry = TaskRegistry()


def get_registry() -> TaskRegistry:
    """Get the global task registry singleton."""
    return _registry


def register_benchmark(
    *,
    name: str,
    description: str,
    category: BenchmarkCategory | str,
    tier_samples: dict[str, int] | None = None,
    total_samples: int = 0,
    requires_sandbox: bool = False,
    requires_vision: bool = False,
    sandbox_profile: str | None = None,
    scoring_type: str = "standard",
    provider_requirements: tuple[str, ...] = (),
) -> Callable:
    """Decorator to register a benchmark task function.

    Usage:
        @register_benchmark(
            name="humaneval",
            description="HumanEval - Python code generation (164 problems)",
            category="code",
            tier_samples={"smoke": 5, "quick": 75, "full": 164},
            total_samples=164,
        )
        @task
        def humaneval(tier: str = "smoke") -> Task:
            ...
    """
    if isinstance(category, str):
        category = BenchmarkCategory(category)

    def decorator(func: Callable) -> Callable:
        # Derive module_path from the function's qualified name
        module = func.__module__
        func_name = func.__name__
        module_path = f"{module}.{func_name}"

        metadata = BenchmarkMetadata(
            name=name,
            description=description,
            category=category,
            module_path=module_path,
            tier_samples=tier_samples or {},
            total_samples=total_samples,
            requires_sandbox=requires_sandbox,
            requires_vision=requires_vision,
            sandbox_profile=sandbox_profile,
            scoring_type=scoring_type,
            provider_requirements=provider_requirements,
        )
        _registry.register(metadata)
        # Attach metadata to function for introspection
        func._benchmark_metadata = metadata  # type: ignore[attr-defined]
        return func

    return decorator
