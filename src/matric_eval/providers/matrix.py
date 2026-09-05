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

from matric_eval.models import LineageRole, ModelSpec


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

    models: list[str | ModelSpec] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    benchmarks: list[str] = field(default_factory=list)
    mode: str = "cartesian"  # "cartesian" or "explicit"
    exclude: list[MatrixExclusion] = field(default_factory=list)
    tier: str = "smoke"
    explicit_runs: list[dict[str, str]] = field(default_factory=list)
    schema_version: str = "1"

    def get_runs(self) -> list[dict[str, Any]]:
        """
        Generate the list of (model, provider, benchmark) runs.

        Returns:
            List of dicts with 'model', 'provider', 'benchmark' keys.
        """
        if self.schema_version == "2":
            self._validate_qualified_cohorts()
            if self.mode == "explicit":
                return self._qualified_explicit_runs()
        elif self.mode == "explicit":
            return list(self.explicit_runs)

        # Cartesian product with exclusions
        runs = []
        for model_entry in self.models:
            model = model_entry.model if isinstance(model_entry, ModelSpec) else model_entry
            model_key = model_entry.id if isinstance(model_entry, ModelSpec) else model
            model_providers = (
                [model_entry.provider]
                if isinstance(model_entry, ModelSpec)
                else self.providers
            )
            for provider in model_providers:
                for benchmark in self.benchmarks:
                    if self._is_excluded(model_key, provider, benchmark):
                        continue
                    run: dict[str, Any] = {
                        "model": model,
                        "provider": provider,
                        "benchmark": benchmark,
                    }
                    if isinstance(model_entry, ModelSpec):
                        run["model_id"] = model_entry.id
                        run["model_spec"] = model_entry.to_dict()
                    runs.append(run)
        return runs

    def _qualified_explicit_runs(self) -> list[dict[str, Any]]:
        specs = {
            model.id: model for model in self.models if isinstance(model, ModelSpec)
        }
        runs: list[dict[str, Any]] = []
        for requested in self.explicit_runs:
            model_id = requested.get("model_id", requested.get("model", ""))
            if model_id not in specs:
                raise ValueError(f"explicit run references unknown qualified model id: {model_id}")
            model = specs[model_id]
            provider = requested.get("provider", model.provider)
            if provider != model.provider:
                raise ValueError(
                    f"explicit run provider '{provider}' does not match model '{model_id}' "
                    f"provider '{model.provider}'"
                )
            run: dict[str, Any] = {
                "model": model.model,
                "model_id": model.id,
                "model_spec": model.to_dict(),
                "provider": provider,
            }
            if requested.get("benchmark"):
                run["benchmark"] = requested["benchmark"]
            runs.append(run)
        return runs

    def _validate_qualified_cohorts(self) -> None:
        if any(not isinstance(model, ModelSpec) for model in self.models):
            raise ValueError("matrix schema_version 2 requires qualified model objects")
        specs = [model for model in self.models if isinstance(model, ModelSpec)]
        ids = [model.id for model in specs]
        if len(ids) != len(set(ids)):
            raise ValueError("qualified model ids must be unique")

        by_group: dict[str, list[ModelSpec]] = {}
        for model in specs:
            by_group.setdefault(model.comparison_group, []).append(model)
        for group, members in by_group.items():
            if any(member.lineage_role is LineageRole.INTERVENTION for member in members):
                controls = {
                    LineageRole.OFFICIAL_INSTRUCT,
                    LineageRole.UNTOUCHED_CONTROL,
                }
                if not any(member.lineage_role in controls for member in members):
                    raise ValueError(
                        f"comparison group '{group}' has an intervention but no untouched control"
                    )
                identities = {member.checkpoint_identity for member in members}
                for member in members:
                    for intervention in member.interventions:
                        if (intervention.parent_source, intervention.parent_revision) not in identities:
                            raise ValueError(
                                f"intervention model '{member.id}' has no parent checkpoint peer "
                                f"in comparison group '{group}'"
                            )
            identities = {member.checkpoint_identity for member in members if not member.quantization}
            for member in members:
                if member.quantization is None:
                    continue
                source_identity = (
                    member.quantization.source_checkpoint,
                    member.quantization.source_revision,
                )
                if source_identity not in identities:
                    raise ValueError(
                        f"quantized model '{member.id}' has no unquantized source peer in "
                        f"comparison group '{group}'"
                    )

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
            excludes.append(
                MatrixExclusion(
                    model=exc_data.get("model", ""),
                    provider=exc_data.get("provider", ""),
                    benchmark=exc_data.get("benchmark", ""),
                )
            )

        matrix_config = eval_data.get("matrix", {})

        raw_models = eval_data.get("models", [])
        schema_version = str(eval_data.get("schema_version", "1"))
        if schema_version not in {"1", "2"}:
            raise ValueError(f"Unsupported evaluation matrix schema_version: {schema_version}")
        if schema_version == "2":
            if not all(isinstance(model, dict) for model in raw_models):
                raise ValueError("matrix schema_version 2 requires qualified model objects")
            models: list[str | ModelSpec] = [ModelSpec.from_dict(model) for model in raw_models]
        else:
            if not all(isinstance(model, str) for model in raw_models):
                raise ValueError("legacy matrix models must be strings; use schema_version 2")
            models = raw_models

        matrix = cls(
            models=models,
            providers=eval_data.get("providers", []),
            benchmarks=eval_data.get("benchmarks", []),
            mode=matrix_config.get("mode", "cartesian"),
            exclude=excludes,
            tier=eval_data.get("tier", "smoke"),
            explicit_runs=eval_data.get("runs", []),
            schema_version=schema_version,
        )
        if schema_version == "2":
            matrix._validate_qualified_cohorts()
        return matrix

    @classmethod
    def from_yaml(cls, path: str | Path) -> EvaluationMatrix:
        """Load an EvaluationMatrix from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        result: dict[str, Any] = {
            "models": [
                model.to_dict() if isinstance(model, ModelSpec) else model for model in self.models
            ],
            "providers": self.providers,
            "benchmarks": self.benchmarks,
            "tier": self.tier,
            "matrix": {"mode": self.mode},
        }
        if self.schema_version != "1":
            result["schema_version"] = self.schema_version
        if self.exclude:
            result["exclude"] = [
                {
                    k: v
                    for k, v in {
                        "model": e.model,
                        "provider": e.provider,
                        "benchmark": e.benchmark,
                    }.items()
                    if v
                }
                for e in self.exclude
            ]
        if self.explicit_runs:
            result["runs"] = self.explicit_runs
        return {"evaluation": result}
