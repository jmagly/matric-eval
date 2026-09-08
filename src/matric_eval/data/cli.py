"""Public dataset acquisition, lossless imports and explicit selection commands."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Literal, cast

import click

from matric_eval.data.acquisition import acquire_source
from matric_eval.data.adapters import project_samples
from matric_eval.data.catalog import DatasetSource, get_source, load_catalog
from matric_eval.data.evidence import load_evidence, make_evidence_record, read_json, read_payloads
from matric_eval.data.roles import canonical, sha256
from matric_eval.data.selection import (
    SelectionRequest,
    json_pointer,
    read_selection,
    select_records,
    verify_selection,
    write_selection,
)


def _write_new(path: Path, content: bytes) -> None:
    """Materialize complete serialized bytes exclusively; never overwrite evidence."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=".dataset-output-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _receipt_file(source: DatasetSource, receipt_path: Path, artifact: Path) -> dict[str, Any]:
    if source.access["status"] != "public" or source.acquisition["status"] != "mapped":
        raise ValueError("source_acquisition_unavailable")
    receipt = read_json(receipt_path.read_text())
    if not isinstance(receipt, dict) or set(receipt) != {
        "version",
        "source_id",
        "source_revision",
        "catalog_source_sha256",
        "status",
        "files",
        "total_bytes",
    }:
        raise ValueError("invalid_acquisition_receipt")
    if (
        receipt["version"] != "1"
        or receipt["status"] != "complete"
        or receipt["source_id"] != source.id
        or receipt["source_revision"] != source.upstream.get("revision")
        or receipt["catalog_source_sha256"] != sha256(canonical(source.model_dump()))
        or receipt_path.name != f"{source.id}-{sha256(canonical(receipt))}.json"
    ):
        raise ValueError("acquisition_receipt_binding_mismatch")
    entries = receipt["files"]
    if not isinstance(entries, list) or len(entries) != len(source.files):
        raise ValueError("receipt_file_scope_mismatch")
    selected = None
    total = 0
    for entry, declared in zip(entries, source.files, strict=True):
        if not isinstance(entry, dict) or set(entry) != set(declared) | {
            "sha256",
            "blob",
            "size_bytes",
        }:
            raise ValueError("receipt_file_metadata_mismatch")
        if any(entry.get(key) != value for key, value in declared.items() if key != "size_bytes"):
            raise ValueError("receipt_file_metadata_mismatch")
        checksum, size = entry["sha256"], entry["size_bytes"]
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(c not in "0123456789abcdef" for c in checksum)
            or type(size) is not int
            or size < 0
            or entry["blob"] != f"blobs/{checksum}"
            or declared.get("size_bytes") is not None
            and size != declared["size_bytes"]
            or declared.get("expected_sha256") is not None
            and checksum != declared["expected_sha256"]
        ):
            raise ValueError("receipt_file_digest_mismatch")
        total += size
        blob = receipt_path.parent.parent / "blobs" / checksum
        if artifact.resolve() == blob.resolve():
            raw = artifact.read_bytes()
            if len(raw) != size or sha256(raw) != checksum:
                raise ValueError("artifact_receipt_mismatch")
            if selected is not None and selected != entry:
                raise ValueError("ambiguous_artifact_origin")
            selected = entry
    if (
        type(receipt["total_bytes"]) is not int
        or receipt["total_bytes"] != total
        or selected is None
    ):
        raise ValueError("artifact_not_in_receipt")
    return selected


@click.group("datasets")
def datasets() -> None:
    """Acquire reviewed raw datasets and compose replayable evidence selections."""


@datasets.command("list")
def list_sources() -> None:
    """List reviewed sources and acquisition/access status as JSON."""
    try:
        click.echo(canonical(load_catalog().model_dump()).decode())
    except (ValueError, OSError, TypeError):
        raise click.ClickException("dataset_catalog_unavailable") from None


@datasets.command("show")
@click.argument("source")
def show_source(source: str) -> None:
    """Show one source's revision, fields, files and access constraints."""
    try:
        click.echo(canonical(get_source(source).model_dump()).decode())
    except (ValueError, OSError, TypeError):
        raise click.ClickException("dataset_source_unavailable") from None


@datasets.command("acquire")
@click.argument("source")
@click.option("--destination", required=True, type=click.Path(path_type=Path))
@click.option("--max-bytes", type=click.IntRange(min=1), default=2_000_000_000, show_default=True)
def acquire(source: str, destination: Path, max_bytes: int) -> None:
    """Download mapped public files and retain a content-addressed receipt."""
    try:
        click.echo(
            canonical(acquire_source(get_source(source), destination, max_bytes=max_bytes)).decode()
        )
    except Exception:
        raise click.ClickException("dataset_acquisition_failed") from None


@datasets.command("import-file")
@click.argument("source")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--receipt", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option(
    "--format", "format_name", type=click.Choice(["json", "jsonl", "jsonl.gz", "csv", "parquet"])
)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.option("--configuration")
@click.option("--split")
@click.option("--id-pointer", help="JSON pointer for an optional native row identity.")
@click.option(
    "--cluster-pointer", help="JSON pointer to a text or integer cluster identity (type preserved)."
)
def import_file(
    source: str,
    path: Path,
    receipt: Path,
    format_name: str | None,
    output: Path,
    configuration: str | None,
    split: str | None,
    id_pointer: str | None,
    cluster_pointer: str | None,
) -> None:
    """Import an exact acquired blob losslessly; no upstream scripts or scorer guesses."""
    try:
        definition = get_source(source)
        entry = _receipt_file(definition, receipt, path)
        declared_format = entry.get("format")
        if (
            format_name is not None
            and declared_format is not None
            and format_name != declared_format
        ):
            raise ValueError("artifact_format_mismatch")
        selected_format = format_name or declared_format
        if selected_format not in {"json", "jsonl", "jsonl.gz", "csv", "parquet"}:
            raise ValueError("explicit_format_required")
        for key, value in [("configuration", configuration), ("split", split)]:
            if key in entry and value is not None and value != entry[key]:
                raise ValueError("artifact_selector_mismatch")
        configuration = entry.get("configuration", configuration)
        split = entry.get("split", split)
        for value, declared in [
            (configuration, definition.configurations),
            (split, definition.splits),
        ]:
            if value is not None and declared and value not in declared:
                raise ValueError("unknown_source_selector")
        # Parse the exact hashed bytes, not a later mutable reread of the blob.
        raw = path.read_bytes()
        if sha256(raw) != entry["sha256"]:
            raise ValueError("artifact_receipt_mismatch")
        with tempfile.TemporaryDirectory(prefix="matric-import-") as directory:
            staged = Path(directory) / Path(entry["path"]).name
            if selected_format == "jsonl.gz" and staged.suffix != ".gz":
                staged = staged.with_name(staged.name + ".gz")
            staged.write_bytes(raw)
            payloads = read_payloads(
                staged, format="jsonl" if selected_format == "jsonl.gz" else selected_format
            )
        records = []
        for index, payload in enumerate(payloads):
            cluster = (
                json_pointer(payload, cluster_pointer) if cluster_pointer is not None else None
            )
            if cluster_pointer is not None:
                if (
                    type(cluster) not in (str, int)
                    or isinstance(cluster, str)
                    and not cluster.strip()
                ):
                    raise ValueError("cluster_identity_requires_text_or_integer")
                cluster = "json:" + canonical(cluster).decode("utf-8")
            records.append(
                make_evidence_record(
                    payload,
                    source_id=definition.id,
                    source_revision=definition.upstream["revision"],
                    artifact_path=entry["path"],
                    artifact_sha256=entry["sha256"],
                    row_index=index,
                    configuration=configuration,
                    split=split,
                    native_id=json_pointer(payload, id_pointer) if id_pointer is not None else None,
                    cluster_id=cluster,
                )
            )
        _write_new(output, b"".join(canonical(record.model_dump()) + b"\n" for record in records))
        click.echo(
            canonical(
                {
                    "status": "imported",
                    "records": len(records),
                    "output": str(output),
                    "source_revision": definition.upstream["revision"],
                    "artifact_sha256": entry["sha256"],
                }
            ).decode()
        )
    except Exception:
        raise click.ClickException("dataset_import_refused") from None


@datasets.command("compose")
@click.argument(
    "evidence",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--request", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--output", required=True, type=click.Path(path_type=Path))
def compose(evidence: tuple[Path, ...], request: Path, output: Path) -> None:
    """Select exact per-source quotas from one or more lossless evidence files."""
    try:
        selection = select_records(
            [record for path in evidence for record in load_evidence(path)],
            SelectionRequest.model_validate(read_json(request.read_text())),
        )
        _write_new(output, write_selection(selection).encode())
        click.echo(
            canonical(
                {
                    "status": "selected",
                    "manifest_sha256": selection.manifest_sha256,
                    "records": len(selection.records),
                }
            ).decode()
        )
    except Exception:
        raise click.ClickException("dataset_selection_refused") from None


@datasets.command("verify")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--evidence",
    multiple=True,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def verify(manifest: Path, evidence: tuple[Path, ...]) -> None:
    """Replay a selection against all original evidence records."""
    try:
        selection = read_selection(manifest.read_text())
        verify_selection(selection, [record for path in evidence for record in load_evidence(path)])
        click.echo(
            canonical({"status": "verified", "manifest_sha256": selection.manifest_sha256}).decode()
        )
    except Exception:
        raise click.ClickException("dataset_replay_refused") from None


@datasets.command("project")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--input-pointer", required=True)
@click.option("--target-pointer", required=True)
@click.option(
    "--input-format", type=click.Choice(["text", "chat"]), default="text", show_default=True
)
@click.option("--output", required=True, type=click.Path(path_type=Path))
def project(
    manifest: Path, input_pointer: str, target_pointer: str, input_format: str, output: Path
) -> None:
    """Project explicit fields into Inspect samples with retained evidence metadata."""
    try:
        samples = project_samples(
            read_selection(manifest.read_text()),
            input_pointer,
            target_pointer,
            cast(Literal["text", "chat"], input_format),
        )
        _write_new(
            output,
            b"".join(canonical(sample.model_dump(mode="json")) + b"\n" for sample in samples),
        )
        click.echo(canonical({"status": "projected", "samples": len(samples)}).decode())
    except Exception:
        raise click.ClickException("dataset_projection_refused") from None
