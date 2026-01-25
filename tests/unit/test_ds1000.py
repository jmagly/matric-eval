"""
Tests for DS-1000 benchmark task (matric_eval.tasks.ds1000).

Covers:
- Dataset loading from JSONL
- Tiered sampling (smoke/quick/full)
- Sample format conversion with code context
- Task definition
- Scorer configuration

DS-1000: 1,000 data science coding problems focusing on pandas, numpy,
matplotlib, and other data science libraries.
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.ds1000 import (
    ds1000,
    load_ds1000,
    record_to_sample,
)

# Import skip marker for tests requiring external data
from tests.conftest import requires_ds1000_data


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton before each test."""
    # Clear environment variables
    monkeypatch.delenv("EVAL_DS1000_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module
    settings_module._settings = None


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
@requires_ds1000_data
class TestLoadDS1000:
    """Tests for load_ds1000() function."""

    def test_load_ds1000_smoke_returns_5_samples(self) -> None:
        """Should load exactly 5 samples for smoke tier."""
        samples = load_ds1000(tier="smoke")
        assert len(samples) == 5

    def test_load_ds1000_quick_returns_50_samples(self) -> None:
        """Should load exactly 50 samples for quick tier."""
        samples = load_ds1000(tier="quick")
        assert len(samples) == 50

    def test_load_ds1000_full_returns_all_samples(self) -> None:
        """Should load all 1000 samples for full tier."""
        samples = load_ds1000(tier="full")
        assert len(samples) == 1000

    def test_load_ds1000_default_is_smoke(self) -> None:
        """Should default to smoke tier if no tier specified."""
        samples = load_ds1000()
        assert len(samples) == 5

    def test_load_ds1000_unknown_tier_defaults_to_smoke(self) -> None:
        """Should fall back to smoke tier for unknown tier names."""
        samples = load_ds1000(tier="unknown_tier")
        assert len(samples) == 5

    def test_load_ds1000_samples_are_sample_objects(self) -> None:
        """Should return list of Sample objects."""
        samples = load_ds1000(tier="smoke")
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_ds1000_samples_have_required_fields(self) -> None:
        """Should have input, target, id, and metadata fields."""
        samples = load_ds1000(tier="smoke")
        for sample in samples:
            assert sample.input is not None
            assert sample.target is not None
            assert sample.id is not None
            assert sample.metadata is not None

    def test_load_ds1000_samples_have_unique_ids(self) -> None:
        """Should have unique IDs for all samples."""
        samples = load_ds1000(tier="full")
        ids = [s.id for s in samples]
        assert len(ids) == len(set(ids))

    def test_load_ds1000_ids_match_pattern(self) -> None:
        """Sample IDs should match DS1000/library_problem pattern."""
        samples = load_ds1000(tier="smoke")
        for sample in samples:
            # IDs should be like "DS1000/Pandas/0"
            assert sample.id.startswith("DS1000/")

    def test_load_ds1000_reproducible_with_seed(self) -> None:
        """Should return same samples for same tier (reproducible sampling)."""
        samples1 = load_ds1000(tier="quick")
        samples2 = load_ds1000(tier="quick")

        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]

        assert ids1 == ids2

    def test_load_ds1000_smoke_subset_of_quick(self) -> None:
        """Smoke samples should be subset of quick samples (nested sampling)."""
        smoke_samples = load_ds1000(tier="smoke")
        quick_samples = load_ds1000(tier="quick")

        smoke_ids = {s.id for s in smoke_samples}
        quick_ids = {s.id for s in quick_samples}

        assert smoke_ids.issubset(quick_ids)

    def test_load_ds1000_quick_subset_of_full(self) -> None:
        """Quick samples should be subset of full samples."""
        quick_samples = load_ds1000(tier="quick")
        full_samples = load_ds1000(tier="full")

        quick_ids = {s.id for s in quick_samples}
        full_ids = {s.id for s in full_samples}

        assert quick_ids.issubset(full_ids)

    def test_load_ds1000_file_not_found_raises_error(self) -> None:
        """Should raise FileNotFoundError if dataset file missing."""
        with patch("matric_eval.tasks.ds1000.DS1000_PATH", "/nonexistent/path.jsonl"):
            with pytest.raises(FileNotFoundError):
                load_ds1000()

    def test_load_ds1000_invalid_json_raises_error(self) -> None:
        """Should raise error for malformed JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("invalid json line\n")
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.ds1000.DS1000_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_ds1000()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Record Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() conversion function."""

    def test_record_to_sample_basic_conversion(self) -> None:
        """Should convert DS-1000 record to Sample."""
        record = {
            "prompt": "Problem:\nHow to shuffle DataFrame rows?\n\nA:\n<code>\nimport pandas as pd\ndf = ...\n</code>\nresult = ... # put solution\nBEGIN SOLUTION\n<code>\n",
            "reference_code": "def g(df, List):\n    return df.iloc[List]\n\nresult = g(df.copy(), List)\n",
            "metadata": {
                "problem_id": 0,
                "library_problem_id": 0,
                "library": "Pandas",
                "test_case_cnt": 1,
                "perturbation_type": "Origin",
                "perturbation_origin_id": 0
            },
            "code_context": "import pandas as pd\n..."
        }

        sample = record_to_sample(record)

        assert isinstance(sample, Sample)
        assert sample.id == "DS1000/Pandas/0"

    def test_record_to_sample_includes_prompt_in_input(self) -> None:
        """Should include problem prompt in input field."""
        record = {
            "prompt": "Problem:\nHow to shuffle DataFrame rows?\n\nA:\n<code>\n",
            "reference_code": "result = df.iloc[List]",
            "metadata": {
                "problem_id": 0,
                "library": "Pandas"
            },
            "code_context": "import pandas as pd\n"
        }

        sample = record_to_sample(record)

        assert "shuffle DataFrame rows" in sample.input

    def test_record_to_sample_includes_code_context_in_input(self) -> None:
        """Should include code context/setup in input."""
        record = {
            "prompt": "Problem:\nHow to do X?\n\nA:\n<code>\n",
            "reference_code": "result = solution()",
            "metadata": {
                "problem_id": 1,
                "library": "Numpy"
            },
            "code_context": "import numpy as np\nimport pandas as pd\n"
        }

        sample = record_to_sample(record)

        # Code context should be preserved in metadata for execution
        assert "code_context" in sample.metadata
        assert "import" in sample.metadata["code_context"]

    def test_record_to_sample_uses_reference_code_as_target(self) -> None:
        """Should use reference_code as target."""
        reference = "def g(df):\n    return df.iloc[0]\n\nresult = g(df)"
        record = {
            "prompt": "Problem:\nGet first row\n\nA:\n<code>\n",
            "reference_code": reference,
            "metadata": {
                "problem_id": 2,
                "library": "Pandas"
            },
            "code_context": "import pandas as pd\n"
        }

        sample = record_to_sample(record)

        assert sample.target == reference

    def test_record_to_sample_includes_metadata(self) -> None:
        """Should include library, problem_id, and test info in metadata."""
        record = {
            "prompt": "Problem:\nTest\n\nA:\n<code>\n",
            "reference_code": "result = 42",
            "metadata": {
                "problem_id": 5,
                "library_problem_id": 10,
                "library": "Matplotlib",
                "test_case_cnt": 3,
                "perturbation_type": "Semantic"
            },
            "code_context": "import matplotlib.pyplot as plt\n"
        }

        sample = record_to_sample(record)

        assert sample.metadata is not None
        assert "library" in sample.metadata
        assert sample.metadata["library"] == "Matplotlib"
        assert "problem_id" in sample.metadata
        assert "test_case_cnt" in sample.metadata
        assert "code_context" in sample.metadata

    def test_record_to_sample_preserves_code_context(self) -> None:
        """Should preserve code_context in metadata for execution."""
        code_context = "import pandas as pd\nimport numpy as np\n\ndef generate_test_case():\n    pass"
        record = {
            "prompt": "Problem:\nTest\n\nA:\n<code>\n",
            "reference_code": "result = 42",
            "metadata": {
                "problem_id": 10,
                "library": "Pandas"
            },
            "code_context": code_context
        }

        sample = record_to_sample(record)

        assert sample.metadata["code_context"] == code_context

    def test_record_to_sample_missing_required_field_raises_error(self) -> None:
        """Should raise KeyError if required field missing."""
        incomplete_record = {
            "prompt": "Problem:\nTest",
            # Missing reference_code, metadata, code_context
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
@requires_ds1000_data
class TestDS1000SampleQuality:
    """Tests for quality and correctness of loaded samples."""

    def test_samples_have_data_science_problems(self) -> None:
        """Should have data science related problem descriptions."""
        samples = load_ds1000(tier="smoke")
        for sample in samples:
            # Should have substantial problem description
            assert len(sample.input) > 50

    def test_samples_have_library_metadata(self) -> None:
        """Should have library field in metadata."""
        samples = load_ds1000(tier="smoke")
        for sample in samples:
            assert "library" in sample.metadata
            # Should be one of the main data science libraries
            assert sample.metadata["library"] in [
                "Pandas", "Numpy", "Scipy", "Sklearn", "Matplotlib", "Tensorflow", "Pytorch"
            ]

    def test_samples_have_problem_ids(self) -> None:
        """Should have problem_id in metadata."""
        samples = load_ds1000(tier="smoke")
        for sample in samples:
            assert "problem_id" in sample.metadata
            assert isinstance(sample.metadata["problem_id"], int)

    def test_samples_have_code_context(self) -> None:
        """Should have code_context in metadata."""
        samples = load_ds1000(tier="smoke")
        for sample in samples:
            assert "code_context" in sample.metadata
            # Code context should have imports or test generation code
            assert "import" in sample.metadata["code_context"] or "def" in sample.metadata["code_context"]

    def test_samples_have_reference_solutions(self) -> None:
        """Should have non-empty reference solutions as targets."""
        samples = load_ds1000(tier="smoke")
        for sample in samples:
            assert len(sample.target) > 0

    def test_first_sample_is_pandas_problem(self) -> None:
        """First problem should be the Pandas shuffle problem."""
        samples = load_ds1000(tier="full")
        first = samples[0]

        assert first.id == "DS1000/Pandas/0"
        assert first.metadata["library"] == "Pandas"


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
@requires_ds1000_data
class TestDS1000Task:
    """Tests for ds1000() task definition."""

    def test_ds1000_task_creation(self) -> None:
        """Should create valid Task object."""
        task = ds1000(tier="smoke")
        assert isinstance(task, Task)

    def test_ds1000_task_name(self) -> None:
        """Should have correct task name."""
        task = ds1000(tier="smoke")
        assert task.name == "ds1000"

    def test_ds1000_task_has_dataset(self) -> None:
        """Should have dataset configured."""
        task = ds1000(tier="smoke")
        assert task.dataset is not None
        assert len(task.dataset) == 5

    def test_ds1000_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = ds1000(tier="smoke")
        assert task.solver is not None

    def test_ds1000_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = ds1000(tier="smoke")
        assert task.scorer is not None

    def test_ds1000_task_respects_tier_parameter(self) -> None:
        """Should create tasks with different sample counts per tier."""
        smoke_task = ds1000(tier="smoke")
        quick_task = ds1000(tier="quick")
        full_task = ds1000(tier="full")

        assert len(smoke_task.dataset) == 5
        assert len(quick_task.dataset) == 50
        assert len(full_task.dataset) == 1000

    def test_ds1000_task_default_tier_is_smoke(self) -> None:
        """Should default to smoke tier."""
        task = ds1000()
        assert len(task.dataset) == 5

    def test_ds1000_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = ds1000(tier="smoke")
        task2 = ds1000(tier="smoke")

        # Should be separate instances
        assert task1 is not task2


# =============================================================================
# Integration with Config System
# =============================================================================


@pytest.mark.unit
@requires_ds1000_data
class TestDS1000ConfigIntegration:
    """Tests for integration with matric_eval.config."""

    def test_load_ds1000_uses_config_tier(self) -> None:
        """Should use TierConfig for sample counts."""
        from matric_eval.config import TIERS

        smoke_count = TIERS["smoke"].ds1000
        quick_count = TIERS["quick"].ds1000
        full_count = TIERS["full"].ds1000

        # If ds1000 not configured, should use default of 5
        expected_smoke = smoke_count if smoke_count > 0 else 5
        expected_quick = quick_count if quick_count > 0 else 50

        assert len(load_ds1000(tier="smoke")) == expected_smoke
        assert len(load_ds1000(tier="quick")) == expected_quick
        assert len(load_ds1000(tier="full")) == full_count

    def test_load_ds1000_respects_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should respect EVAL_DS1000_SAMPLES environment variable."""
        monkeypatch.setenv("EVAL_DS1000_SAMPLES", "15")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        # Should load 15 samples instead of default tier counts
        samples = load_ds1000(tier="smoke")
        assert len(samples) == 15

    def test_load_ds1000_uses_reproducible_seed(self) -> None:
        """Should use get_seed() for reproducible sampling."""
        from matric_eval.config import get_seed

        seed = get_seed()
        assert isinstance(seed, int)

        # Samples should be reproducible
        samples1 = load_ds1000(tier="quick")
        samples2 = load_ds1000(tier="quick")

        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestDS1000ErrorHandling:
    """Tests for error handling in dataset loading."""

    def test_load_ds1000_empty_file_raises_error(self) -> None:
        """Should raise error for empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write nothing
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.ds1000.DS1000_PATH", temp_path):
                with pytest.raises((ValueError, IndexError)):
                    load_ds1000()
        finally:
            Path(temp_path).unlink()

    def test_load_ds1000_corrupted_jsonl_raises_error(self) -> None:
        """Should raise error for corrupted JSONL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"prompt": "test", "incomplete": \n')
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.ds1000.DS1000_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_ds1000()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
@requires_ds1000_data
class TestDS1000EdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_ds1000_sample_count_exceeds_dataset_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return all available samples if requested count exceeds dataset size."""
        monkeypatch.setenv("EVAL_DS1000_SAMPLES", "2000")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_ds1000()
        # Should return all 1000 samples, not 2000
        assert len(samples) == 1000

    def test_load_ds1000_zero_samples_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle zero sample request gracefully."""
        monkeypatch.setenv("EVAL_DS1000_SAMPLES", "0")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        samples = load_ds1000()
        assert len(samples) == 0

    def test_record_to_sample_with_minimal_metadata(self) -> None:
        """Should handle records with minimal metadata."""
        record = {
            "prompt": "Problem:\nTest",
            "reference_code": "result = 1",
            "metadata": {
                "problem_id": 0,
                "library": "Pandas"
            },
            "code_context": "import pandas as pd"
        }

        sample = record_to_sample(record)
        assert sample is not None
        assert len(sample.input) > 0

    def test_record_to_sample_with_long_code_context(self) -> None:
        """Should handle long code context."""
        long_context = "import pandas as pd\n" + "def helper():\n    pass\n" * 50
        record = {
            "prompt": "Problem:\nTest",
            "reference_code": "result = helper()",
            "metadata": {
                "problem_id": 99,
                "library": "Pandas"
            },
            "code_context": long_context
        }

        sample = record_to_sample(record)
        assert sample.metadata["code_context"] == long_context
