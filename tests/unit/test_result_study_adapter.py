"""Study adapters preserve the exact inputs and output of existing estimators."""

from dataclasses import asdict, replace

import pytest

from matric_eval.results.contract import DataReference
from matric_eval.results.study_adapter import from_study, to_study
from matric_eval.studies.analysis import StudyObservation, analyze_observations
from tests.unit.test_study_analysis import _catalog, _observations, _study


def adapt(row: StudyObservation) -> StudyObservation:
    return to_study(
        from_study(
            row,
            trial_id="locked-trial",
            attempt_id="import-1",
            data=DataReference(
                partition_schema_version="1",
                role="unknown",
                row_id=row.sample_id,
                source_id=row.allocation_id,
                independent_unit_id=row.sample_id,
            ),
            artifacts=[],
        )
    )


@pytest.mark.parametrize(
    ("status", "value"),
    [
        ("observed", 0.0),
        ("observed", 0.75),
        ("model-timeout", 0.0),
        ("infrastructure-error", None),
        ("judge-parse-failure", None),
    ],
)
def test_lossless_status_hash_identity_mapping(status: str, value: float | None) -> None:
    original = StudyObservation(
        "study", "a" * 64, "b" * 64, "model", "allocation", "sample", "metric", status, value
    )
    assert asdict(adapt(original)) == asdict(original)


def test_full_paired_analysis_is_identical_after_adapter_round_trip() -> None:
    study = _study(replicates=25)
    manifest = study.selection_manifest(_catalog(study), "full")
    rows = _observations(study, manifest)
    # Unequal allocations from the frozen protocol; introduce asymmetric missingness
    # and timeouts without changing ordered sample identities or protocol hashes.
    rows[0] = replace(rows[0], status="infrastructure-error", value=None)
    rows[1] = replace(rows[1], status="judge-parse-failure", value=None)
    rows[2] = replace(rows[2], status="model-timeout", value=0.0)
    converted = [adapt(row) for row in rows]
    assert converted == rows
    assert analyze_observations(study, manifest, converted) == analyze_observations(
        study, manifest, rows
    )


def test_unsupported_projection_is_explicit() -> None:
    original = StudyObservation(
        "study", "a" * 64, "b" * 64, "model", "allocation", "sample", "metric", "observed", 1.0
    )
    adapted = from_study(
        original,
        trial_id="t",
        attempt_id="a",
        artifacts=[],
        data=DataReference(
            partition_schema_version="1",
            role="unknown",
            row_id="sample",
            source_id="allocation",
            independent_unit_id="sample",
        ),
    )
    adapted.observation.native_status = "new-status"
    with pytest.raises(ValueError, match="projection"):
        to_study(adapted)
