"""Public dataset CLI with synthetic acquired bytes and explicit receipt bindings."""

import gzip
import json

import pytest
from click.testing import CliRunner

from matric_eval.data.catalog import DatasetSource
from matric_eval.data.cli import datasets
from matric_eval.data.evidence import load_evidence
from matric_eval.data.roles import canonical, sha256


def acquired(tmp_path, monkeypatch, access="public", *, raw=None, format_name="jsonl"):
    raw = (
        raw
        if raw is not None
        else b'{"prompt":"question","answer":"answer","score":0,"group":"g"}\n'
    )
    checksum = sha256(raw)
    definition = DatasetSource.model_validate(
        {
            "id": "fixture",
            "title": "Synthetic",
            "domains": ["test"],
            "status": "reviewed",
            "acquisition": {"status": "mapped"},
            "upstream": {"revision": "a" * 40},
            "source_url": "https://example.invalid",
            "source_docs": [],
            "configurations": ["main"],
            "splits": ["train"],
            "native_labels": {},
            "license": {},
            "access": {"status": access},
            "group_identity_hints": [],
            "reported_size": 1,
            "files": [
                {
                    "path": "data/train.jsonl.gz"
                    if format_name == "jsonl.gz"
                    else "data/train.jsonl",
                    "url": f"https://huggingface.co/datasets/x/resolve/{'a' * 40}/data/train.jsonl",
                    "format": format_name,
                    "size_bytes": len(raw),
                    "expected_sha256": checksum,
                }
            ],
        }
    )
    monkeypatch.setattr("matric_eval.data.cli.get_source", lambda source: definition)
    blob = tmp_path / "acquired/blobs" / checksum
    blob.parent.mkdir(parents=True)
    blob.write_bytes(raw)
    receipt = {
        "version": "1",
        "source_id": "fixture",
        "source_revision": "a" * 40,
        "catalog_source_sha256": sha256(canonical(definition.model_dump())),
        "status": "complete",
        "files": [{**definition.files[0], "sha256": checksum, "blob": f"blobs/{checksum}"}],
        "total_bytes": len(raw),
    }
    receipt_path = tmp_path / "acquired/receipts" / f"fixture-{sha256(canonical(receipt))}.json"
    receipt_path.parent.mkdir()
    receipt_path.write_bytes(canonical(receipt) + b"\n")
    return definition, blob, receipt_path


def test_import_compose_verify_project_public_flow(tmp_path, monkeypatch):
    _, blob, receipt = acquired(tmp_path, monkeypatch)
    runner = CliRunner()
    evidence = tmp_path / "evidence.jsonl"
    response = runner.invoke(
        datasets,
        [
            "import-file",
            "fixture",
            str(blob),
            "--receipt",
            str(receipt),
            "--output",
            str(evidence),
            "--configuration",
            "main",
            "--split",
            "train",
            "--cluster-pointer",
            "/group",
        ],
    )
    assert response.exit_code == 0, response.output
    record = load_evidence(evidence)[0]
    assert record.payload["score"] == 0
    assert record.split == "train"
    assert record.cluster_id == 'json:"g"'
    assert record.artifact_path == "data/train.jsonl"
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "version": "1",
                "seed": 42,
                "role": "calibration",
                "sources": [{"source_id": "fixture", "quota": 1}],
            }
        )
    )
    manifest = tmp_path / "manifest.json"
    selected = runner.invoke(
        datasets, ["compose", str(evidence), "--request", str(request), "--output", str(manifest)]
    )
    assert selected.exit_code == 0, selected.output
    verified = runner.invoke(datasets, ["verify", str(manifest), "--evidence", str(evidence)])
    assert verified.exit_code == 0, verified.output
    samples = tmp_path / "samples.jsonl"
    projected = runner.invoke(
        datasets,
        [
            "project",
            str(manifest),
            "--input-pointer",
            "/prompt",
            "--target-pointer",
            "/answer",
            "--output",
            str(samples),
        ],
    )
    assert projected.exit_code == 0, projected.output
    value = json.loads(samples.read_text())
    assert value["input"] == "question"
    assert value["metadata"]["evidence"]["payload"]["score"] == 0
    before = samples.read_bytes()
    repeat = runner.invoke(
        datasets,
        [
            "project",
            str(manifest),
            "--input-pointer",
            "/prompt",
            "--target-pointer",
            "/answer",
            "--output",
            str(samples),
        ],
    )
    assert repeat.exit_code != 0
    assert samples.read_bytes() == before


def test_import_refuses_receipt_tampering_and_local_bypass(tmp_path, monkeypatch):
    _, blob, receipt = acquired(tmp_path, monkeypatch)
    runner = CliRunner()
    output = tmp_path / "output.jsonl"
    original = blob.read_bytes()
    arbitrary = tmp_path / "copy.jsonl"
    arbitrary.write_bytes(original)
    args = [
        "import-file",
        "fixture",
        str(arbitrary),
        "--receipt",
        str(receipt),
        "--output",
        str(output),
    ]
    assert runner.invoke(datasets, args).exit_code != 0
    assert not output.exists()
    blob.write_bytes(b"PRIVATE_CONTENT_MUST_NOT_APPEAR")
    response = runner.invoke(
        datasets,
        ["import-file", "fixture", str(blob), "--receipt", str(receipt), "--output", str(output)],
    )
    assert response.exit_code != 0
    assert "PRIVATE_CONTENT" not in response.output
    assert not output.exists()
    blob.write_bytes(original)
    changed = json.loads(receipt.read_text())
    changed["source_revision"] = "b" * 40
    receipt.write_text(json.dumps(changed))
    assert (
        runner.invoke(
            datasets,
            [
                "import-file",
                "fixture",
                str(blob),
                "--receipt",
                str(receipt),
                "--output",
                str(output),
            ],
        ).exit_code
        != 0
    )


def test_restricted_source_and_invalid_selectors_cannot_import(tmp_path, monkeypatch):
    definition, blob, receipt = acquired(tmp_path, monkeypatch, access="restricted")
    args = [
        "import-file",
        "fixture",
        str(blob),
        "--receipt",
        str(receipt),
        "--output",
        str(tmp_path / "output"),
    ]
    response = CliRunner().invoke(datasets, args)
    assert response.exit_code != 0
    assert "dataset_import_refused" in response.output
    definition.access["status"] = "public"
    # Even an access mutation invalidates the retained catalog binding.
    assert CliRunner().invoke(datasets, args).exit_code != 0


def test_catalog_and_acquire_commands_dispatch_explicit_budget(tmp_path, monkeypatch):
    definition, _, _ = acquired(tmp_path, monkeypatch)
    shown = CliRunner().invoke(datasets, ["show", "fixture"])
    assert shown.exit_code == 0
    assert json.loads(shown.output)["id"] == "fixture"
    calls = []

    def fake_acquire(source, destination, *, max_bytes):
        calls.append((source.id, destination, max_bytes))
        return {"status": "complete", "receipt_path": "fixture"}

    monkeypatch.setattr("matric_eval.data.cli.acquire_source", fake_acquire)
    result = CliRunner().invoke(
        datasets,
        ["acquire", definition.id, "--destination", str(tmp_path / "out"), "--max-bytes", "123"],
    )
    assert result.exit_code == 0, result.output
    assert calls == [("fixture", tmp_path / "out", 123)]
    assert (
        CliRunner()
        .invoke(
            datasets, ["acquire", definition.id, "--destination", str(tmp_path), "--max-bytes", "0"]
        )
        .exit_code
        != 0
    )


def test_import_invalid_configuration_and_format_leave_no_output(tmp_path, monkeypatch):
    _, blob, receipt = acquired(tmp_path, monkeypatch)
    output = tmp_path / "never-written"
    args = ["import-file", "fixture", str(blob), "--receipt", str(receipt), "--output", str(output)]
    for extra in [
        ["--configuration", "unknown"],
        ["--split", "unknown"],
        ["--format", "csv"],
        ["--cluster-pointer", "/missing"],
    ]:
        assert CliRunner().invoke(datasets, [*args, *extra]).exit_code != 0
        assert not output.exists()


def test_gzip_import_and_typed_integer_clusters(tmp_path, monkeypatch):
    raw = gzip.compress(b'{"prompt":"q","answer":"a","group":7}\n')
    _, blob, receipt = acquired(tmp_path, monkeypatch, raw=raw, format_name="jsonl.gz")
    output = tmp_path / "records.jsonl"
    response = CliRunner().invoke(
        datasets,
        [
            "import-file",
            "fixture",
            str(blob),
            "--receipt",
            str(receipt),
            "--format",
            "jsonl.gz",
            "--cluster-pointer",
            "/group",
            "--output",
            str(output),
        ],
    )
    assert response.exit_code == 0, response.output
    record = load_evidence(output)[0]
    assert record.cluster_id == "json:7"
    assert record.payload["group"] == 7
    assert record.artifact_path == "data/train.jsonl.gz"


@pytest.mark.parametrize("cluster", [True, None, 1.5, [], {}])
def test_unsupported_cluster_types_refused(tmp_path, monkeypatch, cluster):
    raw = canonical({"prompt": "q", "answer": "a", "group": cluster}) + b"\n"
    _, blob, receipt = acquired(tmp_path, monkeypatch, raw=raw)
    output = tmp_path / "never-published"
    response = CliRunner().invoke(
        datasets,
        [
            "import-file",
            "fixture",
            str(blob),
            "--receipt",
            str(receipt),
            "--cluster-pointer",
            "/group",
            "--output",
            str(output),
        ],
    )
    assert response.exit_code != 0
    assert not output.exists()


def test_failed_output_fsync_never_publishes_partial_file(tmp_path, monkeypatch):
    from matric_eval.data.cli import _write_new

    output = tmp_path / "new.json"

    def fail_fsync(descriptor):
        raise OSError("synthetic write failure")

    monkeypatch.setattr("matric_eval.data.cli.os.fsync", fail_fsync)
    with pytest.raises(OSError):
        _write_new(output, b"complete document")
    assert not output.exists()
    assert not list(tmp_path.glob(".dataset-output-*"))
