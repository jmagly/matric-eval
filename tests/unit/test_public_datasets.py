"""Independent synthetic checks for lossless public dataset acquisition and evidence."""

import json

import httpx
import pytest
from pydantic import ValidationError

from matric_eval.data import acquisition
from matric_eval.data.catalog import DatasetCatalog, DatasetSource, load_catalog
from matric_eval.data.evidence import (
    EvidenceRecord,
    load_evidence,
    make_evidence_record,
    read_json,
    read_payloads,
)
from matric_eval.data.roles import canonical, sha256

REVISION = "a" * 40
RAW = b'{"id":7,"label":false,"score":0,"reason":null}\n'


def source(**changes):
    document = {
        "id": "fixture",
        "title": "Synthetic fixture",
        "domains": ["test"],
        "status": "candidate",
        "upstream": {"revision": REVISION},
        "source_url": "https://huggingface.co/datasets/fixture/data",
        "source_docs": [],
        "configurations": [],
        "splits": ["test"],
        "native_labels": {"origin": "synthetic"},
        "license": {"id": "fixture"},
        "access": {"status": "public"},
        "acquisition": {"status": "mapped"},
        "group_identity_hints": [],
        "reported_size": None,
        "files": [
            {
                "path": "data.jsonl",
                "url": f"https://huggingface.co/datasets/fixture/data/resolve/{REVISION}/data.jsonl",
                "expected_sha256": sha256(RAW),
                "size_bytes": len(RAW),
            }
        ],
    }
    document.update(changes)
    return DatasetSource.model_validate(document)


def mock_http(monkeypatch, handler):
    real_client = httpx.Client
    calls = []

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(record), **kwargs)

    def record(request):
        calls.append(request)
        return handler(request)

    monkeypatch.setattr(acquisition.httpx, "Client", client)
    return calls


def test_evidence_preserves_native_json_types_and_roundtrips(tmp_path):
    payload = {
        "id": 7,
        "label": False,
        "score": 0,
        "reason": None,
        "ratings": [True, None, 0, "0"],
        "metadata": {},
    }
    row = make_evidence_record(
        payload,
        source_id="fixture",
        source_revision=REVISION,
        artifact_path="data.jsonl",
        artifact_sha256=sha256(RAW),
        row_index=0,
        native_id=7,
        split="test",
    )
    assert row.payload == payload
    assert row.payload["label"] is False and row.payload["reason"] is None
    assert type(row.native_id) is int
    path = tmp_path / "evidence.jsonl"
    path.write_bytes(canonical(row.model_dump()) + b"\n")
    assert load_evidence(path) == [row]
    assert row.cluster_id is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_revision", "b" * 40),
        ("row_index", 1),
        ("split", "train"),
        ("artifact_sha256", "f" * 64),
        ("native_id", "7"),
        ("cluster_id", "forged-cluster"),
    ],
)
def test_evidence_identity_mutations_reject(field, value):
    row = make_evidence_record(
        {"label": None},
        source_id="fixture",
        source_revision=REVISION,
        artifact_path="data.jsonl",
        artifact_sha256=sha256(RAW),
        row_index=0,
    )
    document = row.model_dump()
    document[field] = value
    with pytest.raises(ValidationError, match="identity"):
        EvidenceRecord.model_validate(document)
    document = row.model_dump()
    document["payload"]["label"] = False
    with pytest.raises(ValidationError, match="content"):
        EvidenceRecord.model_validate(document)


@pytest.mark.parametrize(
    "text",
    ['{"a":1,"a":2}', '{"x":{"a":0,"a":false}}', '{"n":NaN}', '{"n":Infinity}', '{"n":1e999}'],
)
def test_strict_json_rejects_ambiguous_or_nonfinite_records(text):
    with pytest.raises(ValueError):
        read_json(text)


def test_csv_preserves_strings_and_multiline_fields(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text('id,label,note\n007,0,"first\nsecond"\n', encoding="utf-8")
    assert read_payloads(path, format="csv") == [
        {"id": "007", "label": "0", "note": "first\nsecond"}
    ]
    path.write_text("id,id\n1,2\n")
    with pytest.raises(ValueError, match="unique_headers"):
        read_payloads(path, format="csv")


def test_jsonl_rejects_nonobject_rows_without_dropping_them(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_bytes(RAW + b"null\n")
    with pytest.raises(ValueError, match="object_rows"):
        read_payloads(path, format="jsonl")


def test_catalog_includes_blocked_sources_without_claiming_acquisition():
    catalog = load_catalog()
    assert len(catalog.sources) >= 15
    assert any(item.access["status"] != "public" for item in catalog.sources)
    document = catalog.model_dump()
    document["sources"].append(document["sources"][0])
    with pytest.raises(ValidationError, match="duplicate_catalog_source"):
        DatasetCatalog.model_validate(document)


def test_acquisition_verifies_bytes_and_replays_identical_receipt(tmp_path, monkeypatch):
    calls = mock_http(monkeypatch, lambda request: httpx.Response(200, content=RAW))
    first = acquisition.acquire_source(source(), tmp_path)
    second = acquisition.acquire_source(source(), tmp_path)
    assert first == second and first["status"] == "complete"
    assert first["total_bytes"] == len(RAW)
    assert (tmp_path / first["files"][0]["blob"]).read_bytes() == RAW
    receipt = json.loads(next((tmp_path / "receipts").glob("*.json")).read_text())
    assert sha256(canonical(receipt)) == first["receipt_sha256"]
    assert len(calls) == 2
    assert not list((tmp_path / "blobs").glob(".download-*"))


@pytest.mark.parametrize("status", ["gated", "restricted", "review_required"])
def test_access_refusal_occurs_before_network_or_artifacts(tmp_path, monkeypatch, status):
    calls = mock_http(monkeypatch, lambda request: pytest.fail("access refusal contacted network"))
    with pytest.raises(ValueError):
        acquisition.acquire_source(source(access={"status": status}), tmp_path / "out")
    assert not calls and not (tmp_path / "out").exists()


def test_download_digest_mismatch_cannot_create_complete_receipt(tmp_path, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b"x" * len(RAW)))
    with pytest.raises(ValueError, match="digest_mismatch"):
        acquisition.acquire_source(source(), tmp_path)
    assert not list(tmp_path.glob("receipts/*.json"))
    assert not list(tmp_path.glob("blobs/.download-*"))


def test_stream_budget_counts_actual_bytes_when_size_unknown(tmp_path, monkeypatch):
    item = source().model_dump()["files"][0]
    item["size_bytes"] = None
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=RAW))
    with pytest.raises(ValueError, match="budget"):
        acquisition.acquire_source(source(files=[item]), tmp_path, max_bytes=len(RAW) - 1)
    assert not list(tmp_path.glob("receipts/*.json"))


def test_http_error_never_claims_complete_acquisition(tmp_path, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(403, content=b"denied"))
    with pytest.raises((ValueError, httpx.HTTPError)):
        acquisition.acquire_source(source(), tmp_path)
    assert not list(tmp_path.glob("receipts/*.json"))


def test_existing_corrupt_blob_is_not_overwritten(tmp_path, monkeypatch):
    (tmp_path / "blobs").mkdir()
    target = tmp_path / "blobs" / sha256(RAW)
    target.write_bytes(b"corrupt")
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=RAW))
    with pytest.raises(ValueError, match="existing_artifact"):
        acquisition.acquire_source(source(), tmp_path)
    assert target.read_bytes() == b"corrupt"
    assert not list(tmp_path.glob("receipts/*.json"))


def test_unmapped_source_refuses_before_contact(tmp_path, monkeypatch):
    calls = mock_http(monkeypatch, lambda request: pytest.fail("unmapped source contacted"))
    with pytest.raises(ValueError, match="unavailable"):
        acquisition.acquire_source(source(acquisition={"status": "unresolved"}), tmp_path)
    assert not calls


@pytest.mark.parametrize(
    "location",
    [
        "http://huggingface.co/file",
        "https://127.0.0.1/private",
        "https://huggingface.co.attacker.example/file",
        "https://user:secret@huggingface.co/file",
    ],
)
def test_redirect_escape_refuses_before_second_request(tmp_path, monkeypatch, location):
    calls = mock_http(
        monkeypatch, lambda request: httpx.Response(302, headers={"location": location})
    )
    with pytest.raises(ValueError, match="redirect"):
        acquisition.acquire_source(source(), tmp_path)
    assert len(calls) == 1
    assert not list(tmp_path.glob("receipts/*.json"))


def test_allowed_cdn_redirect_still_checks_content_integrity(tmp_path, monkeypatch):
    def respond(request):
        if request.url.host == "huggingface.co":
            return httpx.Response(302, headers={"location": "https://cdn-lfs.hf.co/object"})
        return httpx.Response(200, content=RAW)

    calls = mock_http(monkeypatch, respond)
    result = acquisition.acquire_source(source(), tmp_path)
    assert len(calls) == 2 and result["files"][0]["sha256"] == sha256(RAW)


@pytest.mark.parametrize("text", ["id,label\n1\n", "id,label\n1,2,3\n"])
def test_csv_refuses_missing_or_extra_cells(tmp_path, text):
    path = tmp_path / "ragged.csv"
    path.write_text(text)
    with pytest.raises(ValueError, match="csv_row_width_mismatch"):
        read_payloads(path, format="csv")
