"""
Tests for prompt templates module (matric_eval.prompts).

Covers:
- Prompt retrieval for all benchmarks
- Thinking mode toggle
- Default behavior
- Error handling for invalid benchmarks
"""

import pytest

from matric_eval.prompts import get_prompt
from matric_eval.prompts.templates import PROMPTS


# =============================================================================
# Prompt Retrieval Tests
# =============================================================================


@pytest.mark.unit
class TestGetPrompt:
    """Tests for get_prompt() function."""

    def test_get_prompt_livecodebench_thinking_on(self) -> None:
        """Should return thinking-aware prompt for LiveCodeBench."""
        prompt = get_prompt("livecodebench", thinking=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "THINKING" in prompt.upper()
        assert "python" in prompt.lower()

    def test_get_prompt_livecodebench_thinking_off(self) -> None:
        """Should return direct prompt for LiveCodeBench with thinking off."""
        prompt = get_prompt("livecodebench", thinking=False)
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "THINKING" not in prompt.upper()
        assert "python" in prompt.lower()

    def test_get_prompt_humaneval_thinking_on(self) -> None:
        """Should return thinking-aware prompt for HumanEval."""
        prompt = get_prompt("humaneval", thinking=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_humaneval_thinking_off(self) -> None:
        """Should return direct prompt for HumanEval with thinking off."""
        prompt = get_prompt("humaneval", thinking=False)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_mbpp_thinking_on(self) -> None:
        """Should return thinking-aware prompt for MBPP."""
        prompt = get_prompt("mbpp", thinking=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_mbpp_thinking_off(self) -> None:
        """Should return direct prompt for MBPP with thinking off."""
        prompt = get_prompt("mbpp", thinking=False)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_ds1000_thinking_on(self) -> None:
        """Should return thinking-aware prompt for DS-1000."""
        prompt = get_prompt("ds1000", thinking=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_ds1000_thinking_off(self) -> None:
        """Should return direct prompt for DS-1000 with thinking off."""
        prompt = get_prompt("ds1000", thinking=False)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_gsm8k_thinking_on(self) -> None:
        """Should return thinking-aware prompt for GSM8K."""
        prompt = get_prompt("gsm8k", thinking=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_gsm8k_thinking_off(self) -> None:
        """Should return direct prompt for GSM8K with thinking off."""
        prompt = get_prompt("gsm8k", thinking=False)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_arc_thinking_on(self) -> None:
        """Should return thinking-aware prompt for ARC."""
        prompt = get_prompt("arc", thinking=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_arc_thinking_off(self) -> None:
        """Should return direct prompt for ARC with thinking off."""
        prompt = get_prompt("arc", thinking=False)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_ifeval_thinking_on(self) -> None:
        """Should return thinking-aware prompt for IFEval."""
        prompt = get_prompt("ifeval", thinking=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_ifeval_thinking_off(self) -> None:
        """Should return direct prompt for IFEval with thinking off."""
        prompt = get_prompt("ifeval", thinking=False)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_mtbench_thinking_on(self) -> None:
        """Should return thinking-aware prompt for MT-Bench."""
        prompt = get_prompt("mtbench", thinking=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_mtbench_thinking_off(self) -> None:
        """Should return direct prompt for MT-Bench with thinking off."""
        prompt = get_prompt("mtbench", thinking=False)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_prompt_default_thinking_true(self) -> None:
        """Should default to thinking=True when parameter not specified."""
        prompt_explicit = get_prompt("livecodebench", thinking=True)
        prompt_default = get_prompt("livecodebench")
        assert prompt_explicit == prompt_default

    def test_get_prompt_invalid_benchmark_raises_keyerror(self) -> None:
        """Should raise KeyError for unknown benchmark."""
        with pytest.raises(KeyError):
            get_prompt("invalid_benchmark", thinking=True)

    def test_get_prompt_thinking_on_differs_from_off(self) -> None:
        """Should return different prompts for thinking on vs off."""
        prompt_on = get_prompt("livecodebench", thinking=True)
        prompt_off = get_prompt("livecodebench", thinking=False)
        assert prompt_on != prompt_off


# =============================================================================
# Template Structure Tests
# =============================================================================


@pytest.mark.unit
class TestPromptTemplates:
    """Tests for PROMPTS structure."""

    def test_prompts_has_all_benchmarks(self) -> None:
        """Should have templates for all code benchmarks."""
        expected_benchmarks = [
            "livecodebench",
            "humaneval",
            "mbpp",
            "ds1000",
            "gsm8k",
            "arc",
            "ifeval",
            "mtbench",
        ]
        for benchmark in expected_benchmarks:
            assert benchmark in PROMPTS, f"Missing templates for {benchmark}"

    def test_prompts_has_thinking_on_and_off(self) -> None:
        """Should have both thinking_on and thinking_off for each benchmark."""
        for benchmark in PROMPTS.keys():
            assert "thinking_on" in PROMPTS[benchmark]
            assert "thinking_off" in PROMPTS[benchmark]

    def test_prompts_are_non_empty_strings(self) -> None:
        """All prompts should be non-empty strings."""
        for benchmark, modes in PROMPTS.items():
            for mode, prompt in modes.items():
                assert isinstance(prompt, str), f"{benchmark}.{mode} is not a string"
                assert len(prompt) > 0, f"{benchmark}.{mode} is empty"

    def test_code_benchmarks_mention_output_format(self) -> None:
        """Code benchmarks should specify output format requirements."""
        code_benchmarks = ["livecodebench", "humaneval", "mbpp", "ds1000"]
        for benchmark in code_benchmarks:
            prompt_on = PROMPTS[benchmark]["thinking_on"]
            prompt_off = PROMPTS[benchmark]["thinking_off"]
            # Should mention code output
            assert ("code" in prompt_on.lower() or "python" in prompt_on.lower())
            assert ("code" in prompt_off.lower() or "python" in prompt_off.lower())

    def test_thinking_on_prompts_guide_reasoning(self) -> None:
        """Thinking-on prompts should guide reasoning structure."""
        for benchmark in PROMPTS.keys():
            prompt = PROMPTS[benchmark]["thinking_on"]
            # Should have some guidance on approach/thinking
            # (not all benchmarks will have "THINKING" explicitly, but should guide)
            assert len(prompt) > 50, f"{benchmark} thinking_on prompt too short"

    def test_thinking_off_prompts_are_direct(self) -> None:
        """Thinking-off prompts should be direct and concise."""
        for benchmark in PROMPTS.keys():
            prompt = PROMPTS[benchmark]["thinking_off"]
            # Should be relatively direct (may still be multi-line for clarity)
            assert len(prompt) > 0


# =============================================================================
# Content Validation Tests
# =============================================================================


@pytest.mark.unit
class TestPromptContent:
    """Tests for prompt content quality."""

    def test_livecodebench_thinking_on_has_structure(self) -> None:
        """LiveCodeBench thinking-on should guide algorithmic approach."""
        prompt = PROMPTS["livecodebench"]["thinking_on"]
        # Should mention approach, constraints, or implementation
        assert any(word in prompt.lower() for word in ["approach", "algorithm", "constraint"])

    def test_livecodebench_thinking_off_is_minimal(self) -> None:
        """LiveCodeBench thinking-off should be concise."""
        prompt = PROMPTS["livecodebench"]["thinking_off"]
        # Should be shorter and more direct
        assert "solve" in prompt.lower() or "write" in prompt.lower()

    def test_code_benchmarks_specify_python(self) -> None:
        """Code benchmarks should explicitly mention Python."""
        code_benchmarks = ["livecodebench", "humaneval", "mbpp", "ds1000"]
        for benchmark in code_benchmarks:
            prompt_on = PROMPTS[benchmark]["thinking_on"]
            prompt_off = PROMPTS[benchmark]["thinking_off"]
            # At least one should mention Python
            assert "python" in prompt_on.lower() or "python" in prompt_off.lower()

    def test_no_prompts_contain_placeholder_text(self) -> None:
        """Prompts should not contain TODOs or placeholder text."""
        for benchmark, modes in PROMPTS.items():
            for mode, prompt in modes.items():
                assert "TODO" not in prompt.upper()
                assert "PLACEHOLDER" not in prompt.upper()
                assert "XXX" not in prompt.upper()
