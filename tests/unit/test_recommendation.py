"""
Tests for recommendation engine (matric_eval.recommendation).

Covers:
- Capability scoring
- ModelScore dataclass
- RecommendationEngine processing
- Recommendation generation
- Report serialization
"""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from matric_eval.recommendation import (
    Capability,
    ModelScore,
    Recommendation,
    RecommendationEngine,
    RecommendationReport,
    DEFAULT_CAPABILITIES,
    generate_recommendations,
)


# =============================================================================
# Capability Tests
# =============================================================================


@pytest.mark.unit
class TestCapability:
    """Tests for Capability dataclass."""

    def test_basic_creation(self) -> None:
        """Should create capability with required fields."""
        cap = Capability(
            name="test_cap",
            description="Test capability",
            benchmarks=["bench1", "bench2"],
        )
        assert cap.name == "test_cap"
        assert cap.description == "Test capability"
        assert cap.benchmarks == ["bench1", "bench2"]
        assert cap.weight == 1.0

    def test_custom_weight(self) -> None:
        """Should accept custom weight."""
        cap = Capability(
            name="weighted",
            description="Weighted capability",
            benchmarks=["b1"],
            weight=1.5,
        )
        assert cap.weight == 1.5

    def test_compute_score_single_benchmark(self) -> None:
        """Should compute score from single benchmark."""
        cap = Capability(
            name="single",
            description="Single benchmark",
            benchmarks=["humaneval"],
        )
        scores = {"humaneval": 0.8}
        assert cap.compute_score(scores) == 0.8

    def test_compute_score_multiple_benchmarks(self) -> None:
        """Should average scores from multiple benchmarks."""
        cap = Capability(
            name="multi",
            description="Multiple benchmarks",
            benchmarks=["humaneval", "mbpp"],
        )
        scores = {"humaneval": 0.8, "mbpp": 0.6}
        assert cap.compute_score(scores) == 0.7

    def test_compute_score_missing_benchmarks(self) -> None:
        """Should only use available benchmarks."""
        cap = Capability(
            name="partial",
            description="Partial benchmarks",
            benchmarks=["humaneval", "mbpp", "missing"],
        )
        scores = {"humaneval": 0.8, "mbpp": 0.6}
        assert cap.compute_score(scores) == 0.7

    def test_compute_score_no_matching_benchmarks(self) -> None:
        """Should return 0.0 when no benchmarks match."""
        cap = Capability(
            name="none",
            description="No matching benchmarks",
            benchmarks=["humaneval", "mbpp"],
        )
        scores = {"gsm8k": 0.9}
        assert cap.compute_score(scores) == 0.0


# =============================================================================
# Default Capabilities Tests
# =============================================================================


@pytest.mark.unit
class TestDefaultCapabilities:
    """Tests for default capability definitions."""

    def test_has_code_generation(self) -> None:
        """Should have code generation capability."""
        assert "code_generation" in DEFAULT_CAPABILITIES
        cap = DEFAULT_CAPABILITIES["code_generation"]
        assert "humaneval" in cap.benchmarks
        assert "mbpp" in cap.benchmarks

    def test_has_math_reasoning(self) -> None:
        """Should have math reasoning capability."""
        assert "math_reasoning" in DEFAULT_CAPABILITIES
        cap = DEFAULT_CAPABILITIES["math_reasoning"]
        assert "gsm8k" in cap.benchmarks

    def test_has_instruction_following(self) -> None:
        """Should have instruction following capability."""
        assert "instruction_following" in DEFAULT_CAPABILITIES
        cap = DEFAULT_CAPABILITIES["instruction_following"]
        assert "ifeval" in cap.benchmarks

    def test_has_tool_use(self) -> None:
        """Should have tool use capability."""
        assert "tool_use" in DEFAULT_CAPABILITIES
        cap = DEFAULT_CAPABILITIES["tool_use"]
        assert "tool_calling" in cap.benchmarks


# =============================================================================
# ModelScore Tests
# =============================================================================


@pytest.mark.unit
class TestModelScore:
    """Tests for ModelScore dataclass."""

    def test_basic_creation(self) -> None:
        """Should create model score with defaults."""
        score = ModelScore(model="llama3.2:3b")
        assert score.model == "llama3.2:3b"
        assert score.benchmark_scores == {}
        assert score.capability_scores == {}
        assert score.overall_score == 0.0

    def test_full_creation(self) -> None:
        """Should accept all fields."""
        score = ModelScore(
            model="llama3.2:3b",
            benchmark_scores={"humaneval": 0.8, "mbpp": 0.7},
            capability_scores={"code_generation": 0.75},
            overall_score=0.75,
            size_gb=2.0,
            metadata={"tier": "smoke"},
        )
        assert score.benchmark_scores["humaneval"] == 0.8
        assert score.capability_scores["code_generation"] == 0.75
        assert score.overall_score == 0.75
        assert score.size_gb == 2.0
        assert score.metadata["tier"] == "smoke"


# =============================================================================
# Recommendation Tests
# =============================================================================


@pytest.mark.unit
class TestRecommendation:
    """Tests for Recommendation dataclass."""

    def test_basic_creation(self) -> None:
        """Should create recommendation with required fields."""
        rec = Recommendation(
            capability="code_generation",
            recommended_model="llama3.2:3b",
            score=0.85,
        )
        assert rec.capability == "code_generation"
        assert rec.recommended_model == "llama3.2:3b"
        assert rec.score == 0.85
        assert rec.alternatives == []
        assert rec.rationale == ""

    def test_with_alternatives(self) -> None:
        """Should accept alternatives."""
        rec = Recommendation(
            capability="code_generation",
            recommended_model="llama3.2:3b",
            score=0.85,
            alternatives=[("mistral:7b", 0.80), ("codestral:22b", 0.78)],
            rationale="Best overall code generation model",
        )
        assert len(rec.alternatives) == 2
        assert rec.alternatives[0] == ("mistral:7b", 0.80)


# =============================================================================
# RecommendationReport Tests
# =============================================================================


@pytest.mark.unit
class TestRecommendationReport:
    """Tests for RecommendationReport dataclass."""

    def test_empty_report(self) -> None:
        """Should create empty report."""
        report = RecommendationReport()
        assert report.recommendations == {}
        assert report.model_scores == {}
        assert report.best_overall == ""
        assert report.best_balanced == ""

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        report = RecommendationReport(
            recommendations={
                "code_generation": Recommendation(
                    capability="code_generation",
                    recommended_model="llama3.2:3b",
                    score=0.85,
                )
            },
            best_overall="llama3.2:3b",
            best_balanced="llama3.2:3b",
        )
        d = report.to_dict()
        assert "recommendations" in d
        assert "code_generation" in d["recommendations"]
        assert d["best_overall"] == "llama3.2:3b"

    def test_to_json(self) -> None:
        """Should convert to valid JSON."""
        report = RecommendationReport(
            best_overall="llama3.2:3b",
            metadata={"num_models": 3},
        )
        json_str = report.to_json()
        parsed = json.loads(json_str)
        assert parsed["best_overall"] == "llama3.2:3b"
        assert parsed["metadata"]["num_models"] == 3

    def test_to_model_categories(self) -> None:
        """Should generate model-categories.json format."""
        report = RecommendationReport(
            recommendations={
                "code_generation": Recommendation(
                    capability="code_generation",
                    recommended_model="codestral:22b",
                    score=0.9,
                    alternatives=[("llama3.2:3b", 0.85)],
                )
            },
            best_overall="codestral:22b",
        )
        categories = report.to_model_categories()
        assert categories["version"] == "1.0"
        assert categories["generated_by"] == "matric-eval"
        assert categories["best_overall"] == "codestral:22b"
        assert "code_generation" in categories["categories"]
        assert categories["categories"]["code_generation"]["recommended"] == "codestral:22b"


# =============================================================================
# RecommendationEngine Tests
# =============================================================================


@pytest.mark.unit
class TestRecommendationEngine:
    """Tests for RecommendationEngine class."""

    @pytest.fixture
    def engine(self) -> RecommendationEngine:
        """Create engine with defaults."""
        return RecommendationEngine()

    @pytest.fixture
    def sample_results(self) -> list[dict]:
        """Create sample evaluation results."""
        return [
            {
                "model": "ollama/llama3.2:3b",
                "status": "success",
                "overall_score": 0.75,
                "benchmarks": {
                    "humaneval": {"score": 0.8},
                    "mbpp": {"score": 0.7},
                    "gsm8k": {"score": 0.65},
                },
            },
            {
                "model": "ollama/mistral:7b",
                "status": "success",
                "overall_score": 0.80,
                "benchmarks": {
                    "humaneval": {"score": 0.85},
                    "mbpp": {"score": 0.75},
                    "gsm8k": {"score": 0.7},
                },
            },
            {
                "model": "ollama/codestral:22b",
                "status": "success",
                "overall_score": 0.90,
                "benchmarks": {
                    "humaneval": {"score": 0.95},
                    "mbpp": {"score": 0.90},
                    "gsm8k": {"score": 0.5},
                },
            },
        ]

    def test_default_initialization(self, engine: RecommendationEngine) -> None:
        """Should initialize with defaults."""
        assert engine.capabilities == DEFAULT_CAPABILITIES
        assert engine.min_score_threshold == 0.3
        assert engine.top_n_alternatives == 3

    def test_custom_initialization(self) -> None:
        """Should accept custom parameters."""
        custom_caps = {
            "custom": Capability(
                name="custom",
                description="Custom capability",
                benchmarks=["bench1"],
            )
        }
        engine = RecommendationEngine(
            capabilities=custom_caps,
            min_score_threshold=0.5,
            top_n_alternatives=2,
        )
        assert engine.capabilities == custom_caps
        assert engine.min_score_threshold == 0.5
        assert engine.top_n_alternatives == 2

    def test_process_results(
        self, engine: RecommendationEngine, sample_results: list[dict]
    ) -> None:
        """Should process results into model scores."""
        model_scores = engine.process_results(sample_results)
        assert len(model_scores) == 3
        assert "llama3.2:3b" in model_scores
        assert "mistral:7b" in model_scores
        assert "codestral:22b" in model_scores

        # Check benchmark scores extracted
        llama_scores = model_scores["llama3.2:3b"]
        assert llama_scores.benchmark_scores["humaneval"] == 0.8
        assert llama_scores.overall_score == 0.75

    def test_process_results_skips_failed(self, engine: RecommendationEngine) -> None:
        """Should skip failed results."""
        results = [
            {"model": "good", "status": "success", "overall_score": 0.8, "benchmarks": {}},
            {"model": "bad", "status": "error", "overall_score": 0.0, "benchmarks": {}},
        ]
        model_scores = engine.process_results(results)
        assert "good" in model_scores
        assert "bad" not in model_scores

    def test_process_results_strips_ollama_prefix(
        self, engine: RecommendationEngine
    ) -> None:
        """Should strip ollama/ prefix from model names."""
        results = [
            {
                "model": "ollama/llama3.2:3b",
                "status": "success",
                "overall_score": 0.8,
                "benchmarks": {},
            }
        ]
        model_scores = engine.process_results(results)
        assert "llama3.2:3b" in model_scores
        assert "ollama/llama3.2:3b" not in model_scores

    def test_generate_recommendations(
        self, engine: RecommendationEngine, sample_results: list[dict]
    ) -> None:
        """Should generate recommendations from model scores."""
        model_scores = engine.process_results(sample_results)
        report = engine.generate_recommendations(model_scores)

        assert isinstance(report, RecommendationReport)
        assert len(report.model_scores) == 3
        assert report.best_overall == "codestral:22b"  # Highest overall score

    def test_recommendations_by_capability(
        self, engine: RecommendationEngine, sample_results: list[dict]
    ) -> None:
        """Should recommend best model for each capability."""
        model_scores = engine.process_results(sample_results)
        report = engine.generate_recommendations(model_scores)

        # Code generation should recommend codestral (best at humaneval/mbpp)
        code_rec = report.recommendations.get("code_generation")
        assert code_rec is not None
        assert code_rec.recommended_model == "codestral:22b"

    def test_recommendations_include_alternatives(
        self, engine: RecommendationEngine, sample_results: list[dict]
    ) -> None:
        """Should include alternative models."""
        model_scores = engine.process_results(sample_results)
        report = engine.generate_recommendations(model_scores)

        code_rec = report.recommendations.get("code_generation")
        assert code_rec is not None
        assert len(code_rec.alternatives) > 0
        # Alternatives should be sorted by score
        alt_scores = [s for _, s in code_rec.alternatives]
        assert alt_scores == sorted(alt_scores, reverse=True)

    def test_empty_results(self, engine: RecommendationEngine) -> None:
        """Should handle empty results."""
        model_scores = engine.process_results([])
        report = engine.generate_recommendations(model_scores)
        assert report.recommendations == {}
        assert report.best_overall == ""


# =============================================================================
# File Loading Tests
# =============================================================================


@pytest.mark.unit
class TestRecommendationFileLoading:
    """Tests for loading recommendations from files."""

    def test_from_summary_file(self) -> None:
        """Should load recommendations from summary.json."""
        engine = RecommendationEngine()

        with TemporaryDirectory() as tmpdir:
            summary = {
                "results": [
                    {
                        "model": "llama3.2:3b",
                        "status": "success",
                        "overall_score": 0.75,
                        "benchmarks": {"humaneval": {"score": 0.8}},
                    }
                ]
            }
            summary_path = Path(tmpdir) / "summary.json"
            summary_path.write_text(json.dumps(summary))

            report = engine.from_summary_file(summary_path)
            assert "llama3.2:3b" in report.model_scores

    def test_from_results_directory(self) -> None:
        """Should load recommendations from results directory."""
        engine = RecommendationEngine()

        with TemporaryDirectory() as tmpdir:
            # Create individual result files
            result1 = {
                "model": "llama3.2:3b",
                "status": "success",
                "overall_score": 0.75,
                "benchmarks": {"humaneval": {"score": 0.8}},
            }
            result2 = {
                "model": "mistral:7b",
                "status": "success",
                "overall_score": 0.80,
                "benchmarks": {"humaneval": {"score": 0.85}},
            }

            (Path(tmpdir) / "llama3.2_3b.json").write_text(json.dumps(result1))
            (Path(tmpdir) / "mistral_7b.json").write_text(json.dumps(result2))

            report = engine.from_results_directory(tmpdir)
            assert len(report.model_scores) == 2


# =============================================================================
# Convenience Function Tests
# =============================================================================


@pytest.mark.unit
class TestGenerateRecommendations:
    """Tests for generate_recommendations convenience function."""

    def test_basic_usage(self) -> None:
        """Should generate recommendations from results."""
        results = [
            {
                "model": "llama3.2:3b",
                "status": "success",
                "overall_score": 0.75,
                "benchmarks": {"humaneval": {"score": 0.8}},
            }
        ]
        report = generate_recommendations(results)
        assert isinstance(report, RecommendationReport)
        assert "llama3.2:3b" in report.model_scores

    def test_custom_threshold(self) -> None:
        """Should respect custom threshold."""
        results = [
            {
                "model": "low_scorer",
                "status": "success",
                "overall_score": 0.2,
                "benchmarks": {"humaneval": {"score": 0.2}},
            }
        ]
        # High threshold should result in no recommendations
        report = generate_recommendations(results, min_score_threshold=0.5)
        for rec in report.recommendations.values():
            assert rec.recommended_model == "" or rec.score >= 0.5


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
class TestRecommendationIntegration:
    """Integration tests for recommendation engine."""

    def test_full_workflow(self) -> None:
        """Should handle full recommendation workflow."""
        # Create sample results
        results = [
            {
                "model": "ollama/llama3.2:3b",
                "status": "success",
                "overall_score": 0.75,
                "benchmarks": {
                    "humaneval": {"score": 0.7},
                    "mbpp": {"score": 0.65},
                    "gsm8k": {"score": 0.8},
                    "ifeval": {"score": 0.6},
                },
            },
            {
                "model": "ollama/codestral:22b",
                "status": "success",
                "overall_score": 0.85,
                "benchmarks": {
                    "humaneval": {"score": 0.9},
                    "mbpp": {"score": 0.85},
                    "gsm8k": {"score": 0.5},
                    "ifeval": {"score": 0.4},
                },
            },
        ]

        engine = RecommendationEngine()
        model_scores = engine.process_results(results)
        report = engine.generate_recommendations(model_scores)

        # Verify report structure
        assert report.best_overall == "codestral:22b"
        assert len(report.model_scores) == 2

        # Verify serialization
        json_output = report.to_json()
        parsed = json.loads(json_output)
        assert "recommendations" in parsed
        assert "model_scores" in parsed

        # Verify model-categories format
        categories = report.to_model_categories()
        assert categories["version"] == "1.0"
        assert "categories" in categories

    def test_model_with_best_balance(self) -> None:
        """Should identify model with best balance across capabilities."""
        results = [
            {
                "model": "specialist",
                "status": "success",
                "overall_score": 0.9,
                "benchmarks": {
                    "humaneval": {"score": 0.95},
                    "mbpp": {"score": 0.95},
                    "gsm8k": {"score": 0.1},
                    "ifeval": {"score": 0.1},
                },
            },
            {
                "model": "generalist",
                "status": "success",
                "overall_score": 0.7,
                "benchmarks": {
                    "humaneval": {"score": 0.7},
                    "mbpp": {"score": 0.7},
                    "gsm8k": {"score": 0.7},
                    "ifeval": {"score": 0.7},
                },
            },
        ]

        report = generate_recommendations(results)

        # Specialist should be best overall (higher average)
        # Generalist should be best balanced (more consistent)
        assert report.best_overall == "specialist"
        assert report.best_balanced == "generalist"
