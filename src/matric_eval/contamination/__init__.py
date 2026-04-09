"""
Benchmark contamination detection for matric-eval.

Detects when models may have been trained on evaluation data,
providing confidence in score validity.
"""

from matric_eval.contamination.detector import (
    ContaminationEvidence,
    ContaminationReport,
    NgramDetector,
    check_contamination,
)

__all__ = [
    "ContaminationEvidence",
    "ContaminationReport",
    "NgramDetector",
    "check_contamination",
]
