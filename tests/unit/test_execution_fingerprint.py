"""Actual fixed task capture and endpoint-bound metadata resolution, without inference."""

from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import match
from inspect_ai.solver import generate, system_message

from matric_eval.core.execution_fingerprint import (
    _model_identity,
    capture_execution_fingerprint,
    validate_recovery_task,
)
from matric_eval.results.contract import MetricDescriptor


def fixed_task():
    return Task(
        dataset=MemoryDataset(
            [
                Sample(id="a", input="first", target="Default output from mockllm/model"),
                Sample(id="b", input="second", target="not the mock output"),
            ],
            name="controlled/1",
        ),
        solver=generate(),
        scorer=match(),
    )


def descriptor():
    return MetricDescriptor(
        metric_id="match/accuracy",
        version="fixture/1",
        scorer_id="match",
        value_kind="binary",
        units="answer-correct",
        direction="higher",
        minimum=0.0,
        maximum=1.0,
        independent_unit="task",
        missingness_policy="require-complete/1",
        aggregation_id="accuracy/1",
        timeout_value=None,
    )


def capture(task=None, **changes):
    values = {
        "benchmark": "controlled",
        "model": "mockllm/model",
        "metric_descriptors": {"match/accuracy": descriptor()},
        "primary_metric_id": "match/accuracy",
        "generation_config": GenerateConfig(seed=17),
        "selection_seed": 1,
        "generation_seed": 17,
        "generation_seeds": [17, 29],
        "trial_id": "trial-0",
    }
    values.update(changes)
    return capture_execution_fingerprint(task or fixed_task(), **values)


def test_supported_task_capture_has_seven_evidence_components_without_inference():
    task = fixed_task()
    validate_recovery_task(task)
    with patch("urllib.request.urlopen") as transport:
        result = capture(task)
    transport.assert_not_called()
    assert result.eligibility.eligible, result.eligibility.reasons
    assert result.model.document["fixed_output"] == "Default output from mockllm/model"
    assert result.dataset.document["ordered_ids"] == ['"a"', '"b"']
    assert result.prompt.document["pipeline"]["profile"] == "text-generate-match/1"
    assert result.environment.document["source_packages"]["inspect_ai"]
    assert result.environment.document["lock_sha256"]
    assert result.sha256 == capture(task).sha256


@pytest.mark.parametrize("model", ["mockllm/model", "ollama/model"])
def test_replaced_provider_factory_cannot_inherit_first_party_identity(model):
    with (
        patch("matric_eval.core.execution_fingerprint.registry_find", return_value=[object()]),
        patch("urllib.request.urlopen") as transport,
    ):
        result = _model_identity(model, None, {})
    assert result.status == "unverified"
    assert result.unavailable_reason == "provider_implementation_unverified"
    transport.assert_not_called()


def test_effective_mock_with_custom_outputs_cannot_claim_default_output_identity():
    actual = get_model("mockllm/model", config=GenerateConfig(seed=17), memoize=False)
    actual.api.outputs = lambda *_args: "opaque output"
    result = capture(effective_model=actual)
    assert result.model.status == "unverified"
    assert result.model.unavailable_reason == "opaque_model_outputs"


def test_effective_mock_configuration_must_match_dispatch_configuration():
    actual = get_model("mockllm/model", config=GenerateConfig(seed=99), memoize=False)
    result = capture(effective_model=actual)
    assert result.model.status == "unverified"
    assert result.model.unavailable_reason == "provider_implementation_unverified"


def test_registered_hook_blocks_dispatch_and_reuse_until_removed():
    from inspect_ai._util import registry
    from inspect_ai.hooks import Hooks
    from inspect_ai.hooks._hooks import get_all_hooks

    class FixtureHook(Hooks):
        pass

    task = fixed_task()
    validate_recovery_task(task)
    key = registry.registry_key("hooks", "recovery-capture-fixture")
    assert key not in registry._registry
    try:
        registry.registry_add(
            FixtureHook(), registry.RegistryInfo(type="hooks", name="recovery-capture-fixture")
        )
        assert get_all_hooks()
        with pytest.raises(ValueError, match="global Inspect hooks"):
            validate_recovery_task(task)
        result = capture(task)
        assert result.prompt.status == "unverified"
        assert not result.eligibility.eligible
    finally:
        registry._registry.pop(key, None)
        get_all_hooks()
    validate_recovery_task(task)


def test_registry_hook_cannot_be_hidden_by_stale_empty_dispatch_cache(monkeypatch):
    from inspect_ai._util import registry
    from inspect_ai.hooks import Hooks, _hooks

    class FixtureHook(Hooks):
        pass

    key = registry.registry_key("hooks", "recovery-capture-stale-fixture")
    assert key not in registry._registry
    try:
        registry.registry_add(
            FixtureHook(),
            registry.RegistryInfo(type="hooks", name="recovery-capture-stale-fixture"),
        )
        with monkeypatch.context() as patcher:
            patcher.setattr(_hooks, "_hooks_cache", [])
            patcher.setattr(
                _hooks, "_hooks_cache_state", (registry._registry_version, len(registry._registry))
            )
            with pytest.raises(ValueError, match="global Inspect hooks"):
                validate_recovery_task(fixed_task())
    finally:
        registry._registry.pop(key, None)
        _hooks.get_all_hooks()


def test_same_display_ids_with_changed_content_block_reuse():
    original = capture()
    changed = fixed_task()
    changed.dataset[0].input = "changed prompt"
    current = capture(changed)
    assert "component_mismatch:dataset" in original.mismatch_reasons(current)
    assert "component_mismatch:prompt" in original.mismatch_reasons(current)


def test_order_targets_and_full_seed_schedule_are_captured():
    original = capture()
    changed = fixed_task()
    changed.dataset[0].target = "changed target"
    assert "component_mismatch:dataset" in original.mismatch_reasons(capture(changed))
    changed.dataset = MemoryDataset(list(reversed(list(changed.dataset))), name="controlled/1")
    assert (
        original.dataset.document["ordered_ids"] != capture(changed).dataset.document["ordered_ids"]
    )
    assert "component_mismatch:sampler" in original.mismatch_reasons(
        capture(generation_seeds=[17, 31])
    )


def test_scorer_parameters_and_metric_version_are_captured():
    original = capture()
    changed = fixed_task()
    changed.scorer = [match(ignore_case=False)]
    assert "component_mismatch:scorer" in original.mismatch_reasons(capture(changed))
    metric = descriptor().model_copy(update={"version": "fixture/2"})
    assert "component_mismatch:scorer" in original.mismatch_reasons(
        capture(metric_descriptors={metric.metric_id: metric})
    )


@pytest.mark.parametrize("feature", ["closure", "pipeline", "setup", "cleanup", "file"])
def test_opaque_or_side_effecting_tasks_are_rejected_before_execution(feature):
    task = fixed_task()

    async def opaque(state, generate):
        return state

    if feature == "closure":
        task.solver = opaque
    elif feature == "pipeline":
        task = Task(
            dataset=task.dataset,
            solver=[system_message("hidden transform"), generate()],
            scorer=match(),
        )
    elif feature in {"setup", "cleanup"}:
        setattr(task, feature, opaque)
    else:
        task.dataset[0].files = {"owned.txt": "content"}
    with pytest.raises(ValueError):
        validate_recovery_task(task)
    result = capture(task)
    assert not result.prompt.status == "verified"


def test_registered_name_spoof_does_not_verify_opaque_closure():
    task = fixed_task()
    trusted = generate()

    async def opaque(state, generate):
        return state

    opaque.__dict__.update(trusted.__dict__)
    task.solver = opaque
    with pytest.raises(ValueError, match="closure"):
        validate_recovery_task(task)


def test_unknown_models_and_callbacks_cannot_supply_verified_identity():
    assert capture(model="openai/arbitrary").model.status == "unverified"
    result = capture(model_args={"custom_outputs": lambda *args: None})
    assert result.model.status == "unverified"
    assert "custom_outputs" not in result.model.document


def metadata_transport(url, payload=None):
    if url.endswith("/api/tags"):
        return {"models": [{"name": "model:latest", "digest": "a" * 64}]}
    if url.endswith("/api/show"):
        assert payload == {"model": "model:latest"}
        return {
            "model_info": {"architecture": "llama", "context_length": 8192},
            "template": "captured template",
            "parameters": "temperature 0.2",
        }
    assert url.endswith("/api/version")
    return {"version": "fixture-runtime-version"}


def test_stable_ollama_metadata_does_not_bind_dispatch_weights():
    with patch(
        "matric_eval.core.execution_fingerprint._read_json", side_effect=metadata_transport
    ) as transport:
        result = _model_identity("ollama/model", "http://controlled:11434/v1", {})
    assert result.status == "unverified"
    assert result.unavailable_reason == "mutable_provider_tag_not_bound_to_request"
    assert result.document["digest"] == "a" * 64
    assert result.document["endpoint"] == "http://controlled:11434"
    assert result.document["template"] == "captured template"
    assert all(
        call.args[0].startswith("http://controlled:11434/api/") for call in transport.call_args_list
    )
    assert len(transport.call_args_list) == 4


def test_ollama_changed_digest_or_absent_revision_is_unverified():
    values = [
        {"models": [{"name": "model:latest", "digest": "a" * 64}]},
        {"model_info": {"architecture": "llama"}},
        {"version": "fixture"},
        {"models": [{"name": "model:latest", "digest": "b" * 64}]},
    ]
    with patch("matric_eval.core.execution_fingerprint._read_json", side_effect=values):
        assert _model_identity("ollama/model", "http://controlled/v1", {}).status == "unverified"
    with patch("matric_eval.core.execution_fingerprint._read_json", return_value={"models": []}):
        assert _model_identity("ollama/model", "http://controlled/v1", {}).status == "unverified"


@pytest.mark.parametrize(
    "endpoint", [None, "http://user:secret@host/v1", "http://host/v1?key=secret"]
)
def test_implicit_or_credential_bearing_endpoint_is_unverified(endpoint):
    with patch("matric_eval.core.execution_fingerprint._read_json") as transport:
        result = _model_identity("ollama/model", endpoint, {})
    transport.assert_not_called()
    assert result.status == "unverified"
    assert "secret" not in str(result.model_dump())


def test_real_provider_unknown_generation_defaults_block_verified_reuse():
    with patch("matric_eval.core.execution_fingerprint._read_json", side_effect=metadata_transport):
        result = capture(model="ollama/model", model_base_url="http://controlled/v1")
    assert result.model.status == "unverified"
    assert result.model.unavailable_reason == "mutable_provider_tag_not_bound_to_request"
    assert result.sampler.unavailable_reason == "effective_generation_defaults_unverified"


def test_mock_capture_does_not_import_unrelated_provider_dependencies() -> None:
    import builtins

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "inspect_ai.model._providers.ollama":
            raise ModuleNotFoundError("unavailable optional provider dependency")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=guarded_import):
        result = _model_identity("mockllm/model", None, {})
    assert result.status == "verified"
    assert result.document["provider"] == "inspect-mockllm"


def test_selected_provider_missing_dependency_is_unverified() -> None:
    import builtins

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "inspect_ai.model._providers.ollama":
            raise ModuleNotFoundError("unavailable optional provider dependency")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=guarded_import):
        result = _model_identity("ollama/model", "http://127.0.0.1:11434", {})
    assert result.status == "unverified"
    assert result.unavailable_reason == "effective_provider_dependencies_unavailable"
