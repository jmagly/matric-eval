"""Opt-in, content-free evaluation result contract (independent of provenance versions)."""

from matric_eval.results.contract import ResultEnvelope, read_result, write_result

__all__ = ["ResultEnvelope", "read_result", "write_result"]
