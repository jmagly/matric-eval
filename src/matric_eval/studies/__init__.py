"""Preregistered study protocols and validation helpers."""

from matric_eval.studies.analysis import (
    StudyObservation,
    analyze_observations,
    bootstrap_mean_ci,
    exact_mcnemar_pvalue,
    holm_adjust,
    load_observations,
    paired_bootstrap_delta_ci,
    stratified_paired_bootstrap_ci,
    wilson_interval,
)
from matric_eval.studies.batch import (
    StudyBatchRequest,
    build_model_qualification,
    load_batch_requests,
    run_offline_batch,
    validate_batch_contract,
    verify_model_artifact,
)
from matric_eval.studies.protocol import BenchmarkAllocation, StudyProtocol

__all__ = [
    "BenchmarkAllocation",
    "StudyBatchRequest",
    "StudyObservation",
    "StudyProtocol",
    "analyze_observations",
    "bootstrap_mean_ci",
    "build_model_qualification",
    "exact_mcnemar_pvalue",
    "holm_adjust",
    "load_batch_requests",
    "load_observations",
    "paired_bootstrap_delta_ci",
    "run_offline_batch",
    "stratified_paired_bootstrap_ci",
    "validate_batch_contract",
    "verify_model_artifact",
    "wilson_interval",
]
