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
        benchmarks=["arc", "gpqa"],
        weight=1.0,
    ),
    "knowledge": Capability(
        name="knowledge",
        description="Broad domain knowledge across many subjects",
        benchmarks=["mmlu", "gpqa"],
        weight=0.9,
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
class ModelConstraints:
    """Constraints for filtering model recommendations."""

    max_size_gb: Optional[float] = None
    min_score: Optional[float] = None
    required_benchmarks: Optional[list[str]] = None
    prefer: str = "quality"  # "quality", "speed", "balanced", "cost_efficiency"


@dataclass
class Recommendation:
    """A model recommendation for a capability."""

    capability: str
    recommended_model: str
    score: float
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    rationale: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    confidence: float = 1.0


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
                    "strengths": rec.strengths,
                    "weaknesses": rec.weaknesses,
                    "confidence": rec.confidence,
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

            best_model_score = model_scores[best_model]
            strengths, weaknesses = self._compute_strengths_weaknesses(
                best_model_score, model_scores
            )
            confidence = self._compute_confidence(best_model_score)

            recommendations[cap_name] = Recommendation(
                capability=cap_name,
                recommended_model=best_model,
                score=best_score,
                alternatives=alternatives,
                rationale=f"Best performing model for {cap.description}",
                strengths=strengths,
                weaknesses=weaknesses,
                confidence=confidence,
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

    def filter_by_constraints(
        self,
        model_scores: dict[str, ModelScore],
        constraints: ModelConstraints,
    ) -> dict[str, ModelScore]:
        """
        Filter models by constraints.

        Args:
            model_scores: All model scores
            constraints: Filtering constraints

        Returns:
            Filtered model scores meeting all constraints
        """
        filtered = {}
        for model, score in model_scores.items():
            # Size constraint
            if constraints.max_size_gb is not None and score.size_gb > constraints.max_size_gb:
                continue

            # Minimum score constraint
            if constraints.min_score is not None and score.overall_score < constraints.min_score:
                continue

            # Required benchmarks constraint
            if constraints.required_benchmarks:
                has_all = all(
                    b in score.benchmark_scores for b in constraints.required_benchmarks
                )
                if not has_all:
                    continue

            filtered[model] = score

        return filtered

    def pareto_frontier(
        self,
        model_scores: dict[str, ModelScore],
        dimensions: list[str],
    ) -> list[str]:
        """
        Find Pareto-optimal models across the given dimensions.

        A model is Pareto-optimal if no other model is strictly better
        in all dimensions simultaneously.

        Args:
            model_scores: Model scores to analyze
            dimensions: Benchmark or capability names to use as dimensions

        Returns:
            List of Pareto-optimal model names
        """
        models = list(model_scores.keys())
        if not models:
            return []

        def get_dim_score(model: str, dim: str) -> float:
            score = model_scores[model]
            if dim in score.benchmark_scores:
                return score.benchmark_scores[dim]
            if dim in score.capability_scores:
                return score.capability_scores[dim]
            if dim == "size" and score.size_gb > 0:
                # Smaller is better for size — invert
                return 1.0 / score.size_gb
            return 0.0

        pareto = []
        for i, model in enumerate(models):
            dominated = False
            for j, other in enumerate(models):
                if i == j:
                    continue
                # Check if 'other' dominates 'model'
                all_ge = True
                any_gt = False
                for dim in dimensions:
                    s_model = get_dim_score(model, dim)
                    s_other = get_dim_score(other, dim)
                    if s_other < s_model:
                        all_ge = False
                        break
                    if s_other > s_model:
                        any_gt = True
                if all_ge and any_gt:
                    dominated = True
                    break
            if not dominated:
                pareto.append(model)

        return pareto

    def _compute_strengths_weaknesses(
        self,
        score: ModelScore,
        all_scores: dict[str, ModelScore],
    ) -> tuple[list[str], list[str]]:
        """
        Compute strengths and weaknesses relative to all models.

        Args:
            score: The model's scores
            all_scores: All model scores for comparison

        Returns:
            Tuple of (strengths, weaknesses) lists
        """
        if len(all_scores) < 2:
            return [], []

        strengths = []
        weaknesses = []

        for cap_name, cap_score in score.capability_scores.items():
            # Get average across all models for this capability
            all_cap_scores = [
                s.capability_scores.get(cap_name, 0.0) for s in all_scores.values()
            ]
            avg = sum(all_cap_scores) / len(all_cap_scores) if all_cap_scores else 0.0

            cap = self.capabilities.get(cap_name)
            label = cap.description if cap else cap_name

            if cap_score > avg * 1.2:  # 20% above average
                strengths.append(f"Strong at {label} ({cap_score:.1%})")
            elif cap_score < avg * 0.8 and cap_score > 0:  # 20% below average
                weaknesses.append(f"Below average at {label} ({cap_score:.1%})")

        return strengths, weaknesses

    def _compute_confidence(
        self,
        score: ModelScore,
    ) -> float:
        """
        Compute confidence in a recommendation based on evaluation coverage.

        Confidence is higher when more benchmarks have been evaluated.

        Args:
            score: The model's scores

        Returns:
            Confidence score between 0.0 and 1.0
        """
        total_benchmarks = sum(
            len(cap.benchmarks) for cap in self.capabilities.values()
        )
        if total_benchmarks == 0:
            return 0.0

        evaluated = len(score.benchmark_scores)
        return min(1.0, evaluated / max(1, total_benchmarks * 0.5))

    def recommend(
        self,
        results: list[dict[str, Any]],
        constraints: Optional[ModelConstraints] = None,
    ) -> RecommendationReport:
        """
        Generate recommendations with optional constraint filtering.

        Convenience method combining process_results, filter, and recommend.

        Args:
            results: List of evaluation result dictionaries
            constraints: Optional model constraints

        Returns:
            RecommendationReport
        """
        model_scores = self.process_results(results)
        if constraints:
            model_scores = self.filter_by_constraints(model_scores, constraints)
        return self.generate_recommendations(model_scores)

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
