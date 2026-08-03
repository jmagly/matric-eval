"""Deterministic benchmark source/protocol freshness auditing."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

import httpx

from matric_eval.datasets import is_immutable_hf_revision
from matric_eval.tasks.registry import (
    BenchmarkAccess,
    BenchmarkMetadata,
    BenchmarkReleasePolicy,
    BenchmarkSourceKind,
    BenchmarkStatus,
    TaskRegistry,
    get_registry,
)

AUDIT_SCHEMA_VERSION = "1"


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class AuditFinding:
    code: str
    severity: AuditSeverity
    message: str


@dataclass(frozen=True)
class SourceProbeResult:
    resolvable: bool
    detail: str


class SourceProbe(Protocol):
    def probe(self, metadata: BenchmarkMetadata) -> SourceProbeResult: ...


class LiveSourceProbe:
    """Resolve public benchmark sources without downloading benchmark payloads."""

    def probe(self, metadata: BenchmarkMetadata) -> SourceProbeResult:
        if metadata.source_kind == BenchmarkSourceKind.HUGGINGFACE:
            from huggingface_hub import HfApi

            try:
                info = HfApi().dataset_info(
                    metadata.dataset_source or "",
                    revision=metadata.dataset_revision,
                    token=os.environ.get("HF_TOKEN") or None,
                )
            except Exception as exc:
                return SourceProbeResult(False, f"{type(exc).__name__}: {exc}")
            return SourceProbeResult(True, f"resolved {info.sha}")

        if metadata.source_kind == BenchmarkSourceKind.GITHUB:
            source = metadata.dataset_source or ""
            if source.startswith("https://github.com/"):
                source = source.removeprefix("https://github.com/")
            parts = source.strip("/").split("/")
            if len(parts) < 2:
                return SourceProbeResult(False, "invalid GitHub owner/repository source")
            url = f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
            if metadata.dataset_revision:
                url += f"/commits/{metadata.dataset_revision}"
            try:
                response = httpx.get(url, timeout=20, follow_redirects=True)
                response.raise_for_status()
            except Exception as exc:
                return SourceProbeResult(False, f"{type(exc).__name__}: {exc}")
            return SourceProbeResult(True, f"HTTP {response.status_code}")

        return SourceProbeResult(True, "source type has no network probe")


def _classification(metadata: BenchmarkMetadata) -> str:
    if metadata.status == BenchmarkStatus.UNAVAILABLE:
        return "unavailable"
    if metadata.access == BenchmarkAccess.LOCAL:
        return "local"
    if metadata.successor:
        return "successor_available"
    if (
        metadata.latest_protocol_version
        and metadata.protocol_version != metadata.latest_protocol_version
    ):
        return "outdated"
    if metadata.status == BenchmarkStatus.GATED or metadata.access == BenchmarkAccess.GATED:
        return "gated"
    if metadata.release_policy == BenchmarkReleasePolicy.IMMUTABLE:
        return "immutable"
    return "current"


def _source_evidence_url(metadata: BenchmarkMetadata) -> str | None:
    source = metadata.dataset_source
    if not source:
        return None
    revision = metadata.dataset_revision
    if metadata.source_kind == BenchmarkSourceKind.HUGGINGFACE:
        url = f"https://huggingface.co/datasets/{source}"
        return f"{url}/tree/{revision}" if revision else url
    if metadata.source_kind == BenchmarkSourceKind.GITHUB:
        source = source.removeprefix("https://github.com/").strip("/")
        owner_repo = "/".join(source.split("/")[:2])
        url = f"https://github.com/{owner_repo}"
        return f"{url}/tree/{revision}" if revision else url
    return source if source.startswith(("https://", "http://")) else None


def _metadata_findings(metadata: BenchmarkMetadata) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    if metadata.status == BenchmarkStatus.UNAVAILABLE:
        if not metadata.status_reason:
            findings.append(
                AuditFinding(
                    "unavailable-without-reason",
                    AuditSeverity.ERROR,
                    "Unavailable benchmark has no re-enable or status reason",
                )
            )
        return findings

    if metadata.access is None:
        findings.append(
            AuditFinding("missing-access", AuditSeverity.ERROR, "Access class is not declared")
        )
    if metadata.release_policy is None:
        findings.append(
            AuditFinding(
                "missing-release-policy",
                AuditSeverity.ERROR,
                "Release policy is not declared",
            )
        )
    if not metadata.protocol_version:
        findings.append(
            AuditFinding(
                "missing-protocol", AuditSeverity.ERROR, "Protocol version is not declared"
            )
        )

    external = metadata.access in {
        BenchmarkAccess.PUBLIC,
        BenchmarkAccess.GATED,
        BenchmarkAccess.PRIVATE,
    }
    if external:
        if not metadata.dataset_source:
            findings.append(
                AuditFinding(
                    "missing-source", AuditSeverity.ERROR, "Canonical dataset source is missing"
                )
            )
        if metadata.source_kind is None:
            findings.append(
                AuditFinding(
                    "missing-source-kind",
                    AuditSeverity.ERROR,
                    "Canonical source kind is missing",
                )
            )
        if not metadata.dataset_revision:
            findings.append(
                AuditFinding(
                    "missing-revision",
                    AuditSeverity.ERROR,
                    "Immutable dataset revision is missing",
                )
            )
        if not metadata.dataset_splits:
            findings.append(
                AuditFinding(
                    "missing-splits",
                    AuditSeverity.ERROR,
                    "Expected dataset split names are not declared",
                )
            )
        if metadata.total_samples <= 0:
            findings.append(
                AuditFinding(
                    "missing-count",
                    AuditSeverity.ERROR,
                    "Expected dataset sample count is not declared",
                )
            )
        if any(not value for value in (*metadata.dataset_configs, *metadata.dataset_splits)):
            findings.append(
                AuditFinding(
                    "empty-dataset-shape",
                    AuditSeverity.ERROR,
                    "Expected dataset configs and splits cannot contain empty names",
                )
            )
        elif (
            metadata.source_kind == BenchmarkSourceKind.HUGGINGFACE
            and not is_immutable_hf_revision(metadata.dataset_revision)
        ):
            findings.append(
                AuditFinding(
                    "mutable-revision",
                    AuditSeverity.ERROR,
                    "Hugging Face revision "
                    f"{metadata.dataset_revision!r} is not a full commit hash",
                )
            )
        if not metadata.license:
            findings.append(
                AuditFinding(
                    "missing-license",
                    AuditSeverity.WARNING,
                    "Dataset or benchmark license is not declared",
                )
            )

    if metadata.status == BenchmarkStatus.STABLE and metadata.total_samples == 0:
        findings.append(
            AuditFinding(
                "stable-zero-samples",
                AuditSeverity.ERROR,
                "Stable benchmark declares zero samples",
            )
        )
    if metadata.status == BenchmarkStatus.STABLE and metadata.scoring_type in {
        "placeholder",
        "synthetic_placeholder",
        "tbd",
    }:
        findings.append(
            AuditFinding(
                "placeholder-scorer",
                AuditSeverity.ERROR,
                "Production-enabled benchmark declares placeholder scoring",
            )
        )
    if external and not metadata.evaluator_revision:
        findings.append(
            AuditFinding(
                "missing-evaluator-revision",
                AuditSeverity.WARNING,
                "Evaluator revision is not declared",
            )
        )
    return findings


def audit_registry(
    registry: TaskRegistry | None = None,
    *,
    live: bool = False,
    source_probe: SourceProbe | None = None,
) -> dict[str, Any]:
    """Audit registry metadata and optionally probe canonical sources."""
    if registry is None:
        import matric_eval.tasks  # noqa: F401

        registry = get_registry()
    probe = source_probe or LiveSourceProbe()
    records: list[dict[str, Any]] = []
    totals = {severity.value: 0 for severity in AuditSeverity}
    classifications: dict[str, int] = {}

    for metadata in registry.list_metadata():
        findings = _metadata_findings(metadata)
        if live and metadata.access == BenchmarkAccess.PUBLIC and metadata.dataset_source:
            result = probe.probe(metadata)
            findings.append(
                AuditFinding(
                    "source-resolvable" if result.resolvable else "source-unresolvable",
                    AuditSeverity.INFO if result.resolvable else AuditSeverity.ERROR,
                    result.detail,
                )
            )
        classification = _classification(metadata)
        classifications[classification] = classifications.get(classification, 0) + 1
        for finding in findings:
            totals[finding.severity.value] += 1
        records.append(
            {
                "name": metadata.name,
                "classification": classification,
                "status": metadata.status.value,
                "source": metadata.dataset_source,
                "revision": metadata.dataset_revision,
                "evidence_url": _source_evidence_url(metadata),
                "protocol": metadata.protocol_version,
                "expected": {
                    "configs": list(metadata.dataset_configs),
                    "splits": list(metadata.dataset_splits),
                    "total_samples": metadata.total_samples,
                },
                "findings": [
                    {**asdict(finding), "severity": finding.severity.value} for finding in findings
                ],
            }
        )

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "live": live,
        "summary": {
            "benchmarks": len(records),
            **totals,
            "classifications": classifications,
        },
        "benchmarks": records,
    }
