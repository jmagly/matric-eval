"""Strict role contracts; partition and cluster identities use the result schema."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from matric_eval.contamination.diagnostics import strict_json
from matric_eval.results.contract import DataReference, Digest, Record, Text

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")]
UseKind = Literal[
    "sft_export",
    "final_assessment",
    "rubric_discovery",
    "prompt_example",
    "tuning",
    "checkpoint_selection",
]


class RoleError(ValueError):
    """A content-free role policy or integrity failure."""


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def moment(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RoleError("timezone_required")
    return parsed


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceRow(Record):
    data: DataReference
    input_file: Text
    input_sha256: Digest
    target: Text
    access: Literal["permitted", "restricted"]
    permitted_uses: list[UseKind]
    label_origin: Literal["synthetic", "judge", "human", "unknown"]
    scorer_version: Text
    rubric_version: Text
    calibration_sha256: Digest | None

    @model_validator(mode="after")
    def opaque_identity(self) -> Self:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", self.data.row_id):
            raise RoleError("opaque_row_identifier_required")
        return self


class RoleInventory(Record):
    role_inventory_version: Literal["1"] = "1"
    synthetic_only: bool
    source_id: Text
    source_revision: Digest
    completeness_scope: Text
    owner: Identifier
    retention_owner: Identifier
    recipient: Identifier
    license_id: Text
    consent_file: Text
    consent_sha256: Digest
    expires_at: Text
    near_duplicate_threshold: float | None = Field(default=None, ge=0, le=1)
    root_checkpoint_sha256: list[Digest]
    rows: list[SourceRow] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def boundaries(self) -> Self:
        moment(self.expires_at)
        identities = [row.data.row_id for row in self.rows]
        if len(identities) != len(set(identities)):
            raise RoleError("duplicate_row_identity")
        if any(row.data.source_id != self.source_id for row in self.rows):
            raise RoleError("inventory_source_mismatch")
        return self


class ExportRequest(Record):
    request_id: Identifier
    row_ids: list[Identifier] = Field(min_length=1, max_length=256)
    kind: Literal["sft", "preference", "reward"] = "sft"
    allow_subset: bool = False
    protocol_sha256: Digest
    checkpoint_sha256: Digest
    recipient: Identifier

    @model_validator(mode="after")
    def unique_rows(self) -> Self:
        if len(self.row_ids) != len(set(self.row_ids)):
            raise RoleError("duplicate_requested_row")
        return self


class SFTRecord(Record):
    input: Text
    target: Text


class ExportRow(Record):
    data: DataReference
    input_sha256: Digest
    record_sha256: Digest
    scorer_version: Text
    rubric_version: Text
    calibration_sha256: Digest | None
    label_origin: Literal["synthetic"] = "synthetic"


class ExportManifest(Record):
    export_schema_version: Literal["1"] = "1"
    format: Literal["matric-sft-jsonl/1"] = "matric-sft-jsonl/1"
    synthetic_only: Literal[True] = True
    inventory_sha256: Digest
    source_revision: Digest
    consent_sha256: Digest
    license_id: Text
    owner: Identifier
    retention_owner: Identifier
    recipient: Identifier
    protocol_sha256: Digest
    checkpoint_sha256: Digest
    policy_version: Literal["synthetic-sft/1"] = "synthetic-sft/1"
    authorization_sha256: Digest
    payload_sha256: Digest
    rows: list[ExportRow] = Field(min_length=1)
    duplicate_method: Literal["input-utf8-exact-and-shared-independent-unit/1"] = (
        "input-utf8-exact-and-shared-independent-unit/1"
    )
    near_duplicate_method: Literal["nfc-casefold-whitespace-token-jaccard/1"] = (
        "nfc-casefold-whitespace-token-jaccard/1"
    )
    near_duplicate_threshold: float | None = Field(ge=0, le=1)
    near_duplicate_pairs_checked: int = Field(ge=0)
    limits: list[
        Literal["declared_inventory_scope", "near_duplicates_unverified", "synthetic_only"]
    ]


class Checkpoint(Record):
    checkpoint_sha256: Digest
    parent_sha256: Digest | None
    reward_evidence_sha256: Digest | None
    independent_quality_evidence_sha256: Digest | None


class UseRecord(Record):
    event_id: Identifier
    purpose: UseKind
    row_ids: list[Identifier] = Field(min_length=1, max_length=256)
    checkpoint_sha256: Digest
    candidate_checkpoint_sha256: list[Digest] = Field(min_length=1)
    protocol_sha256: Digest
    policy_sha256: Digest | None
    output_sha256: Digest

    @model_validator(mode="after")
    def selection_scope(self) -> Self:
        if len(self.row_ids) != len(set(self.row_ids)) or len(
            self.candidate_checkpoint_sha256
        ) != len(set(self.candidate_checkpoint_sha256)):
            raise RoleError("duplicate_use_identity")
        if self.checkpoint_sha256 not in self.candidate_checkpoint_sha256:
            raise RoleError("selected_checkpoint_not_a_candidate")
        return self


def parse_inventory(payload: bytes) -> RoleInventory:
    try:
        return RoleInventory.model_validate(strict_json(payload.decode("utf-8")))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise RoleError("invalid_role_inventory") from exc
