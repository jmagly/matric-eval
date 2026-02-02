"""
Tests for thinking model detection and dual-mode evaluation.

Covers:
- Model thinking capability detection
- CLI --thinking parameter
- Engine support for thinking mode toggle
- Results directory structure for thinking modes
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from click.testing import CliRunner

from matric_eval.models.detection import has_thinking_capability, get_ollama_model_info
from matric_eval.cli import cli


# =============================================================================
# Model Detection Tests
# =============================================================================


@pytest.mark.unit
class TestModelDetection:
    """Tests for thinking capability detection."""

    def test_has_thinking_capability_qwen3(self) -> None:
        """Qwen3 models should be detected as thinking-capable."""
        mock_info = {
            "modelfile": "FROM qwen3:14b",
            "parameters": {},
            "capabilities": ["thinking", "chat"],
        }

        with patch("matric_eval.models.detection.get_ollama_model_info") as mock_get:
            mock_get.return_value = mock_info
            assert has_thinking_capability("qwen3:14b") is True

    def test_has_thinking_capability_standard_model(self) -> None:
        """Standard models without thinking should return False."""
        mock_info = {
            "modelfile": "FROM llama3.2:3b",
            "parameters": {},
            "capabilities": ["chat"],
        }

        with patch("matric_eval.models.detection.get_ollama_model_info") as mock_get:
            mock_get.return_value = mock_info
            assert has_thinking_capability("llama3.2:3b") is False

    def test_has_thinking_capability_no_capabilities_field(self) -> None:
        """Models without capabilities field should return False."""
        mock_info = {
            "modelfile": "FROM mistral:7b",
            "parameters": {},
        }

        with patch("matric_eval.models.detection.get_ollama_model_info") as mock_get:
            mock_get.return_value = mock_info
            assert has_thinking_capability("mistral:7b") is False

    def test_has_thinking_capability_empty_capabilities(self) -> None:
        """Models with empty capabilities should return False."""
        mock_info = {
            "modelfile": "FROM codellama:7b",
            "parameters": {},
            "capabilities": [],
        }

        with patch("matric_eval.models.detection.get_ollama_model_info") as mock_get:
            mock_get.return_value = mock_info
            assert has_thinking_capability("codellama:7b") is False

    def test_get_ollama_model_info_success(self) -> None:
        """Should successfully retrieve model info from ollama show."""
        mock_output = json.dumps({
            "modelfile": "FROM qwen3:14b",
            "parameters": {"temperature": 0.8},
            "capabilities": ["thinking", "chat"],
        })

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                stdout=mock_output,
                returncode=0,
                stderr="",
            )
            info = get_ollama_model_info("qwen3:14b")

            assert info["capabilities"] == ["thinking", "chat"]
            mock_run.assert_called_once()

    def test_get_ollama_model_info_model_not_found(self) -> None:
        """Should raise ValueError when model not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                stdout="",
                returncode=1,
                stderr="Error: model 'nonexistent' not found",
            )

            with pytest.raises(ValueError, match="Model.*not found"):
                get_ollama_model_info("nonexistent:model")

    def test_get_ollama_model_info_invalid_json(self) -> None:
        """Should raise ValueError when ollama returns invalid JSON."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                stdout="not valid json",
                returncode=0,
                stderr="",
            )

            with pytest.raises(ValueError, match="Invalid JSON"):
                get_ollama_model_info("somemodel:tag")


# =============================================================================
# CLI --thinking Parameter Tests
# =============================================================================


@pytest.mark.unit
class TestThinkingCLIParameter:
    """Tests for --thinking CLI parameter."""

    def test_thinking_parameter_default(self) -> None:
        """Default should be 'auto'."""
        runner = CliRunner()

        with patch("matric_eval.cli.run_evaluation") as mock_eval:
            mock_eval.return_value = {
                "model": "ollama/llama3.2:3b",
                "status": "success",
                "overall_score": 0.8,
            }

            result = runner.invoke(cli, [
                "run",
                "--tier", "smoke",
                "--model", "llama3.2:3b",
                "--output-format", "json",
            ])

            # Should succeed with auto mode
            assert result.exit_code == 0

    def test_thinking_parameter_on(self) -> None:
        """Should accept --thinking on."""
        runner = CliRunner()

        with patch("matric_eval.cli.run_evaluation") as mock_eval:
            mock_eval.return_value = {
                "model": "ollama/qwen3:14b",
                "status": "success",
                "overall_score": 0.8,
            }

            result = runner.invoke(cli, [
                "run",
                "--tier", "smoke",
                "--model", "qwen3:14b",
                "--thinking", "on",
                "--output-format", "json",
            ])

            assert result.exit_code == 0
            # Verify thinking=on was passed to run_evaluation
            call_args = mock_eval.call_args
            assert call_args is not None
            assert call_args.kwargs.get("thinking_mode") == "on"

    def test_thinking_parameter_off(self) -> None:
        """Should accept --thinking off."""
        runner = CliRunner()

        with patch("matric_eval.cli.run_evaluation") as mock_eval:
            mock_eval.return_value = {
                "model": "ollama/qwen3:14b",
                "status": "success",
                "overall_score": 0.8,
            }

            result = runner.invoke(cli, [
                "run",
                "--tier", "smoke",
                "--model", "qwen3:14b",
                "--thinking", "off",
                "--output-format", "json",
            ])

            assert result.exit_code == 0
            call_args = mock_eval.call_args
            assert call_args is not None
            assert call_args.kwargs.get("thinking_mode") == "off"

    def test_thinking_parameter_both(self) -> None:
        """Should accept --thinking both and run twice."""
        runner = CliRunner()

        with patch("matric_eval.cli.run_evaluation") as mock_eval, \
             patch("matric_eval.cli.has_thinking_capability") as mock_detect:

            mock_detect.return_value = True  # qwen3 is thinking-capable
            mock_eval.return_value = {
                "model": "ollama/qwen3:14b",
                "status": "success",
                "overall_score": 0.8,
            }

            result = runner.invoke(cli, [
                "run",
                "--tier", "smoke",
                "--model", "qwen3:14b",
                "--thinking", "both",
                "--output-format", "json",
            ])

            assert result.exit_code == 0
            # Should call run_evaluation twice (once with on, once with off)
            assert mock_eval.call_count == 2

    def test_thinking_parameter_auto_thinking_model(self) -> None:
        """Auto mode should detect thinking and run appropriate mode."""
        runner = CliRunner()

        with patch("matric_eval.cli.run_evaluation") as mock_eval, \
             patch("matric_eval.cli.has_thinking_capability") as mock_detect:

            mock_detect.return_value = True  # qwen3 is thinking-capable
            mock_eval.return_value = {
                "model": "ollama/qwen3:14b",
                "status": "success",
                "overall_score": 0.8,
            }

            result = runner.invoke(cli, [
                "run",
                "--tier", "smoke",
                "--model", "qwen3:14b",
                "--thinking", "auto",
                "--output-format", "json",
            ])

            assert result.exit_code == 0
            # Auto should run thinking-off mode for thinking models by default
            call_args = mock_eval.call_args
            assert call_args is not None
            assert call_args.kwargs.get("thinking_mode") == "off"

    def test_thinking_parameter_auto_standard_model(self) -> None:
        """Auto mode should use standard mode for non-thinking models."""
        runner = CliRunner()

        with patch("matric_eval.cli.run_evaluation") as mock_eval, \
             patch("matric_eval.cli.has_thinking_capability") as mock_detect:

            mock_detect.return_value = False  # llama3.2 is not thinking-capable
            mock_eval.return_value = {
                "model": "ollama/llama3.2:3b",
                "status": "success",
                "overall_score": 0.8,
            }

            result = runner.invoke(cli, [
                "run",
                "--tier", "smoke",
                "--model", "llama3.2:3b",
                "--thinking", "auto",
                "--output-format", "json",
            ])

            assert result.exit_code == 0
            call_args = mock_eval.call_args
            assert call_args is not None
            # For standard models, thinking_mode should be None (not applicable)
            assert call_args.kwargs.get("thinking_mode") is None

    def test_thinking_parameter_invalid(self) -> None:
        """Should reject invalid --thinking values."""
        runner = CliRunner()

        result = runner.invoke(cli, [
            "run",
            "--tier", "smoke",
            "--model", "llama3.2:3b",
            "--thinking", "invalid",
        ])

        # Click should reject the invalid choice
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid choice" in result.output.lower()


# =============================================================================
# Engine Thinking Mode Tests
# =============================================================================


@pytest.mark.unit
class TestEngineThinkingMode:
    """Tests for EvaluationEngine thinking mode support."""

    def test_engine_with_thinking_on(self, tmp_results_dir: Path) -> None:
        """Engine should configure generation for thinking mode on."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="on",
        )

        assert engine.thinking_mode == "on"
        assert engine.model == "ollama/qwen3:14b"

    def test_engine_with_thinking_off(self, tmp_results_dir: Path) -> None:
        """Engine should configure generation for thinking mode off."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="off",
        )

        assert engine.thinking_mode == "off"

    def test_engine_default_no_thinking_mode(self, tmp_results_dir: Path) -> None:
        """Engine should default to None for thinking_mode."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/llama3.2:3b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
        )

        assert engine.thinking_mode is None

    def test_engine_thinking_mode_in_eval_kwargs(self, tmp_results_dir: Path) -> None:
        """Engine should pass thinking mode to eval via generate_config."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="off",
        )

        # Get eval kwargs
        eval_kwargs = engine._get_eval_kwargs()

        assert "generate_config" in eval_kwargs
        gen_config = eval_kwargs["generate_config"]
        # Check that thinking is disabled in extra_body
        assert hasattr(gen_config, "extra_body")
        assert gen_config.extra_body.get("enable_thinking") is False


# =============================================================================
# Results Directory Structure Tests
# =============================================================================


@pytest.mark.unit
class TestResultsDirectoryStructure:
    """Tests for thinking mode results directory structure."""

    def test_results_dir_thinking_on(self, tmp_results_dir: Path) -> None:
        """Results for thinking-on should go in thinking-on subdirectory."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="on",
        )

        # Get the model-specific log directory
        model_log_dir = engine._get_model_log_dir()

        # Should include thinking-on in path
        assert "thinking-on" in str(model_log_dir)

    def test_results_dir_thinking_off(self, tmp_results_dir: Path) -> None:
        """Results for thinking-off should go in thinking-off subdirectory."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="off",
        )

        model_log_dir = engine._get_model_log_dir()
        assert "thinking-off" in str(model_log_dir)

    def test_results_dir_no_thinking_mode(self, tmp_results_dir: Path) -> None:
        """Standard models should not have thinking subdirectory."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/llama3.2:3b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode=None,
        )

        model_log_dir = engine._get_model_log_dir()
        # Should not include thinking-on or thinking-off
        assert "thinking-on" not in str(model_log_dir)
        assert "thinking-off" not in str(model_log_dir)

    def test_results_structure_both_modes(self, tmp_results_dir: Path) -> None:
        """Both modes should create separate directories."""
        from matric_eval.core.engine import EvaluationEngine

        # Simulate running both modes
        engine_on = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="on",
        )

        engine_off = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="off",
        )

        dir_on = engine_on._get_model_log_dir()
        dir_off = engine_off._get_model_log_dir()

        # Should be different directories
        assert dir_on != dir_off
        assert "thinking-on" in str(dir_on)
        assert "thinking-off" in str(dir_off)


# =============================================================================
# Integration Tests (marked for later execution)
# =============================================================================


@pytest.mark.integration
class TestThinkingModeIntegration:
    """Integration tests for thinking mode (requires Ollama)."""

    @pytest.mark.skipif(True, reason="Requires Ollama with thinking model installed")
    def test_run_qwen3_with_thinking_off(self, tmp_results_dir: Path) -> None:
        """Should successfully run Qwen3 with thinking disabled."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="off",
        )

        result = engine.run_benchmark("humaneval")

        assert result["status"] == "success"
        assert result["score"] >= 0.0
        assert result["samples"] > 0

    @pytest.mark.skipif(True, reason="Requires Ollama with thinking model installed")
    def test_run_qwen3_with_thinking_on(self, tmp_results_dir: Path) -> None:
        """Should successfully run Qwen3 with thinking enabled."""
        from matric_eval.core.engine import EvaluationEngine

        engine = EvaluationEngine(
            model="ollama/qwen3:14b",
            tier="smoke",
            log_dir=tmp_results_dir / "logs",
            thinking_mode="on",
        )

        result = engine.run_benchmark("humaneval")

        assert result["status"] == "success"
        assert result["score"] >= 0.0
        assert result["samples"] > 0
