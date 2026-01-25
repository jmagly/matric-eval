"""
Test data factories for matric-eval tests.

Provides factory functions to generate test data dynamically,
following the Factory pattern for test data generation.
"""

from typing import Any

from inspect_ai.dataset import Sample


# =============================================================================
# Sample Factories
# =============================================================================


class SampleFactory:
    """Factory for creating test Sample objects."""

    @staticmethod
    def create_humaneval_sample(
        problem_id: int = 0,
        difficulty: str = "easy",
        **overrides: Any,
    ) -> Sample:
        """
        Create a HumanEval-style sample.

        Args:
            problem_id: Problem identifier
            difficulty: Difficulty level (easy, medium, hard)
            **overrides: Override default fields

        Returns:
            Sample object for testing
        """
        defaults = {
            "input": f"""Write a Python function `test_function_{problem_id}(x: int) -> int`.

Example:
>>> test_function_{problem_id}(5)
10

Return only the function code.""",
            "target": f"""def test_function_{problem_id}(x: int) -> int:
    return x * 2""",
            "id": f"humaneval_test_{problem_id}",
            "metadata": {
                "difficulty": difficulty,
                "category": "code",
            },
        }

        return Sample(**{**defaults, **overrides})

    @staticmethod
    def create_mbpp_sample(
        problem_id: int = 0,
        function_name: str = "test_func",
        **overrides: Any,
    ) -> Sample:
        """
        Create an MBPP-style sample.

        Args:
            problem_id: Problem identifier
            function_name: Name of function to implement
            **overrides: Override default fields

        Returns:
            Sample object for testing
        """
        defaults = {
            "input": f"""Write a Python function `{function_name}(x)`.

Test cases:
assert {function_name}(1) == 2
assert {function_name}(5) == 10

Return only the function code.""",
            "target": f"""def {function_name}(x):
    return x * 2""",
            "id": f"mbpp_test_{problem_id}",
            "metadata": {
                "difficulty": "easy",
                "category": "code",
                "function_name": function_name,
            },
        }

        return Sample(**{**defaults, **overrides})

    @staticmethod
    def create_gsm8k_sample(
        problem_id: int = 0,
        answer: str = "42",
        **overrides: Any,
    ) -> Sample:
        """
        Create a GSM8K-style sample.

        Args:
            problem_id: Problem identifier
            answer: Numeric answer as string
            **overrides: Override default fields

        Returns:
            Sample object for testing
        """
        defaults = {
            "input": f"""Math problem {problem_id}: If x = 21, what is 2x?

Think step by step, then provide the final numeric answer.""",
            "target": answer,
            "id": f"gsm8k_test_{problem_id}",
            "metadata": {
                "difficulty": "easy",
                "category": "math",
            },
        }

        return Sample(**{**defaults, **overrides})

    @staticmethod
    def create_batch(
        count: int,
        factory_type: str = "humaneval",
        **kwargs: Any,
    ) -> list[Sample]:
        """
        Create a batch of samples.

        Args:
            count: Number of samples to create
            factory_type: Type of samples (humaneval, mbpp, gsm8k)
            **kwargs: Additional arguments to factory

        Returns:
            List of Sample objects
        """
        factory_map = {
            "humaneval": SampleFactory.create_humaneval_sample,
            "mbpp": SampleFactory.create_mbpp_sample,
            "gsm8k": SampleFactory.create_gsm8k_sample,
        }

        factory = factory_map.get(factory_type, SampleFactory.create_humaneval_sample)

        return [factory(problem_id=i, **kwargs) for i in range(count)]


# =============================================================================
# Model Result Factories
# =============================================================================


class ResultFactory:
    """Factory for creating test result structures."""

    @staticmethod
    def create_benchmark_result(
        benchmark: str = "humaneval",
        score: float = 0.8,
        samples: int = 5,
        status: str = "success",
        **overrides: Any,
    ) -> dict[str, Any]:
        """
        Create a benchmark result dictionary.

        Args:
            benchmark: Benchmark name
            score: Score value (0.0 to 1.0)
            samples: Number of samples evaluated
            status: Result status
            **overrides: Override fields

        Returns:
            Benchmark result dictionary
        """
        defaults = {
            "score": score,
            "samples": samples,
            "status": status,
        }

        if status == "error":
            defaults["error"] = overrides.pop("error", "Test error")

        return {**defaults, **overrides}

    @staticmethod
    def create_model_result(
        model: str = "test-model:latest",
        benchmarks: dict[str, dict[str, Any]] | None = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        """
        Create a complete model evaluation result.

        Args:
            model: Model name
            benchmarks: Benchmark results dict
            **overrides: Override fields

        Returns:
            Complete model result dictionary
        """
        if benchmarks is None:
            benchmarks = {
                "humaneval": ResultFactory.create_benchmark_result("humaneval", 0.6),
                "mbpp": ResultFactory.create_benchmark_result("mbpp", 0.7),
                "gsm8k": ResultFactory.create_benchmark_result("gsm8k", 0.5),
            }

        scores = [
            b.get("score", 0)
            for b in benchmarks.values()
            if b.get("status") == "success"
        ]
        overall_score = sum(scores) / len(scores) if scores else 0

        defaults = {
            "model": model,
            "timestamp": "2024-01-20T12:00:00",
            "benchmarks": benchmarks,
            "overall_score": overall_score,
            "status": "success",
        }

        return {**defaults, **overrides}

    @staticmethod
    def create_summary(
        results: list[dict[str, Any]] | None = None,
        tier: str = "smoke",
        **overrides: Any,
    ) -> dict[str, Any]:
        """
        Create an evaluation summary.

        Args:
            results: List of model results
            tier: Evaluation tier
            **overrides: Override fields

        Returns:
            Summary dictionary
        """
        if results is None:
            results = [
                ResultFactory.create_model_result("model1:latest"),
                ResultFactory.create_model_result("model2:latest"),
            ]

        defaults = {
            "timestamp": "2024-01-20T12:00:00",
            "tier": tier,
            "models_evaluated": len(results),
            "results": results,
        }

        return {**defaults, **overrides}


# =============================================================================
# Ollama Mock Data Factories
# =============================================================================


class OllamaFactory:
    """Factory for creating Ollama-related test data."""

    @staticmethod
    def create_model_info(
        name: str = "test-model:latest",
        size_gb: float = 2.0,
        **overrides: Any,
    ) -> dict[str, Any]:
        """
        Create model info dictionary.

        Args:
            name: Model name
            size_gb: Size in GB
            **overrides: Override fields

        Returns:
            Model info dictionary
        """
        defaults = {
            "name": name,
            "size_gb": size_gb,
            "size_str": f"{size_gb} GB",
        }

        return {**defaults, **overrides}

    @staticmethod
    def create_model_list(count: int = 3) -> list[dict[str, Any]]:
        """
        Create a list of model info dictionaries.

        Args:
            count: Number of models to create

        Returns:
            List of model info dictionaries
        """
        sizes = [2.0, 4.5, 7.0, 13.0, 34.0, 70.0]
        models = []

        for i in range(count):
            size = sizes[i % len(sizes)]
            models.append(
                OllamaFactory.create_model_info(
                    name=f"model{i+1}:latest",
                    size_gb=size,
                )
            )

        return models

    @staticmethod
    def create_ollama_list_output(models: list[dict[str, Any]]) -> str:
        """
        Create mock 'ollama list' output.

        Args:
            models: List of model info dictionaries

        Returns:
            Formatted ollama list output string
        """
        lines = ["NAME                    ID              SIZE      MODIFIED"]

        for model in models:
            # Simplified formatting
            lines.append(
                f"{model['name']:<24} {'a'*12} {model['size_str']:<10} 1 week ago"
            )

        return "\n".join(lines)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_test_dataset(count: int = 10, sample_type: str = "humaneval") -> list[Sample]:
    """
    Convenience function to create test dataset.

    Args:
        count: Number of samples
        sample_type: Type of samples

    Returns:
        List of Sample objects
    """
    return SampleFactory.create_batch(count, sample_type)
