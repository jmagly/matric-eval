"""
Model recommendation engine for matric-eval.

Generates model configuration recommendations based on evaluation results,
mapping capabilities to the best-performing models.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class Capability:
    """Represents a capability category."""

    name: str
    description: str
    benchmarks: list[str]
    weight: float = 1.0

    def compute_score(self, benchmark_scores: dict[str, float]) -> float:
        """Compute capability score from benchmark scores."""
        relevant_scores = [
            benchmark_scores.get(b, 0.0) for b in self.benchmarks if b in benchmark_scores
        ]
        if not relevant_scores:
            return 0.0
        return sum(relevant_scores) / len(relevant_scores)


# Default capability definitions
DEFAULT_CAPABILITIES = {
    "code_generation": Capability(
        name="code_generation",
        description="Ability to generate correct, executable code",
        benchmarks=["humaneval", "mbpp", "livecodebench", "ds1000"],
        weight=1.5,
    ),
    "math_reasoning": Capability(
        name="math_reasoning",
        description="Mathematical problem solving and reasoning",
        benchmarks=["gsm8k"],
        weight=1.2,
    ),
    "instruction_following": Capability(
        name="instruction_following",
        description="Ability to follow complex instructions precisely",
        benchmarks=["ifeval"],
        weight=1.0,
    ),
    "reasoning": Capability(
        name="reasoning",
        description="General reasoning and knowledge",
        benchmarks=["arc"],
        weight=1.0,
    ),
    "conversation": Capability(
        name="conversation",
        description="Multi-turn conversation quality",
        benchmarks=["mtbench"],
        weight=0.8,
    ),
    "tool_use": Capability(
        name="tool_use",
        description="Ability to use tools and function calling",
        benchmarks=["tool_calling"],
        weight=1.3,
    ),
}


@dataclass
class ModelScore:
    """Scores for a single model."""

    model: str
    benchmark_scores: dict[str, float] = field(default_factory=dict)
    capability_scores: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    size_gb: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Recommendation:
    """A model recommendation for a capability."""

    capability: str
    recommended_model: str
    score: float
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    rationale: str = ""


@dataclass
class RecommendationReport:
    """Complete recommendation report."""

    recommendations: dict[str, Recommendation] = field(default_factory=dict)
    model_scores: dict[str, ModelScore] = field(default_factory=dict)
    best_overall: str = ""
    best_balanced: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "recommendations": {
                cap: {
                    "capability": rec.capability,
                    "recommended": rec.recommended_model,
                    "score": rec.score,
                    "alternatives": [
                        {"model": m, "score": s} for m, s in rec.alternatives
                    ],
                    "rationale": rec.rationale,
                }
                for cap, rec in self.recommendations.items()
            },
            "model_scores": {
                model: {
                    "model": score.model,
                    "benchmark_scores": score.benchmark_scores,
                    "capability_scores": score.capability_scores,
                    "overall_score": score.overall_score,
                    "size_gb": score.size_gb,
                }
                for model, score in self.model_scores.items()
            },
            "best_overall": self.best_overall,
            "best_balanced": self.best_balanced,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_model_categories(self) -> dict[str, Any]:
        """
        Generate model-categories.json format.

        This format is compatible with matric-cli's model configuration.
        """
        categories = {}
        for cap_name, rec in self.recommendations.items():
            categories[cap_name] = {
                "description": DEFAULT_CAPABILITIES.get(
                    cap_name, Capability(cap_name, cap_name, [])
                ).description,
                "recommended": rec.recommended_model,
                "alternatives": [m for m, _ in rec.alternatives[:2]],
                "score": rec.score,
            }
        return {
            "version": "1.0",
            "generated_by": "matric-eval",
            "best_overall": self.best_overall,
            "categories": categories,
        }


class RecommendationEngine:
    """
    Generates model recommendations based on evaluation results.

    Analyzes benchmark scores across models and produces recommendations
    for which model to use for different capabilities.
    """

    def __init__(
        self,
        capabilities: dict[str, Capability] | None = None,
        min_score_threshold: float = 0.3,
        top_n_alternatives: int = 3,
    ) -> None:
        """
        Initialize recommendation engine.

        Args:
            capabilities: Capability definitions (uses defaults if not provided)
            min_score_threshold: Minimum score to recommend a model
            top_n_alternatives: Number of alternative models to include
        """
        self.capabilities = capabilities or DEFAULT_CAPABILITIES
        self.min_score_threshold = min_score_threshold
        self.top_n_alternatives = top_n_alternatives

    def process_results(
        self,
        results: list[dict[str, Any]],
    ) -> dict[str, ModelScore]:
        """
        Process evaluation results into model scores.

        Args:
            results: List of evaluation result dictionaries

        Returns:
            Dictionary mapping model names to ModelScore objects
        """
        model_scores: dict[str, ModelScore] = {}

        for result in results:
            model = result.get("model", "").replace("ollama/", "")
            if not model:
                continue

            if result.get("status") != "success":
                continue

            # Extract benchmark scores
            benchmark_scores: dict[str, float] = {}
            benchmarks = result.get("benchmarks", {})
            for bench_name, bench_data in benchmarks.items():
                if isinstance(bench_data, dict):
                    score = bench_data.get("score", bench_data.get("accuracy", 0.0))
                    benchmark_scores[bench_name] = float(score)

            # Use overall score if available
            overall = result.get("overall_score", 0.0)

            # Compute capability scores
            capability_scores: dict[str, float] = {}
            for cap_name, cap in self.capabilities.items():
                capability_scores[cap_name] = cap.compute_score(benchmark_scores)

            model_scores[model] = ModelScore(
                model=model,
                benchmark_scores=benchmark_scores,
                capability_scores=capability_scores,
                overall_score=float(overall),
                size_gb=result.get("size_gb", 0.0),
                metadata={"tier": result.get("tier")},
            )

        return model_scores

    def generate_recommendations(
        self,
        model_scores: dict[str, ModelScore],
    ) -> RecommendationReport:
        """
        Generate recommendations from model scores.

        Args:
            model_scores: Dictionary of model scores

        Returns:
            RecommendationReport with recommendations for each capability
        """
        if not model_scores:
            return RecommendationReport()

        recommendations: dict[str, Recommendation] = {}

        # Generate recommendation for each capability
        for cap_name, cap in self.capabilities.items():
            # Sort models by capability score
            scored_models = [
                (model, score.capability_scores.get(cap_name, 0.0))
                for model, score in model_scores.items()
            ]
            scored_models.sort(key=lambda x: x[1], reverse=True)

            if not scored_models:
                continue

            best_model, best_score = scored_models[0]

            # Only recommend if above threshold
            if best_score < self.min_score_threshold:
                recommendations[cap_name] = Recommendation(
                    capability=cap_name,
                    recommended_model="",
                    score=best_score,
                    alternatives=[],
                    rationale=f"No model scored above threshold ({self.min_score_threshold})",
                )
                continue

            # Get alternatives
            alternatives = scored_models[1 : self.top_n_alternatives + 1]

            recommendations[cap_name] = Recommendation(
                capability=cap_name,
                recommended_model=best_model,
                score=best_score,
                alternatives=alternatives,
                rationale=f"Best performing model for {cap.description}",
            )

        # Find best overall model
        overall_scores = [
            (model, score.overall_score) for model, score in model_scores.items()
        ]
        overall_scores.sort(key=lambda x: x[1], reverse=True)
        best_overall = overall_scores[0][0] if overall_scores else ""

        # Find best balanced model (good across all capabilities)
        balanced_scores: list[tuple[str, float]] = []
        for model, score in model_scores.items():
            cap_scores = list(score.capability_scores.values())
            if cap_scores:
                # Balance score = harmonic mean of capability scores
                non_zero = [s for s in cap_scores if s > 0]
                if non_zero:
                    harmonic_mean = len(non_zero) / sum(1 / s for s in non_zero)
                    balanced_scores.append((model, harmonic_mean))

        balanced_scores.sort(key=lambda x: x[1], reverse=True)
        best_balanced = balanced_scores[0][0] if balanced_scores else best_overall

        return RecommendationReport(
            recommendations=recommendations,
            model_scores=model_scores,
            best_overall=best_overall,
            best_balanced=best_balanced,
            metadata={"num_models": len(model_scores)},
        )

    def from_summary_file(self, path: Path | str) -> RecommendationReport:
        """
        Generate recommendations from a summary.json file.

        Args:
            path: Path to summary.json file

        Returns:
            RecommendationReport
        """
        path = Path(path)
        with path.open() as f:
            summary = json.load(f)

        results = summary.get("results", [])
        model_scores = self.process_results(results)
        return self.generate_recommendations(model_scores)

    def from_results_directory(self, path: Path | str) -> RecommendationReport:
        """
        Generate recommendations from a results directory.

        Reads all JSON files in the directory.

        Args:
            path: Path to results directory

        Returns:
            RecommendationReport
        """
        path = Path(path)
        results = []

        for json_file in path.glob("*.json"):
            if json_file.name == "summary.json":
                continue
            try:
                with json_file.open() as f:
                    result = json.load(f)
                    results.append(result)
            except (json.JSONDecodeError, OSError):
                continue

        model_scores = self.process_results(results)
        return self.generate_recommendations(model_scores)


def generate_recommendations(
    results: list[dict[str, Any]],
    capabilities: dict[str, Capability] | None = None,
    min_score_threshold: float = 0.3,
) -> RecommendationReport:
    """
    Convenience function to generate recommendations.

    Args:
        results: List of evaluation result dictionaries
        capabilities: Optional custom capability definitions
        min_score_threshold: Minimum score to recommend a model

    Returns:
        RecommendationReport
    """
    engine = RecommendationEngine(
        capabilities=capabilities,
        min_score_threshold=min_score_threshold,
    )
    model_scores = engine.process_results(results)
    return engine.generate_recommendations(model_scores)
