"""
Tests for CLI module (matric_eval.cli).

Covers:
- Click command structure
- Tier-based evaluation execution
- Model listing and benchmark discovery
- Rich progress reporting
- JSON output formatting
"""

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from click.testing import CliRunner

from matric_eval.cli import (
    cli,
    filter_models,
    get_available_benchmarks,
    get_ollama_models,
)


# =============================================================================
# Model Discovery Tests
# =============================================================================


@pytest.mark.unit
class TestGetOllamaModels:
    """Tests for get_ollama_models() function."""

    def test_parse_models_success(
        self,
        mock_ollama_list_output: str,
        mock_ollama_models: list[dict[str, Any]],
    ) -> None:
        """Should parse ollama list output and filter by size."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_ollama_list_output
            mock_run.return_value.returncode = 0

            models = get_ollama_models(max_size_gb=15.0)

            # Should exclude nomic-embed (274 MB), snowflake-embed (669 MB), and llama3.2:70b (40 GB)
            assert len(models) == 4
            assert models == mock_ollama_models

    def test_parse_models_with_lower_threshold(
        self,
        mock_ollama_list_output: str,
    ) -> None:
        """Should filter models above lower size threshold."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_ollama_list_output
            mock_run.return_value.returncode = 0

            models = get_ollama_models(max_size_gb=3.0)

            # Only llama3.2:3b (2.0 GB) should remain
            assert len(models) == 1
            assert models[0]["name"] == "llama3.2:3b"

    def test_ollama_not_found(self) -> None:
        """Should return empty list if ollama is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            models = get_ollama_models()
            assert models == []

    def test_ollama_error(self) -> None:
        """Should return empty list if ollama command fails."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ollama list"),
        ):
            models = get_ollama_models()
            assert models == []

    def test_empty_output(self) -> None:
        """Should handle empty ollama list output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "NAME    ID    SIZE    MODIFIED\n"
            mock_run.return_value.returncode = 0

            models = get_ollama_models()
            assert models == []

    def test_malformed_lines(self) -> None:
        """Should skip malformed lines in ollama output."""
        malformed_output = """NAME                    ID              SIZE      MODIFIED
llama3.2:3b            a80c4f17acd5    2.0 GB    2 weeks ago
invalid line
qwen2.5:7b             e9c23b5a5d51    4.7       1 week ago"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = malformed_output
            mock_run.return_value.returncode = 0

            models = get_ollama_models()

            # Should successfully parse llama3.2:3b, skip others
            assert len(models) >= 1
            assert any(m["name"] == "llama3.2:3b" for m in models)


@pytest.mark.unit
class TestFilterModels:
    """Tests for filter_models() function."""

    def test_filter_embedding_models(
        self,
        mock_ollama_models: list[dict[str, Any]],
    ) -> None:
        """Should filter out embedding models."""
        models_with_embeds = mock_ollama_models + [
            {"name": "nomic-embed-text", "size_gb": 0.27, "size_str": "274 MB"},
            {"name": "snowflake-arctic-embed", "size_gb": 0.67, "size_str": "669 MB"},
        ]

        filtered = filter_models(models_with_embeds)

        # Should remove embedding models
        assert len(filtered) == 4
        assert all("embed" not in m["name"].lower() for m in filtered)

    def test_filter_custom_patterns(self) -> None:
        """Should filter using custom exclusion patterns."""
        models = [
            {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"},
            {"name": "custom-test:latest", "size_gb": 1.0, "size_str": "1.0 GB"},
        ]

        filtered = filter_models(models, exclude_patterns=["custom"])

        assert len(filtered) == 1
        assert filtered[0]["name"] == "llama3.2:3b"

    def test_filter_empty_list(self) -> None:
        """Should handle empty model list."""
        filtered = filter_models([])
        assert filtered == []

    def test_filter_case_insensitive(self) -> None:
        """Should perform case-insensitive filtering."""
        models = [
            {"name": "NOMIC-EMBED-TEXT", "size_gb": 0.27, "size_str": "274 MB"},
            {"name": "Llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"},
        ]

        filtered = filter_models(models)

        assert len(filtered) == 1
        assert filtered[0]["name"] == "Llama3.2:3b"


# =============================================================================
# Benchmark Discovery Tests
# =============================================================================


@pytest.mark.unit
class TestGetAvailableBenchmarks:
    """Tests for get_available_benchmarks() function."""

    def test_returns_available_benchmarks(self) -> None:
        """Should return list of available benchmark names."""
        benchmarks = get_available_benchmarks()

        assert isinstance(benchmarks, list)
        assert len(benchmarks) > 0
        assert "humaneval" in benchmarks
        assert "mbpp" in benchmarks
        assert "gsm8k" in benchmarks

    def test_benchmarks_with_descriptions(self) -> None:
        """Should return benchmarks with descriptions."""
        benchmarks = get_available_benchmarks(with_descriptions=True)

        assert isinstance(benchmarks, dict)
        assert "humaneval" in benchmarks
        assert isinstance(benchmarks["humaneval"], str)
        assert len(benchmarks["humaneval"]) > 0


# =============================================================================
# CLI Command Tests - run
# =============================================================================


@pytest.mark.unit
class TestRunCommand:
    """Tests for 'matric-eval run' command."""

    def test_run_smoke_tier_single_model(
        self,
        tmp_results_dir: Path,
    ) -> None:
        """Should run smoke tier evaluation on single model."""
        runner = CliRunner()

        with (
            patch("matric_eval.cli.get_ollama_models") as mock_get_models,
            patch("matric_eval.cli.run_evaluation") as mock_run_eval,
        ):
            mock_get_models.return_value = [
                {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"}
            ]
            mock_run_eval.return_value = {
                "model": "ollama/llama3.2:3b",
                "tier": "smoke",
                "benchmarks": {
                    "humaneval": {"score": 0.6, "samples": 5, "status": "success"},
                    "mbpp": {"score": 0.8, "samples": 5, "status": "success"},
                    "gsm8k": {"score": 0.4, "samples": 5, "status": "success"},
                },
                "overall_score": 0.6,
                "status": "success",
            }

            result = runner.invoke(
                cli,
                ["run", "--tier", "smoke", "--model", "llama3.2:3b", "--output", str(tmp_results_dir)],
            )

            assert result.exit_code == 0
            assert "llama3.2:3b" in result.output
            mock_run_eval.assert_called_once()

    def test_run_quick_tier(
        self,
        tmp_results_dir: Path,
    ) -> None:
        """Should run quick tier evaluation."""
        runner = CliRunner()

        with (
            patch("matric_eval.cli.get_ollama_models") as mock_get_models,
            patch("matric_eval.cli.run_evaluation") as mock_run_eval,
        ):
            mock_get_models.return_value = [
                {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"}
            ]
            mock_run_eval.return_value = {
                "model": "ollama/llama3.2:3b",
                "tier": "quick",
                "status": "success",
                "overall_score": 0.5,
            }

            result = runner.invoke(
                cli,
                ["run", "--tier", "quick", "--model", "llama3.2:3b", "--output", str(tmp_results_dir)],
            )

            assert result.exit_code == 0
            # Verify tier was passed correctly
            call_args = mock_run_eval.call_args
            assert call_args[1]["tier"] == "quick"

    def test_run_full_tier(
        self,
        tmp_results_dir: Path,
    ) -> None:
        """Should run full tier evaluation."""
        runner = CliRunner()

        with (
            patch("matric_eval.cli.get_ollama_models") as mock_get_models,
            patch("matric_eval.cli.run_evaluation") as mock_run_eval,
        ):
            mock_get_models.return_value = [
                {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"}
            ]
            mock_run_eval.return_value = {
                "model": "ollama/llama3.2:3b",
                "tier": "full",
                "status": "success",
                "overall_score": 0.5,
            }

            result = runner.invoke(
                cli,
                ["run", "--tier", "full", "--model", "llama3.2:3b", "--output", str(tmp_results_dir)],
            )

            assert result.exit_code == 0
            call_args = mock_run_eval.call_args
            assert call_args[1]["tier"] == "full"

    def test_run_with_specific_benchmark(
        self,
        tmp_results_dir: Path,
    ) -> None:
        """Should run evaluation with specific benchmark only."""
        runner = CliRunner()

        with (
            patch("matric_eval.cli.get_ollama_models") as mock_get_models,
            patch("matric_eval.cli.run_evaluation") as mock_run_eval,
        ):
            mock_get_models.return_value = [
                {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"}
            ]
            mock_run_eval.return_value = {
                "model": "ollama/llama3.2:3b",
                "tier": "smoke",
                "benchmarks": {
                    "humaneval": {"score": 0.6, "samples": 5, "status": "success"},
                },
                "status": "success",
                "overall_score": 0.6,
            }

            result = runner.invoke(
                cli,
                [
                    "run",
                    "--tier", "smoke",
                    "--model", "llama3.2:3b",
                    "--benchmark", "humaneval",
                    "--output", str(tmp_results_dir),
                ],
            )

            assert result.exit_code == 0
            # Verify only humaneval was passed
            call_args = mock_run_eval.call_args
            assert call_args[1]["benchmarks"] == ["humaneval"]

    def test_run_with_json_output(
        self,
        tmp_results_dir: Path,
    ) -> None:
        """Should output results in JSON format when --output-format json is used."""
        runner = CliRunner()

        with (
            patch("matric_eval.cli.get_ollama_models") as mock_get_models,
            patch("matric_eval.cli.run_evaluation") as mock_run_eval,
        ):
            mock_get_models.return_value = [
                {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"}
            ]
            result_data = {
                "model": "ollama/llama3.2:3b",
                "tier": "smoke",
                "benchmarks": {
                    "humaneval": {"score": 0.6, "samples": 5, "status": "success"},
                },
                "overall_score": 0.6,
                "status": "success",
            }
            mock_run_eval.return_value = result_data

            result = runner.invoke(
                cli,
                [
                    "run",
                    "--tier", "smoke",
                    "--model", "llama3.2:3b",
                    "--output-format", "json",
                    "--output", str(tmp_results_dir),
                ],
            )

            assert result.exit_code == 0
            # Output should be valid JSON
            output_json = json.loads(result.output)
            # Model name should match (with or without ollama/ prefix)
            assert "llama3.2:3b" in output_json["model"]
            assert output_json["overall_score"] == 0.6

    def test_run_no_models_found_error(self) -> None:
        """Should exit with error if no models found."""
        runner = CliRunner()

        with patch("matric_eval.cli.get_ollama_models") as mock_get_models:
            mock_get_models.return_value = []

            result = runner.invoke(
                cli,
                ["run", "--tier", "smoke"],
            )

            assert result.exit_code != 0
            assert "No models found" in result.output

    def test_run_with_max_size_filter(
        self,
        tmp_results_dir: Path,
    ) -> None:
        """Should filter models by max-size parameter."""
        runner = CliRunner()

        with (
            patch("matric_eval.cli.get_ollama_models") as mock_get_models,
            patch("matric_eval.cli.run_evaluation") as mock_run_eval,
        ):
            mock_get_models.return_value = [
                {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"}
            ]
            mock_run_eval.return_value = {
                "model": "ollama/llama3.2:3b",
                "tier": "smoke",
                "status": "success",
                "overall_score": 0.5,
            }

            result = runner.invoke(
                cli,
                [
                    "run",
                    "--tier", "smoke",
                    "--max-size", "3.0",
                    "--output", str(tmp_results_dir),
                ],
            )

            assert result.exit_code == 0
            # Verify max_size was passed to get_ollama_models
            # Verify max_size was passed to get_ollama_models
            assert mock_get_models.call_count == 1
            assert mock_get_models.call_args[0][0] == 3.0 or mock_get_models.call_args[1].get("max_size_gb") == 3.0

# =============================================================================
# CLI Command Tests - list-models
# =============================================================================


@pytest.mark.unit
class TestListModelsCommand:
    """Tests for 'matric-eval list-models' command."""

    def test_list_models_success(
        self,
        mock_ollama_list_output: str,
    ) -> None:
        """Should list available models in table format."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_ollama_list_output
            mock_run.return_value.returncode = 0

            result = runner.invoke(cli, ["list-models"])

            assert result.exit_code == 0
            assert "llama3.2:3b" in result.output
            assert "2.0 GB" in result.output
            assert "qwen2.5:7b" in result.output
            # Should not show embedding models
            assert "nomic-embed" not in result.output

    def test_list_models_with_max_size_filter(
        self,
        mock_ollama_list_output: str,
    ) -> None:
        """Should filter models by --max-size parameter."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_ollama_list_output
            mock_run.return_value.returncode = 0

            result = runner.invoke(cli, ["list-models", "--max-size", "3.0"])

            assert result.exit_code == 0
            assert "llama3.2:3b" in result.output
            # Should not show larger models
            assert "qwen2.5:7b" not in result.output

    def test_list_models_json_output(
        self,
        mock_ollama_list_output: str,
    ) -> None:
        """Should output models in JSON format when requested."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_ollama_list_output
            mock_run.return_value.returncode = 0

            result = runner.invoke(cli, ["list-models", "--output-format", "json"])

            assert result.exit_code == 0
            # Output should be valid JSON
            models = json.loads(result.output)
            assert isinstance(models, list)
            assert len(models) > 0
            assert models[0]["name"] == "llama3.2:3b"

    def test_list_models_no_ollama(self) -> None:
        """Should show error if Ollama is not installed."""
        runner = CliRunner()

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = runner.invoke(cli, ["list-models"])

            assert result.exit_code != 0
            assert "Ollama not found" in result.output or "not installed" in result.output


# =============================================================================
# CLI Command Tests - list-benchmarks
# =============================================================================


@pytest.mark.unit
class TestListBenchmarksCommand:
    """Tests for 'matric-eval list-benchmarks' command."""

    def test_list_benchmarks_success(self) -> None:
        """Should list available benchmarks with descriptions."""
        runner = CliRunner()

        result = runner.invoke(cli, ["list-benchmarks"])

        assert result.exit_code == 0
        assert "humaneval" in result.output.lower()
        assert "mbpp" in result.output.lower()
        assert "gsm8k" in result.output.lower()

    def test_list_benchmarks_with_tier_info(self) -> None:
        """Should show sample counts for each tier."""
        runner = CliRunner()

        result = runner.invoke(cli, ["list-benchmarks", "--tier", "smoke"])

        assert result.exit_code == 0
        # Should show sample count for smoke tier
        assert "5" in result.output  # Smoke tier has 5 samples

    def test_list_benchmarks_json_output(self) -> None:
        """Should output benchmarks in JSON format when requested."""
        runner = CliRunner()

        result = runner.invoke(cli, ["list-benchmarks", "--output-format", "json"])

        assert result.exit_code == 0
        # Output should be valid JSON
        benchmarks = json.loads(result.output)
        assert isinstance(benchmarks, dict) or isinstance(benchmarks, list)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_invalid_tier(self) -> None:
        """Should reject invalid tier names."""
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["run", "--tier", "invalid", "--model", "llama3.2:3b"],
        )

        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid" in result.output.lower()

    def test_invalid_benchmark(
        self,
        tmp_results_dir: Path,
    ) -> None:
        """Should reject invalid benchmark names."""
        runner = CliRunner()

        with (
            patch("matric_eval.cli.get_ollama_models") as mock_get_models,
            patch("matric_eval.cli.run_evaluation") as mock_run_eval,
        ):
            mock_get_models.return_value = [
                {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"}
            ]
            mock_run_eval.side_effect = ValueError("Unknown benchmark: invalid_benchmark")

            result = runner.invoke(
                cli,
                [
                    "run",
                    "--tier", "smoke",
                    "--model", "llama3.2:3b",
                    "--benchmark", "invalid_benchmark",
                    "--output", str(tmp_results_dir),
                ],
            )

            assert result.exit_code != 0

    def test_model_not_found(self) -> None:
        """Should handle non-existent model by allowing user to specify it."""
        runner = CliRunner()

        # When --model is specified, we allow it even if not in Ollama list
        with patch("matric_eval.cli.run_evaluation") as mock_run_eval:
            # Simulate the model not being available (will fail during evaluation)
            mock_run_eval.side_effect = Exception("Model not found")

            result = runner.invoke(
                cli,
                ["run", "--tier", "smoke", "--model", "nonexistent:model"],
            )

            # Should exit with error after trying to evaluate
            assert result.exit_code != 0

    def test_evaluation_failure_handling(
        self,
        tmp_results_dir: Path,
    ) -> None:
        """Should handle evaluation failures gracefully."""
        runner = CliRunner()

        with (
            patch("matric_eval.cli.get_ollama_models") as mock_get_models,
            patch("matric_eval.cli.run_evaluation") as mock_run_eval,
        ):
            mock_get_models.return_value = [
                {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"}
            ]
            mock_run_eval.side_effect = Exception("Model timeout")

            result = runner.invoke(
                cli,
                ["run", "--tier", "smoke", "--model", "llama3.2:3b", "--output", str(tmp_results_dir)],
            )

            # Should handle error gracefully
            assert result.exit_code != 0
            assert "error" in result.output.lower() or "timeout" in result.output.lower()
