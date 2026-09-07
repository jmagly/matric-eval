"""Hand-specified identity distinctions and conservative replay cases."""

import copy
import hashlib
import json
from typing import Any

import pytest
from pydantic import ValidationError

from matric_eval.state.observation_identity import (
    COMPONENTS,
    CleanupReceipt,
    ExecutionFingerprint,
    FingerprintComponent,
    ReplayCapability,
    recovery_decision,
)


def fingerprint_data() -> dict[str, Any]:
    return {
        name: {
            "document": {"revision": f"{name}-1", "configuration": {"seed": 7}},
            "status": "verified",
        }
        for name in COMPONENTS
    }


def capability(mode: str = "isolated") -> ReplayCapability:
    return ReplayCapability.model_validate(
        {
            "adapter_id": "fixture-adapter",
            "mode": mode,
            "mechanism_version": "1",
            "idempotency_key": "stable-request-1" if mode == "idempotent" else None,
        }
    )


def receipt() -> CleanupReceipt:
    return CleanupReceipt.model_validate(
        {
            "attempt_id": "attempt-1",
            "worker_id": "exact-container-1",
            "status": "verified_absent",
            "evidence": {"uri": "fixture:cleanup", "sha256": "a" * 64, "unavailable_reason": None},
        }
    )


def test_digest_canonical_document_and_order_independence() -> None:
    first = ExecutionFingerprint.model_validate(fingerprint_data())
    reordered = dict(reversed(list(fingerprint_data().items())))
    second = ExecutionFingerprint.model_validate(reordered)
    independently_encoded = json.dumps(
        first.model_dump(),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    assert first.sha256 == hashlib.sha256(independently_encoded.encode("utf-8")).hexdigest()
    assert first.sha256 == second.sha256
    assert first.mismatch_reasons(second) == []
    assert first.eligibility.eligible


@pytest.mark.parametrize("component", COMPONENTS)
def test_each_changed_component_blocks_reuse(component: str) -> None:
    original = ExecutionFingerprint.model_validate(fingerprint_data())
    changed = fingerprint_data()
    changed[component]["document"]["revision"] = "changed"
    current = ExecutionFingerprint.model_validate(changed)
    assert original.mismatch_reasons(current) == [f"component_mismatch:{component}"]
    assert original.sha256 != current.sha256


def test_unknown_components_and_mismatch_reasons_follow_contract_order() -> None:
    data = fingerprint_data()
    for name in ("model", "environment"):
        data[name].update(
            status="unverified", unavailable_reason="effective revision not available"
        )
    unknown = ExecutionFingerprint.model_validate(data)
    assert unknown.eligibility.reasons == [
        "component_unknown:model",
        "component_unknown:environment",
    ]
    assert not unknown.eligibility.eligible
    assert unknown.mismatch_reasons(unknown) == unknown.eligibility.reasons
    changed = copy.deepcopy(data)
    changed["model"]["document"]["revision"] = "different"
    assert unknown.mismatch_reasons(ExecutionFingerprint.model_validate(changed)) == [
        "component_unknown:model",
        "component_mismatch:model",
        "component_unknown:environment",
    ]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), (1, 2), b"text", 9007199254740992])
def test_component_rejects_empty_nonfinite_and_non_json_values(value: Any) -> None:
    with pytest.raises((ValidationError, ValueError)):
        FingerprintComponent(document={"revision": value}, status="verified")


def test_nested_empty_configuration_values_are_preserved() -> None:
    document = {"revision": "1", "stop": [], "options": {}, "seed": None, "prefix": ""}
    assert FingerprintComponent(document=document, status="verified").document == document
    with pytest.raises(ValidationError):
        FingerprintComponent(document={}, status="verified")


def test_no_boolean_numeric_coercion_or_digest_only_identity() -> None:
    true_data = fingerprint_data()
    one_data = fingerprint_data()
    true_data["model"]["document"]["configuration"]["seed"] = True
    one_data["model"]["document"]["configuration"]["seed"] = 1
    left = ExecutionFingerprint.model_validate(true_data)
    right = ExecutionFingerprint.model_validate(one_data)
    assert left.model.document["configuration"]["seed"] is True
    assert left.mismatch_reasons(right) == ["component_mismatch:model"]
    with pytest.raises(ValidationError):
        FingerprintComponent(document={"sha256": "a" * 64}, status="verified")


@pytest.mark.parametrize("change", [{"version": "2"}, {"extra": "unknown"}, {"model": None}])
def test_unknown_fields_versions_and_missing_components_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ExecutionFingerprint.model_validate({**fingerprint_data(), **change})
    data = fingerprint_data()
    del data["protocol"]
    with pytest.raises(ValidationError):
        ExecutionFingerprint.model_validate(data)


@pytest.mark.parametrize("status,reason", [("verified", "unknown"), ("unverified", None)])
def test_evidence_reason_matches_status(status: str, reason: str | None) -> None:
    with pytest.raises(ValidationError):
        FingerprintComponent.model_validate(
            {"document": {"revision": "1"}, "status": status, "unavailable_reason": reason}
        )


def test_recovery_requires_bound_verified_cleanup_for_isolated_replay() -> None:
    kwargs: dict[str, Any] = {
        "intent_exists": True,
        "terminal_committed": False,
        "expected_attempt_id": "attempt-1",
    }
    assert recovery_decision(capability(), **kwargs).reasons == ["cleanup_unverified"]
    assert recovery_decision(capability(), cleanup=receipt(), **kwargs).action == "replay"
    wrong = receipt().model_copy(update={"attempt_id": "other-attempt"})
    assert recovery_decision(capability(), cleanup=wrong, **kwargs).reasons == [
        "cleanup_attempt_mismatch"
    ]
    for status in ("uncertain", "not_required"):
        unverified = CleanupReceipt.model_validate({"attempt_id": "attempt-1", "status": status})
        assert recovery_decision(capability(), cleanup=unverified, **kwargs).action == "manual"


def test_external_capability_does_not_invent_reconciliation() -> None:
    for mode, reason in (
        ("manual", "unsafe_external_replay"),
        ("idempotent", "reconciliation_required"),
    ):
        decision = recovery_decision(
            capability(mode),
            intent_exists=True,
            terminal_committed=False,
            cleanup=receipt(),
            expected_attempt_id="attempt-1",
        )
        assert decision.action == "manual"
        assert decision.reasons == [reason]


def test_initial_dispatch_and_terminal_reuse_are_distinct() -> None:
    assert (
        recovery_decision(
            capability("manual"),
            intent_exists=False,
            terminal_committed=False,
            expected_attempt_id="attempt-1",
        ).action
        == "execute"
    )
    assert (
        recovery_decision(
            capability("manual"),
            intent_exists=True,
            terminal_committed=True,
            expected_attempt_id="attempt-1",
        ).action
        == "check_acceptance"
    )
    assert recovery_decision(
        capability(), intent_exists=False, terminal_committed=True, expected_attempt_id="attempt-1"
    ).reasons == ["terminal_without_intent"]
    with pytest.raises(ValueError):
        recovery_decision(
            capability(), intent_exists=1, terminal_committed=False, expected_attempt_id="attempt-1"
        )  # type: ignore[arg-type]


def test_key_and_verified_receipt_evidence_are_required() -> None:
    for mode, key in (("idempotent", None), ("manual", "key"), ("isolated", "key")):
        with pytest.raises(ValidationError):
            ReplayCapability.model_validate(
                {
                    "adapter_id": "adapter",
                    "mode": mode,
                    "mechanism_version": "1",
                    "idempotency_key": key,
                }
            )
    for changes in (
        {"worker_id": None},
        {"evidence": None},
        {
            "evidence": {
                "uri": "fixture:missing",
                "sha256": None,
                "unavailable_reason": "not retained",
            }
        },
    ):
        with pytest.raises(ValidationError):
            CleanupReceipt.model_validate({**receipt().model_dump(), **changes})


def test_isolated_terminal_reuse_still_requires_verified_cleanup() -> None:
    kwargs: dict[str, Any] = {
        "intent_exists": True,
        "terminal_committed": True,
        "expected_attempt_id": "attempt-1",
    }
    assert recovery_decision(capability(), **kwargs).reasons == ["cleanup_unverified"]
    for status in ("uncertain", "not_required"):
        unverified = CleanupReceipt.model_validate({"attempt_id": "attempt-1", "status": status})
        assert recovery_decision(capability(), cleanup=unverified, **kwargs).action == "manual"
    assert recovery_decision(capability(), cleanup=receipt(), **kwargs).action == "check_acceptance"


def test_fingerprint_wire_roundtrip_is_strict() -> None:
    fingerprint = ExecutionFingerprint.model_validate(fingerprint_data())
    reread = ExecutionFingerprint.model_validate_json(fingerprint.model_dump_json())
    assert reread.sha256 == fingerprint.sha256
    assert reread.mismatch_reasons(fingerprint) == []
