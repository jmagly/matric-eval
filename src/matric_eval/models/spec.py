"""Immutable model, treatment, and runtime identities for matched evaluations."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


def _immutable_revision(value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if not _COMMIT_RE.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must be an immutable 40- or 64-character hexadecimal revision"
        )
    return normalized


def _sha256(value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a SHA-256 digest")
    return normalized.removeprefix("sha256:")


class LineageRole(str, Enum):
    """A checkpoint's role in a matched comparison cohort."""

    PRETRAINED_BASE = "pretrained-base"
    OFFICIAL_INSTRUCT = "official-instruct"
    UNTOUCHED_CONTROL = "untouched-control"
    INTERVENTION = "intervention"


class ExecutionMode(str, Enum):
    """Whether a model is measured directly or through an agent harness."""

    DIRECT_ENDPOINT = "direct-endpoint"
    AGENT_HARNESS = "agent-harness"


class ProvenanceStatus(str, Enum):
    """Whether a model identity is complete or a disclosed historical reconstruction."""

    COMPLETE = "complete"
    RECONSTRUCTED_WITH_GAPS = "reconstructed-with-gaps"


@dataclass(frozen=True)
class InterventionSpec:
    """One transformation applied to a parent checkpoint."""

    method: str
    parent_source: str
    parent_revision: str
    implementation_source: str
    config_sha256: str
    implementation_revision: str | None = None
    implementation_artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parent_revision",
            _immutable_revision(self.parent_revision, "intervention.parent_revision"),
        )
        if self.implementation_revision is not None:
            object.__setattr__(
                self,
                "implementation_revision",
                _immutable_revision(
                    self.implementation_revision, "intervention.implementation_revision"
                ),
            )
        object.__setattr__(
            self,
            "config_sha256",
            _sha256(self.config_sha256, "intervention.config_sha256"),
        )
        if self.implementation_artifact_sha256 is not None:
            object.__setattr__(
                self,
                "implementation_artifact_sha256",
                _sha256(
                    self.implementation_artifact_sha256,
                    "intervention.implementation_artifact_sha256",
                ),
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterventionSpec:
        return cls(**data)


@dataclass(frozen=True)
class QuantizationSpec:
    """Deployment quantization, kept separate from training/intervention lineage."""

    method: str
    bits: int
    library: str
    library_version: str
    config_sha256: str
    source_checkpoint: str
    source_revision: str
    library_revision: str | None = None

    def __post_init__(self) -> None:
        if self.bits < 1 or self.bits > 32:
            raise ValueError("quantization.bits must be between 1 and 32")
        if self.library_revision is not None:
            object.__setattr__(
                self,
                "library_revision",
                _immutable_revision(self.library_revision, "quantization.library_revision"),
            )
        object.__setattr__(
            self,
            "source_revision",
            _immutable_revision(self.source_revision, "quantization.source_revision"),
        )
        object.__setattr__(
            self,
            "config_sha256",
            _sha256(self.config_sha256, "quantization.config_sha256"),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuantizationSpec:
        return cls(**data)


@dataclass(frozen=True)
class RuntimeSpec:
    """Inference and harness factors that can change measured behavior."""

    execution_mode: ExecutionMode
    dtype: str
    chat_template_sha256: str
    reasoning_mode: str
    context_limit: int
    tool_protocol: str | None = None
    agent_harness: str | None = None
    agent_harness_revision: str | None = None
    sampler: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_mode", ExecutionMode(self.execution_mode))
        object.__setattr__(
            self,
            "chat_template_sha256",
            _sha256(self.chat_template_sha256, "runtime.chat_template_sha256"),
        )
        if self.context_limit < 1:
            raise ValueError("runtime.context_limit must be positive")
        required_sampler = {"temperature", "max_tokens", "seed"}
        missing_sampler = required_sampler - self.sampler.keys()
        if missing_sampler:
            raise ValueError(
                "runtime.sampler is missing required values: " + ", ".join(sorted(missing_sampler))
            )
        if self.reasoning_mode not in {"on", "off", "auto"}:
            raise ValueError("runtime.reasoning_mode must be on, off, or auto")
        if self.execution_mode is ExecutionMode.AGENT_HARNESS and not self.agent_harness:
            raise ValueError("runtime.agent_harness is required for agent-harness execution")
        if self.agent_harness_revision is not None:
            object.__setattr__(
                self,
                "agent_harness_revision",
                _immutable_revision(self.agent_harness_revision, "runtime.agent_harness_revision"),
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeSpec:
        return cls(**data)


@dataclass(frozen=True)
class ModelSpec:
    """A fully qualified model variant used in a reproducible study."""

    id: str
    model: str
    family: str
    lineage_role: LineageRole
    source: str
    checkpoint_revision: str
    comparison_group: str
    provider: str
    runtime: RuntimeSpec
    interventions: tuple[InterventionSpec, ...] = ()
    quantization: QuantizationSpec | None = None
    provenance_status: ProvenanceStatus = ProvenanceStatus.COMPLETE
    evidence_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "lineage_role", LineageRole(self.lineage_role))
        object.__setattr__(self, "provenance_status", ProvenanceStatus(self.provenance_status))
        object.__setattr__(
            self,
            "checkpoint_revision",
            _immutable_revision(self.checkpoint_revision, "model.checkpoint_revision"),
        )
        if not all(
            (self.id, self.model, self.family, self.source, self.comparison_group, self.provider)
        ):
            raise ValueError("qualified model identity fields cannot be empty")
        if self.lineage_role is LineageRole.INTERVENTION and not self.interventions:
            raise ValueError("intervention models must declare at least one intervention")
        if self.lineage_role is not LineageRole.INTERVENTION and self.interventions:
            raise ValueError("only intervention models may declare interventions")
        if self.provenance_status is ProvenanceStatus.COMPLETE and self.evidence_gaps:
            raise ValueError("complete model provenance cannot declare evidence gaps")
        if self.provenance_status is ProvenanceStatus.RECONSTRUCTED_WITH_GAPS:
            if not self.evidence_gaps:
                raise ValueError("reconstructed model provenance must enumerate evidence gaps")
        elif any(item.implementation_revision is None for item in self.interventions):
            raise ValueError("complete intervention provenance requires an implementation revision")
        if (
            self.runtime.execution_mode is ExecutionMode.AGENT_HARNESS
            and not self.runtime.agent_harness_revision
            and self.provenance_status is ProvenanceStatus.COMPLETE
        ):
            raise ValueError("complete agent-harness provenance requires a harness revision")
        if (
            self.quantization is not None
            and self.quantization.library_revision is None
            and self.provenance_status is ProvenanceStatus.COMPLETE
        ):
            raise ValueError("complete quantization provenance requires a library revision")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelSpec:
        payload = dict(data)
        runtime = payload.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("qualified models require a runtime object")
        payload["runtime"] = RuntimeSpec.from_dict(runtime)
        payload["interventions"] = tuple(
            InterventionSpec.from_dict(item) for item in payload.get("interventions", [])
        )
        payload["evidence_gaps"] = tuple(payload.get("evidence_gaps", []))
        quantization = payload.get("quantization")
        payload["quantization"] = (
            QuantizationSpec.from_dict(quantization) if quantization is not None else None
        )
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        """Serialize enums as their stable wire values."""
        result = asdict(self)
        result["lineage_role"] = self.lineage_role.value
        result["provenance_status"] = self.provenance_status.value
        result["runtime"]["execution_mode"] = self.runtime.execution_mode.value
        return result

    @property
    def checkpoint_identity(self) -> tuple[str, str]:
        return self.source, self.checkpoint_revision
