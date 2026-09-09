"""OBLITERATUS imports preserve source evidence and isolate legacy views."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from matric_eval.data.cli import datasets
from matric_eval.data.evidence import make_evidence_record
from matric_eval.data.obliteratus import (
    ObliteratusSource,
    derive_obliteratus_legacy_pairs,
    derive_obliteratus_views,
    deterministic_limit,
    generated_control_views,
    get_obliteratus_source,
    import_obliteratus_evidence,
    load_obliteratus_manifest,
    read_obliteratus_payloads,
    resolve_obliteratus_artifact,
    verify_obliteratus_artifact,
)
from matric_eval.data.roles import sha256
from matric_eval.datasets import DatasetAccessError, DatasetOfflineError, DatasetSourceError


def source_fixture(base: str, raw: bytes, *, count: int, accepted: int) -> ObliteratusSource:
    document = get_obliteratus_source(base).model_dump()
    document["artifact"].update(
        {
            "sha256": sha256(raw),
            "checksum_unavailable_reason": None,
            "repository_oid": None,
            "size_bytes": len(raw),
            "raw_count": count,
            "accepted_count": accepted,
        }
    )
    document["access"] = "public"
    return ObliteratusSource.model_validate(document)


def evidence(source: ObliteratusSource, rows: list[dict]):
    return [
        make_evidence_record(
            row,
            source_id=source.canonical_id,
            source_revision=source.distribution.revision,
            artifact_path=source.artifact.path,
            artifact_sha256="a" * 64,
            row_index=index,
            native_id=index,
        )
        for index, row in enumerate(rows)
    ]


def test_source_manifest_records_originals_distributions_terms_and_unavailable_hashes():
    manifest = load_obliteratus_manifest()
    assert len(manifest.sources) == 9
    assert {source.id for source in manifest.sources} >= {
        "obliteratus-builtin",
        "advbench",
        "harmbench",
        "anthropic-red-team",
        "wildjailbreak-train",
        "wildjailbreak-eval",
        "jailbreakbench-harmful",
        "jailbreakbench-benign",
        "wikitext-2-raw-test",
    }
    for source in manifest.sources:
        assert len(source.distribution.revision) == 40
        assert source.artifact.path and source.transformation_version
        assert source.license.identifier and source.license.notes
        assert source.role == "unknown"
        if source.access == "public":
            assert source.artifact.sha256 is not None
            assert source.artifact.raw_count is not None
            assert source.artifact.accepted_count is not None
        else:
            assert source.artifact.repository_oid
            if source.id == "wildjailbreak-train":
                assert (
                    source.artifact.sha256
                    == "376719bfdb46ad1a19e7ba4f587f80cc7cb1368cc213ee647ef739c170550f7a"
                )
                assert source.artifact.checksum_unavailable_reason is None
            else:
                assert source.artifact.sha256 is None
                assert source.artifact.checksum_unavailable_reason


def test_builtin_ast_preserves_pairs_offsets_and_never_executes_snapshot(tmp_path: Path):
    raw = b"""raise RuntimeError("must not execute")
_HARMLESS_POOL = ["control one", "control two"]
BUILTIN_HARMFUL = ["harm one", "harm two"]
BUILTIN_HARMLESS = ["safe one", "safe two"]
"""
    path = tmp_path / "prompts.py"
    path.write_bytes(raw)
    source = source_fixture("obliteratus-builtin", raw, count=2, accepted=4)
    digest = verify_obliteratus_artifact(source, path)
    records, controls = import_obliteratus_evidence(source, path, artifact_sha256=digest)
    views = derive_obliteratus_views(source, records)
    assert len(records) == 2 and len(views) == 4 and len(controls) == 2
    assert records[0].payload["pair_index"] == 0
    assert records[0].payload["harmful_source_line"] == 3
    assert records[0].payload["harmless_source_line"] == 4
    assert {view.data.role for view in views} == {"unknown"}
    assert {view.metadata["tier"] for view in views} == {"unknown"}
    assert views[0].counterpart_view_id == views[1].view_id
    assert views[1].counterpart_view_id == views[0].view_id


def test_wildjailbreak_uses_data_type_for_both_vanilla_and_adversarial_semantics():
    source = get_obliteratus_source("wildjailbreak-eval")
    rows = [
        {
            "data_type": "vanilla_harmful",
            "vanilla": "harmful vanilla request",
            "adversarial": "harmful adversarial request",
            "completion": "retained response",
            "tactics": "none",
        },
        {
            "data_type": "adversarial_benign",
            "vanilla": "benign vanilla request",
            "adversarial": "benign adversarial request",
            "completion": "retained response",
            "tactics": "role play",
        },
    ]
    views = derive_obliteratus_views(source, evidence(source, rows))
    by_text = {view.text: view for view in views}
    assert by_text["harmful vanilla request"].semantic_label == "harmful"
    assert by_text["harmful adversarial request"].semantic_label == "harmful"
    assert by_text["benign vanilla request"].semantic_label == "benign"
    assert by_text["benign adversarial request"].semantic_label == "benign"
    assert all(view.counterpart_view_id for view in views)
    with pytest.raises(DatasetSourceError, match="semantics_unknown"):
        derive_obliteratus_views(
            source,
            evidence(source, [{**rows[0], "data_type": "unclassified"}]),
        )


def test_anthropic_first_turn_is_not_silently_declared_harmful_or_refused():
    source = get_obliteratus_source("anthropic-red-team")
    row = {
        "transcript": "Human: explain this request in context\n\nAssistant: response",
        "min_harmlessness_score_transcript": 0.2,
        "num_params": "52B",
        "model_type": "context distillation",
        "rating": 0.0,
        "task_description": "description",
        "task_descripton_harmlessness_score": 1.0,
        "red_team_member_id": 3,
        "is_upworker": False,
        "tags": None,
    }
    document = source.model_dump()
    document["artifact"]["accepted_count"] = None
    source = ObliteratusSource.model_validate(document)
    views = derive_obliteratus_views(source, evidence(source, [row]))
    assert len(views) == 1
    assert views[0].text == "explain this request in context"
    assert views[0].semantic_label == "unknown"
    assert "ratings_retained_only_in_parent_evidence" in views[0].limitations


def test_schema_count_checksum_and_wrong_source_are_refused(tmp_path: Path):
    raw = b"goal,target\nquestion,response\n"
    path = tmp_path / "advbench.csv"
    path.write_bytes(raw)
    source = source_fixture("advbench", raw, count=1, accepted=1)
    verify_obliteratus_artifact(source, path)
    rows, _ = read_obliteratus_payloads(source, path)
    assert rows == [{"goal": "question", "target": "response"}]
    path.write_bytes(b"goal\nquestion\n")
    with pytest.raises(DatasetSourceError, match="checksum_mismatch"):
        verify_obliteratus_artifact(source, path)
    drift_source = source_fixture("advbench", path.read_bytes(), count=1, accepted=1)
    with pytest.raises(DatasetSourceError, match="schema_drift"):
        read_obliteratus_payloads(drift_source, path)
    path.write_bytes(b"goal,target\none,a\ntwo,b\n")
    count_source = source_fixture("advbench", path.read_bytes(), count=1, accepted=1)
    with pytest.raises(DatasetSourceError, match="count_drift"):
        read_obliteratus_payloads(count_source, path)


def test_gated_access_and_offline_resolution_have_no_network_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    gated = get_obliteratus_source("wildjailbreak-eval")
    with pytest.raises(DatasetOfflineError, match="offline"):
        resolve_obliteratus_artifact(gated, tmp_path / "cache", offline=True)

    def denied(**_kwargs):
        raise RuntimeError("synthetic gated denial")

    monkeypatch.setattr("huggingface_hub.hf_hub_download", denied)
    with pytest.raises(DatasetAccessError, match="gated"):
        resolve_obliteratus_artifact(gated, tmp_path / "cache", offline=False)
    artifact = tmp_path / "eval.tsv"
    artifact.write_text(
        "data_type\tvanilla\tadversarial\tcompletion\ttactics\n"
        "benign\tplain text\tchanged text\tanswer\tnone\n"
    )
    gated_document = gated.model_dump()
    gated_document["artifact"]["size_bytes"] = artifact.stat().st_size
    gated = ObliteratusSource.model_validate(gated_document)
    with pytest.raises(DatasetAccessError, match="reviewed_checksum"):
        verify_obliteratus_artifact(gated, artifact)
    assert verify_obliteratus_artifact(
        gated, artifact, supplied_sha256=sha256(artifact.read_bytes())
    ) == sha256(artifact.read_bytes())
    monkeypatch.setattr("huggingface_hub.hf_hub_download", lambda **_kwargs: str(artifact))
    resolved, digest, receipt = resolve_obliteratus_artifact(
        gated, tmp_path / "cache", offline=False
    )
    assert resolved == artifact and digest == sha256(artifact.read_bytes())
    assert receipt is not None
    assert receipt["source_revision"] == gated.distribution.revision
    assert receipt["artifact_path"] == gated.artifact.path

    known_checksum = get_obliteratus_source("wildjailbreak-train")
    with pytest.raises(DatasetSourceError, match="checksum_mismatch"):
        resolve_obliteratus_artifact(known_checksum, tmp_path / "cache")

    raw = b"goal,target\nquestion,response\n"
    public = source_fixture("advbench", raw, count=1, accepted=1)
    cache = tmp_path / "public"
    blob = cache / "blobs" / sha256(raw)
    blob.parent.mkdir(parents=True)
    blob.write_bytes(raw)
    resolved, digest, receipt = resolve_obliteratus_artifact(public, cache, offline=True)
    assert resolved == blob and digest == sha256(raw) and receipt is None
    with pytest.raises(DatasetOfflineError, match="offline"):
        resolve_obliteratus_artifact(public, tmp_path / "empty", offline=True)


def test_generated_controls_repeat_with_explicit_parentage_and_distinct_legacy_ids():
    source = get_obliteratus_source("advbench")
    document = source.model_dump()
    document["artifact"]["accepted_count"] = None
    source = ObliteratusSource.model_validate(document)
    rows = [{"goal": f"harm {index}", "target": "response"} for index in range(100)]
    harmful = derive_obliteratus_views(source, evidence(source, rows))
    controls = [
        {"pool_index": index, "text": f"control {index}", "source_line": index + 10}
        for index in range(99)
    ]
    generated = generated_control_views(
        harmful,
        controls,
        source_revision="b" * 40,
        artifact_sha256="c" * 64,
    )
    assert generated[0].text == generated[99].text
    assert generated[0].data.row_id == generated[99].data.row_id
    assert generated[0].view_id != generated[99].view_id
    assert "not_an_upstream_paired_label" in generated[0].limitations
    legacy = derive_obliteratus_legacy_pairs(
        source,
        evidence(source, rows[:2]),
        controls,
        control_source_revision="b" * 40,
        control_artifact_sha256="c" * 64,
    )
    assert len(legacy) == 4
    assert all(view.view_id not in {item.view_id for item in harmful[:2]} for view in legacy)
    assert legacy[0].counterpart_view_id == legacy[1].view_id


def test_deterministic_limits_are_recordable_and_stable():
    source = get_obliteratus_source("advbench")
    document = source.model_dump()
    document["artifact"]["accepted_count"] = None
    source = ObliteratusSource.model_validate(document)
    views = derive_obliteratus_views(
        source,
        evidence(source, [{"goal": f"goal {index}", "target": "ok"} for index in range(20)]),
    )
    assert deterministic_limit(views, 5, seed=7) == deterministic_limit(
        list(reversed(views)), 5, seed=7
    )
    assert deterministic_limit(views, None, seed=99) == views
    with pytest.raises(ValueError, match="positive"):
        deterministic_limit(views, 0, seed=7)


def test_prepare_cli_writes_lossless_evidence_views_and_receipt(tmp_path: Path, monkeypatch):
    raw = b"goal,target\nquestion,response\n"
    artifact = tmp_path / "advbench.csv"
    artifact.write_bytes(raw)
    source = source_fixture("advbench", raw, count=1, accepted=1)
    monkeypatch.setattr("matric_eval.data.cli.get_obliteratus_source", lambda _: source)
    output = tmp_path / "prepared"
    response = CliRunner().invoke(
        datasets,
        [
            "prepare-obliteratus",
            "advbench",
            "--cache",
            str(tmp_path / "cache"),
            "--artifact",
            str(artifact),
            "--output-dir",
            str(output),
        ],
    )
    assert response.exit_code == 0, response.output
    report = json.loads(response.output)
    assert report["raw_records"] == report["prompt_views"] == 1
    receipt = json.loads((output / "advbench.receipt.json").read_text())
    assert receipt["raw_records"] == receipt["accepted_prompt_views"] == 1
    assert receipt["selection"] == {"algorithm": "all/1", "limit": None, "seed": None}
    assert len((output / "advbench.evidence.jsonl").read_text().splitlines()) == 1
    assert len((output / "advbench.prompts.jsonl").read_text().splitlines()) == 1
