"""
Tests for the provider abstraction layer.

Tests cover:
- Provider protocol compliance
- Provider registry
- Each provider implementation (Ollama, llama.cpp, vLLM, OpenRouter, Chutes)
- Evaluation matrix
- CLI integration
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from matric_eval.providers.base import (
    ModelInfo,
    Provider,
    ProviderConfig,
    ProviderConnectionError,
    ProviderError,
    ProviderModelNotFoundError,
)
from matric_eval.providers.registry import (
    ProviderRegistry,
    get_provider,
    list_providers,
    register_provider,
)
from matric_eval.providers.ollama import OllamaProvider
from matric_eval.providers.llamacpp import LlamaCppProvider
from matric_eval.providers.vllm import VLLMProvider
from matric_eval.providers.openrouter import OpenRouterProvider
from matric_eval.providers.chutes import ChutesProvider
from matric_eval.providers.matrix import EvaluationMatrix, MatrixExclusion


# =============================================================================
# ModelInfo Tests
# =============================================================================


class TestModelInfo:
    def test_basic_creation(self):
        info = ModelInfo(name="llama3.2:3b", size_gb=2.0)
        assert info.name == "llama3.2:3b"
        assert info.size_gb == 2.0
        assert info.capabilities == []
        assert info.metadata == {}

    def test_capabilities(self):
        info = ModelInfo(name="qwen3:14b", capabilities=["thinking", "tool_calling"])
        assert info.has_capability("thinking")
        assert info.has_capability("tool_calling")
        assert not info.has_capability("vision")

    def test_metadata(self):
        info = ModelInfo(name="test", metadata={"context_length": 8192})
        assert info.metadata["context_length"] == 8192


# =============================================================================
# ProviderConfig Tests
# =============================================================================


class TestProviderConfig:
    def test_defaults(self):
        config = ProviderConfig()
        assert config.base_url == ""
        assert config.api_key == ""
        assert config.timeout == 120
        assert config.max_retries == 3
        assert config.extra == {}

    def test_custom_config(self):
        config = ProviderConfig(
            base_url="http://localhost:8080",
            api_key="test-key",
            timeout=60,
            extra={"temperature": 0.7},
        )
        assert config.base_url == "http://localhost:8080"
        assert config.api_key == "test-key"
        assert config.extra["temperature"] == 0.7


# =============================================================================
# Exception Tests
# =============================================================================


class TestExceptions:
    def test_provider_error_hierarchy(self):
        assert issubclass(ProviderConnectionError, ProviderError)
        assert issubclass(ProviderModelNotFoundError, ProviderError)

    def test_exception_messages(self):
        with pytest.raises(ProviderConnectionError, match="unreachable"):
            raise ProviderConnectionError("Server unreachable")

        with pytest.raises(ProviderModelNotFoundError, match="not found"):
            raise ProviderModelNotFoundError("Model not found")


# =============================================================================
# Provider Protocol Tests
# =============================================================================


class TestProviderProtocol:
    """Test that all providers satisfy the Provider protocol."""

    @pytest.mark.parametrize("provider_cls", [
        OllamaProvider,
        LlamaCppProvider,
        VLLMProvider,
        OpenRouterProvider,
        ChutesProvider,
    ])
    def test_is_provider(self, provider_cls):
        provider = provider_cls()
        assert isinstance(provider, Provider)

    @pytest.mark.parametrize("provider_cls,expected_name", [
        (OllamaProvider, "ollama"),
        (LlamaCppProvider, "llama-cpp"),
        (VLLMProvider, "vllm"),
        (OpenRouterProvider, "openrouter"),
        (ChutesProvider, "chutes"),
    ])
    def test_provider_names(self, provider_cls, expected_name):
        provider = provider_cls()
        assert provider.name == expected_name

    @pytest.mark.parametrize("provider_cls,expected_display", [
        (OllamaProvider, "Ollama"),
        (LlamaCppProvider, "llama.cpp"),
        (VLLMProvider, "vLLM"),
        (OpenRouterProvider, "OpenRouter"),
        (ChutesProvider, "Chutes"),
    ])
    def test_provider_display_names(self, provider_cls, expected_display):
        provider = provider_cls()
        assert provider.display_name == expected_display


# =============================================================================
# OllamaProvider Tests
# =============================================================================


class TestOllamaProvider:
    def test_default_config(self):
        provider = OllamaProvider()
        assert provider.name == "ollama"
        assert provider._config.base_url == "http://localhost:11434"

    def test_custom_config(self):
        config = ProviderConfig(base_url="http://remote:11434")
        provider = OllamaProvider(config)
        assert provider._config.base_url == "http://remote:11434"

    def test_format_model_id(self):
        provider = OllamaProvider()
        assert provider.format_model_id("llama3.2:3b") == "ollama/llama3.2:3b"
        assert provider.format_model_id("ollama/llama3.2:3b") == "ollama/llama3.2:3b"

    @patch("matric_eval.providers.ollama.subprocess.run")
    def test_is_available_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        provider = OllamaProvider()
        assert provider.is_available()

    @patch("matric_eval.providers.ollama.subprocess.run")
    def test_is_available_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        provider = OllamaProvider()
        assert not provider.is_available()

    @patch("matric_eval.providers.ollama.subprocess.run")
    def test_list_models(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout="""NAME                    ID              SIZE      MODIFIED
llama3.2:3b            a80c4f17acd5    2.0 GB    2 weeks ago
qwen2.5:7b             e9c23b5a5d51    4.7 GB    3 days ago
nomic-embed-text       5c3f3d2e1f23    274 MB    1 month ago""",
        )
        provider = OllamaProvider()
        models = provider.list_models()
        assert len(models) == 2  # Excludes embedding model
        assert models[0].name == "llama3.2:3b"
        assert models[0].size_gb == 2.0
        assert models[1].name == "qwen2.5:7b"

    @patch("matric_eval.providers.ollama.subprocess.run")
    def test_list_models_with_size_filter(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout="""NAME                    ID              SIZE      MODIFIED
llama3.2:3b            a80c4f17acd5    2.0 GB    2 weeks ago
qwen2.5:7b             e9c23b5a5d51    4.7 GB    3 days ago""",
        )
        provider = OllamaProvider()
        models = provider.list_models(max_size_gb=3.0)
        assert len(models) == 1
        assert models[0].name == "llama3.2:3b"

    @patch("matric_eval.providers.ollama.subprocess.run")
    def test_list_models_connection_error(self, mock_run):
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, "ollama list")
        provider = OllamaProvider()
        with pytest.raises(ProviderConnectionError):
            provider.list_models()

    @patch("matric_eval.providers.ollama.subprocess.run")
    def test_get_model_info(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({"capabilities": ["thinking"]}),
        )
        provider = OllamaProvider()
        info = provider.get_model_info("qwen3:14b")
        assert info.name == "qwen3:14b"
        assert info.has_capability("thinking")

    @patch("matric_eval.providers.ollama.subprocess.run")
    def test_get_model_info_not_found(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stderr="model not found")
        provider = OllamaProvider()
        with pytest.raises(ProviderModelNotFoundError):
            provider.get_model_info("nonexistent")

    def test_get_eval_kwargs_default(self):
        provider = OllamaProvider()
        kwargs = provider.get_eval_kwargs("llama3.2:3b")
        assert kwargs == {}

    def test_get_eval_kwargs_custom_url(self):
        config = ProviderConfig(base_url="http://remote:11434")
        provider = OllamaProvider(config)
        kwargs = provider.get_eval_kwargs("llama3.2:3b")
        assert kwargs["model_base_url"] == "http://remote:11434"


# =============================================================================
# LlamaCppProvider Tests
# =============================================================================


class TestLlamaCppProvider:
    def test_default_config(self):
        provider = LlamaCppProvider()
        assert provider.name == "llama-cpp"
        assert provider._config.base_url == "http://localhost:8080"

    def test_format_model_id(self):
        provider = LlamaCppProvider()
        assert provider.format_model_id("my-model") == "openai/my-model"
        assert provider.format_model_id("openai/my-model") == "openai/my-model"

    @patch("matric_eval.providers.llamacpp.urllib.request.urlopen")
    def test_is_available_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_resp.read.return_value = json.dumps({"status": "ok"}).encode()
        mock_urlopen.return_value = mock_resp

        provider = LlamaCppProvider()
        assert provider.is_available()

    @patch("matric_eval.providers.llamacpp.urllib.request.urlopen")
    def test_is_available_down(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        provider = LlamaCppProvider()
        assert not provider.is_available()

    @patch("matric_eval.providers.llamacpp.urllib.request.urlopen")
    def test_list_models(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_resp.read.return_value = json.dumps({
            "data": [{"id": "my-gguf-model"}]
        }).encode()
        mock_urlopen.return_value = mock_resp

        provider = LlamaCppProvider()
        models = provider.list_models()
        assert len(models) == 1
        assert models[0].name == "my-gguf-model"

    def test_get_eval_kwargs(self):
        provider = LlamaCppProvider()
        kwargs = provider.get_eval_kwargs("test-model")
        assert kwargs["model_base_url"] == "http://localhost:8080/v1"
        assert kwargs["model_args"]["api_key"] == "not-needed"

    def test_get_eval_kwargs_with_extra_params(self):
        config = ProviderConfig(extra={"temperature": 0.5, "top_k": 40})
        provider = LlamaCppProvider(config)
        kwargs = provider.get_eval_kwargs("test-model")
        assert kwargs["extra_body"]["temperature"] == 0.5
        assert kwargs["extra_body"]["top_k"] == 40


# =============================================================================
# VLLMProvider Tests
# =============================================================================


class TestVLLMProvider:
    def test_default_config(self):
        provider = VLLMProvider()
        assert provider.name == "vllm"
        assert provider._config.base_url == "http://localhost:8000"

    def test_format_model_id(self):
        provider = VLLMProvider()
        assert provider.format_model_id("meta-llama/Llama-3.2-3B") == "openai/meta-llama/Llama-3.2-3B"

    @patch("matric_eval.providers.vllm.urllib.request.urlopen")
    def test_is_available_health(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        provider = VLLMProvider()
        assert provider.is_available()

    @patch("matric_eval.providers.vllm.urllib.request.urlopen")
    def test_list_models(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_resp.read.return_value = json.dumps({
            "data": [
                {"id": "meta-llama/Llama-3.2-3B"},
                {"id": "mistralai/Mistral-7B"},
            ]
        }).encode()
        mock_urlopen.return_value = mock_resp

        provider = VLLMProvider()
        models = provider.list_models()
        assert len(models) == 2

    def test_get_eval_kwargs_no_api_key(self):
        provider = VLLMProvider()
        kwargs = provider.get_eval_kwargs("test")
        assert kwargs["model_base_url"] == "http://localhost:8000/v1"
        assert kwargs["model_args"]["api_key"] == "not-needed"

    def test_get_eval_kwargs_with_api_key(self):
        config = ProviderConfig(api_key="my-key")
        provider = VLLMProvider(config)
        kwargs = provider.get_eval_kwargs("test")
        assert kwargs["model_args"]["api_key"] == "my-key"


# =============================================================================
# OpenRouterProvider Tests
# =============================================================================


class TestOpenRouterProvider:
    def test_default_config(self):
        provider = OpenRouterProvider()
        assert provider.name == "openrouter"
        assert "openrouter.ai" in provider._config.base_url

    def test_not_available_without_key(self):
        config = ProviderConfig(api_key="")
        provider = OpenRouterProvider(config)
        assert not provider.is_available()

    def test_format_model_id(self):
        provider = OpenRouterProvider()
        assert provider.format_model_id("anthropic/claude-3.5-sonnet") == "openai/anthropic/claude-3.5-sonnet"

    @patch("matric_eval.providers.openrouter.urllib.request.urlopen")
    def test_list_models(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_resp.read.return_value = json.dumps({
            "data": [
                {
                    "id": "anthropic/claude-3.5-sonnet",
                    "pricing": {"prompt": "0.003", "completion": "0.015"},
                    "context_length": 200000,
                },
            ]
        }).encode()
        mock_urlopen.return_value = mock_resp

        config = ProviderConfig(api_key="test-key")
        provider = OpenRouterProvider(config)
        models = provider.list_models()
        assert len(models) == 1
        assert models[0].name == "anthropic/claude-3.5-sonnet"
        assert models[0].metadata["context_length"] == 200000

    def test_get_eval_kwargs(self):
        config = ProviderConfig(api_key="test-key")
        provider = OpenRouterProvider(config)
        kwargs = provider.get_eval_kwargs("test-model")
        assert "openrouter.ai" in kwargs["model_base_url"]
        assert kwargs["model_args"]["api_key"] == "test-key"
        assert "HTTP-Referer" in kwargs["model_args"]["extra_headers"]

    def test_get_eval_kwargs_with_routing(self):
        config = ProviderConfig(
            api_key="test-key",
            extra={"route": "fallback", "transforms": ["middle-out"]},
        )
        provider = OpenRouterProvider(config)
        kwargs = provider.get_eval_kwargs("test-model")
        assert kwargs["extra_body"]["route"] == "fallback"
        assert kwargs["extra_body"]["transforms"] == ["middle-out"]


# =============================================================================
# ChutesProvider Tests
# =============================================================================


class TestChutesProvider:
    def test_default_config(self):
        provider = ChutesProvider()
        assert provider.name == "chutes"
        assert "chutes.ai" in provider._config.base_url

    def test_not_available_without_key(self):
        config = ProviderConfig(api_key="")
        provider = ChutesProvider(config)
        assert not provider.is_available()

    def test_format_model_id(self):
        provider = ChutesProvider()
        assert provider.format_model_id("llama3.2:3b") == "openai/llama3.2:3b"

    def test_get_eval_kwargs_cold_start_timeout(self):
        config = ProviderConfig(
            api_key="test-key",
            extra={"cold_start_timeout": 600},
        )
        provider = ChutesProvider(config)
        kwargs = provider.get_eval_kwargs("test-model")
        assert kwargs["model_args"]["timeout"] == 600

    def test_get_eval_kwargs_default_cold_start(self):
        config = ProviderConfig(api_key="test-key")
        provider = ChutesProvider(config)
        kwargs = provider.get_eval_kwargs("test-model")
        assert kwargs["model_args"]["timeout"] == 300  # Default cold start timeout


# =============================================================================
# ProviderRegistry Tests
# =============================================================================


class TestProviderRegistry:
    def test_create_registry(self):
        registry = ProviderRegistry()
        assert registry.list_names() == []

    def test_register_and_get(self):
        registry = ProviderRegistry()
        registry.register("ollama", OllamaProvider)
        provider = registry.get("ollama")
        assert provider.name == "ollama"

    def test_get_caches_instances(self):
        registry = ProviderRegistry()
        registry.register("ollama", OllamaProvider)
        p1 = registry.get("ollama")
        p2 = registry.get("ollama")
        assert p1 is p2

    def test_get_with_config_creates_fresh(self):
        registry = ProviderRegistry()
        registry.register("ollama", OllamaProvider)
        config = ProviderConfig(base_url="http://other:11434")
        p1 = registry.get("ollama")
        p2 = registry.get("ollama", config=config)
        assert p1 is not p2
        assert p2._config.base_url == "http://other:11434"

    def test_get_unknown_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ValueError, match="Unknown provider"):
            registry.get("nonexistent")

    def test_list_names(self):
        registry = ProviderRegistry()
        registry.register("a", OllamaProvider)
        registry.register("b", VLLMProvider)
        assert "a" in registry.list_names()
        assert "b" in registry.list_names()

    def test_clear_cache(self):
        registry = ProviderRegistry()
        registry.register("ollama", OllamaProvider)
        p1 = registry.get("ollama")
        registry.clear_cache()
        p2 = registry.get("ollama")
        assert p1 is not p2


class TestGlobalRegistry:
    def test_list_providers(self):
        names = list_providers()
        assert "ollama" in names
        assert "llama-cpp" in names
        assert "vllm" in names
        assert "openrouter" in names
        assert "chutes" in names

    def test_get_provider(self):
        provider = get_provider("ollama")
        assert provider.name == "ollama"

    def test_get_provider_unknown(self):
        with pytest.raises(ValueError):
            get_provider("nonexistent")

    def test_register_custom_provider(self):
        class CustomProvider:
            @property
            def name(self): return "custom"
            @property
            def display_name(self): return "Custom"
            def is_available(self): return True
            def list_models(self, max_size_gb=0): return []
            def get_model_info(self, model): return ModelInfo(name=model)
            def format_model_id(self, model): return f"custom/{model}"
            def get_eval_kwargs(self, model, **kw): return {}

        register_provider("custom", CustomProvider)
        provider = get_provider("custom")
        assert provider.name == "custom"
        assert isinstance(provider, Provider)


# =============================================================================
# EvaluationMatrix Tests
# =============================================================================


class TestEvaluationMatrix:
    def test_cartesian_product(self):
        matrix = EvaluationMatrix(
            models=["llama3.2:3b", "mistral:7b"],
            providers=["ollama", "vllm"],
            benchmarks=["humaneval", "gsm8k"],
        )
        runs = matrix.get_runs()
        assert len(runs) == 8  # 2 models * 2 providers * 2 benchmarks

    def test_cartesian_with_exclusion(self):
        matrix = EvaluationMatrix(
            models=["llama3.2:3b", "qwen2.5:14b"],
            providers=["ollama", "vllm"],
            benchmarks=["humaneval"],
            exclude=[MatrixExclusion(model="qwen2.5:14b", provider="ollama")],
        )
        runs = matrix.get_runs()
        assert len(runs) == 3  # 4 - 1 excluded
        excluded = [r for r in runs if r["model"] == "qwen2.5:14b" and r["provider"] == "ollama"]
        assert len(excluded) == 0

    def test_explicit_mode(self):
        matrix = EvaluationMatrix(
            mode="explicit",
            explicit_runs=[
                {"model": "llama3.2:3b", "provider": "ollama", "benchmark": "humaneval"},
                {"model": "gpt-4", "provider": "openrouter", "benchmark": "gsm8k"},
            ],
        )
        runs = matrix.get_runs()
        assert len(runs) == 2
        assert runs[0]["model"] == "llama3.2:3b"
        assert runs[1]["provider"] == "openrouter"

    def test_from_dict(self):
        data = {
            "evaluation": {
                "models": ["llama3.2:3b"],
                "providers": ["ollama"],
                "benchmarks": ["humaneval"],
                "tier": "quick",
                "matrix": {"mode": "cartesian"},
                "exclude": [{"model": "big-model", "provider": "ollama"}],
            }
        }
        matrix = EvaluationMatrix.from_dict(data)
        assert matrix.models == ["llama3.2:3b"]
        assert matrix.tier == "quick"
        assert len(matrix.exclude) == 1
        assert matrix.exclude[0].model == "big-model"

    def test_from_yaml(self, tmp_path):
        yaml_content = """
evaluation:
  models:
    - llama3.2:3b
    - mistral:7b
  providers:
    - ollama
    - vllm
  benchmarks:
    - humaneval
    - gsm8k
  tier: smoke
  matrix:
    mode: cartesian
  exclude:
    - model: mistral:7b
      provider: vllm
"""
        yaml_file = tmp_path / "matrix.yaml"
        yaml_file.write_text(yaml_content)

        matrix = EvaluationMatrix.from_yaml(yaml_file)
        assert len(matrix.models) == 2
        assert len(matrix.providers) == 2
        runs = matrix.get_runs()
        # 2 models * 2 providers * 2 benchmarks = 8, minus 2 excluded (mistral:7b on vllm * 2 benchmarks)
        assert len(runs) == 6

    def test_to_dict(self):
        matrix = EvaluationMatrix(
            models=["llama3.2:3b"],
            providers=["ollama"],
            benchmarks=["humaneval"],
            tier="smoke",
        )
        d = matrix.to_dict()
        assert d["evaluation"]["models"] == ["llama3.2:3b"]
        assert d["evaluation"]["tier"] == "smoke"

    def test_empty_matrix(self):
        matrix = EvaluationMatrix()
        runs = matrix.get_runs()
        assert runs == []

    def test_exclusion_by_benchmark(self):
        matrix = EvaluationMatrix(
            models=["m1"],
            providers=["p1"],
            benchmarks=["b1", "b2"],
            exclude=[MatrixExclusion(benchmark="b2")],
        )
        runs = matrix.get_runs()
        assert len(runs) == 1
        assert runs[0]["benchmark"] == "b1"

    def test_exclusion_by_provider_only(self):
        matrix = EvaluationMatrix(
            models=["m1", "m2"],
            providers=["p1", "p2"],
            benchmarks=["b1"],
            exclude=[MatrixExclusion(provider="p2")],
        )
        runs = matrix.get_runs()
        assert len(runs) == 2  # Only p1 runs
        assert all(r["provider"] == "p1" for r in runs)


# =============================================================================
# Engine Provider Integration Tests
# =============================================================================


class TestEngineProviderIntegration:
    def test_engine_with_provider(self):
        from matric_eval.core.engine import EvaluationEngine
        provider = OllamaProvider()
        engine = EvaluationEngine(
            model="llama3.2:3b",
            tier="smoke",
            provider=provider,
        )
        assert engine.model == "ollama/llama3.2:3b"
        assert engine._raw_model == "llama3.2:3b"
        assert engine._get_provider_name() == "ollama"

    def test_engine_without_provider(self):
        from matric_eval.core.engine import EvaluationEngine
        engine = EvaluationEngine(model="ollama/llama3.2:3b", tier="smoke")
        assert engine.model == "ollama/llama3.2:3b"
        assert engine.provider is None
        assert engine._get_provider_name() == "ollama"

    def test_engine_provider_in_results(self):
        from matric_eval.core.engine import EvaluationEngine
        provider = VLLMProvider()
        engine = EvaluationEngine(
            model="test-model",
            tier="smoke",
            provider=provider,
        )
        # run_all would need inspect_ai, so just check metadata
        assert engine._get_provider_name() == "vllm"

    def test_engine_openai_prefix_detection(self):
        from matric_eval.core.engine import EvaluationEngine
        engine = EvaluationEngine(model="openai/gpt-4", tier="smoke")
        assert engine._get_provider_name() == "openai"

    def test_engine_unknown_prefix_detection(self):
        from matric_eval.core.engine import EvaluationEngine
        engine = EvaluationEngine(model="some-model", tier="smoke")
        assert engine._get_provider_name() == "unknown"


# =============================================================================
# CLI Provider Integration Tests
# =============================================================================


class TestCLIProviderIntegration:
    def test_list_providers_command(self):
        from click.testing import CliRunner
        from matric_eval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["list-providers"])
        assert result.exit_code == 0
        assert "ollama" in result.output
        assert "vllm" in result.output
        assert "llama-cpp" in result.output
        assert "openrouter" in result.output
        assert "chutes" in result.output

    def test_list_providers_json(self):
        from click.testing import CliRunner
        from matric_eval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["list-providers", "--output-format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [p["name"] for p in data]
        assert "ollama" in names
        assert "vllm" in names

    def test_run_with_unknown_provider(self):
        from click.testing import CliRunner
        from matric_eval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "run", "--model", "test", "--provider", "nonexistent",
        ])
        assert result.exit_code == 1
        assert "Unknown provider" in result.output or "Available providers" in result.output
