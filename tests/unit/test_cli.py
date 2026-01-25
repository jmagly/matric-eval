"""
Tests for CLI (matric_eval.cli).

Covers:
- Model discovery functions
- CLI helper functions
- Click commands
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
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
    """Tests for get_ollama_models function."""

    def test_no_ollama_installed(self) -> None:
        """Should return empty list when ollama not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ollama not found")
            models = get_ollama_models()
            assert models == []

    def test_ollama_error(self) -> None:
        """Should return empty list on ollama error."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "ollama")
            models = get_ollama_models()
            assert models == []

    def test_parse_ollama_output(self) -> None:
        """Should parse ollama list output."""
        mock_output = """NAME                  	ID          	SIZE  	MODIFIED
llama3.2:3b           	abc123      	2.0 GB	1 day ago
mistral:7b            	def456      	4.1 GB	2 days ago
nomic-embed-text      	ghi789      	274 MB	3 days ago"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            models = get_ollama_models(max_size_gb=15.0)

            # nomic-embed-text should be filtered out as embedding model
            model_names = [m["name"] for m in models]
            assert "nomic-embed-text" not in model_names

    def test_respects_size_limit(self) -> None:
        """Should filter models by size."""
        mock_output = """NAME                  	ID          	SIZE  	MODIFIED
small:1b              	abc123      	0.5 GB	1 day ago
large:70b             	def456      	40.0 GB	2 days ago"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            models = get_ollama_models(max_size_gb=5.0)

            model_names = [m["name"] for m in models]
            assert "small:1b" in model_names
            assert "large:70b" not in model_names


# =============================================================================
# Filter Models Tests
# =============================================================================


@pytest.mark.unit
class TestFilterModels:
    """Tests for filter_models function."""

    def test_filter_embedding_models(self) -> None:
        """Should filter out embedding models."""
        models = [
            {"name": "llama3.2:3b", "size_gb": 2.0},
            {"name": "nomic-embed-text", "size_gb": 0.3},
            {"name": "all-minilm", "size_gb": 0.1},
            {"name": "mistral:7b", "size_gb": 4.1},
        ]

        filtered = filter_models(models)
        names = [m["name"] for m in filtered]

        assert "llama3.2:3b" in names
        assert "mistral:7b" in names
        assert "nomic-embed-text" not in names
        assert "all-minilm" not in names

    def test_custom_exclude_patterns(self) -> None:
        """Should use custom exclude patterns."""
        models = [
            {"name": "llama3.2:3b", "size_gb": 2.0},
            {"name": "test-model", "size_gb": 1.0},
        ]

        filtered = filter_models(models, exclude_patterns=["test"])
        names = [m["name"] for m in filtered]

        assert "llama3.2:3b" in names
        assert "test-model" not in names

    def test_empty_list(self) -> None:
        """Should handle empty list."""
        assert filter_models([]) == []


# =============================================================================
# Get Available Benchmarks Tests
# =============================================================================


@pytest.mark.unit
class TestGetAvailableBenchmarks:
    """Tests for get_available_benchmarks function."""

    def test_returns_list(self) -> None:
        """Should return list of benchmark names."""
        benchmarks = get_available_benchmarks()
        assert isinstance(benchmarks, list)
        assert len(benchmarks) > 0

    def test_includes_known_benchmarks(self) -> None:
        """Should include known benchmarks."""
        benchmarks = get_available_benchmarks()
        # Check for expected benchmarks
        assert "humaneval" in benchmarks
        assert "mbpp" in benchmarks
        assert "gsm8k" in benchmarks

    def test_with_descriptions(self) -> None:
        """Should return dict with descriptions."""
        benchmarks = get_available_benchmarks(with_descriptions=True)
        assert isinstance(benchmarks, dict)
        assert "humaneval" in benchmarks
        assert isinstance(benchmarks["humaneval"], str)


# =============================================================================
# CLI Command Tests
# =============================================================================


@pytest.mark.unit
class TestCLICommands:
    """Tests for CLI commands using Click CliRunner."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI runner."""
        return CliRunner()

    def test_cli_help(self, runner: CliRunner) -> None:
        """Should show help message."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "matric-eval" in result.output.lower() or "evaluation" in result.output.lower()

    def test_run_help(self, runner: CliRunner) -> None:
        """Should show run command help."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--tier" in result.output or "--model" in result.output

    def test_list_models_command(self, runner: CliRunner) -> None:
        """Should have list-models command."""
        # The command may fail if ollama is not installed, which is OK for unit tests
        # Just verify the command exists and runs
        result = runner.invoke(cli, ["list-models", "--help"])
        assert result.exit_code == 0
        assert "--max-size" in result.output or "max" in result.output.lower()

    def test_list_benchmarks_command(self, runner: CliRunner) -> None:
        """Should list available benchmarks."""
        result = runner.invoke(cli, ["list-benchmarks"])
        assert result.exit_code == 0
        # Should contain benchmark names
        output_lower = result.output.lower()
        assert "humaneval" in output_lower or "benchmark" in output_lower

    def test_validate_command(self, runner: CliRunner) -> None:
        """Should have validate command."""
        result = runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
class TestCLIIntegration:
    """Integration tests for CLI."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI runner."""
        return CliRunner()

    def test_list_models_with_format(self, runner: CliRunner) -> None:
        """Should support different output formats."""
        # Test JSON format option exists
        result = runner.invoke(cli, ["list-models", "--help"])
        assert result.exit_code == 0
        # Verify format option exists
        assert "--format" in result.output or "format" in result.output.lower()

    def test_list_benchmarks_with_tier(self, runner: CliRunner) -> None:
        """Should filter benchmarks by tier."""
        result = runner.invoke(cli, ["list-benchmarks", "--tier", "smoke"])
        assert result.exit_code == 0
