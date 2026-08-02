"""NL2RepoBench canonical adapter tests."""

from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task

from matric_eval.tasks.nl2repo import NL2REPO_REVISION, load_nl2repo, nl2repo, record_to_sample


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def test_record_uses_official_test_metadata() -> None:
    sample = record_to_sample(
        {
            "id": "demo",
            "specification": "Create a complete package.",
            "test_commands": ["pip install -e .", "pytest tests"],
            "test_case_count": 12,
        }
    )
    assert sample.id == "demo"
    assert "complete package" in sample.input
    assert sample.metadata["test_commands"] == ["pip install -e .", "pytest tests"]
    assert sample.metadata["test_case_count"] == 12
    assert sample.metadata["dataset_revision"] == NL2REPO_REVISION
    assert "nl2repobench/demo:1.0" in Path(sample.sandbox.config).read_text()


def test_missing_snapshot_fails_clearly() -> None:
    with patch("matric_eval.tasks.nl2repo.get_dataset_path", return_value=None):
        with pytest.raises(FileNotFoundError, match="canonical snapshot"):
            load_nl2repo()


def test_registration_and_task() -> None:
    metadata = nl2repo._benchmark_metadata
    assert metadata.total_samples == 104
    assert metadata.scoring_type == "official_test_pass_rate"
    assert metadata.dataset_revision == NL2REPO_REVISION
    with patch(
        "matric_eval.tasks.nl2repo.load_nl2repo", return_value=[record_to_sample({"id": "x"})]
    ):
        result = nl2repo()
    assert isinstance(result, Task)
    assert result.name == "nl2repobench_104"
