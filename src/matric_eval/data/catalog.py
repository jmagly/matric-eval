"""Reviewed public source catalog, independent of tasks and scorer selection."""

from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any, Literal, Self

from pydantic import model_validator

from matric_eval.results.contract import Record, Text


class DatasetSource(Record):
    id: Text
    title: Text
    domains: list[str]
    status: str
    acquisition: dict[str, Any]
    upstream: dict[str, Any]
    source_url: Text
    source_docs: list[Any]
    configurations: list[str]
    splits: list[str]
    native_layout_notes: str = ""
    native_labels: dict[str, Any]
    license: dict[str, Any]
    access: dict[str, Any]
    group_identity_hints: list[Any]
    reported_size: Any
    files: list[dict[str, Any]]

    @model_validator(mode="after")
    def safe_identity(self) -> Self:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", self.id):
            raise ValueError("invalid_catalog_source_id")
        revision = self.upstream.get("revision")
        if revision is not None and not re.fullmatch(r"[0-9a-f]{40,64}", revision):
            raise ValueError("catalog_revision_requires_immutable_commit")
        if self.access.get("status") not in {"public", "gated", "restricted", "review_required"}:
            raise ValueError("unknown_catalog_access_status")
        return self


class DatasetCatalog(Record):
    schema_version: Literal[1] = 1
    catalog_id: Text
    reviewed_at: Text
    scope_notes: list[str]
    sources: list[DatasetSource]

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("duplicate_catalog_source")
        return self


def load_catalog() -> DatasetCatalog:
    return DatasetCatalog.model_validate(
        json.loads(files("matric_eval.data").joinpath("public_sources.json").read_text())
    )


def get_source(source_id: str) -> DatasetSource:
    for source in load_catalog().sources:
        if source.id == source_id:
            return source
    raise ValueError("unknown_dataset_source")
