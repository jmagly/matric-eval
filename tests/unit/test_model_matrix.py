"""Qualified model cohort and matrix provenance tests."""

from pathlib import Path

import pytest

from matric_eval.models import ModelSpec
from matric_eval.providers.matrix import EvaluationMatrix

REV_A = "a" * 40
REV_B = "b" * 40
REV_C = "c" * 40
HASH_A = "1" * 64
HASH_B = "2" * 64


def _runtime(*, mode: str = "direct-endpoint") -> dict[str, object]:
    runtime: dict[str, object] = {
        "execution_mode": mode,
        "dtype": "bfloat16",
        "chat_template_sha256": HASH_A,
        "reasoning_mode": "on",
        "context_limit": 32768,
        "tool_protocol": "openai-tools",
        "sampler": {"temperature": 0.0, "max_tokens": 8192, "seed": 300},
    }
    if mode == "agent-harness":
        runtime.update({"agent_harness": "inspect-react", "agent_harness_revision": REV_C})
    return runtime


def _control() -> dict[str, object]:
    return {
        "id": "qwen-control-bf16",
        "model": "Qwen/Qwen3.8-27B",
        "family": "qwen3.8-27b",
        "lineage_role": "official-instruct",
        "source": "Qwen/Qwen3.8-27B",
        "checkpoint_revision": REV_A,
        "comparison_group": "qwen-e03",
        "provider": "vllm",
        "runtime": _runtime(),
    }


def _intervention() -> dict[str, object]:
    return {
        "id": "qwen-e03-bf16",
        "model": "manitcor/Qwen3.8-27B-Obliterated-E03",
        "family": "qwen3.8-27b",
        "lineage_role": "intervention",
        "source": "manitcor/Qwen3.8-27B-Obliterated-E03",
        "checkpoint_revision": REV_B,
        "comparison_group": "qwen-e03",
        "provider": "vllm",
        "runtime": _runtime(),
        "interventions": [
            {
                "method": "svd-refusal-direction-projection",
                "parent_source": "Qwen/Qwen3.8-27B",
                "parent_revision": REV_A,
                "implementation_source": "bt6/OBLITERATUS",
                "implementation_revision": REV_C,
                "config_sha256": HASH_B,
            }
        ],
    }


def test_qualified_matrix_emits_model_provenance() -> None:
    matrix = EvaluationMatrix.from_dict(
        {
            "evaluation": {
                "schema_version": 2,
                "models": [_control(), _intervention()],
                "benchmarks": ["bfcl_v4", "tau2"],
                "tier": "smoke",
            }
        }
    )

    runs = matrix.get_runs()

    assert len(runs) == 4
    assert runs[0]["model_id"] == "qwen-control-bf16"
    assert runs[0]["model_spec"]["checkpoint_revision"] == REV_A
    assert runs[1]["model_spec"]["runtime"]["execution_mode"] == "direct-endpoint"


def test_qualified_matrix_round_trips() -> None:
    matrix = EvaluationMatrix.from_dict(
        {
            "evaluation": {
                "schema_version": "2",
                "models": [_control(), _intervention()],
                "benchmarks": ["tool_calling"],
            }
        }
    )
    assert EvaluationMatrix.from_dict(matrix.to_dict()).to_dict() == matrix.to_dict()


def test_mutable_checkpoint_revision_is_rejected() -> None:
    control = _control()
    control["checkpoint_revision"] = "main"
    with pytest.raises(ValueError, match="immutable"):
        ModelSpec.from_dict(control)


def test_intervention_requires_untouched_control() -> None:
    with pytest.raises(ValueError, match="no untouched control"):
        EvaluationMatrix.from_dict(
            {
                "evaluation": {
                    "schema_version": 2,
                    "models": [_intervention()],
                    "benchmarks": ["tool_calling"],
                }
            }
        )


def test_quantization_requires_unquantized_source_peer() -> None:
    quantized = _intervention()
    quantized.update(
        {
            "id": "qwen-e03-nf4",
            "source": "manitcor/Qwen3.8-27B-Obliterated-E03-bnb-4bit",
            "checkpoint_revision": REV_C,
            "quantization": {
                "method": "bitsandbytes-nf4",
                "bits": 4,
                "library": "bitsandbytes",
                "library_version": "0.50.0",
                "library_revision": REV_C,
                "config_sha256": HASH_A,
                "source_checkpoint": "manitcor/Qwen3.8-27B-Obliterated-E03",
                "source_revision": REV_B,
            },
        }
    )
    with pytest.raises(ValueError, match="no unquantized source peer"):
        EvaluationMatrix.from_dict(
            {
                "evaluation": {
                    "schema_version": 2,
                    "models": [_control(), quantized],
                    "benchmarks": ["tool_calling"],
                }
            }
        )

    matrix = EvaluationMatrix.from_dict(
        {
            "evaluation": {
                "schema_version": 2,
                "models": [_control(), _intervention(), quantized],
                "benchmarks": ["tool_calling"],
            }
        }
    )
    assert len(matrix.get_runs()) == 3


def test_agent_harness_requires_name_and_pinned_revision() -> None:
    control = _control()
    control["runtime"] = _runtime(mode="agent-harness")
    runtime = control["runtime"]
    assert isinstance(runtime, dict)
    runtime.pop("agent_harness")
    with pytest.raises(ValueError, match="agent_harness"):
        ModelSpec.from_dict(control)


def test_historical_reconstruction_discloses_missing_implementation_commit() -> None:
    historical = _intervention()
    intervention = historical["interventions"]
    assert isinstance(intervention, list)
    intervention[0].pop("implementation_revision")
    historical.update(
        {
            "provenance_status": "reconstructed-with-gaps",
            "evidence_gaps": ["exact OBLITERATUS git commit was not retained"],
        }
    )
    spec = ModelSpec.from_dict(historical)
    assert spec.interventions[0].implementation_revision is None
    assert spec.to_dict()["provenance_status"] == "reconstructed-with-gaps"


def test_complete_intervention_rejects_missing_implementation_commit() -> None:
    incomplete = _intervention()
    intervention = incomplete["interventions"]
    assert isinstance(intervention, list)
    intervention[0].pop("implementation_revision")
    with pytest.raises(ValueError, match="implementation revision"):
        ModelSpec.from_dict(incomplete)


def test_qwen38_e03_example_is_a_matched_reconstructed_cohort() -> None:
    path = Path(__file__).parents[2] / "examples" / "qwen38-e03-agentic.yaml"
    matrix = EvaluationMatrix.from_yaml(path)
    assert len(matrix.models) == 3
    assert len(matrix.get_runs()) == 9
    specs = {model.id: model for model in matrix.models if isinstance(model, ModelSpec)}
    assert specs["qwen38-e03-bf16"].checkpoint_revision == (
        "56bbc4a80c17353254c0ed0f31828e3980970495"
    )
    assert specs["qwen38-e03-bnb-nf4"].quantization is not None
    assert specs["qwen38-e03-bnb-nf4"].quantization.source_revision == (
        specs["qwen38-e03-bf16"].checkpoint_revision
    )


def test_qualified_explicit_runs_resolve_model_ids() -> None:
    matrix = EvaluationMatrix.from_dict(
        {
            "evaluation": {
                "schema_version": 2,
                "matrix": {"mode": "explicit"},
                "models": [_control(), _intervention()],
                "runs": [
                    {"model_id": "qwen-e03-bf16", "benchmark": "bfcl_v4_agentic"}
                ],
            }
        }
    )
    assert matrix.get_runs()[0]["model"] == "manitcor/Qwen3.8-27B-Obliterated-E03"


def test_qualified_explicit_runs_reject_provider_override() -> None:
    matrix = EvaluationMatrix.from_dict(
        {
            "evaluation": {
                "schema_version": 2,
                "matrix": {"mode": "explicit"},
                "models": [_control(), _intervention()],
                "runs": [
                    {
                        "model_id": "qwen-e03-bf16",
                        "provider": "ollama",
                        "benchmark": "tool_calling",
                    }
                ],
            }
        }
    )
    with pytest.raises(ValueError, match="does not match"):
        matrix.get_runs()


def test_matrix_runner_applies_qualified_sampler_and_reasoning(monkeypatch, tmp_path) -> None:
    from matric_eval.cli import _run_matrix_evaluation

    matrix = EvaluationMatrix.from_dict(
        {
            "evaluation": {
                "schema_version": 2,
                "models": [_control(), _intervention()],
                "benchmarks": ["tool_calling"],
            }
        }
    )
    calls: list[dict[str, object]] = []

    def fake_run_evaluation(**kwargs):
        calls.append(kwargs)
        return {"model": kwargs["model"], "status": "success", "overall_score": 1.0}

    monkeypatch.setattr("matric_eval.cli.get_provider", lambda name: object())
    monkeypatch.setattr("matric_eval.cli.run_evaluation", fake_run_evaluation)
    _run_matrix_evaluation(matrix, tmp_path, "json", "off", "smoke")

    assert len(calls) == 2
    assert calls[0]["thinking_mode"] == "on"
    eval_kwargs = calls[0]["eval_kwargs"]
    assert isinstance(eval_kwargs, dict)
    assert {key: eval_kwargs[key] for key in ("temperature", "max_tokens", "seed")} == {
        "temperature": 0.0,
        "max_tokens": 8192,
        "seed": 300,
    }
    assert eval_kwargs["metadata"]["model_spec"]["id"] == "qwen-control-bf16"
