"""OmniDocBench v1.7 routing and protocol tests."""

import pytest
from inspect_ai.model import ContentImage

from matric_eval.tasks.omnidocbench import (
    OMNIDOC_EVALUATOR_REVISION,
    build_omnidocbench_command,
    omnidoc_overall,
    omnidocbench,
    omnidocbench_scorer,
    record_to_sample,
)
from matric_eval.tasks.registry import BenchmarkStatus, BenchmarkUnavailableError


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def test_page_conversion_includes_real_image() -> None:
    sample = record_to_sample(
        {
            "page_info": {
                "image_path": "page.jpg",
                "page_no": 3,
                "page_attribute": {"language": "english"},
            }
        },
        image_path="/data/page.jpg",
    )
    assert sample.id == "page.jpg"
    assert isinstance(sample.input[0].content[0], ContentImage)
    assert sample.metadata["evaluator_revision"] == OMNIDOC_EVALUATOR_REVISION


def test_official_overall_formula() -> None:
    assert omnidoc_overall(text_edit_distance=0.1, table_teds=80.0, formula_cdm=70.0) == 80.0


def test_official_command() -> None:
    assert build_omnidocbench_command("/repo", config="config.yaml")[-2:] == [
        "--config",
        "config.yaml",
    ]


def test_inspect_placeholder_is_rejected() -> None:
    with pytest.raises(BenchmarkUnavailableError, match="batch MGAM"):
        omnidocbench_scorer()
    with pytest.raises(BenchmarkUnavailableError, match="batch-scored"):
        omnidocbench()


def test_registration() -> None:
    metadata = omnidocbench._benchmark_metadata
    assert metadata.total_samples == 1651
    assert metadata.protocol_version == "1.7"
    assert metadata.scoring_type == "official_mgam_edit_teds_cdm"
    assert metadata.status == BenchmarkStatus.GATED
