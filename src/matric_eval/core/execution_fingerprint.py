"""Capture evidence for the deliberately limited recovery execution profile.

No caller-supplied document can mark a component verified. Provider resolution
observes an endpoint at capture time, but cannot bind mutable tags to the weights
used by an inference request. Even matching before/after digests remain unverified:
a tag could change for dispatch and change back before the second observation.
Only the controlled first-party mock currently supports verified model identity.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json
import platform
import types
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from inspect_ai import Task
from inspect_ai._util.registry import (
    registry_find,
    registry_info,
    registry_params,
    registry_unqualified_name,
)
from inspect_ai.model import GenerateConfig, Model, get_model
from inspect_ai.scorer import includes, match
from inspect_ai.solver import generate
from inspect_ai.solver._chain import Chain

from matric_eval.results.contract import MetricDescriptor
from matric_eval.results.inspect_adapter import sample_identity
from matric_eval.state.observation_identity import (
    ExecutionFingerprint,
    FingerprintComponent,
    canonical_json,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _component(document: dict[str, Any], reason: str | None = None) -> FingerprintComponent:
    return FingerprintComponent(
        document=document, status="unverified" if reason else "verified", unavailable_reason=reason
    )


def _closure_equal(actual: object, expected: object) -> bool:
    """Verify factory-produced functions, not merely spoofable registry labels."""
    if isinstance(actual, types.FunctionType) and isinstance(expected, types.FunctionType):
        if actual.__code__ is not expected.__code__ or actual.__defaults__ != expected.__defaults__:
            return False
        left = actual.__closure__ or ()
        right = expected.__closure__ or ()
        return len(left) == len(right) and all(
            _closure_equal(a.cell_contents, b.cell_contents)
            for a, b in zip(left, right, strict=True)
        )
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _closure_equal(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            _closure_equal(a, b) for a, b in zip(actual, expected, strict=True)
        )
    if actual is None or isinstance(actual, (str, bool, int, float)):
        return actual == expected
    return False


def _registered(callable_: object, factories: dict[str, Any]) -> dict[str, Any]:
    info = registry_info(callable_)
    name = info.name.rsplit("/", 1)[-1]
    if name not in factories:
        raise ValueError("unsupported registered recovery callable")
    params = registry_params(callable_)
    canonical_json(params)
    reconstructed = factories[name](**params)
    if not _closure_equal(callable_, reconstructed):
        raise ValueError("opaque or changed recovery callable closure")
    source = inspect.getsourcefile(inspect.unwrap(factories[name]))
    if source is None:
        raise ValueError("callable source unavailable")
    return {
        "name": info.name,
        "parameters": params,
        "factory_source_sha256": _sha(Path(source).read_bytes()),
    }


def _pipeline(task: Task) -> dict[str, Any]:
    from inspect_ai.hooks._hooks import get_all_hooks

    # Inspect hook subscribers are process-wide mutable executable objects.
    # Do not call enabled(): that is itself an opaque callback and may change
    # between events. Consult both the registry and what Inspect would emit to,
    # so a stale empty cache cannot hide a newly registered subscriber.
    registered_hooks = registry_find(lambda info: info.type == "hooks")
    emitted_hooks = get_all_hooks()
    if registered_hooks or emitted_hooks:
        raise ValueError("unsupported recovery task feature: global Inspect hooks")
    for attribute in (
        "setup",
        "cleanup",
        "on_checkpoint",
        "on_resume",
        "sample_source",
        "sandbox",
        "model",
        "model_roles",
        "approval",
        "early_stopping",
        "checkpoint",
    ):
        if getattr(task, attribute, None):
            raise ValueError(f"unsupported recovery task feature: {attribute}")
    if task.metrics is not None:
        raise ValueError("custom metric reducers are unsupported")
    solvers = list(task.solver) if isinstance(task.solver, Chain) else [task.solver]
    if len(solvers) != 1:
        raise ValueError("recovery profile requires exactly one generate solver")
    solver = _registered(solvers[0], {"generate": generate})
    if solver["parameters"] not in ({}, {"tool_calls": "none"}):
        raise ValueError("generation overrides must be explicit in the recovery configuration")
    scorers = list(task.scorer or [])
    if not scorers:
        raise ValueError("a supported registered scorer is required")
    scorer_records = [_registered(item, {"match": match, "includes": includes}) for item in scorers]
    if len({item["name"] for item in scorer_records}) != len(scorer_records):
        raise ValueError("duplicate named scorers are unsupported")
    for sample in task.dataset:
        if sample.files or sample.sandbox or not isinstance(sample.input, str):
            raise ValueError(
                "first recovery profile supports text-only samples without files or sandbox"
            )
    execution = {
        name: getattr(task, name, None)
        for name in (
            "fail_on_error",
            "continue_on_fail",
            "score_on_error",
            "message_limit",
            "token_limit",
            "token_limit_type",
            "turn_limit",
            "time_limit",
            "working_limit",
            "cost_limit",
            "version",
            "metadata",
            "epochs",
            "epochs_reducer",
        )
    }
    execution = json.loads(canonical_json(execution))
    return {
        "solver": solver,
        "scorers": scorer_records,
        "profile": "text-generate-match/1",
        "task_execution": execution,
    }


def validate_recovery_task(task: Task) -> None:
    """Reject unreviewed executable task closures before dispatch."""
    _pipeline(task)


def _read_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("provider metadata exceeds capture limit")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("provider metadata is not an object")
    return result


def _model_identity(
    model: str,
    model_base_url: str | None,
    model_args: dict[str, Any],
    *,
    effective_model: Model | None = None,
    generation_config: GenerateConfig | None = None,
) -> FingerprintComponent:
    provider_name = model.split("/", 1)[0]
    if provider_name in {"mockllm", "ollama"}:
        from inspect_ai.model._providers import providers

        expected_factory = providers.mockllm if provider_name == "mockllm" else providers.ollama
        selected_factories = registry_find(
            lambda info: (
                info.type == "modelapi" and registry_unqualified_name(info) == provider_name
            )
        )
        if not selected_factories or selected_factories[0] is not expected_factory:
            return _component({"model": model}, "provider_implementation_unverified")
        # Resolve outside Inspect's model cache and validate the actual dispatch
        # object. A display-name prefix never establishes implementation identity.
        if not model_args and (provider_name == "mockllm" or model_base_url is not None):
            config = generation_config or GenerateConfig()
            try:
                # Inspect providers load optional SDKs lazily. Importing an
                # unrelated provider must not break an offline capture profile.
                expected_type: type[Any]
                if provider_name == "mockllm":
                    from inspect_ai.model._providers.mockllm import MockLLM

                    expected_type = MockLLM
                else:
                    from inspect_ai.model._providers.ollama import OllamaAPI

                    expected_type = OllamaAPI
                actual = effective_model or get_model(
                    model, base_url=model_base_url, config=config, memoize=False
                )
            except ImportError:
                return _component({"model": model}, "effective_provider_dependencies_unavailable")
            except (ValueError, TypeError, OSError):
                return _component({"model": model}, "effective_provider_resolution_failed")
            if (
                type(actual) is not Model
                or type(actual.api) is not expected_type
                or actual.api.model_name != model.split("/", 1)[1]
                or (model_base_url is not None and actual.api.base_url != model_base_url)
                or actual.model_args
                or actual.config.model_dump() != config.model_dump()
                or "generate" in vars(actual)
                or "generate" in vars(actual.api)
            ):
                return _component({"model": model}, "provider_implementation_unverified")
            if provider_name == "mockllm":
                from inspect_ai.model._providers.mockllm import MockLLM

                if not isinstance(actual.api, MockLLM):
                    return _component({"model": model}, "provider_implementation_unverified")
                expected_outputs = MockLLM(model_name=model.split("/", 1)[1]).outputs
                if (
                    not isinstance(actual.api.outputs, types.GeneratorType)
                    or not isinstance(expected_outputs, types.GeneratorType)
                    or actual.api.outputs.gi_code is not expected_outputs.gi_code
                    or actual.api.default_output != MockLLM.default_output
                ):
                    return _component({"model": model}, "opaque_model_outputs")
    if model.startswith("mockllm/") and not model_args and model_base_url is None:
        from inspect_ai.model._providers.mockllm import MockLLM

        source = inspect.getsourcefile(MockLLM)
        assert source is not None
        return _component(
            {
                "provider": "inspect-mockllm",
                "model": model,
                "fixed_output": MockLLM.default_output,
                "implementation_sha256": _sha(Path(source).read_bytes()),
            }
        )
    if not model.startswith("ollama/"):
        return _component(
            {"model": model, "provider": model.split("/", 1)[0]},
            "provider_immutable_identity_unavailable",
        )
    if model_args:
        return _component({"model": model}, "opaque_model_arguments")
    if model_base_url is None:
        return _component({"model": model}, "effective_model_endpoint_unverified")
    parts = urlsplit(model_base_url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        return _component({"model": model}, "unsupported_model_endpoint")
    path = parts.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    endpoint = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    name = model.removeprefix("ollama/")
    if ":" not in name.rsplit("/", 1)[-1]:
        name += ":latest"
    try:

        def resolved_digest() -> str:
            tags = _read_json(endpoint + "/api/tags")
            matches = [
                item
                for item in tags.get("models", [])
                if item.get("name") == name or item.get("model") == name
            ]
            if len(matches) != 1:
                raise ValueError("model tag is not uniquely resolved")
            digest = matches[0].get("digest", "")
            if not isinstance(digest, str):
                raise ValueError("immutable model digest is not a string")
            normalized = digest.removeprefix("sha256:")
            if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
                raise ValueError("immutable model digest unavailable")
            return normalized

        before = resolved_digest()
        shown = _read_json(endpoint + "/api/show", {"model": name})
        version = _read_json(endpoint + "/api/version")
        after = resolved_digest()
        if (
            before != after
            or not shown.get("model_info")
            or not isinstance(version.get("version"), str)
        ):
            raise ValueError("unstable or incomplete provider metadata")
        return _component(
            {
                "provider": "ollama",
                "endpoint": endpoint,
                "model": name,
                "digest": before,
                "server_version": version["version"],
                "model_info": shown["model_info"],
                "parameters": shown.get("parameters", ""),
                "template": shown.get("template", ""),
                "system": shown.get("system", ""),
                "scope": "endpoint-resolution-at-capture-time/1",
            },
            "mutable_provider_tag_not_bound_to_request",
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return _component(
            {"model": model, "endpoint": endpoint}, "provider_identity_resolution_failed"
        )


def _environment() -> FingerprintComponent:
    import inspect_ai

    import matric_eval

    root = Path(__file__).resolve().parents[3]
    document: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "execution_profile": "text-generate-match/1",
    }
    try:
        lock = root / "uv.lock"
        document["lock_sha256"] = _sha(lock.read_bytes())
        packages = {}
        for module in (inspect_ai, matric_eval):
            source_file = module.__file__
            if source_file is None:
                raise ValueError("package source location unavailable")
            directory = Path(source_file).resolve().parent
            records = [
                (str(path.relative_to(directory)), _sha(path.read_bytes()))
                for path in sorted(directory.rglob("*.py"))
            ]
            if not records:
                raise ValueError("package source closure unavailable")
            packages[module.__name__] = _sha(canonical_json(records).encode())
        document["source_packages"] = packages
        document["installed_distributions"] = sorted(
            (distribution.metadata["Name"], distribution.version)
            for distribution in importlib.metadata.distributions()
            if "Name" in distribution.metadata
        )
        # Convert tuples to explicit JSON arrays before strict identity validation.
        return _component(json.loads(canonical_json(document)))
    except (OSError, ValueError, TypeError):
        return _component(document, "source_lock_or_runtime_identity_unavailable")


def capture_execution_fingerprint(
    task: Task,
    *,
    benchmark: str,
    model: str,
    metric_descriptors: dict[str, MetricDescriptor],
    generation_config: GenerateConfig,
    selection_seed: int,
    generation_seed: int,
    trial_id: str,
    generation_seeds: list[int],
    primary_metric_id: str,
    model_base_url: str | None = None,
    model_args: dict[str, Any] | None = None,
    effective_model: Model | None = None,
) -> ExecutionFingerprint:
    """Capture a full frozen-plan identity; unsupported evidence is explicitly unverified."""
    samples = list(task.dataset)
    payload = [sample.model_dump(mode="json") for sample in samples]
    try:
        pipeline = _pipeline(task)
        prompt = _component(
            {
                "pipeline": pipeline,
                "ordered_input_sha256": _sha(
                    canonical_json([sample.input for sample in samples]).encode()
                ),
            }
        )
        checked_metrics = {
            key: MetricDescriptor.model_validate(item.model_dump())
            for key, item in metric_descriptors.items()
        }
        if (
            not checked_metrics
            or primary_metric_id not in checked_metrics
            or any(
                key != item.metric_id
                or item.scorer_id
                not in {row["name"].rsplit("/", 1)[-1] for row in pipeline["scorers"]}
                for key, item in checked_metrics.items()
            )
        ):
            raise ValueError("metric declarations differ from configured scorers")
        scorer = _component(
            {
                "registered_scorers": pipeline["scorers"],
                "descriptors": {
                    key: item.model_dump() for key, item in sorted(metric_descriptors.items())
                },
            }
        )
    except (ValueError, TypeError, OSError):
        prompt = _component({"benchmark": benchmark}, "opaque_prompt_solver_or_tools")
        scorer = _component(
            {"metric_ids": sorted(metric_descriptors)}, "scorer_implementation_unverified"
        )
    dataset = _component(
        {
            "benchmark": benchmark,
            "dataset_name": task.dataset.name,
            "ordered_ids": [
                sample_identity(sample.id) if isinstance(sample.id, (str, int)) else None
                for sample in samples
            ],
            "ordered_content_sha256": _sha(canonical_json(payload).encode()),
        }
    )
    if (
        task.sample_source is not None
        or not samples
        or any(type(sample.id) not in (str, int) for sample in samples)
    ):
        dataset = _component(dataset.document, "frozen_manifest_unverified")
    resolved_model = _model_identity(
        model,
        model_base_url,
        model_args or {},
        effective_model=effective_model,
        generation_config=generation_config,
    )
    config = generation_config.model_dump(mode="json")
    required = ("seed", "temperature", "max_tokens", "top_p", "stop_seqs", "max_retries")
    sampler_reason = None
    if (
        any(
            type(seed) is not int or not 0 <= seed <= 9007199254740991
            for seed in [selection_seed, generation_seed, *generation_seeds]
        )
        or len(set(generation_seeds)) != len(generation_seeds)
        or not generation_seeds
    ):
        sampler_reason = "invalid_generation_schedule"
    elif config.get("seed") != generation_seed or generation_seed not in generation_seeds:
        sampler_reason = "generation_schedule_mismatch"
    elif not model.startswith("mockllm/") and any(config.get(key) is None for key in required):
        sampler_reason = "effective_generation_defaults_unverified"
    return ExecutionFingerprint(
        model=resolved_model,
        dataset=dataset,
        prompt=prompt,
        scorer=scorer,
        sampler=_component(
            {
                "selection_seed": selection_seed,
                "generation_seed": generation_seed,
                "generation_seeds": generation_seeds,
                "trial_id": trial_id,
                "effective_config": config,
                "task_config": task.config.model_dump(mode="json"),
            },
            sampler_reason,
        ),
        environment=_environment(),
        protocol=_component(
            {
                "profile": "recoverable-text-sample/1",
                "benchmark": benchmark,
                "primary_metric_id": primary_metric_id,
                "journal_version": "1",
                "result_version": "2",
                "epochs": 1,
                "sample_shuffle": False,
                "retry_scope": "manual-no-replay",
            }
        ),
    )
