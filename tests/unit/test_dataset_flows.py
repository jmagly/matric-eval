"""Frozen evidence selections survive the Inspect task/result boundary."""

import pytest
from inspect_ai.scorer import exact
from inspect_ai.solver import generate

from matric_eval.data.adapters import InspectProjection, project_samples
from matric_eval.data.evidence import make_evidence_record
from matric_eval.data.flows import adapt_selection_log, task_from_selection
from matric_eval.data.selection import SelectionRequest, SourceSelection, select_records
from matric_eval.results.inspect_adapter import sample_identity
from tests.unit.test_inspect_result_adapter import descriptor, native_log, sample


def mixture():
    records = [
        make_evidence_record(
            {"input": f"prompt {index}", "target": "answer", "rating": None},
            source_id=source,
            source_revision="a" * 40,
            artifact_path="records.jsonl",
            artifact_sha256="b" * 64,
            row_index=index,
            native_id=index,
            cluster_id=cluster,
        )
        for index, (source, cluster) in enumerate(
            [
                ("source-a", "document-1"),
                ("source-b", None),
            ]
        )
    ]
    return select_records(
        records,
        SelectionRequest(
            seed=17,
            role="development",
            sources=[
                SourceSelection(source_id="source-a", quota=1),
                SourceSelection(source_id="source-b", quota=1),
            ],
        ),
    )


def adapt(log, manifest):
    return adapt_selection_log(
        log,
        manifest,
        run_id="run-fixture",
        model_id="mockllm/model",
        benchmark_id="mixture",
        primary_metric_id="exact/accuracy",
        descriptors={"exact/accuracy": descriptor()},
    )


def bound_log(manifest, *, missing=False):
    projection = InspectProjection(input_pointer="/input", target_pointer="/target")
    projected = project_samples(manifest, input_pointer="/input", target_pointer="/target")
    observed = projected[:1] if missing else projected
    samples = [
        sample(row.id, input=row.input, target=row.target, metadata=row.metadata)
        for row in observed
    ]
    log = native_log(samples, ids=[row.id for row in projected])
    log.eval.dataset.name = f"mixture-{manifest.manifest_sha256}"
    log.eval.metadata = {
        "dataset_selection": {
            "manifest_sha256": manifest.manifest_sha256,
            "projection": projection.model_dump(),
        }
    }
    return log


def test_frozen_task_preserves_all_ordered_records_and_explicit_components(monkeypatch):
    manifest = mixture()
    monkeypatch.setenv("MATRIC_EVAL_SEED", "999")
    solver = generate()
    scorer = exact()
    task = task_from_selection(
        manifest,
        InspectProjection(input_pointer="/input", target_pointer="/target"),
        solver=solver,
        scorer=scorer,
    )
    rows = list(task.dataset)
    assert len(rows) == 2
    assert [row.id for row in rows] == [row.selection_id for row in manifest.records]
    assert [row.input for row in rows] == [
        row.evidence.payload["input"] for row in manifest.records
    ]
    assert all(row.target == "answer" for row in rows)
    assert task.solver is solver
    assert task.scorer == [scorer]
    assert all(row.metadata["evidence"]["payload"]["rating"] is None for row in rows)


def test_task_requires_caller_solver_and_scorer():
    with pytest.raises(TypeError):
        task_from_selection(
            mixture(), InspectProjection(input_pointer="/input", target_pointer="/target")
        )


def test_result_retains_lineage_for_missing_native_sample():
    manifest = mixture()
    log = bound_log(manifest, missing=True)
    result = adapt(log, manifest)
    assert result.coverage.requested == 2
    assert result.coverage.unknown == 1
    assert not result.eligibility.eligible
    assert result.manifest_sha256 == manifest.manifest_sha256
    by_id = {row.sample_id: row for row in result.selection}
    for selected in manifest.records:
        data = by_id[sample_identity(selected.selection_id)].data
        evidence = selected.evidence
        assert data.source_id == evidence.source_id
        assert data.row_id == evidence.record_id
        assert data.role == "development"
        expected = (
            f"{evidence.source_id}:{evidence.cluster_id}"
            if evidence.cluster_id is not None
            else f"unknown-cluster:{evidence.record_id}"
        )
        assert data.independent_unit_id == expected


def test_inspect_subset_cannot_claim_full_frozen_mixture():
    manifest = mixture()
    selected = manifest.records[0].selection_id
    with pytest.raises(ValueError, match="selection_mismatch"):
        adapt(native_log([sample(selected)], ids=[selected]), manifest)


def test_native_foreign_id_cannot_inherit_catalog_lineage():
    manifest = mixture()
    ids = [manifest.records[0].selection_id, "foreign"]
    with pytest.raises(ValueError, match="selection_mismatch"):
        adapt(native_log([sample(value) for value in ids], ids=ids), manifest)


def test_ordered_native_selection_is_required():
    manifest = mixture()
    log = bound_log(manifest)
    log.eval.dataset.sample_ids.reverse()
    with pytest.raises(ValueError):
        adapt(log, manifest)


def test_changed_native_prompt_cannot_claim_frozen_content():
    manifest = mixture()
    log = bound_log(manifest)
    log.samples[0].input = "changed prompt"
    with pytest.raises(ValueError):
        adapt(log, manifest)


def test_missing_task_context_cannot_claim_frozen_content():
    manifest = mixture()
    log = bound_log(manifest)
    log.eval.metadata = None
    with pytest.raises(ValueError):
        adapt(log, manifest)
