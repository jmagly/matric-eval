"""Reproducible offline vLLM execution for preregistered studies."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from matric_eval.models import ExecutionMode, ModelSpec
from matric_eval.studies.protocol import StudyProtocol


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class StudyBatchRequest:
    """One manifest-qualified chat request."""

    request_id: str
    allocation_id: str
    sample_id: str
    messages: tuple[dict[str, Any], ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any], line_number: int) -> StudyBatchRequest:
        context = f"request line {line_number}"
        required = ("request_id", "allocation_id", "sample_id")
        values: dict[str, str] = {}
        for key in required:
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{context}.{key} must be a non-empty string")
            values[key] = value.strip()
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError(f"{context}.messages must be a non-empty list")
        if not all(
            isinstance(message, dict)
            and isinstance(message.get("role"), str)
            and isinstance(message.get("content"), str)
            for message in messages
        ):
            raise ValueError(f"{context}.messages must contain string role/content objects")
        return cls(
            request_id=values["request_id"],
            allocation_id=values["allocation_id"],
            sample_id=values["sample_id"],
            messages=tuple(dict(message) for message in messages),
        )


def load_batch_requests(path: str | Path) -> list[StudyBatchRequest]:
    """Load and validate ordered JSONL requests."""
    requests: list[StudyBatchRequest] = []
    for line_number, raw_line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"request line {line_number} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"request line {line_number} must contain an object")
        requests.append(StudyBatchRequest.from_dict(payload, line_number))
    if not requests:
        raise ValueError("request JSONL must contain at least one request")
    request_ids = [request.request_id for request in requests]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError("request JSONL contains duplicate request_id values")
    sample_keys = [(request.allocation_id, request.sample_id) for request in requests]
    if len(sample_keys) != len(set(sample_keys)):
        raise ValueError("request JSONL contains duplicate allocation/sample pairs")
    return requests


def validate_batch_contract(
    study: StudyProtocol,
    manifest: dict[str, Any],
    requests: list[StudyBatchRequest],
) -> None:
    """Require requests to equal the ordered offline subset of a study manifest."""
    if manifest.get("study_id") != study.id:
        raise ValueError("manifest study_id does not match the protocol")
    if manifest.get("protocol_sha256") != study.canonical_sha256:
        raise ValueError("manifest protocol_sha256 does not match the protocol")
    canonical_manifest = dict(manifest)
    declared_manifest_sha256 = canonical_manifest.pop("manifest_sha256", None)
    actual_manifest_sha256 = hashlib.sha256(
        json.dumps(canonical_manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared_manifest_sha256 != actual_manifest_sha256:
        raise ValueError("manifest_sha256 does not match the manifest's canonical content")
    allocations = manifest.get("allocations")
    if not isinstance(allocations, list):
        raise ValueError("manifest.allocations must be a list")

    modes = {allocation.id: allocation.execution_mode for allocation in study.benchmarks}
    manifest_ids = [
        allocation.get("allocation_id") if isinstance(allocation, dict) else None
        for allocation in allocations
    ]
    expected_allocation_ids = [allocation.id for allocation in study.benchmarks]
    if manifest_ids != expected_allocation_ids:
        raise ValueError("manifest allocations must exactly match protocol order")
    cohort = manifest.get("cohort")
    if cohort not in {"pilot", "full"}:
        raise ValueError("manifest cohort must be pilot or full")
    allocation_specs = {allocation.id: allocation for allocation in study.benchmarks}
    requested_allocation_ids = list(
        dict.fromkeys(request.allocation_id for request in requests)
    )
    if any(
        allocation_id not in modes or modes[allocation_id] != "offline-batch"
        for allocation_id in requested_allocation_ids
    ):
        raise ValueError("requests may contain only protocol-qualified offline-batch allocations")
    expected_requested_order = [
        allocation.id
        for allocation in study.benchmarks
        if allocation.id in requested_allocation_ids
    ]
    if requested_allocation_ids != expected_requested_order:
        raise ValueError("request allocation blocks must follow protocol order")

    expected: list[tuple[str, str]] = []
    for manifest_allocation in allocations:
        if not isinstance(manifest_allocation, dict):
            raise ValueError("each manifest allocation must be an object")
        allocation_id = manifest_allocation.get("allocation_id")
        selected_ids = manifest_allocation.get("selected_ids")
        if not isinstance(allocation_id, str) or allocation_id not in modes:
            raise ValueError(f"manifest contains unknown allocation: {allocation_id!r}")
        if not isinstance(selected_ids, list) or not all(
            isinstance(sample_id, str) for sample_id in selected_ids
        ):
            raise ValueError(f"manifest allocation {allocation_id} has invalid selected_ids")
        expected_count = (
            allocation_specs[allocation_id].pilot_samples
            if cohort == "pilot"
            else allocation_specs[allocation_id].full_samples
        )
        if len(selected_ids) != expected_count or len(selected_ids) != len(set(selected_ids)):
            raise ValueError(
                f"manifest allocation {allocation_id} does not contain {expected_count} unique IDs"
            )
        expected_ids_sha256 = hashlib.sha256("\n".join(selected_ids).encode()).hexdigest()
        if manifest_allocation.get("ordered_ids_sha256") != expected_ids_sha256:
            raise ValueError(f"manifest allocation {allocation_id} ordered ID hash mismatch")
        if allocation_id in requested_allocation_ids:
            expected.extend((allocation_id, sample_id) for sample_id in selected_ids)

    actual = [(request.allocation_id, request.sample_id) for request in requests]
    if actual != expected:
        raise ValueError(
            "request order/content must exactly match each requested manifest allocation"
        )


def _load_json_object(path: str | Path, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{description} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must contain an object")
    return payload


def _model_for_id(study: StudyProtocol, model_id: str) -> ModelSpec:
    model = next((candidate for candidate in study.models if candidate.id == model_id), None)
    if model is None:
        raise ValueError(f"unknown study model id: {model_id}")
    if model.runtime.execution_mode is not ExecutionMode.OFFLINE_BATCH:
        raise ValueError(f"study model {model_id} is not qualified for offline-batch execution")
    return model


def verify_model_artifact(
    model: ModelSpec,
    model_directory: Path,
    qualification: dict[str, Any],
) -> str:
    """Verify every qualified artifact and all tensors referenced by the model index."""
    required_identity = {
        "schema_version": "1",
        "model_id": model.id,
        "model_source": model.source,
        "model_revision": model.checkpoint_revision,
    }
    for key, expected in required_identity.items():
        if qualification.get(key) != expected:
            raise ValueError(f"model qualification {key} does not match {expected!r}")
    raw_files = qualification.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("model qualification files must be a non-empty list")

    qualified_paths: set[str] = set()
    for position, raw_file in enumerate(raw_files):
        if not isinstance(raw_file, dict):
            raise ValueError(f"model qualification file {position} must be an object")
        relative = raw_file.get("path")
        size = raw_file.get("size")
        expected_sha256 = raw_file.get("sha256")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise ValueError(f"model qualification file {position} has an unsafe path")
        if relative in qualified_paths:
            raise ValueError(f"model qualification repeats file {relative}")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"model qualification file {relative} has an invalid size")
        if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
            raise ValueError(f"model qualification file {relative} has an invalid SHA-256")
        artifact = model_directory / relative
        if not artifact.is_file() or artifact.stat().st_size != size:
            raise ValueError(f"qualified model artifact is missing or has wrong size: {relative}")
        actual_sha256 = _sha256_file(artifact)
        if actual_sha256 != expected_sha256.lower():
            raise ValueError(f"qualified model artifact SHA-256 mismatch: {relative}")
        qualified_paths.add(relative)

    index_name = qualification.get("model_index", "model.safetensors.index.json")
    if not isinstance(index_name, str) or index_name not in qualified_paths:
        raise ValueError("model qualification must include its model_index")
    index = _load_json_object(model_directory / index_name, "model tensor index")
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise ValueError("model tensor index must contain a non-empty weight_map")
    raw_referenced = set(weight_map.values())
    if not all(isinstance(path, str) for path in raw_referenced):
        raise ValueError("model tensor index contains a non-string artifact path")
    referenced = {str(path) for path in raw_referenced}
    missing = referenced - qualified_paths
    if missing:
        raise ValueError(
            "model qualification omits indexed tensor files: " + ", ".join(sorted(missing))
        )
    required_support = {"config.json", "tokenizer_config.json", "chat_template.jinja"}
    if not required_support.issubset(qualified_paths):
        missing_support = ", ".join(sorted(required_support - qualified_paths))
        raise ValueError(f"model qualification omits required support files: {missing_support}")
    canonical_payload = dict(qualification)
    declared_sha256 = canonical_payload.pop("qualification_sha256", None)
    canonical = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode()
    actual_qualification_sha256 = hashlib.sha256(canonical).hexdigest()
    if declared_sha256 != actual_qualification_sha256:
        raise ValueError("model qualification SHA-256 does not match its canonical content")
    return actual_qualification_sha256


def build_model_qualification(
    study: StudyProtocol,
    model_id: str,
    model_directory: str | Path,
) -> dict[str, Any]:
    """Create a deterministic qualification manifest for an indexed local checkpoint."""
    model = _model_for_id(study, model_id)
    directory = Path(model_directory).resolve()
    if not directory.is_dir():
        raise ValueError(f"model path is not a directory: {directory}")
    index_name = "model.safetensors.index.json"
    index = _load_json_object(directory / index_name, "model tensor index")
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise ValueError("model tensor index must contain a non-empty weight_map")
    raw_tensor_paths = set(weight_map.values())
    if not all(isinstance(path, str) for path in raw_tensor_paths):
        raise ValueError("model tensor index contains a non-string artifact path")
    tensor_paths = {str(path) for path in raw_tensor_paths}
    paths = sorted(
        tensor_paths
        | {
            index_name,
            "config.json",
            "tokenizer_config.json",
            "chat_template.jinja",
        }
    )
    files = []
    for relative in paths:
        path = directory / relative
        if not path.is_file():
            raise ValueError(f"required model artifact is missing: {relative}")
        files.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    qualification: dict[str, Any] = {
        "schema_version": "1",
        "model_id": model.id,
        "model_source": model.source,
        "model_revision": model.checkpoint_revision,
        "model_index": index_name,
        "indexed_tensor_files": len(tensor_paths),
        "indexed_tensor_bytes": sum(item["size"] for item in files if item["path"] in tensor_paths),
        "files": files,
    }
    qualification["qualification_sha256"] = hashlib.sha256(
        json.dumps(qualification, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    verify_model_artifact(model, directory, qualification)
    return qualification


def _sampling_kwargs(model: ModelSpec, seed: int) -> dict[str, Any]:
    allowed = {
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "presence_penalty",
        "repetition_penalty",
        "max_tokens",
    }
    result = {key: value for key, value in model.runtime.sampler.items() if key in allowed}
    result["seed"] = seed
    return result


def run_offline_batch(
    *,
    protocol_path: str | Path,
    manifest_path: str | Path,
    requests_path: str | Path,
    model_id: str,
    model_path: str | Path,
    model_qualification_path: str | Path,
    chat_template_path: str | Path,
    lease_receipt_path: str | Path,
    output_path: str | Path,
    engine_factory: Callable[..., Any] | None = None,
    tokenizer_factory: Callable[..., Any] | None = None,
    sampling_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute one model's exact ordered offline cohort and retain JSONL evidence."""
    study = StudyProtocol.from_yaml(protocol_path)
    model = _model_for_id(study, model_id)
    manifest = _load_json_object(manifest_path, "study manifest")
    requests = load_batch_requests(requests_path)
    validate_batch_contract(study, manifest, requests)

    output = Path(output_path)
    if output.exists():
        raise ValueError(f"refusing to overwrite existing batch output: {output}")
    model_directory = Path(model_path).resolve()
    if not model_directory.is_dir():
        raise ValueError(f"model path is not a directory: {model_directory}")
    qualification = _load_json_object(model_qualification_path, "model qualification")
    qualification_sha256 = verify_model_artifact(model, model_directory, qualification)
    lease_receipt = Path(lease_receipt_path)
    if not lease_receipt.is_file():
        raise ValueError(f"GPU lease receipt does not exist: {lease_receipt}")
    lease_sha256 = _sha256_file(lease_receipt)

    template_path = Path(chat_template_path)
    template = template_path.read_text(encoding="utf-8")
    template_sha256 = hashlib.sha256(template.encode()).hexdigest()
    if template_sha256 != model.runtime.chat_template_sha256:
        raise ValueError("chat template SHA-256 does not match the qualified runtime")

    expected_hostname = study.raw["study"]["execution"].get("expected_hostname")
    if expected_hostname and platform.node() != expected_hostname:
        raise ValueError(
            f"offline study batches require host {expected_hostname}, found {platform.node()}"
        )

    os.environ["VLLM_BATCH_INVARIANT"] = "1"
    os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"
    if engine_factory is None or tokenizer_factory is None or sampling_factory is None:
        try:
            from transformers import AutoTokenizer  # type: ignore[import-not-found]
            from vllm import LLM, SamplingParams  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised on the A100 runtime
            raise RuntimeError(
                "offline execution requires vLLM and transformers in the pinned A100 image"
            ) from exc
        engine_factory = engine_factory or LLM
        tokenizer_factory = tokenizer_factory or AutoTokenizer.from_pretrained
        sampling_factory = sampling_factory or SamplingParams

    tokenizer = tokenizer_factory(str(model_directory), trust_remote_code=False)
    prompts = [
        tokenizer.apply_chat_template(
            list(request.messages),
            tokenize=False,
            add_generation_prompt=True,
            chat_template=template,
            enable_thinking=model.runtime.reasoning_mode == "on",
        )
        for request in requests
    ]
    sampling_params = [
        sampling_factory(
            **_sampling_kwargs(
                model,
                study.generation_seed(request.allocation_id, request.sample_id),
            )
        )
        for request in requests
    ]
    execution = study.raw["study"]["execution"]
    server = execution["model_server"]
    engine = engine_factory(
        model=str(model_directory),
        dtype=model.runtime.dtype,
        max_model_len=model.runtime.context_limit,
        tensor_parallel_size=server["tensor_parallel_size"],
        trust_remote_code=False,
        enable_prefix_caching=False,
    )

    started = time.time()
    generated = engine.generate(prompts, sampling_params, use_tqdm=True)
    elapsed_seconds = time.time() - started
    if len(generated) != len(requests):
        raise RuntimeError(f"vLLM returned {len(generated)} results for {len(requests)} requests")

    for request, result in zip(requests, generated, strict=True):
        candidates = list(getattr(result, "outputs", ()))
        if len(candidates) != 1:
            raise RuntimeError(
                f"request {request.request_id} returned {len(candidates)} candidates"
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        for request, prompt, result in zip(requests, prompts, generated, strict=True):
            candidates = list(getattr(result, "outputs", ()))
            candidate = candidates[0]
            record = {
                "schema_version": "1",
                "study_id": study.id,
                "protocol_sha256": study.canonical_sha256,
                "manifest_sha256": manifest.get("manifest_sha256"),
                "model_id": model.id,
                "model_source": model.source,
                "model_revision": model.checkpoint_revision,
                "request_id": request.request_id,
                "allocation_id": request.allocation_id,
                "sample_id": request.sample_id,
                "generation_seed": study.generation_seed(request.allocation_id, request.sample_id),
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "completion": candidate.text,
                "finish_reason": getattr(candidate, "finish_reason", None),
                "prompt_tokens": len(getattr(result, "prompt_token_ids", ())),
                "completion_tokens": len(getattr(candidate, "token_ids", ())),
                "runtime": {
                    "engine": "vllm",
                    "image": server["image"],
                    "batch_invariant": True,
                    "v1_multiprocessing": False,
                    "chat_template_sha256": template_sha256,
                    "lease_receipt_sha256": lease_sha256,
                    "model_qualification_sha256": qualification_sha256,
                },
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(output)
    return {
        "study_id": study.id,
        "model_id": model.id,
        "requests": len(requests),
        "allocations": list(dict.fromkeys(request.allocation_id for request in requests)),
        "elapsed_seconds": elapsed_seconds,
        "output": str(output),
        "output_sha256": _sha256_file(output),
    }
