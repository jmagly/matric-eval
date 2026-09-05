"""Model capability and versioned identity utilities."""

from matric_eval.models.detection import (
    get_ollama_model_info,
    has_thinking_capability,
)
from matric_eval.models.spec import (
    ExecutionMode,
    InterventionSpec,
    LineageRole,
    ModelSpec,
    ProvenanceStatus,
    QuantizationSpec,
    RuntimeSpec,
)

__all__ = [
    "ExecutionMode",
    "InterventionSpec",
    "LineageRole",
    "ModelSpec",
    "ProvenanceStatus",
    "QuantizationSpec",
    "RuntimeSpec",
    "get_ollama_model_info",
    "has_thinking_capability",
]
