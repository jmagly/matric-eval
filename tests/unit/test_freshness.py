"""Tests for benchmark source and protocol freshness auditing."""

import json

import pytest

from matric_eval.freshness import SourceProbeResult, audit_registry
from matric_eval.provenance import benchmark_provenance
from matric_eval.tasks.registry import (
    BenchmarkAccess,
    BenchmarkCategory,
    BenchmarkMetadata,
    BenchmarkReleasePolicy,
    BenchmarkSourceKind,
    BenchmarkStatus,
    TaskRegistry,
)


def _metadata(name: str, **overrides: object) -> BenchmarkMetadata:
    values = {
        "name": name,
        "description": name,
        "category": BenchmarkCategory.REASONING,
        "module_path": f"matric_eval.tasks.{name}.{name}",
        "tier_samples": {"smoke": 1},
        "total_samples": 1,
        "protocol_version": "1",
        "dataset_source": "owner/dataset",
        "dataset_revision": "a" * 40,
        "dataset_splits": ("test",),
        "evaluator_source": "owner/evaluator",
        "evaluator_revision": "b" * 40,
        "license": "MIT",
        "access": BenchmarkAccess.PUBLIC,
        "source_kind": BenchmarkSourceKind.HUGGINGFACE,
        "release_policy": BenchmarkReleasePolicy.IMMUTABLE,
    }
    values.update(overrides)
    return BenchmarkMetadata(**values)


@pytest.mark.unit
def test_audit_registry_classifies_and_serializes() -> None:
    registry = TaskRegistry()
    registry.register(
        _metadata("current", release_policy=BenchmarkReleasePolicy.VERSIONED)
    )
    registry.register(_metadata("immutable"))
    registry.register(_metadata("outdated", latest_protocol_version="2"))
    registry.register(_metadata("successor", successor="replacement"))
    registry.register(
        _metadata(
            "gated",
            access=BenchmarkAccess.GATED,
            status=BenchmarkStatus.GATED,
        )
    )
    registry.register(
        _metadata(
            "local",
            access=BenchmarkAccess.LOCAL,
            source_kind=BenchmarkSourceKind.LOCAL,
            release_policy=BenchmarkReleasePolicy.LOCAL,
            dataset_source=None,
            dataset_revision="project-v1",
        )
    )
    registry.register(
        _metadata(
            "unavailable",
            status=BenchmarkStatus.UNAVAILABLE,
            status_reason="No public release",
            access=BenchmarkAccess.UNAVAILABLE,
            release_policy=BenchmarkReleasePolicy.UNRELEASED,
        )
    )

    report = audit_registry(registry)

    assert report["summary"]["error"] == 0
    assert report["summary"]["classifications"] == {
        "current": 1,
        "immutable": 1,
        "outdated": 1,
        "successor_available": 1,
        "gated": 1,
        "local": 1,
        "unavailable": 1,
    }
    assert json.loads(json.dumps(report))["schema_version"] == "1"
    assert report["benchmarks"][0]["expected"]["total_samples"] == 1
    assert report["benchmarks"][0]["evidence_url"].endswith("/tree/" + "a" * 40)


@pytest.mark.unit
@pytest.mark.parametrize(
    "status",
    [
        BenchmarkStatus.STABLE,
        BenchmarkStatus.LEGACY,
        BenchmarkStatus.GATED,
        BenchmarkStatus.EXPERIMENTAL,
        BenchmarkStatus.UNAVAILABLE,
    ],
)
def test_result_provenance_supports_every_lifecycle_status(
    status: BenchmarkStatus,
) -> None:
    metadata = _metadata(
        status.value,
        status=status,
        status_reason="Not runnable" if status == BenchmarkStatus.UNAVAILABLE else None,
        prompt_revision="prompt-sha256:abc",
        container_revision="image@sha256:def",
    )

    result = benchmark_provenance(metadata.name, metadata)

    assert result["benchmark"]["status"] == status.value
    assert result["benchmark"]["prompt_revision"] == "prompt-sha256:abc"
    assert result["benchmark"]["container_revision"] == "image@sha256:def"


@pytest.mark.unit
def test_audit_registry_reports_reproducibility_errors() -> None:
    registry = TaskRegistry()
    registry.register(
        _metadata(
            "broken",
            dataset_revision="main",
            scoring_type="placeholder",
        )
    )

    report = audit_registry(registry)
    codes = {finding["code"] for finding in report["benchmarks"][0]["findings"]}

    assert {"mutable-revision", "placeholder-scorer"}.issubset(codes)
    assert report["summary"]["error"] == 2


@pytest.mark.unit
def test_live_probe_only_checks_public_sources() -> None:
    class Probe:
        def __init__(self) -> None:
            self.names: list[str] = []

        def probe(self, metadata: BenchmarkMetadata) -> SourceProbeResult:
            self.names.append(metadata.name)
            return SourceProbeResult(True, "resolved")

    registry = TaskRegistry()
    registry.register(_metadata("public"))
    registry.register(
        _metadata(
            "gated",
            access=BenchmarkAccess.GATED,
            status=BenchmarkStatus.GATED,
        )
    )
    probe = Probe()

    report = audit_registry(registry, live=True, source_probe=probe)

    assert probe.names == ["public"]
    assert report["summary"]["info"] == 1
    assert report["summary"]["error"] == 0
