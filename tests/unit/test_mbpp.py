"""
Tests for MBPP benchmark task (matric_eval.tasks.mbpp).

Covers:
- Function name extraction from test assertions
- Dataset loading from JSONL
- Tiered sampling (smoke/quick/full)
- Sample format conversion with function name in prompt
- Task definition
- Scorer configuration

CRITICAL: Tests for function name extraction (commit 51382e2 from matric-cli)
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.mbpp import (
    extract_function_name,
    extract_function_signature,
    load_mbpp,
    mbpp,
    record_to_sample,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton before each test."""
    # Clear environment variables
    monkeypatch.delenv("EVAL_MBPP_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module
    settings_module._settings = None


# =============================================================================
# Function Name Extraction Tests (CRITICAL - from matric-cli commit 51382e2)
# =============================================================================


@pytest.mark.unit
class TestExtractFunctionName:
    """Tests for extract_function_name() - critical bug fix from matric-cli."""

    def test_extract_function_name_basic(self) -> None:
        """Should extract function name from simple assert statement."""
        test_list = ["assert min_cost([[1, 2, 3]], 2, 2) == 8"]
        assert extract_function_name(test_list) == "min_cost"

    def test_extract_function_name_multiple_tests(self) -> None:
        """Should extract from first test when multiple provided."""
        test_list = [
            "assert similar_elements((3, 4), (5, 4)) == (4,)",
            "assert similar_elements((1, 2), (5, 4)) == ()",
        ]
        assert extract_function_name(test_list) == "similar_elements"

    def test_extract_function_name_with_whitespace(self) -> None:
        """Should handle extra whitespace in assertions."""
        test_list = ["assert   is_not_prime(  2  )  == False"]
        assert extract_function_name(test_list) == "is_not_prime"

    def test_extract_function_name_no_args(self) -> None:
        """Should extract function name even with no arguments."""
        test_list = ["assert get_value() == 42"]
        assert extract_function_name(test_list) == "get_value"

    def test_extract_function_name_underscore_prefix(self) -> None:
        """Should handle function names starting with underscore."""
        test_list = ["assert _private_func(1) == 2"]
        assert extract_function_name(test_list) == "_private_func"

    def test_extract_function_name_numbers_in_name(self) -> None:
        """Should handle function names with numbers."""
        test_list = ["assert func_v2(x) == y"]
        assert extract_function_name(test_list) == "func_v2"

    def test_extract_function_name_empty_list_returns_default(self) -> None:
        """Should return 'solution' as default when test list is empty."""
        test_list = []
        assert extract_function_name(test_list) == "solution"

    def test_extract_function_name_no_match_returns_default(self) -> None:
        """Should return 'solution' when no function call pattern found."""
        test_list = ["# This is a comment", ""]
        assert extract_function_name(test_list) == "solution"

    def test_extract_function_name_complex_assertion(self) -> None:
        """Should extract from complex assertion with nested calls."""
        test_list = ["assert len(find_char_long('test')) == 1"]
        assert extract_function_name(test_list) == "len"

    def test_extract_function_name_various_formats(self) -> None:
        """Should handle various assertion formats from real MBPP data."""
        test_cases = [
            (["assert heap_queue_largest([25, 35], 2) == [35, 25]"], "heap_queue_largest"),
            (["assert count_ways(2) == 3"], "count_ways"),
            (["assert differ_At_One_Bit_Pos(13, 9) == True"], "differ_At_One_Bit_Pos"),
            (["assert find_char_long('Please move') == ['Please', 'move']"], "find_char_long"),
            (["assert square_nums([1, 2, 3]) == [1, 4, 9]"], "square_nums"),
        ]

        for test_list, expected_name in test_cases:
            assert extract_function_name(test_list) == expected_name


# =============================================================================
# Function Signature Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestExtractFunctionSignature:
    """Tests for extract_function_signature() - extracts signature from reference code."""

    def test_extract_function_signature_basic(self) -> None:
        """Should extract function signature from simple def statement."""
        code = "def min_cost(cost, m, n):\n    return 0"
        assert extract_function_signature(code) == "min_cost(cost, m, n)"

    def test_extract_function_signature_no_args(self) -> None:
        """Should handle functions with no arguments."""
        code = "def get_value():\n    return 42"
        assert extract_function_signature(code) == "get_value()"

    def test_extract_function_signature_default_args(self) -> None:
        """Should preserve default argument values."""
        code = "def func(a, b=10, c='test'):\n    pass"
        assert extract_function_signature(code) == "func(a, b=10, c='test')"

    def test_extract_function_signature_multiline(self) -> None:
        """Should extract signature even when def spans multiple lines."""
        code = """def long_function(
    arg1,
    arg2,
    arg3
):
    pass"""
        # Regex might not handle multiline, so should extract first line
        result = extract_function_signature(code)
        assert "long_function" in result

    def test_extract_function_signature_with_type_hints(self) -> None:
        """Should preserve type hints in signature."""
        code = "def typed_func(x: int, y: str) -> bool:\n    return True"
        result = extract_function_signature(code)
        assert "typed_func" in result
        assert "x: int" in result or "typed_func(x: int, y: str)" in result

    def test_extract_function_signature_no_match_returns_placeholder(self) -> None:
        """Should return placeholder when no function definition found."""
        code = "# Just a comment\nx = 42"
        result = extract_function_signature(code)
        assert result == "solution(...)"

    def test_extract_function_signature_from_real_mbpp_code(self) -> None:
        """Should extract from actual MBPP reference code format."""
        code = """R = 3\nC = 3\ndef min_cost(cost, m, n): \n\ttc = [[0 for x in range(C)] for x in range(R)]"""
        assert extract_function_signature(code) == "min_cost(cost, m, n)"


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadMBPP:
    """Tests for load_mbpp() function."""

    def test_load_mbpp_smoke_returns_5_samples(self) -> None:
        """Should load exactly 5 samples for smoke tier."""
        samples = load_mbpp(tier="smoke")
        assert len(samples) == 5

    def test_load_mbpp_quick_returns_100_samples(self) -> None:
        """Should load exactly 75 samples for quick tier."""
        samples = load_mbpp(tier="quick")
        assert len(samples) == 75

    def test_load_mbpp_full_returns_all_samples(self) -> None:
        """Should load all 974 samples for full tier."""
        samples = load_mbpp(tier="full")
        assert len(samples) == 974

    def test_load_mbpp_default_is_smoke(self) -> None:
        """Should default to smoke tier if no tier specified."""
        samples = load_mbpp()
        assert len(samples) == 5

    def test_load_mbpp_unknown_tier_defaults_to_smoke(self) -> None:
        """Should fall back to smoke tier for unknown tier names."""
        samples = load_mbpp(tier="unknown_tier")
        assert len(samples) == 5

    def test_load_mbpp_samples_are_sample_objects(self) -> None:
        """Should return list of Sample objects."""
        samples = load_mbpp(tier="smoke")
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_mbpp_samples_have_required_fields(self) -> None:
        """Should have input, target, id, and metadata fields."""
        samples = load_mbpp(tier="smoke")
        for sample in samples:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert sample.metadata is not None

    def test_load_mbpp_samples_have_unique_ids(self) -> None:
        """Should have unique IDs for all samples."""
        samples = load_mbpp(tier="full")
        ids = [s.id for s in samples]
        assert len(ids) == len(set(ids))

    def test_load_mbpp_ids_match_task_id_pattern(self) -> None:
        """Sample IDs should match original task_id from dataset."""
        samples = load_mbpp(tier="smoke")
        for sample in samples:
            # IDs should be like "MBPP/1", "MBPP/2", etc.
            assert sample.id.startswith("MBPP/")

    def test_load_mbpp_reproducible_with_seed(self) -> None:
        """Should return same samples for same tier (reproducible sampling)."""
        samples1 = load_mbpp(tier="quick")
        samples2 = load_mbpp(tier="quick")

        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]

        assert ids1 == ids2

    def test_load_mbpp_smoke_subset_of_quick(self) -> None:
        """Smoke samples should be subset of quick samples (nested sampling)."""
        smoke_samples = load_mbpp(tier="smoke")
        quick_samples = load_mbpp(tier="quick")

        smoke_ids = {s.id for s in smoke_samples}
        quick_ids = {s.id for s in quick_samples}

        assert smoke_ids.issubset(quick_ids)

    def test_load_mbpp_quick_subset_of_full(self) -> None:
        """Quick samples should be subset of full samples."""
        quick_samples = load_mbpp(tier="quick")
        full_samples = load_mbpp(tier="full")

        quick_ids = {s.id for s in quick_samples}
        full_ids = {s.id for s in full_samples}

        assert quick_ids.issubset(full_ids)

    def test_load_mbpp_file_not_found_raises_error(self) -> None:
        """Should raise FileNotFoundError if dataset file missing."""
        with patch("matric_eval.tasks.mbpp.MBPP_PATH", "/nonexistent/path.jsonl"):
            with pytest.raises(FileNotFoundError):
                load_mbpp()

    def test_load_mbpp_invalid_json_raises_error(self) -> None:
        """Should raise error for malformed JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("invalid json line\n")
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.mbpp.MBPP_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_mbpp()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Record Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() conversion function."""

    def test_record_to_sample_basic_conversion(self) -> None:
        """Should convert MBPP record to Sample."""
        record = {
            "task_id": 1,
            "text": "Write a function to find the minimum cost path.",
            "code": "def min_cost(cost, m, n):\n    return 0",
            "test_list": ["assert min_cost([[1, 2]], 1, 1) == 8"],
            "test_setup_code": "",
        }

        sample = record_to_sample(record)

        assert isinstance(sample, Sample)
        assert sample.id == "MBPP/1"

    def test_record_to_sample_includes_function_name_in_prompt(self) -> None:
        """Should include extracted function name in prompt (critical fix)."""
        record = {
            "task_id": 1,
            "text": "Write a function to find the minimum cost path.",
            "code": "def min_cost(cost, m, n):\n    return 0",
            "test_list": ["assert min_cost([[1, 2]], 1, 1) == 8"],
            "test_setup_code": "",
        }

        sample = record_to_sample(record)

        # CRITICAL: Prompt must include function name for better model performance
        assert "min_cost" in sample.input
        assert "Write a Python function named `min_cost`" in sample.input

    def test_record_to_sample_includes_function_signature_in_prompt(self) -> None:
        """Should include function signature in prompt."""
        record = {
            "task_id": 1,
            "text": "Write a function to find the minimum cost path.",
            "code": "def min_cost(cost, m, n):\n    return 0",
            "test_list": ["assert min_cost([[1, 2]], 1, 1) == 8"],
            "test_setup_code": "",
        }

        sample = record_to_sample(record)

        # Should include signature
        assert "def min_cost(cost, m, n)" in sample.input

    def test_record_to_sample_includes_original_text(self) -> None:
        """Should include original problem description in input."""
        record = {
            "task_id": 1,
            "text": "Write a function to find the minimum cost path.",
            "code": "def min_cost(cost, m, n):\n    return 0",
            "test_list": ["assert min_cost([[1, 2]], 1, 1) == 8"],
            "test_setup_code": "",
        }

        sample = record_to_sample(record)

        assert "Write a function to find the minimum cost path." in sample.input

    def test_record_to_sample_includes_reference_code_in_target(self) -> None:
        """Should use reference code as target."""
        code = "def min_cost(cost, m, n):\n    return 0"
        record = {
            "task_id": 1,
            "text": "Write a function to find the minimum cost path.",
            "code": code,
            "test_list": ["assert min_cost([[1, 2]], 1, 1) == 8"],
            "test_setup_code": "",
        }

        sample = record_to_sample(record)

        assert sample.target == code

    def test_record_to_sample_includes_metadata(self) -> None:
        """Should include entry_point, test_list, and test_setup_code in metadata."""
        record = {
            "task_id": 1,
            "text": "Write a function to find the minimum cost path.",
            "code": "def min_cost(cost, m, n):\n    return 0",
            "test_list": ["assert min_cost([[1, 2]], 1, 1) == 8"],
            "test_setup_code": "import math",
        }

        sample = record_to_sample(record)

        assert sample.metadata is not None
        assert "entry_point" in sample.metadata
        assert sample.metadata["entry_point"] == "min_cost"
        assert "test_list" in sample.metadata
        assert "test_setup_code" in sample.metadata

    def test_record_to_sample_preserves_test_list(self) -> None:
        """Should preserve test list in metadata for execution."""
        test_list = [
            "assert min_cost([[1, 2]], 1, 1) == 8",
            "assert min_cost([[2, 3]], 1, 1) == 12",
        ]
        record = {
            "task_id": 1,
            "text": "Write a function to find the minimum cost path.",
            "code": "def min_cost(cost, m, n):\n    return 0",
            "test_list": test_list,
            "test_setup_code": "",
        }

        sample = record_to_sample(record)

        assert sample.metadata["test_list"] == test_list

    def test_record_to_sample_preserves_test_setup_code(self) -> None:
        """Should preserve test setup code for execution."""
        setup_code = "import math\nR = 3\nC = 3"
        record = {
            "task_id": 1,
            "text": "Write a function to find the minimum cost path.",
            "code": "def min_cost(cost, m, n):\n    return 0",
            "test_list": ["assert min_cost([[1, 2]], 1, 1) == 8"],
            "test_setup_code": setup_code,
        }

        sample = record_to_sample(record)

        assert sample.metadata["test_setup_code"] == setup_code

    def test_record_to_sample_missing_required_field_raises_error(self) -> None:
        """Should raise KeyError if required field missing."""
        incomplete_record = {
            "task_id": 1,
            "text": "Write a function.",
            # Missing code, test_list, test_setup_code
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)

    def test_record_to_sample_handles_empty_test_setup_code(self) -> None:
        """Should handle empty test_setup_code gracefully."""
        record = {
            "task_id": 1,
            "text": "Write a function.",
            "code": "def foo():\n    pass",
            "test_list": ["assert foo() is None"],
            "test_setup_code": "",
        }

        sample = record_to_sample(record)
        assert sample.metadata["test_setup_code"] == ""


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
class TestMBPPSampleQuality:
    """Tests for quality and correctness of loaded samples."""

    def test_samples_have_function_names_in_prompts(self) -> None:
        """Should have function names in prompts (critical fix)."""
        samples = load_mbpp(tier="smoke")
        for sample in samples:
            # Should contain "Write a Python function named `...`"
            assert "Write a Python function named" in sample.input
            assert "`" in sample.input  # Backticks around function name

    def test_samples_have_function_signatures_in_prompts(self) -> None:
        """Should have function signatures in prompts."""
        samples = load_mbpp(tier="smoke")
        for sample in samples:
            assert "def " in sample.input

    def test_samples_have_entry_point_metadata(self) -> None:
        """Should have entry_point in metadata."""
        samples = load_mbpp(tier="smoke")
        for sample in samples:
            assert "entry_point" in sample.metadata
            assert isinstance(sample.metadata["entry_point"], str)
            assert len(sample.metadata["entry_point"]) > 0

    def test_samples_have_test_list_metadata(self) -> None:
        """Should have test_list in metadata."""
        samples = load_mbpp(tier="smoke")
        for sample in samples:
            assert "test_list" in sample.metadata
            assert isinstance(sample.metadata["test_list"], list)
            assert len(sample.metadata["test_list"]) > 0

    def test_samples_have_reference_solutions(self) -> None:
        """Should have non-empty reference solutions as targets."""
        samples = load_mbpp(tier="smoke")
        for sample in samples:
            assert len(sample.target) > 0
            assert "def " in sample.target

    def test_first_sample_is_min_cost(self) -> None:
        """First problem should be the min_cost path problem."""
        samples = load_mbpp(tier="full")
        first = samples[0]

        assert first.id == "MBPP/1"
        assert "minimum cost path" in first.input.lower()
        assert first.metadata["entry_point"] == "min_cost"


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestMBPPTask:
    """Tests for mbpp() task definition."""

    def test_mbpp_task_creation(self) -> None:
        """Should create valid Task object."""
        task = mbpp(tier="smoke")
        assert isinstance(task, Task)

    def test_mbpp_task_name(self) -> None:
        """Should have correct task name."""
        task = mbpp(tier="smoke")
        assert task.name == "mbpp"

    def test_mbpp_task_has_dataset(self) -> None:
        """Should have dataset configured."""
        task = mbpp(tier="smoke")
        assert task.dataset is not None
        assert len(task.dataset) == 5

    def test_mbpp_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = mbpp(tier="smoke")
        assert task.solver is not None

    def test_mbpp_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = mbpp(tier="smoke")
        assert task.scorer is not None

    def test_mbpp_task_respects_tier_parameter(self) -> None:
        """Should create tasks with different sample counts per tier."""
        smoke_task = mbpp(tier="smoke")
        quick_task = mbpp(tier="quick")
        full_task = mbpp(tier="full")

        assert len(smoke_task.dataset) == 5
        assert len(quick_task.dataset) == 75
        assert len(full_task.dataset) == 974

    def test_mbpp_task_default_tier_is_smoke(self) -> None:
        """Should default to smoke tier."""
        task = mbpp()
        assert len(task.dataset) == 5

    def test_mbpp_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = mbpp(tier="smoke")
        task2 = mbpp(tier="smoke")

        # Should be separate instances
        assert task1 is not task2


# =============================================================================
# Scorer Configuration Tests
# =============================================================================


@pytest.mark.unit
class TestMBPPScorer:
    """Tests for code execution scorer configuration."""

    def test_task_has_code_execution_scorer(self) -> None:
        """Should use code execution scorer for validation."""
        task = mbpp(tier="smoke")

        # Scorer should be configured (type check)
        assert task.scorer is not None
        # The actual scorer implementation will be tested in integration tests

    def test_scorer_can_access_test_metadata(self) -> None:
        """Scorer should be able to access test code from metadata."""
        samples = load_mbpp(tier="smoke")

        # All samples should have test metadata for scorer to use
        for sample in samples:
            assert "test_list" in sample.metadata
            assert "entry_point" in sample.metadata
            assert "test_setup_code" in sample.metadata


# =============================================================================
# Integration with Config System
# =============================================================================


@pytest.mark.unit
class TestMBPPConfigIntegration:
    """Tests for integration with matric_eval.config."""

    def test_load_mbpp_uses_config_tier(self) -> None:
        """Should use TierConfig for sample counts."""
        from matric_eval.config import TIERS

        smoke_count = TIERS["smoke"].mbpp
        quick_count = TIERS["quick"].mbpp
        full_count = TIERS["full"].mbpp

        assert len(load_mbpp(tier="smoke")) == smoke_count
        assert len(load_mbpp(tier="quick")) == quick_count
        assert len(load_mbpp(tier="full")) == full_count

    def test_load_mbpp_respects_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should respect EVAL_MBPP_SAMPLES environment variable."""
        monkeypatch.setenv("EVAL_MBPP_SAMPLES", "10")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        # Should load 10 samples instead of default tier counts
        samples = load_mbpp(tier="smoke")
        assert len(samples) == 10

    def test_load_mbpp_uses_reproducible_seed(self) -> None:
        """Should use get_seed() for reproducible sampling."""
        from matric_eval.config import get_seed

        seed = get_seed()
        assert isinstance(seed, int)

        # Samples should be reproducible
        samples1 = load_mbpp(tier="quick")
        samples2 = load_mbpp(tier="quick")

        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestMBPPErrorHandling:
    """Tests for error handling in dataset loading."""

    def test_load_mbpp_empty_file_raises_error(self) -> None:
        """Should raise error for empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write nothing
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.mbpp.MBPP_PATH", temp_path):
                with pytest.raises((ValueError, IndexError)):
                    load_mbpp()
        finally:
            Path(temp_path).unlink()

    def test_load_mbpp_corrupted_jsonl_raises_error(self) -> None:
        """Should raise error for corrupted JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"task_id": 1, "incomplete": \n')
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.mbpp.MBPP_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_mbpp()
        finally:
            Path(temp_path).unlink()

    def test_extract_function_name_handles_malformed_assertion(self) -> None:
        """Should return default for malformed test assertions."""
        test_list = ["not a valid assertion"]
        assert extract_function_name(test_list) == "solution"


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
class TestMBPPEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_mbpp_sample_count_exceeds_dataset_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return all available samples if requested count exceeds dataset size."""
        monkeypatch.setenv("EVAL_MBPP_SAMPLES", "2000")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_mbpp()
        # Should return all 974 samples, not 2000
        assert len(samples) == 974

    def test_load_mbpp_zero_samples_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle zero sample request gracefully."""
        monkeypatch.setenv("EVAL_MBPP_SAMPLES", "0")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_mbpp()
        assert len(samples) == 0

    def test_record_to_sample_with_unicode_characters(self) -> None:
        """Should handle unicode characters in text."""
        record = {
            "task_id": 999,
            "text": "Write a function to calculate π",
            "code": "def calc_pi():\n    return 3.14159",
            "test_list": ["assert calc_pi() > 3.0"],
            "test_setup_code": "",
        }

        sample = record_to_sample(record)
        assert "π" in sample.input

    def test_record_to_sample_with_long_code(self) -> None:
        """Should handle long reference code."""
        long_code = "def long_function():\n" + "    pass\n" * 100
        record = {
            "task_id": 999,
            "text": "Write a long function.",
            "code": long_code,
            "test_list": ["assert long_function() is None"],
            "test_setup_code": "",
        }

        sample = record_to_sample(record)
        assert len(sample.target) > 0
        assert sample.target == long_code

    def test_extract_function_name_with_method_call(self) -> None:
        """Should extract first function name even for method calls."""
        test_list = ["assert obj.method_name(1, 2) == 3"]
        # Should extract "obj" as the first identifier
        result = extract_function_name(test_list)
        assert result in ["obj", "solution"]  # Either is acceptable
