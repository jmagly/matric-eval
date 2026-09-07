"""Declared recovery identities and conservative replay decisions.

These models validate supplied evidence; they do not capture or attest provider,
filesystem, or worker state. Adapters remain responsible for that evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal, Self

from pydantic import field_validator, model_validator

from matric_eval.results.contract import ArtifactReference, Eligibility, Record, Text

COMPONENTS = ("model", "dataset", "prompt", "scorer", "sampler", "environment", "protocol")


def _validate_document(value: object) -> object:
    """Reject Python-only objects and coercions before Pydantic touches values."""
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str or not key.strip():
                raise ValueError("identity document keys must be nonempty strings")
            key.encode("utf-8")
            _validate_document(child)
    elif type(value) is list:
        for child in value:
            _validate_document(child)
    elif type(value) is str:
        value.encode("utf-8")
    elif value is None:
        pass
    elif type(value) is bool:
        pass  # A JSON boolean remains a boolean, never a numeric identity.
    elif type(value) is int:
        if abs(value) > 9007199254740991:
            raise ValueError("identity integers must be exactly representable in JSON consumers")
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("identity numbers must be finite")
    else:
        raise ValueError("identity documents require nonempty strict JSON values")
    return value


def canonical_json(document: object) -> str:
    """Version-1 encoding: UTF-8, sorted keys, compact finite JSON, no coercion."""
    return json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


class FingerprintComponent(Record):
    document: dict[str, Any]
    status: Literal["verified", "unverified"]
    unavailable_reason: Text | None = None

    @field_validator("document", mode="before")
    @classmethod
    def strict_document(cls, value: object) -> object:
        if type(value) is not dict or not value:
            raise ValueError("component document must be a nonempty object")
        return _validate_document(value)

    @model_validator(mode="after")
    def evidence_status(self) -> Self:
        if (self.status == "unverified") != (self.unavailable_reason is not None):
            raise ValueError("unverified components require an unavailable reason only")
        if set(self.document) <= {"sha256", "digest", "fingerprint"}:
            raise ValueError("an opaque digest alone is not an execution identity document")
        return self


class ExecutionFingerprint(Record):
    version: Literal["1"] = "1"
    model: FingerprintComponent
    dataset: FingerprintComponent
    prompt: FingerprintComponent
    scorer: FingerprintComponent
    sampler: FingerprintComponent
    environment: FingerprintComponent
    protocol: FingerprintComponent

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.model_dump()).encode("utf-8")).hexdigest()

    @property
    def eligibility(self) -> Eligibility:
        reasons = [
            f"component_unknown:{name}"
            for name in COMPONENTS
            if getattr(self, name).status != "verified"
        ]
        return Eligibility(eligible=not reasons, reasons=reasons)

    def mismatch_reasons(self, current: ExecutionFingerprint) -> list[str]:
        reasons: list[str] = []
        for name in COMPONENTS:
            retained = getattr(self, name)
            effective = getattr(current, name)
            if retained.status != "verified" or effective.status != "verified":
                reasons.append(f"component_unknown:{name}")
            if canonical_json(retained.document) != canonical_json(effective.document):
                reasons.append(f"component_mismatch:{name}")
        return reasons


class ReplayCapability(Record):
    version: Literal["1"] = "1"
    adapter_id: Text
    mode: Literal["isolated", "idempotent", "manual"]
    mechanism_version: Text
    idempotency_key: Text | None = None

    @model_validator(mode="after")
    def keyed_mechanism(self) -> Self:
        if (self.mode == "idempotent") != (self.idempotency_key is not None):
            raise ValueError("only idempotent adapters require an idempotency key")
        return self


class CleanupReceipt(Record):
    version: Literal["1"] = "1"
    attempt_id: Text
    worker_id: Text | None = None
    status: Literal["verified_absent", "uncertain", "not_required"]
    evidence: ArtifactReference | None = None

    @model_validator(mode="after")
    def bound_worker(self) -> Self:
        if self.status == "verified_absent" and (
            self.worker_id is None or self.evidence is None or self.evidence.sha256 is None
        ):
            raise ValueError(
                "verified absence requires an exact worker and verified evidence artifact"
            )
        return self


class RecoveryDecision(Record):
    action: Literal["check_acceptance", "execute", "replay", "manual"]
    reasons: list[Text]


def recovery_decision(
    capability: ReplayCapability,
    *,
    intent_exists: bool,
    terminal_committed: bool,
    cleanup: CleanupReceipt | None = None,
    expected_attempt_id: str,
) -> RecoveryDecision:
    """Return permission to consider execution; never reconcile an external action.

    A keyed capability alone cannot prove reconciliation, so uncertain keyed
    work remains manual until an adapter supplies that mechanism separately.
    A committed terminal may be a losing attempt. ``check_acceptance`` grants
    no reuse permission: the journal must verify its authoritative acceptance,
    complete identities, current fingerprint and cleanup via ``load_accepted``.
    """
    if type(intent_exists) is not bool or type(terminal_committed) is not bool:
        raise ValueError("recovery state flags must be booleans")
    if not isinstance(expected_attempt_id, str) or not expected_attempt_id.strip():
        raise ValueError("expected attempt identity is required")
    if cleanup is not None and cleanup.attempt_id != expected_attempt_id:
        return RecoveryDecision(action="manual", reasons=["cleanup_attempt_mismatch"])
    if terminal_committed:
        if (
            intent_exists
            and capability.mode == "isolated"
            and (cleanup is None or cleanup.status != "verified_absent")
        ):
            return RecoveryDecision(action="manual", reasons=["cleanup_unverified"])
        return (
            RecoveryDecision(action="check_acceptance", reasons=[])
            if intent_exists
            else RecoveryDecision(action="manual", reasons=["terminal_without_intent"])
        )
    if not intent_exists:
        return RecoveryDecision(action="execute", reasons=[])
    if capability.mode == "isolated":
        if cleanup is None or cleanup.status != "verified_absent":
            return RecoveryDecision(action="manual", reasons=["cleanup_unverified"])
        return RecoveryDecision(action="replay", reasons=[])
    reason = (
        "reconciliation_required" if capability.mode == "idempotent" else "unsafe_external_replay"
    )
    return RecoveryDecision(action="manual", reasons=[reason])
