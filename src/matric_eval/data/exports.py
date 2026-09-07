"""Permitted synthetic SFT export, with current authorization before every reuse."""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Any

from matric_eval.contamination.diagnostics import strict_json
from matric_eval.data.access import SourceVault, private_descriptor
from matric_eval.data.role_ledger import RoleLedger
from matric_eval.data.roles import (
    ExportManifest,
    ExportRequest,
    ExportRow,
    RoleError,
    RoleInventory,
    SFTRecord,
    canonical,
    moment,
    now,
    sha256,
)


def _tokens(payload: bytes) -> set[str]:
    return set(unicodedata.normalize("NFC", payload.decode("utf-8")).casefold().split())


def plan_export(vault: SourceVault, ledger: RoleLedger, request: ExportRequest) -> dict[str, Any]:
    """Call inside a ledger transaction to bind decisions to the exact cutoff."""
    request = ExportRequest.model_validate(request.model_dump())
    inventory, inventory_hash = vault.inventory()
    identity = ledger.connection.execute("SELECT inventory_sha256 FROM identity").fetchone()
    if identity is None or identity[0] != inventory_hash:
        raise RoleError("ledger_inventory_or_version_mismatch")
    ledger.ancestors(request.checkpoint_sha256)
    expired = moment(now()) >= moment(inventory.expires_at)
    withdrawn = ledger.withdrawn()
    rows = {row.data.row_id: row for row in inventory.rows}
    final = [row for row in inventory.rows if row.data.role == "final_test"]
    decisions = []
    pairs_checked = 0
    for row_id in request.row_ids:
        row = rows.get(row_id)
        reasons: list[str] = []
        if row is None:
            reasons.append("row_not_in_custodian_inventory")
        else:
            if not inventory.synthetic_only:
                reasons.append("real_materialization_unsupported")
            if request.kind != "sft":
                reasons.append("export_kind_unsupported")
            if expired:
                reasons.append("grant_expired")
            if request.recipient != inventory.recipient:
                reasons.append("recipient_not_permitted")
            if row_id in withdrawn:
                reasons.append("withdrawn")
            if row.data.role == "final_test":
                reasons.append("final_test_export_denied")
            elif row.data.role == "unknown":
                reasons.append("unknown_partition_role")
            elif row.data.role not in {"training", "development"}:
                reasons.append("role_unsupported_by_sft_profile")
            if row.access != "permitted":
                reasons.append("restricted_access")
            if "sft_export" not in row.permitted_uses:
                reasons.append("sft_use_not_permitted")
            if row.label_origin == "judge":
                # Preserve the calibration identity without claiming it is
                # unqualified: this profile does not materialize judge labels.
                reasons.append("judge_export_profile_unsupported")
            elif row.label_origin != "synthetic":
                reasons.append("label_origin_unsupported_by_synthetic_profile")
            if any(
                other.data.row_id != row_id and other.input_sha256 == row.input_sha256
                for other in final
            ):
                reasons.append("input_matches_final_holdout")
            if any(
                other.data.row_id != row_id
                and other.data.independent_unit_id == row.data.independent_unit_id
                for other in final
            ):
                reasons.append("independent_unit_crosses_holdout_boundary")
            if final and inventory.near_duplicate_threshold is None:
                reasons.append("protected_near_duplicate_check_unavailable")
            elif final:
                tokens = _tokens(vault.read(row.input_file))
                for other in final:
                    if other.data.row_id == row_id:
                        continue
                    other_tokens = _tokens(vault.read(other.input_file))
                    pairs_checked += 1
                    union = tokens | other_tokens
                    similarity = len(tokens & other_tokens) / len(union) if union else 1.0
                    if (
                        inventory.near_duplicate_threshold is not None
                        and similarity >= inventory.near_duplicate_threshold
                    ):
                        reasons.append("suspected_near_duplicate_holdout")
                        break
        decisions.append(
            {
                "row_id": row_id,
                "allowed": not reasons,
                "reasons": reasons,
                "data": row.data.model_dump() if row else None,
                "scorer_version": row.scorer_version if row else None,
                "rubric_version": row.rubric_version if row else None,
                "label_origin": row.label_origin if row else None,
                "calibration_sha256": row.calibration_sha256 if row else None,
            }
        )
    allowed = [item["row_id"] for item in decisions if item["allowed"]]
    policy_state = {
        "inventory_sha256": inventory_hash,
        "withdrawn": sorted(withdrawn),
        "checkpoints": ledger.checkpoints(),
        "disclosures": [event for event in ledger.events("role_use") if event["final_disclosure"]],
    }
    return {
        "plan_version": "1",
        "inventory_sha256": inventory_hash,
        "authorization_sha256": sha256(canonical(policy_state)),
        "ledger_cutoff": ledger.cutoff(),
        "decisions": decisions,
        "allowed_row_ids": allowed,
        "eligible": bool(allowed)
        and (request.allow_subset or len(allowed) == len(request.row_ids)),
        "near_duplicate_method": "nfc-casefold-whitespace-token-jaccard/1",
        "near_duplicate_threshold": inventory.near_duplicate_threshold,
        "near_duplicate_pairs_checked": pairs_checked,
        "limits": ["declared_inventory_scope", "near_duplicates_unverified", "synthetic_only"],
    }


def dry_run(vault: SourceVault, ledger: RoleLedger, request: ExportRequest) -> dict[str, Any]:
    ledger.intent(request.model_dump())
    with ledger.transaction():
        result = plan_export(vault, ledger, request)
        ledger.receipt(request.request_id, "dry_run", _audit_plan(result))
        return result


def _audit_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "inventory_sha256": plan["inventory_sha256"],
        "authorization_sha256": plan["authorization_sha256"],
        "ledger_cutoff": plan["ledger_cutoff"],
        "eligible": plan["eligible"],
        "decisions": [
            {
                "row_identity_sha256": sha256(item["row_id"].encode()),
                "allowed": item["allowed"],
                "reasons": item["reasons"],
            }
            for item in plan["decisions"]
        ],
    }


def _material(
    inventory: RoleInventory,
    inventory_hash: str,
    vault: SourceVault,
    request: ExportRequest,
    plan: dict[str, Any],
) -> tuple[bytes, bytes]:
    by_id = {row.data.row_id: row for row in inventory.rows}
    payload = bytearray()
    rows = []
    for row_id in plan["allowed_row_ids"]:
        row = by_id[row_id]
        raw = vault.read(row.input_file)
        if sha256(raw) != row.input_sha256:
            raise RoleError("source_changed_during_publication")
        item = SFTRecord(input=raw.decode("utf-8"), target=row.target)
        serialized = canonical(item.model_dump())
        payload.extend(serialized + b"\n")
        if len(payload) > 4 * 1024 * 1024:
            raise RoleError("export_artifact_limit")
        rows.append(
            ExportRow(
                data=row.data,
                input_sha256=row.input_sha256,
                record_sha256=sha256(serialized),
                scorer_version=row.scorer_version,
                rubric_version=row.rubric_version,
                calibration_sha256=row.calibration_sha256,
            )
        )
    manifest = ExportManifest(
        inventory_sha256=inventory_hash,
        source_revision=inventory.source_revision,
        consent_sha256=inventory.consent_sha256,
        license_id=inventory.license_id,
        owner=inventory.owner,
        retention_owner=inventory.retention_owner,
        recipient=request.recipient,
        protocol_sha256=request.protocol_sha256,
        checkpoint_sha256=request.checkpoint_sha256,
        authorization_sha256=plan["authorization_sha256"],
        payload_sha256=sha256(bytes(payload)),
        rows=rows,
        limits=plan["limits"],
        near_duplicate_threshold=plan["near_duplicate_threshold"],
        near_duplicate_pairs_checked=plan["near_duplicate_pairs_checked"],
    )
    return bytes(payload), canonical(manifest.model_dump()) + b"\n"


def _write_exclusive(directory: int, name: str, payload: bytes) -> None:
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(directory)


def _read_output(directory: int, name: str) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        private_descriptor(fd, directory=False)
        with os.fdopen(os.dup(fd), "rb") as stream:
            payload = stream.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise RoleError("export_artifact_limit")
        return payload
    finally:
        os.close(fd)


def _export_sft(
    vault: SourceVault, ledger: RoleLedger, request: ExportRequest, output: Path
) -> dict[str, Any]:
    request = ExportRequest.model_validate(request.model_dump())
    ledger.intent(request.model_dump())
    with ledger.transaction():
        checked = plan_export(vault, ledger, request)
        ledger.receipt(request.request_id, "policy_checked", _audit_plan(checked))
    # Policy-check receipt survives a crash during publication. The second
    # transaction rechecks revocation and serializes release against withdrawal.
    result: dict[str, Any]
    with ledger.transaction():
        plan = plan_export(vault, ledger, request)
        if not plan["eligible"]:
            ledger.receipt(request.request_id, "denied", _audit_plan(plan))
            return {"status": "denied", "plan": plan, "manifest": None}
        inventory, inventory_hash = vault.inventory()
        payload, manifest = _material(inventory, inventory_hash, vault, request, plan)
        stem = sha256(request.request_id.encode())
        names = (stem + ".jsonl", stem + ".manifest.json")
        directory = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            private_descriptor(directory, directory=True)
            prior = ledger.accepted(request.request_id)
            if prior:
                if (
                    sha256(_read_output(directory, names[0])),
                    sha256(_read_output(directory, names[1])),
                ) != (sha256(payload), sha256(manifest)):
                    raise RoleError("accepted_artifact_changed")
                ledger.receipt(request.request_id, "reused", _audit_plan(plan))
                return {
                    "status": "reused",
                    "plan": plan,
                    "manifest": strict_json(manifest.decode()),
                }
            # Existing files without acceptance are orphans, never overwritten.
            # If manifest creation fails, the exclusively created payload remains
            # an unreleased orphan for diagnosis, not a success on retry.
            _write_exclusive(directory, names[0], payload)
            _write_exclusive(directory, names[1], manifest)
            final = plan_export(vault, ledger, request)
            if (
                not final["eligible"]
                or final["authorization_sha256"] != plan["authorization_sha256"]
            ):
                raise RoleError("authorization_changed_during_publication")
            receipt = {
                "payload_sha256": sha256(payload),
                "manifest_sha256": sha256(manifest),
                "ledger_cutoff": plan["ledger_cutoff"],
                "authorization_sha256": plan["authorization_sha256"],
            }
            ledger.receipt(request.request_id, "accepted", receipt)
            ledger._event(
                "export",
                "export:" + sha256(request.request_id.encode()),
                {
                    "purpose": "sft_export",
                    "input_sha256": sha256(
                        canonical(
                            [
                                row.model_dump()
                                for row in ExportManifest.model_validate(
                                    strict_json(manifest.decode())
                                ).rows
                            ]
                        )
                    ),
                    "output_sha256": sha256(payload),
                    "manifest_sha256": sha256(manifest),
                    "checkpoint_sha256": request.checkpoint_sha256,
                    "protocol_sha256": request.protocol_sha256,
                },
            )
            result = {
                "status": "accepted",
                "plan": plan,
                "manifest": strict_json(manifest.decode()),
            }
        except (OSError, UnicodeError, ValueError) as exc:
            # Retain failure outside this rolled-back transaction below callers;
            # the already committed intent/policy receipt still identifies it.
            raise RoleError("publication_unavailable_or_orphaned") from exc
        finally:
            os.close(directory)
    return result


def export_sft(
    vault: SourceVault, ledger: RoleLedger, request: ExportRequest, output: Path
) -> dict[str, Any]:
    try:
        return _export_sft(vault, ledger, request, output)
    except (OSError, UnicodeError, ValueError) as exc:
        with ledger.transaction():
            ledger.receipt(
                request.request_id, "failed", {"reason": "publication_unavailable_or_orphaned"}
            )
        raise RoleError("publication_unavailable_or_orphaned") from exc


def read_sft_export(
    manifest_payload: bytes, records_payload: bytes
) -> tuple[ExportManifest, list[SFTRecord]]:
    """Validate schema, hashes, order and roles without inferring use permission."""
    try:
        manifest = ExportManifest.model_validate(strict_json(manifest_payload.decode("utf-8")))
        if sha256(records_payload) != manifest.payload_sha256 or not records_payload.endswith(
            b"\n"
        ):
            raise RoleError("export_payload_mismatch")
        records = [
            SFTRecord.model_validate(strict_json(line))
            for line in records_payload.decode("utf-8").splitlines()
        ]
        if len(records) != len(manifest.rows):
            raise RoleError("export_row_count_mismatch")
        keys = []
        for item, row in zip(records, manifest.rows, strict=True):
            if row.data.role not in {"training", "development"}:
                raise RoleError("export_profile_mismatch")
            if (
                sha256(item.input.encode()) != row.input_sha256
                or sha256(canonical(item.model_dump())) != row.record_sha256
            ):
                raise RoleError("export_record_mismatch")
            keys.append((row.data.source_id, row.data.row_id))
        if len(keys) != len(set(keys)):
            raise RoleError("export_duplicate_row")
        return manifest, records
    except (ValueError, TypeError, UnicodeError) as exc:
        raise RoleError("invalid_sft_export") from exc
