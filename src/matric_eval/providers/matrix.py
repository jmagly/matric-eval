"""
Evaluation matrix configuration for matric-eval.

Supports YAML/dict-based evaluation matrix definitions that specify
which models to evaluate on which providers with which benchmarks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MatrixExclusion:
    """A specific model-provider combination to exclude."""

    model: str = ""
    provider: str = ""
    benchmark: str = ""


@dataclass
class EvaluationMatrix:
    """
    Defines an evaluation run across models, providers, and benchmarks.

    Supports two modes:
    - Cartesian: all combinations of models x providers x benchmarks
    - Explicit: only specified (model, provider, benchmark) tuples
    """

    models: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    benchmarks: list[str] = field(default_factory=list)
    mode: str = "cartesian"  # "cartesian" or "explicit"
    exclude: list[MatrixExclusion] = field(default_factory=list)
    tier: str = "smoke"
    explicit_runs: list[dict[str, str]] = field(default_factory=list)

    def get_runs(self) -> list[dict[str, str]]:
        """
        Generate the list of (model, provider, benchmark) runs.

        Returns:
            List of dicts with 'model', 'provider', 'benchmark' keys.
        """
        if self.mode == "explicit":
            return list(self.explicit_runs)

        # Cartesian product with exclusions
        runs = []
        for model in self.models:
            for provider in self.providers:
                for benchmark in self.benchmarks:
                    if self._is_excluded(model, provider, benchmark):
                        continue
                    runs.append({
                        "model": model,
                        "provider": provider,
                        "benchmark": benchmark,
                    })
        return runs

    def _is_excluded(self, model: str, provider: str, benchmark: str) -> bool:
        """Check if a combination is excluded."""
        for exc in self.exclude:
            match = True
            if exc.model and exc.model != model:
                match = False
            if exc.provider and exc.provider != provider:
                match = False
            if exc.benchmark and exc.benchmark != benchmark:
                match = False
            if match:
                return True
        return False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationMatrix:
        """Create an EvaluationMatrix from a dictionary (e.g., parsed YAML)."""
        eval_data = data.get("evaluation", data)

        excludes = []
        for exc_data in eval_data.get("exclude", []):
            excludes.append(MatrixExclusion(
                model=exc_data.get("model", ""),
                provider=exc_data.get("provider", ""),
                benchmark=exc_data.get("benchmark", ""),
            ))

        matrix_config = eval_data.get("matrix", {})

        return cls(
            models=eval_data.get("models", []),
            providers=eval_data.get("providers", []),
            benchmarks=eval_data.get("benchmarks", []),
            mode=matrix_config.get("mode", "cartesian"),
            exclude=excludes,
            tier=eval_data.get("tier", "smoke"),
            explicit_runs=eval_data.get("runs", []),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> EvaluationMatrix:
        """Load an EvaluationMatrix from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        result: dict[str, Any] = {
            "models": self.models,
            "providers": self.providers,
            "benchmarks": self.benchmarks,
            "tier": self.tier,
            "matrix": {"mode": self.mode},
        }
        if self.exclude:
            result["exclude"] = [
                {k: v for k, v in {"model": e.model, "provider": e.provider, "benchmark": e.benchmark}.items() if v}
                for e in self.exclude
            ]
        if self.explicit_runs:
            result["runs"] = self.explicit_runs
        return {"evaluation": result}
