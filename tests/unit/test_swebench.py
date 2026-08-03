"""
Tests for SWE-bench benchmark variants (matric_eval.tasks.swebench).

Covers:
- Shared factory (record conversion, task creation)
- Verified variant registration
- Pro variant registration
- Multilingual variant registration with language metadata
- Test path extraction from diff
"""

from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.swebench.factory import (
    SWEBENCH_SYSTEM_PROMPT,
    VARIANT_CONFIG,
    _extract_test_path,
    create_swebench_task,
    load_swebench,
    swebench_record_to_sample,
)
from matric_eval.tasks.swebench.multilingual import multilingual_record_to_sample
from matric_eval.tasks.swebench.pro import load_swebench_pro, parse_pro_test_list

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_swebench_record() -> dict[str, Any]:
    """Minimal SWE-bench record for testing."""
    return {
        "instance_id": "django__django-11099",
        "repo": "django/django",
        "base_commit": "a" * 40,
        "problem_statement": "Fix bug in URL resolver when using namespaces.",
        "patch": (
            "--- a/django/urls/resolvers.py\n+++ b/django/urls/resolvers.py\n"
            "@@ -1 +1 @@\n-old\n+new\n"
        ),
        "test_patch": (
            "+++ b/tests/urlpatterns/tests.py\n@@ -100 +100 @@\n+def test_namespace_fix():\n"
        ),
        "hints_text": "Check the URL resolver logic.",
        "version": "4.0",
    }


@pytest.fixture
def sample_swebench_record_no_hints() -> dict[str, Any]:
    """SWE-bench record without hints."""
    return {
        "instance_id": "flask__flask-5000",
        "repo": "pallets/flask",
        "base_commit": "b" * 40,
        "problem_statement": "Fix routing issue.",
        "patch": "--- a/src/flask/app.py\n+++ b/src/flask/app.py\n",
        "test_patch": "",
        "hints_text": "",
    }


@pytest.fixture
def multilingual_record() -> dict[str, Any]:
    """SWE-bench multilingual record with language field."""
    return {
        "instance_id": "express__express-4000",
        "repo": "expressjs/express",
        "base_commit": "c" * 40,
        "problem_statement": "Fix middleware chaining bug.",
        "patch": "--- a/lib/router/index.js\n+++ b/lib/router/index.js\n",
        "test_patch": "+++ b/test/router.test.js\n",
        "hints_text": "",
        "language": "javascript",
    }


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    """Use isolated registry for all tests in this module."""


# =============================================================================
# Record to Sample Conversion
# =============================================================================


class TestSwebenchRecordToSample:
    """Tests for swebench_record_to_sample()."""

    def test_basic_conversion(self, sample_swebench_record: dict) -> None:
        sample = swebench_record_to_sample(sample_swebench_record)
        assert isinstance(sample, Sample)
        assert sample.id == "django__django-11099"
        assert "django/django" in sample.input
        assert "Fix bug in URL resolver" in sample.input
        assert sample.target == sample_swebench_record["patch"]

    def test_metadata_fields(self, sample_swebench_record: dict) -> None:
        sample = swebench_record_to_sample(sample_swebench_record)
        assert sample.metadata["repo"] == "django/django"
        assert sample.metadata["base_commit"] == "a" * 40
        assert sample.metadata["instance_id"] == "django__django-11099"
        assert "repo_path" in sample.metadata

    def test_hints_included(self, sample_swebench_record: dict) -> None:
        sample = swebench_record_to_sample(sample_swebench_record)
        assert "Hints" in sample.input
        assert "Check the URL resolver logic" in sample.input

    def test_no_hints_section_when_empty(self, sample_swebench_record_no_hints: dict) -> None:
        sample = swebench_record_to_sample(sample_swebench_record_no_hints)
        assert "Hints" not in sample.input

    def test_repo_path_derived_from_repo(self, sample_swebench_record: dict) -> None:
        sample = swebench_record_to_sample(sample_swebench_record)
        assert sample.metadata["repo_path"] == "/workspace/django_django"

    def test_test_path_extracted(self, sample_swebench_record: dict) -> None:
        sample = swebench_record_to_sample(sample_swebench_record)
        assert sample.metadata["test_path"] == "tests/urlpatterns/tests.py"

    def test_empty_record_fallbacks(self) -> None:
        sample = swebench_record_to_sample({})
        assert sample.id == ""
        assert sample.target == ""
        assert sample.metadata["repo"] == ""


class TestMultilingualRecordToSample:
    """Tests for multilingual variant's record converter."""

    def test_language_in_metadata(self, multilingual_record: dict) -> None:
        sample = multilingual_record_to_sample(multilingual_record)
        assert sample.metadata["language"] == "javascript"

    def test_default_language_python(self, sample_swebench_record: dict) -> None:
        sample = multilingual_record_to_sample(sample_swebench_record)
        assert sample.metadata["language"] == "python"

    def test_preserves_base_fields(self, multilingual_record: dict) -> None:
        sample = multilingual_record_to_sample(multilingual_record)
        assert sample.id == "express__express-4000"
        assert sample.metadata["repo"] == "expressjs/express"


# =============================================================================
# Test Path Extraction
# =============================================================================


class TestExtractTestPath:
    """Tests for _extract_test_path()."""

    def test_extracts_from_diff(self) -> None:
        patch = "+++ b/tests/test_api.py\n@@ -1 +1 @@\n"
        assert _extract_test_path(patch) == "tests/test_api.py"

    def test_empty_patch(self) -> None:
        assert _extract_test_path("") == ""

    def test_no_test_file(self) -> None:
        assert _extract_test_path("some random text") == ""

    def test_ignores_dev_null(self) -> None:
        patch = "+++ /dev/null\n"
        assert _extract_test_path(patch) == ""

    def test_multiple_files_returns_first(self) -> None:
        patch = "+++ b/tests/first.py\n+++ b/tests/second.py\n"
        assert _extract_test_path(patch) == "tests/first.py"


# =============================================================================
# Variant Configuration
# =============================================================================


class TestVariantConfig:
    """Tests for variant configuration."""

    def test_verified_config_exists(self) -> None:
        assert "verified" in VARIANT_CONFIG
        assert VARIANT_CONFIG["verified"]["total_samples"] == 500

    def test_pro_config_exists(self) -> None:
        assert "pro" in VARIANT_CONFIG

    def test_multilingual_config_exists(self) -> None:
        assert "multilingual" in VARIANT_CONFIG

    def test_unknown_variant_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown SWE-bench variant"):
            load_swebench("nonexistent")


class TestSwebenchPro:
    """Tests for the dedicated SWE-bench Pro adapter."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (["test_a"], ["test_a"]),
            ("['test_a', 'test_b']", ["test_a", "test_b"]),
            (None, []),
        ],
    )
    def test_parse_test_list(self, value: object, expected: list[str]) -> None:
        assert parse_pro_test_list(value) == expected

    @patch("matric_eval.tasks.swebench.pro.pro_record_to_sample")
    @patch("matric_eval.tasks.swebench.pro.get_sample_count", return_value=1)
    @patch("matric_eval.tasks.swebench.pro._records")
    def test_samples_before_loading_harness_scripts(
        self, mock_records, _mock_count, mock_convert
    ) -> None:
        mock_records.return_value = [
            {"instance_id": "one"},
            {"instance_id": "two"},
        ]
        mock_convert.side_effect = lambda record: Sample(
            input="task", target="", id=record["instance_id"]
        )

        samples = load_swebench_pro("smoke")

        assert len(samples) == 1
        assert mock_convert.call_count == 1


# =============================================================================
# Task Creation
# =============================================================================


class TestCreateSwebenchTask:
    """Tests for create_swebench_task()."""

    @patch("matric_eval.tasks.swebench.factory.load_swebench")
    def test_returns_task(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="test", target="patch", id="test-1")]
        task = create_swebench_task(variant="verified", tier="smoke")
        assert isinstance(task, Task)
        assert task.name == "swebench_verified"

    @patch("matric_eval.tasks.swebench.factory.load_swebench")
    def test_pro_variant_name(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="t", target="p", id="1")]
        task = create_swebench_task(variant="pro", tier="smoke")
        assert task.name == "swebench_pro"

    @patch("matric_eval.tasks.swebench.factory.load_swebench")
    def test_multilingual_variant_name(self, mock_load) -> None:
        mock_load.return_value = [Sample(input="t", target="p", id="1")]
        task = create_swebench_task(variant="multilingual", tier="smoke")
        assert task.name == "swebench_multilingual"


# =============================================================================
# Registration
# =============================================================================


class TestSwebenchRegistration:
    """Tests for benchmark registration."""

    def test_verified_registered(self) -> None:
        from matric_eval.tasks.swebench.verified import swebench_verified

        meta = swebench_verified._benchmark_metadata
        assert meta.name == "swebench_verified"
        assert meta.requires_sandbox is True
        assert meta.category.value == "agentic"
        assert meta.total_samples == 500

    def test_pro_registered(self) -> None:
        from matric_eval.tasks.swebench.pro import swebench_pro

        meta = swebench_pro._benchmark_metadata
        assert meta.name == "swebench_pro"
        assert meta.requires_sandbox is True

    def test_multilingual_registered(self) -> None:
        from matric_eval.tasks.swebench.multilingual import swebench_multilingual

        meta = swebench_multilingual._benchmark_metadata
        assert meta.name == "swebench_multilingual"
        assert meta.requires_sandbox is True


# =============================================================================
# System Prompt
# =============================================================================


class TestSystemPrompt:
    """Tests for the SWE-bench system prompt."""

    def test_prompt_not_empty(self) -> None:
        assert len(SWEBENCH_SYSTEM_PROMPT) > 50

    def test_prompt_mentions_patch(self) -> None:
        assert "patch" in SWEBENCH_SYSTEM_PROMPT.lower()
