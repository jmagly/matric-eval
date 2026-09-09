"""Pinned OBLITERATUS prompt-source imports and explicit derived views.

The import layer never imports or executes OBLITERATUS or upstream dataset code.
Raw rows become ordinary :class:`EvidenceRecord` objects before any prompt
projection.  OBLITERATUS-compatible pairings are separately named derived
views so repeated controls and historical semantic assumptions remain visible.
"""

from __future__ import annotations

import ast
import csv
import gzip
import hashlib
import io
import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, Self, cast

from pydantic import Field, JsonValue, model_validator

from matric_eval.data.acquisition import acquire_source
from matric_eval.data.catalog import DatasetSource
from matric_eval.data.evidence import EvidenceRecord, make_evidence_record, read_payloads
from matric_eval.data.roles import canonical, sha256
from matric_eval.datasets import (
    DatasetAccessError,
    DatasetOfflineError,
    DatasetSourceError,
)
from matric_eval.results.contract import Count, DataReference, Digest, Record, Text

SourceFormat = Literal["python-ast-pairs", "csv", "json.gz", "parquet", "tsv"]
SemanticLabel = Literal["harmful", "benign", "unknown"]
PromptForm = Literal[
    "builtin_harmful",
    "builtin_harmless",
    "vanilla",
    "adversarial",
    "first_human_turn",
    "capability_text",
    "generated_control",
]


class ObliteratusArtifact(Record):
    path: Text
    format: SourceFormat
    url: Text
    sha256: Digest | None
    checksum_unavailable_reason: Text | None
    repository_oid: str | None = Field(default=None, pattern=r"^[a-f0-9]{40,64}$")
    size_bytes: Count | None
    raw_count: Count | None
    accepted_count: Count | None

    @model_validator(mode="after")
    def checksum_evidence(self) -> Self:
        if (self.sha256 is None) != (self.checksum_unavailable_reason is not None):
            raise ValueError("artifact_needs_checksum_or_unavailable_reason")
        return self


class ProjectReference(Record):
    kind: Literal["github", "gitea", "huggingface"]
    repo: Text
    revision: Text
    url: Text

    @model_validator(mode="after")
    def immutable_revision(self) -> Self:
        if not re.fullmatch(r"[a-f0-9]{40,64}", self.revision):
            raise ValueError("source_revision_requires_immutable_commit")
        return self


class DatasetTerms(Record):
    identifier: Text
    status: Literal["publisher-stated", "review-required"]
    url: Text
    notes: Text


class ObliteratusSource(Record):
    id: Text
    title: Text
    canonical_id: Text
    original_project: ProjectReference
    distribution: ProjectReference
    inspected_revision: Text | None = None
    configuration: str | None
    split: str | None
    access: Literal["public", "gated"]
    artifact: ObliteratusArtifact
    license: DatasetTerms
    required_fields: list[Text]
    native_identity_field: str | None
    transformation_version: Text
    role: Literal["unknown"] = "unknown"
    limitations: list[Text]

    @model_validator(mode="after")
    def source_identity(self) -> Self:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", self.id):
            raise ValueError("invalid_obliteratus_source_id")
        if self.inspected_revision is not None and not re.fullmatch(
            r"[a-f0-9]{40,64}", self.inspected_revision
        ):
            raise ValueError("inspected_revision_requires_immutable_commit")
        if len(self.required_fields) != len(set(self.required_fields)):
            raise ValueError("duplicate_required_source_field")
        if self.access == "public" and self.artifact.sha256 is None:
            raise ValueError("public_artifact_requires_checksum")
        return self


class ObliteratusSourceManifest(Record):
    schema_version: Literal[1] = 1
    manifest_id: Text
    reviewed_at: Text
    sources: list[ObliteratusSource]
    limitations: list[Text]

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("duplicate_obliteratus_source")
        return self


class PromptView(Record):
    version: Literal["1"] = "1"
    view_id: Text
    data: DataReference
    parent_content_sha256: Digest
    transformation_version: Text
    semantic_label: SemanticLabel
    prompt_form: PromptForm
    text: Text
    pair_id: str | None
    counterpart_view_id: str | None
    source_fields: list[Text]
    metadata: dict[str, JsonValue]
    limitations: list[Text]

    @model_validator(mode="after")
    def stable_identity(self) -> Self:
        payload = self.model_dump(exclude={"view_id", "counterpart_view_id"})
        expected = f"prompt:{sha256(canonical(payload))}"
        if self.view_id != expected:
            raise ValueError("prompt_view_identity_mismatch")
        return self


def load_obliteratus_manifest() -> ObliteratusSourceManifest:
    """Load the packaged, reviewed source map."""
    return ObliteratusSourceManifest.model_validate(
        json.loads(files("matric_eval.data").joinpath("obliteratus_sources.json").read_text())
    )


def get_obliteratus_source(source_id: str) -> ObliteratusSource:
    for source in load_obliteratus_manifest().sources:
        if source.id == source_id:
            return source
    raise ValueError("unknown_obliteratus_source")


def _actual_artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_obliteratus_artifact(
    source: ObliteratusSource,
    path: Path,
    *,
    supplied_sha256: str | None = None,
) -> str:
    """Verify a local artifact without guessing its source or mutating it."""
    if not path.is_file():
        if source.access == "gated":
            raise DatasetAccessError("gated_obliteratus_artifact_unavailable")
        raise DatasetSourceError("obliteratus_artifact_unavailable")
    actual = _actual_artifact_sha256(path)
    expected = source.artifact.sha256
    if expected is None:
        if supplied_sha256 is None:
            raise DatasetAccessError("gated_obliteratus_artifact_requires_reviewed_checksum")
        if not re.fullmatch(r"[a-f0-9]{64}", supplied_sha256):
            raise DatasetAccessError("invalid_reviewed_gated_artifact_checksum")
        expected = supplied_sha256
    elif supplied_sha256 is not None and supplied_sha256 != expected:
        raise DatasetSourceError("supplied_checksum_conflicts_with_source_manifest")
    if actual != expected:
        raise DatasetSourceError("obliteratus_artifact_checksum_mismatch")
    expected_size = source.artifact.size_bytes
    if expected_size is not None and path.stat().st_size != expected_size:
        raise DatasetSourceError("obliteratus_artifact_size_mismatch")
    return actual


def resolve_obliteratus_artifact(
    source: ObliteratusSource,
    cache: Path,
    *,
    artifact: Path | None = None,
    offline: bool = False,
    supplied_sha256: str | None = None,
) -> tuple[Path, str, dict[str, Any] | None]:
    """Resolve a supplied/cached artifact or acquire a pinned public file.

    Offline mode only reads an explicit path or its expected content-addressed
    cache blob.  Gated sources never trigger unauthenticated fallback or a
    substitution with another dataset.
    """
    if artifact is not None:
        return (
            artifact,
            verify_obliteratus_artifact(source, artifact, supplied_sha256=supplied_sha256),
            None,
        )
    if source.artifact.sha256 is not None:
        cached = cache / "blobs" / source.artifact.sha256
        if cached.is_file():
            return cached, verify_obliteratus_artifact(source, cached), None
    if source.access == "gated":
        if source.distribution.kind != "huggingface":
            raise DatasetAccessError("gated_obliteratus_artifact_unavailable")
        try:
            from huggingface_hub import hf_hub_download

            downloaded = Path(
                hf_hub_download(
                    repo_id=source.distribution.repo,
                    repo_type="dataset",
                    revision=source.distribution.revision,
                    filename=source.artifact.path,
                    local_files_only=offline,
                )
            )
        except Exception as exc:
            error = type(exc).__name__.casefold()
            if offline or "localentrynotfound" in error:
                raise DatasetOfflineError("gated_obliteratus_artifact_unavailable_offline") from exc
            raise DatasetAccessError("gated_obliteratus_artifact_unavailable") from exc
        actual = _actual_artifact_sha256(downloaded)
        if source.artifact.sha256 is not None:
            actual = verify_obliteratus_artifact(
                source,
                downloaded,
                supplied_sha256=supplied_sha256,
            )
        elif supplied_sha256 is not None:
            if not re.fullmatch(r"[a-f0-9]{64}", supplied_sha256):
                raise DatasetAccessError("invalid_reviewed_gated_artifact_checksum")
            if actual != supplied_sha256:
                raise DatasetSourceError("obliteratus_artifact_checksum_mismatch")
        if (
            source.artifact.size_bytes is not None
            and downloaded.stat().st_size != source.artifact.size_bytes
        ):
            raise DatasetSourceError("obliteratus_artifact_size_mismatch")
        receipt_body = {
            "version": "1",
            "source_id": source.id,
            "source_revision": source.distribution.revision,
            "artifact_path": source.artifact.path,
            "artifact_sha256": actual,
            "size_bytes": downloaded.stat().st_size,
            "resolver": "huggingface-hub-pinned-revision/1",
        }
        return (
            downloaded,
            actual,
            {
                **receipt_body,
                "receipt_sha256": sha256(canonical(receipt_body)),
            },
        )
    if offline:
        raise DatasetOfflineError("pinned_obliteratus_artifact_unavailable_offline")
    definition = DatasetSource.model_validate(
        {
            "id": source.id,
            "title": source.title,
            "domains": ["safety"],
            "status": "reviewed",
            "acquisition": {"status": "mapped"},
            "upstream": {"revision": source.distribution.revision},
            "source_url": source.distribution.url,
            "source_docs": [source.license.url],
            "configurations": [source.configuration] if source.configuration else [],
            "splits": [source.split] if source.split else [],
            "native_labels": {"origin": "source-native"},
            "license": source.license.model_dump(),
            "access": {"status": "public"},
            "group_identity_hints": [],
            "reported_size": source.artifact.raw_count,
            "files": [
                {
                    "path": source.artifact.path,
                    "format": source.artifact.format,
                    "url": source.artifact.url,
                    "size_bytes": source.artifact.size_bytes,
                    "expected_sha256": source.artifact.sha256,
                }
            ],
        }
    )
    receipt = acquire_source(definition, cache)
    path = cache / cast(str, receipt["files"][0]["blob"])
    return path, verify_obliteratus_artifact(source, path), receipt


def _literal_assignment(tree: ast.Module, name: str) -> tuple[list[str], list[int]]:
    matches: list[ast.expr] = []
    for statement in tree.body:
        value: ast.expr | None
        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value = statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
            value = statement.value
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            if value is None:
                raise DatasetSourceError("obliteratus_builtin_assignment_missing")
            matches.append(value)
    if len(matches) != 1:
        raise DatasetSourceError("obliteratus_builtin_assignment_drift")
    node = matches[0]
    if not isinstance(node, (ast.List, ast.Tuple)):
        raise DatasetSourceError("obliteratus_builtin_assignment_drift")
    try:
        values = ast.literal_eval(node)
    except (ValueError, TypeError, MemoryError, RecursionError, SyntaxError) as exc:
        raise DatasetSourceError("obliteratus_builtin_literal_required") from exc
    if not isinstance(values, (list, tuple)) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise DatasetSourceError("obliteratus_builtin_text_list_required")
    offsets = [item.lineno for item in node.elts]
    return list(values), offsets


def extract_builtin_snapshot(
    path: Path,
) -> tuple[list[dict[str, JsonValue]], list[dict[str, JsonValue]]]:
    """Extract literals and line offsets from a verified snapshot via AST only."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise DatasetSourceError("obliteratus_builtin_python_unreadable") from exc
    harmful, harmful_lines = _literal_assignment(tree, "BUILTIN_HARMFUL")
    harmless, harmless_lines = _literal_assignment(tree, "BUILTIN_HARMLESS")
    pool, pool_lines = _literal_assignment(tree, "_HARMLESS_POOL")
    if len(harmful) != len(harmless):
        raise DatasetSourceError("obliteratus_builtin_pair_count_mismatch")
    pairs: list[dict[str, JsonValue]] = [
        {
            "pair_index": index,
            "harmful": bad,
            "harmless": good,
            "harmful_source_line": harmful_lines[index],
            "harmless_source_line": harmless_lines[index],
            "tier": "unknown",
        }
        for index, (bad, good) in enumerate(zip(harmful, harmless, strict=True))
    ]
    controls: list[dict[str, JsonValue]] = [
        {"pool_index": index, "text": text, "source_line": pool_lines[index]}
        for index, text in enumerate(pool)
    ]
    return pairs, controls


def _read_tsv(path: Path) -> list[dict[str, JsonValue]]:
    text = path.read_bytes().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise DatasetSourceError("obliteratus_tsv_requires_unique_headers")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise DatasetSourceError("obliteratus_tsv_row_width_mismatch")
    canonical(rows)
    return cast(list[dict[str, JsonValue]], rows)


def _read_json_gzip(path: Path) -> list[dict[str, JsonValue]]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as source:
            value = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetSourceError("obliteratus_gzip_json_unreadable") from exc
    canonical(value)
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise DatasetSourceError("obliteratus_gzip_json_requires_object_array")
    return cast(list[dict[str, JsonValue]], value)


def read_obliteratus_payloads(
    source: ObliteratusSource, path: Path
) -> tuple[list[dict[str, JsonValue]], list[dict[str, JsonValue]]]:
    """Read source-native records and, for the builtin snapshot, its control pool."""
    controls: list[dict[str, JsonValue]] = []
    if source.artifact.format == "python-ast-pairs":
        rows, controls = extract_builtin_snapshot(path)
    elif source.artifact.format == "json.gz":
        rows = _read_json_gzip(path)
    elif source.artifact.format == "tsv":
        rows = _read_tsv(path)
    else:
        rows = read_payloads(path, format=source.artifact.format)
    required = set(source.required_fields)
    if any(not required.issubset(row) for row in rows):
        raise DatasetSourceError("obliteratus_source_schema_drift")
    expected = source.artifact.raw_count
    if expected is not None and len(rows) != expected:
        raise DatasetSourceError("obliteratus_source_count_drift")
    return rows, controls


def _native_id(source: ObliteratusSource, row: dict[str, JsonValue], index: int) -> JsonValue:
    if source.native_identity_field is None:
        return index
    value = row.get(source.native_identity_field)
    if value is None or isinstance(value, (dict, list)):
        raise DatasetSourceError("obliteratus_native_identity_unavailable")
    return value


def import_obliteratus_evidence(
    source: ObliteratusSource,
    path: Path,
    *,
    artifact_sha256: str,
) -> tuple[list[EvidenceRecord], list[dict[str, JsonValue]]]:
    rows, controls = read_obliteratus_payloads(source, path)
    records: list[EvidenceRecord] = []
    for index, row in enumerate(rows):
        native_id = _native_id(source, row, index)
        cluster_id = None
        if source.id == "obliteratus-builtin":
            cluster_id = f"pair:{index}"
        elif source.id == "harmbench":
            cluster_id = f"behavior:{native_id}"
        elif source.id.startswith("jailbreakbench-"):
            cluster_id = f"behavior:{row['Behavior']}:{native_id}"
        records.append(
            make_evidence_record(
                row,
                source_id=source.canonical_id,
                source_revision=source.distribution.revision,
                configuration=source.configuration,
                split=source.split,
                artifact_path=source.artifact.path,
                artifact_sha256=artifact_sha256,
                row_index=index,
                native_id=native_id,
                cluster_id=cluster_id,
            )
        )
    return records, controls


def _first_human_turn(transcript: JsonValue) -> str | None:
    if not isinstance(transcript, str) or "Human:" not in transcript:
        return None
    sections = transcript.split("Human:")
    if len(sections) < 2:
        return None
    turn = sections[1].split("Assistant:")[0].strip()
    return turn if len(turn) > 15 else None


def _wild_label(data_type: JsonValue) -> SemanticLabel:
    if not isinstance(data_type, str):
        raise DatasetSourceError("wildjailbreak_data_type_requires_text")
    normalized = data_type.casefold().replace("-", "_").replace(" ", "_")
    harmful = "harmful" in normalized
    benign = "benign" in normalized
    if harmful == benign:
        raise DatasetSourceError("wildjailbreak_data_type_semantics_unknown")
    return "harmful" if harmful else "benign"


def _view(
    record: EvidenceRecord,
    *,
    transformation_version: str,
    text: JsonValue,
    label: SemanticLabel,
    form: PromptForm,
    pair_id: str | None = None,
    source_fields: list[str],
    metadata: dict[str, JsonValue] | None = None,
    limitations: list[str] | None = None,
) -> PromptView:
    if not isinstance(text, str) or not text.strip():
        raise DatasetSourceError("obliteratus_prompt_text_required")
    data = DataReference(
        partition_schema_version="1",
        role="unknown",
        row_id=record.record_id,
        source_id=record.source_id,
        independent_unit_id=(
            f"{record.source_id}:{record.cluster_id}"
            if record.cluster_id is not None
            else f"unknown-cluster:{record.record_id}"
        ),
    )
    payload: dict[str, Any] = {
        "version": "1",
        "data": data.model_dump(),
        "parent_content_sha256": record.content_sha256,
        "transformation_version": transformation_version,
        "semantic_label": label,
        "prompt_form": form,
        "text": text.strip(),
        "pair_id": pair_id,
        "counterpart_view_id": None,
        "source_fields": source_fields,
        "metadata": metadata or {},
        "limitations": limitations or [],
    }
    identity = sha256(
        canonical({key: value for key, value in payload.items() if key != "counterpart_view_id"})
    )
    return PromptView.model_validate({**payload, "view_id": f"prompt:{identity}"})


def _paired(first: PromptView, second: PromptView) -> tuple[PromptView, PromptView]:
    return (
        PromptView.model_validate({**first.model_dump(), "counterpart_view_id": second.view_id}),
        PromptView.model_validate({**second.model_dump(), "counterpart_view_id": first.view_id}),
    )


def derive_obliteratus_views(
    source: ObliteratusSource, records: list[EvidenceRecord]
) -> list[PromptView]:
    """Create canonical prompt views without historical caps or relabeling."""
    views: list[PromptView] = []
    for record in records:
        row = record.payload
        version = source.transformation_version
        if source.id == "obliteratus-builtin":
            pair_id = f"obliteratus-builtin:{row['pair_index']}"
            bad = _view(
                record,
                transformation_version=version,
                text=row["harmful"],
                label="unknown",
                form="builtin_harmful",
                pair_id=pair_id,
                source_fields=["/harmful", "/harmful_source_line"],
                metadata={"tier": "unknown", "source_line": row["harmful_source_line"]},
                limitations=["publisher_tier_assignment_unverified"],
            )
            good = _view(
                record,
                transformation_version=version,
                text=row["harmless"],
                label="unknown",
                form="builtin_harmless",
                pair_id=pair_id,
                source_fields=["/harmless", "/harmless_source_line"],
                metadata={"tier": "unknown", "source_line": row["harmless_source_line"]},
                limitations=["publisher_tier_assignment_unverified"],
            )
            views.extend(_paired(bad, good))
        elif source.id == "advbench":
            views.append(
                _view(
                    record,
                    transformation_version=version,
                    text=row["goal"],
                    label="harmful",
                    form="vanilla",
                    source_fields=["/goal"],
                )
            )
        elif source.id == "harmbench":
            views.append(
                _view(
                    record,
                    transformation_version=version,
                    text=row["Behavior"],
                    label="harmful",
                    form="vanilla",
                    source_fields=["/Behavior", "/ContextString", "/BehaviorID"],
                )
            )
        elif source.id == "anthropic-red-team":
            turn = _first_human_turn(row["transcript"])
            if turn is not None:
                views.append(
                    _view(
                        record,
                        transformation_version=version,
                        text=turn,
                        label="unknown",
                        form="first_human_turn",
                        source_fields=["/transcript"],
                        limitations=[
                            "red_team_attempt_not_verified_harmful_or_refused",
                            "ratings_retained_only_in_parent_evidence",
                        ],
                    )
                )
        elif source.id.startswith("wildjailbreak-"):
            wild_label = _wild_label(row["data_type"])
            pair_id = f"{record.source_id}:{record.record_id}"
            vanilla = _view(
                record,
                transformation_version=version,
                text=row["vanilla"],
                label=wild_label,
                form="vanilla",
                pair_id=pair_id,
                source_fields=["/vanilla", "/data_type"],
            )
            adversarial = _view(
                record,
                transformation_version=version,
                text=row["adversarial"],
                label=wild_label,
                form="adversarial",
                pair_id=pair_id,
                source_fields=["/adversarial", "/data_type", "/tactics"],
            )
            views.extend(_paired(vanilla, adversarial))
        elif source.id.startswith("jailbreakbench-"):
            jbb_label: SemanticLabel = (
                "harmful" if source.id == "jailbreakbench-harmful" else "benign"
            )
            views.append(
                _view(
                    record,
                    transformation_version=version,
                    text=row["Goal"],
                    label=jbb_label,
                    form="vanilla",
                    source_fields=["/Goal", "/Index", "/Behavior", "/Category", "/Source"],
                )
            )
        elif source.id == "wikitext-2-raw-test":
            text = row["text"]
            if isinstance(text, str) and text.strip():
                views.append(
                    _view(
                        record,
                        transformation_version=version,
                        text=text,
                        label="unknown",
                        form="capability_text",
                        source_fields=["/text"],
                        limitations=["ancillary_capability_data_not_contrastive_prompt"],
                    )
                )
        else:  # pragma: no cover - manifest validation and tests enumerate sources
            raise DatasetSourceError("unsupported_obliteratus_source_adapter")
    expected = source.artifact.accepted_count
    if expected is not None and len(views) != expected:
        raise DatasetSourceError("obliteratus_accepted_count_drift")
    return views


def generated_control_views(
    harmful_views: list[PromptView],
    controls: list[dict[str, JsonValue]],
    *,
    source_revision: str,
    artifact_sha256: str,
) -> list[PromptView]:
    """Reproduce the 99-item cycled controls as an explicitly legacy view."""
    if not controls:
        raise DatasetSourceError("obliteratus_control_pool_unavailable")
    generated: list[PromptView] = []
    for index, harmful in enumerate(harmful_views):
        control = controls[index % len(controls)]
        text = control.get("text")
        if not isinstance(text, str) or not text.strip():
            raise DatasetSourceError("obliteratus_control_pool_schema_drift")
        pool_index = control.get("pool_index")
        source_line = control.get("source_line")
        record_id = "obliteratus-control:" + sha256(
            canonical([source_revision, artifact_sha256, pool_index])
        )
        data = DataReference(
            partition_schema_version="1",
            role="unknown",
            row_id=record_id,
            source_id="obliteratus-harmless-control-pool",
            independent_unit_id=f"obliteratus-control:{pool_index}",
        )
        pair_id = harmful.pair_id or f"obliteratus-legacy:{harmful.view_id}"
        payload: dict[str, Any] = {
            "version": "1",
            "data": data.model_dump(),
            "parent_content_sha256": sha256(canonical(control)),
            "transformation_version": "obliteratus-generated-controls/1",
            "semantic_label": "unknown",
            "prompt_form": "generated_control",
            "text": text.strip(),
            "pair_id": pair_id,
            "counterpart_view_id": harmful.view_id,
            "source_fields": ["/_HARMLESS_POOL"],
            "metadata": {
                "pool_index": pool_index,
                "source_line": source_line,
                "cycle_position": index,
            },
            "limitations": [
                "repository_derived_repeated_control",
                "not_an_upstream_paired_label",
            ],
        }
        identity = sha256(
            canonical(
                {key: value for key, value in payload.items() if key != "counterpart_view_id"}
            )
        )
        generated.append(PromptView.model_validate({**payload, "view_id": f"prompt:{identity}"}))
    return generated


def _legacy_clone(view: PromptView, *, ordinal: int, assumption: str) -> PromptView:
    pair_id = f"obliteratus-legacy:{view.view_id}"
    payload = view.model_dump()
    payload.update(
        {
            "transformation_version": "obliteratus-legacy-source-selection/1",
            "pair_id": pair_id,
            "counterpart_view_id": None,
            "metadata": {
                **view.metadata,
                "legacy_ordinal": ordinal,
                "legacy_assumption": assumption,
            },
            "limitations": [
                *view.limitations,
                "historical_obliteratus_compatibility_view",
                "not_canonical_upstream_semantics",
            ],
        }
    )
    identity = sha256(
        canonical(
            {
                key: value
                for key, value in payload.items()
                if key not in {"view_id", "counterpart_view_id"}
            }
        )
    )
    return PromptView.model_validate({**payload, "view_id": f"prompt:{identity}"})


def derive_obliteratus_legacy_pairs(
    source: ObliteratusSource,
    records: list[EvidenceRecord],
    controls: list[dict[str, JsonValue]],
    *,
    control_source_revision: str,
    control_artifact_sha256: str,
) -> list[PromptView]:
    """Reproduce historical external-source pairing under distinct identities.

    AdvBench and HarmBench retain all accepted rows. Anthropic reproduces the
    first-seen text de-duplication and explicit 2,000-row cap. WildJailbreak is
    intentionally excluded: its historical relabeling conflicts with the
    publisher's four semantic data types, so canonical corrected pairs are the
    only supported import.
    """
    if source.id not in {"advbench", "harmbench", "anthropic-red-team"}:
        raise DatasetSourceError("obliteratus_legacy_pairing_unsupported_for_source")
    canonical_views = derive_obliteratus_views(source, records)
    if source.id == "anthropic-red-team":
        unique: list[PromptView] = []
        seen: set[str] = set()
        for view in canonical_views:
            if view.text not in seen:
                seen.add(view.text)
                unique.append(view)
        canonical_views = unique[:2000]
    assumption = {
        "advbench": "goal treated as harmful; paired with cycled OBLITERATUS control",
        "harmbench": "behavior treated as harmful; paired with cycled OBLITERATUS control",
        "anthropic-red-team": (
            "first human turn treated as harmful without checking refusal or rating; "
            "deduplicated and capped at 2000"
        ),
    }[source.id]
    selected = [
        _legacy_clone(view, ordinal=index, assumption=assumption)
        for index, view in enumerate(canonical_views)
    ]
    generated = generated_control_views(
        selected,
        controls,
        source_revision=control_source_revision,
        artifact_sha256=control_artifact_sha256,
    )
    paired: list[PromptView] = []
    for harmful, control in zip(selected, generated, strict=True):
        harmful = PromptView.model_validate(
            {**harmful.model_dump(), "counterpart_view_id": control.view_id}
        )
        paired.extend([harmful, control])
    return paired


def deterministic_limit(
    views: list[PromptView], limit: int | None, *, seed: int
) -> list[PromptView]:
    """Apply an optional recorded stable-hash limit; ``None`` means every view."""
    if limit is None:
        return list(views)
    if limit <= 0:
        raise ValueError("positive_obliteratus_limit_required")
    ranked = sorted(
        views,
        key=lambda view: sha256(canonical([seed, view.view_id])),
    )
    return ranked[:limit]
