"""Local overlap diagnostics. Foundation-model training exposure remains unknown."""

from matric_eval.contamination.detector import (
    ContaminationEvidence,
    ContaminationReport,
    NgramDetector,
    check_contamination,
    check_overlap,
)
from matric_eval.contamination.diagnostics import (
    LegacyDiagnostic,
    Method,
    OverlapReport,
    SampleDiagnostic,
    read_diagnostic,
    score_series_diagnostics,
    write_diagnostic,
)

__all__ = [
    "ContaminationEvidence",
    "ContaminationReport",
    "NgramDetector",
    "check_contamination",
    "check_overlap",
    "LegacyDiagnostic",
    "Method",
    "OverlapReport",
    "SampleDiagnostic",
    "read_diagnostic",
    "score_series_diagnostics",
    "write_diagnostic",
]
