"""Frontier agentic benchmark provenance and safety-contract tests."""

import pytest

from matric_eval.tasks.frontier_agentic import (
    ARC_AGI_3_REVISION,
    ARC_AGI_3_PUBLIC_ENVIRONMENTS,
    ARC_AGI_3_PUBLIC_MANIFEST_SHA256,
    BROWSECOMP_DATASET_SHA256,
    HLE_DATASET_REVISION,
    OSWORLD2_RELEASE,
    OSWORLD2_REVISION,
    OSWORLD2_TASK_MANIFEST_SHA256,
    arc_agi_3,
    arc_agi_3_environment_manifest,
    browsecomp,
    build_arc_agi_3_server_command,
    build_osworld2_download_commands,
    gdpval,
    hle,
    osworld2,
)
from matric_eval.tasks.registry import BenchmarkStatus, BenchmarkUnavailableError
from matric_eval.tasks.upstream import INSPECT_EVALS_REVISION, INSPECT_EVALS_VERSION


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def test_current_inspect_evals_provenance_is_pinned() -> None:
    assert INSPECT_EVALS_VERSION == "0.19.0"
    assert INSPECT_EVALS_REVISION == "1eda2bfd205dc7d97e4dc91cfb1e7f05a2d4c504"


def test_browsecomp_and_hle_metadata_pin_data_and_protocol() -> None:
    browse_metadata = browsecomp._benchmark_metadata
    assert browse_metadata.protocol_version == "3-B"
    assert browse_metadata.dataset_revision == BROWSECOMP_DATASET_SHA256
    assert len(BROWSECOMP_DATASET_SHA256) == 64

    hle_metadata = hle._benchmark_metadata
    assert hle_metadata.protocol_version == "5-C"
    assert hle_metadata.dataset_revision == HLE_DATASET_REVISION
    assert hle_metadata.status == BenchmarkStatus.GATED


def test_gdpval_rejects_implicit_exact_match_scoring() -> None:
    with pytest.raises(BenchmarkUnavailableError, match="explicit expert or validated rubric"):
        gdpval()


def test_arc_agi_3_command_and_external_runtime_contract() -> None:
    command = build_arc_agi_3_server_command("/benchmarks/arc-agi", port=8123)
    assert command[:5] == ["uv", "run", "--project", "/benchmarks/arc-agi", "--python"]
    assert "port=8123" in command[-1]
    assert "save_all_recordings=True" in command[-1]
    assert arc_agi_3._benchmark_metadata.dataset_revision == ARC_AGI_3_REVISION
    assert arc_agi_3._benchmark_metadata.total_samples == 25
    manifest = arc_agi_3_environment_manifest(reversed(ARC_AGI_3_PUBLIC_ENVIRONMENTS))
    assert manifest["count"] == 25
    assert manifest["sha256"] == ARC_AGI_3_PUBLIC_MANIFEST_SHA256
    with pytest.raises(BenchmarkUnavailableError, match="stateful visual-action"):
        arc_agi_3()


def test_osworld2_release_downloads_and_hashes_are_pinned() -> None:
    commands = build_osworld2_download_commands("/benchmarks/osworld2")
    assert len(commands) == 2
    assert all(command[-1] == OSWORLD2_RELEASE for command in commands)
    assert OSWORLD2_REVISION == "d578d2d4e0dc82b43e270fdaa7fa89d9708cd154"
    assert len(OSWORLD2_TASK_MANIFEST_SHA256) == 64
    assert osworld2._benchmark_metadata.protocol_version == OSWORLD2_RELEASE
    with pytest.raises(BenchmarkUnavailableError, match="official .* external runtime"):
        osworld2()
