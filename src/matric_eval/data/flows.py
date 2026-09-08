"""Explicit bridges from frozen mixtures to Inspect tasks and result lineage."""

from __future__ import annotations

from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset
from inspect_ai.log import EvalLog
from inspect_ai.scorer import Scorer
from inspect_ai.solver import Solver

from matric_eval.data.adapters import InspectProjection, project_samples
from matric_eval.data.selection import SelectionManifest
from matric_eval.results.contract import BenchmarkResult, DataReference, MetricDescriptor
from matric_eval.results.inspect_adapter import adapt_log, sample_identity


def task_from_selection(
    manifest: SelectionManifest,
    projection: InspectProjection,
    *,
    solver: Solver,
    scorer: Scorer | list[Scorer],
) -> Task:
    """Use exactly the frozen records with caller-selected solver and scoring.

    The task does not apply benchmark tier sampling. Downstream callers must not
    add Inspect limits/sample filters when claiming the complete frozen mixture.
    """
    samples = project_samples(manifest, **projection.model_dump(exclude={"version"}))
    return Task(
        dataset=MemoryDataset(samples=samples, name=f"mixture-{manifest.manifest_sha256}"),
        solver=solver,
        scorer=scorer,
        metadata={
            "dataset_selection": {
                "manifest_sha256": manifest.manifest_sha256,
                "projection": projection.model_dump(),
            }
        },
    )


def adapt_selection_log(
    log: EvalLog,
    manifest: SelectionManifest,
    *,
    run_id: str,
    model_id: str,
    benchmark_id: str,
    primary_metric_id: str | None = None,
    descriptors: dict[str, MetricDescriptor] | None = None,
) -> BenchmarkResult:
    """Bind all selected rows (including failed/unlogged rows) to source lineage."""
    manifest = SelectionManifest.model_validate(manifest.model_dump())
    expected = {sample_identity(row.selection_id): row for row in manifest.records}
    actual = log.eval.dataset.sample_ids
    if actual is None or [sample_identity(value) for value in actual] != list(expected):
        raise ValueError("frozen_mixture_selection_mismatch")
    binding = (log.eval.metadata or {}).get("dataset_selection", {})
    if (
        not isinstance(binding, dict)
        or binding.get("manifest_sha256") != manifest.manifest_sha256
        or log.eval.dataset.name != f"mixture-{manifest.manifest_sha256}"
    ):
        raise ValueError("frozen_mixture_task_binding_mismatch")
    projection = InspectProjection.model_validate(binding.get("projection"))
    projected = {
        sample_identity(sample.id): sample
        for sample in project_samples(manifest, **projection.model_dump(exclude={"version"}))
        if sample.id is not None
    }
    for sample in log.samples or []:
        expected_sample = projected.get(sample_identity(sample.id))
        if (
            expected_sample is None
            or sample.input != expected_sample.input
            or sample.target != expected_sample.target
            or (sample.metadata or {}).get("evidence")
            != (expected_sample.metadata or {}).get("evidence")
        ):
            raise ValueError("frozen_mixture_logged_content_mismatch")
    result = adapt_log(
        log,
        run_id=run_id,
        model_id=model_id,
        benchmark_id=benchmark_id,
        primary_metric_id=primary_metric_id,
        descriptors=descriptors,
    )
    for row in result.selection:
        evidence = expected[row.sample_id].evidence
        # Unknown grouping is explicit; row identity is only a fallback grouping,
        # not proof of statistical independence or calibration eligibility.
        row.data = DataReference(
            partition_schema_version="1",
            role=manifest.request.role,
            row_id=evidence.record_id,
            source_id=evidence.source_id,
            independent_unit_id=(
                f"{evidence.source_id}:{evidence.cluster_id}"
                if evidence.cluster_id is not None
                else f"unknown-cluster:{evidence.record_id}"
            ),
        )
    result.manifest_sha256 = manifest.manifest_sha256
    return BenchmarkResult.model_validate(result.model_dump())
