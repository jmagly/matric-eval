"""Lossless JSON records with verifiable source and artifact identities."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import Field, JsonValue, model_validator

from matric_eval.data.roles import canonical, sha256
from matric_eval.results.contract import Digest, Record, Text


class EvidenceRecord(Record):
    version: Literal["1"] = "1"
    source_id: Text
    source_revision: Text
    configuration: str | None = None
    split: str | None = None
    artifact_path: Text
    artifact_sha256: Digest
    row_index: int = Field(ge=0)
    native_id: JsonValue = None
    payload: dict[str, JsonValue]
    content_sha256: Digest
    record_id: Text
    cluster_id: Text | None = None

    def identity(self) -> dict[str, JsonValue]:
        return {
            key: getattr(self, key)
            for key in (
                "source_id",
                "source_revision",
                "configuration",
                "split",
                "artifact_path",
                "artifact_sha256",
                "row_index",
                "native_id",
                "cluster_id",
            )
        }

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if sha256(canonical(self.payload)) != self.content_sha256:
            raise ValueError("evidence_content_digest_mismatch")
        if self.record_id != f"{self.source_id}:{sha256(canonical(self.identity()))}":
            raise ValueError("evidence_identity_mismatch")
        return self


def make_evidence_record(
    payload: dict[str, JsonValue],
    *,
    source_id: str,
    source_revision: str,
    artifact_path: str,
    artifact_sha256: str,
    row_index: int,
    configuration: str | None = None,
    split: str | None = None,
    native_id: JsonValue = None,
    cluster_id: str | None = None,
) -> EvidenceRecord:
    identity = dict(
        source_id=source_id,
        source_revision=source_revision,
        configuration=configuration,
        split=split,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        row_index=row_index,
        native_id=native_id,
        cluster_id=cluster_id,
    )
    return EvidenceRecord.model_validate(
        {
            **identity,
            "payload": payload,
            "native_id": native_id,
            "cluster_id": cluster_id,
            "content_sha256": sha256(canonical(payload)),
            "record_id": f"{source_id}:{sha256(canonical(identity))}",
        }
    )


def _object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def read_json(text: str) -> JsonValue:
    """Reject duplicate keys and nonfinite values instead of silently changing data."""
    value: JsonValue = json.loads(text, object_pairs_hook=_object)
    canonical(value)
    return value


def read_payloads(path: Path, *, format: str) -> list[dict[str, JsonValue]]:
    """Read raw data only. CSV retains native strings; no upstream code executes."""
    if format == "parquet":
        import pyarrow.parquet as pq

        rows = pq.read_table(path).to_pylist()
    else:
        raw = path.read_bytes()
        if path.suffix == ".gz":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8-sig")
        if format == "jsonl":
            rows = [read_json(line) for line in text.splitlines() if line.strip()]
        elif format == "json":
            value = read_json(text)
            rows = value if isinstance(value, list) else [value]
        elif format == "csv":
            import io

            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("csv_requires_unique_headers")
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError("csv_row_width_mismatch")
        else:
            raise ValueError("unsupported_raw_format")
    if any(not isinstance(row, dict) or any(not isinstance(k, str) for k in row) for row in rows):
        raise ValueError("payload_requires_object_rows")
    # Validate JSON compatibility without converting dates, bytes or special floats.
    canonical(rows)
    return cast(list[dict[str, JsonValue]], rows)


def load_evidence(path: Path) -> list[EvidenceRecord]:
    return [
        EvidenceRecord.model_validate(read_json(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
