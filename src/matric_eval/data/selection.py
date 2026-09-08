"""Replayable whole-cluster selection with explicit roles and field filters."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal, Self

from pydantic import Field, JsonValue, model_validator

from matric_eval.data.evidence import EvidenceRecord
from matric_eval.data.roles import canonical
from matric_eval.results.contract import Count, Digest, PartitionRole, Record, Text


class SelectionError(ValueError):
    """Stable content-free selection or projection failure."""


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def json_pointer(value: Any, pointer: str) -> Any:
    """Read RFC 6901 object/list locations without key or value coercion."""
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise SelectionError("invalid_json_pointer")
    if pointer == "":
        return value
    for encoded in pointer[1:].split("/"):
        if re.search(r"~(?![01])", encoded):
            raise SelectionError("invalid_json_pointer")
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            index = int(key)
            if index >= len(value):
                raise SelectionError("field_unavailable")
            value = value[index]
        else:
            raise SelectionError("field_unavailable")
    return value


class SourceSelection(Record):
    source_id: Text
    quota: Count
    configurations: list[str | None] | None = None
    splits: list[str | None] | None = None
    filters: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def scalar_filters(self) -> Self:
        for values in (self.configurations, self.splits):
            if values is not None and (not values or len(set(values)) != len(values)):
                raise SelectionError("selectors_require_unique_nonempty_values")
        for pointer, value in self.filters.items():
            if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
                raise SelectionError("invalid_filter_pointer")
            if isinstance(value, (dict, list)):
                raise SelectionError("filter_requires_scalar_equality")
            canonical(value)
        return self


class SelectionRequest(Record):
    version: Literal["1"] = "1"
    seed: Count
    role: PartitionRole
    sources: list[SourceSelection] = Field(min_length=1)

    @model_validator(mode="after")
    def source_identity(self) -> Self:
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise SelectionError("duplicate_source_request")
        if sum(source.quota for source in self.sources) == 0:
            raise SelectionError("empty_selection_request")
        return self


class SelectedRecord(Record):
    selection_id: Text
    evidence: EvidenceRecord


class SelectionManifest(Record):
    selection_schema_version: Literal["1"] = "1"
    algorithm: Literal["sha256-whole-cluster-greedy/1"] = "sha256-whole-cluster-greedy/1"
    request: SelectionRequest
    population_sha256: Digest
    records: list[SelectedRecord] = Field(min_length=1)
    manifest_sha256: Digest
    limitations: list[str] = Field(
        default_factory=lambda: [
            "intended_role_not_usage_authorization",
            "cross_manifest_role_ledger_required",
            "source_clusters_only_no_inferred_independence",
            "greedy_exact_quota_may_refuse_feasible_subset",
        ]
    )

    @model_validator(mode="after")
    def binding(self) -> Self:
        if self.limitations != [
            "intended_role_not_usage_authorization",
            "cross_manifest_role_ledger_required",
            "source_clusters_only_no_inferred_independence",
            "greedy_exact_quota_may_refuse_feasible_subset",
        ]:
            raise SelectionError("selection_limitations_mismatch")
        expected = digest(self.model_dump(exclude={"manifest_sha256"}))
        if self.manifest_sha256 != expected:
            raise SelectionError("selection_manifest_hash_mismatch")
        ids = [row.selection_id for row in self.records]
        if len(set(ids)) != len(ids):
            raise SelectionError("duplicate_selected_identity")
        requested = {source.source_id: source.quota for source in self.request.sources}
        counts = dict.fromkeys(requested, 0)
        for row in self.records:
            if row.evidence.source_id not in counts:
                raise SelectionError("selected_source_outside_request")
            counts[row.evidence.source_id] += 1
            specification = next(
                source
                for source in self.request.sources
                if source.source_id == row.evidence.source_id
            )
            if not _record_matches(row.evidence, specification):
                raise SelectionError("selected_record_filter_mismatch")
            if row.selection_id != _selection_id(row.evidence):
                raise SelectionError("selected_identity_mismatch")
        if counts != requested:
            raise SelectionError("selection_quota_mismatch")
        return self


def _selection_id(record: EvidenceRecord) -> str:
    return "selection:" + digest([record.source_id, record.record_id])


def _matches(payload: Any, filters: dict[str, JsonValue]) -> bool:
    for pointer, expected in filters.items():
        try:
            actual = json_pointer(payload, pointer)
        except SelectionError as exc:
            if str(exc) == "field_unavailable":
                return False
            raise
        # JSON true is not the integer 1; object/list values never equal scalars.
        if type(actual) is not type(expected) or actual != expected:
            return False
    return True


def _record_matches(record: EvidenceRecord, source: SourceSelection) -> bool:
    return (
        (source.configurations is None or record.configuration in source.configurations)
        and (source.splits is None or record.split in source.splits)
        and _matches(record.payload, source.filters)
    )


def select_records(records: list[EvidenceRecord], request: SelectionRequest) -> SelectionManifest:
    """Select exact source quotas without splitting declared cluster/content groups.

    Whole groups are ranked by SHA-256 of seed, source and stable members. A
    single greedy pass takes a group only if it fits the remaining quota. Failure
    is explicit; it never silently changes the quota or splits a group. Input
    ordering and request-source ordering do not change selection or manifest.
    """
    request = SelectionRequest.model_validate(request.model_dump())
    request.sources.sort(key=lambda source: source.source_id)
    for source in request.sources:
        for selector in (source.configurations, source.splits):
            if selector is not None:
                selector.sort(key=lambda value: (value is not None, value or ""))
    population = [EvidenceRecord.model_validate(record.model_dump()) for record in records]
    population.sort(key=lambda record: (record.source_id, record.record_id))
    identities = [(record.source_id, record.record_id) for record in population]
    if len(set(identities)) != len(identities):
        raise SelectionError("duplicate_evidence_identity")
    contents: dict[str, str] = {}
    for record in population:
        content = digest(record.payload)
        if content in contents and contents[content] != record.source_id:
            raise SelectionError("duplicate_content_across_sources")
        contents[content] = record.source_id
    selected: list[SelectedRecord] = []
    for source in request.sources:
        candidates = [record for record in population if record.source_id == source.source_id]
        if not candidates:
            raise SelectionError("requested_source_unavailable")
        # Union content duplicates and declared source-local clusters transitively.
        parents = list(range(len(candidates)))

        def root(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        keys: dict[tuple[str, str], int] = {}
        for index, record in enumerate(candidates):
            group_keys = [("content", digest(record.payload))]
            if record.cluster_id is not None:
                group_keys.append(("cluster", record.cluster_id))
            for key in group_keys:
                if key in keys:
                    parents[root(index)] = root(keys[key])
                else:
                    keys[key] = index
        groups: dict[int, list[EvidenceRecord]] = {}
        for index, record in enumerate(candidates):
            groups.setdefault(root(index), []).append(record)
        eligible = []
        for group in groups.values():
            matches = [_record_matches(record, source) for record in group]
            if any(matches) and not all(matches):
                raise SelectionError("filter_splits_cluster")
            if all(matches):
                eligible.append(group)
        eligible.sort(
            key=lambda group: digest(
                [request.seed, source.source_id, [record.record_id for record in group]]
            )
        )
        remaining = source.quota
        for group in eligible:
            if len(group) <= remaining:
                selected.extend(
                    SelectedRecord(selection_id=_selection_id(record), evidence=record)
                    for record in group
                )
                remaining -= len(group)
        if remaining:
            raise SelectionError("quota_unavailable_without_cluster_split")
    selected.sort(key=lambda row: row.selection_id)
    payload = {
        "selection_schema_version": "1",
        "algorithm": "sha256-whole-cluster-greedy/1",
        "request": request.model_dump(),
        "population_sha256": digest([record.model_dump() for record in population]),
        "records": [row.model_dump() for row in selected],
        "limitations": [
            "intended_role_not_usage_authorization",
            "cross_manifest_role_ledger_required",
            "source_clusters_only_no_inferred_independence",
            "greedy_exact_quota_may_refuse_feasible_subset",
        ],
    }
    return SelectionManifest.model_validate({**payload, "manifest_sha256": digest(payload)})


def verify_selection(manifest: SelectionManifest, records: list[EvidenceRecord]) -> None:
    manifest = SelectionManifest.model_validate(manifest.model_dump())
    replay = select_records(records, manifest.request)
    if canonical(replay.model_dump()) != canonical(manifest.model_dump()):
        raise SelectionError("selection_replay_mismatch")


def write_selection(manifest: SelectionManifest) -> str:
    verified = SelectionManifest.model_validate(manifest.model_dump())
    return canonical(verified.model_dump()).decode("utf-8") + "\n"


def read_selection(source: str) -> SelectionManifest:
    from matric_eval.results.consumer import strict_json

    try:
        return SelectionManifest.model_validate(strict_json(source))
    except (ValueError, TypeError):
        raise SelectionError("invalid_selection_manifest") from None
