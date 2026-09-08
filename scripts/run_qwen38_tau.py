#!/usr/bin/env python3
"""Run and officially score a manifest-locked tau3-bench cohort."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.request
from collections import Counter
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, Sequence

import yaml
from qwen38_tau_context import (
    TargetContextGuard,
    TargetContextRuntimeInvalid,
    exception_chain,
    load_attested_tokenizer,
    load_patch_contract,
    verify_tau_checkout,
)

from matric_eval.studies.run_status import AdapterStatus, adapter_main

TAU_PACKAGE_VERSION = "1.0.1"
TAU_SOURCE_REVISION = "672227c6b6676edc20d57ea53b7000262aae77b9"
SANDBOX_RUNTIME_PACKAGE_VERSION = "0.0.23"
RANK_BM25_PACKAGE_VERSION = "0.2.2"
TAU_EXTERNAL_MODEL = "gpt-4.1-2025-04-14"
CONTEXT_SAFETY_MARGIN_TOKENS = 32
PRIVATE_ROOT = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TAU_PATCH_MANIFEST = (
    REPOSITORY_ROOT / "studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-context-guard.json"
)
JsonObject = dict[str, Any]
SENSITIVE_FRAGMENTS = ("key", "token", "secret", "password", "credential")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _git_revision(checkout: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    revision = result.stdout.strip()
    if len(revision) != 40:
        raise RuntimeError(f"{checkout} did not report a full Git revision")
    return revision


def _tau_worktree_evidence(checkout: Path, manifest_path: Path) -> JsonObject:
    contract = load_patch_contract(manifest_path)
    if contract.upstream_revision != TAU_SOURCE_REVISION:
        raise RuntimeError("Tau patch manifest does not match the protocol-pinned revision")
    return verify_tau_checkout(checkout, contract)


def _generation_seed(root_seed: int, sample_id: str) -> int:
    payload = f"{root_seed}\0tau3-bench\0{sample_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _load_protocol(path: Path, model_id: str) -> tuple[JsonObject, JsonObject, JsonObject]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("study"), dict):
        raise ValueError("protocol must contain a study object")
    study: JsonObject = payload["study"]
    models = study.get("models")
    if not isinstance(models, list):
        raise ValueError("protocol models must be a list")
    model = next(
        (
            candidate
            for candidate in models
            if isinstance(candidate, dict) and candidate.get("id") == model_id
        ),
        None,
    )
    if model is None:
        raise ValueError(f"unknown study model id: {model_id}")
    runtime = model.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("execution_mode") != "offline-batch":
        raise ValueError("tau target must use the primary offline-batch runtime contract")
    sampler = runtime.get("sampler")
    if not isinstance(sampler, dict) or sampler.get("seed") != study.get("seed"):
        raise ValueError("model sampler must use the shared study seed")
    benchmarks = study.get("benchmarks")
    tau = (
        next(
            (
                candidate
                for candidate in benchmarks
                if isinstance(candidate, dict) and candidate.get("id") == "tau3-bench"
            ),
            None,
        )
        if isinstance(benchmarks, list)
        else None
    )
    if tau is None or tau.get("dataset_revision") != TAU_SOURCE_REVISION:
        raise ValueError("protocol does not contain the pinned tau3-bench allocation")
    if tau.get("scoring_protocol") != "tau3-bench-1.0.1-official-reward":
        raise ValueError("protocol does not require the pinned official tau reward")
    return study, model, sampler


def _flatten_scored_ids(scored_by_domain: JsonObject) -> list[str]:
    flattened: list[str] = []
    for domain, task_ids in scored_by_domain.items():
        if not isinstance(domain, str) or not domain or not isinstance(task_ids, list):
            raise ValueError("tau scored IDs must map domain names to task ID lists")
        if not task_ids or not all(isinstance(task_id, str) and task_id for task_id in task_ids):
            raise ValueError(f"tau domain {domain!r} has an invalid task ID list")
        flattened.extend(f"{domain}:{task_id}" for task_id in task_ids)
    if len(flattened) != len(set(flattened)):
        raise ValueError("tau scored IDs must be unique")
    return flattened


def _verify_manifest(
    manifest_path: Path,
    summary: JsonObject,
    scored_ids: list[str],
    study_id: str,
) -> str:
    manifest = _load_object(manifest_path, "study manifest")
    canonical = dict(manifest)
    declared_hash = canonical.pop("manifest_sha256", None)
    actual_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared_hash != actual_hash or summary.get("manifest_sha256") != actual_hash:
        raise ValueError("study manifest hash does not match the agentic input summary")
    cohort = manifest.get("cohort")
    if (
        manifest.get("study_id") != study_id
        or cohort not in {"pilot", "full"}
        or summary.get("cohort") != cohort
    ):
        raise ValueError("tau runner requires the declared pilot or full manifest")
    allocations = manifest.get("allocations")
    selected = (
        next(
            (
                allocation.get("selected_ids")
                for allocation in allocations
                if isinstance(allocation, dict) and allocation.get("allocation_id") == "tau3-bench"
            ),
            None,
        )
        if isinstance(allocations, list)
        else None
    )
    if selected != scored_ids:
        raise ValueError("tau scored IDs do not exactly match the study manifest")
    return actual_hash


def _validate_endpoint(endpoint: str, model_id: str, model_path: Path) -> None:
    if not endpoint.startswith("http://127.0.0.1:") or not endpoint.endswith("/v1"):
        raise ValueError("tau endpoint must be a localhost HTTP /v1 endpoint")
    with urllib.request.urlopen(f"{endpoint}/models", timeout=10) as response:
        payload = json.loads(response.read(1024 * 1024))
    data = payload.get("data") if isinstance(payload, dict) else None
    served = (
        {
            item.get("id")
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if isinstance(data, list)
        else set()
    )
    if model_id not in served or str(model_path) not in served:
        raise RuntimeError("study server does not advertise both required tau model names")


def _load_external_args(path: Path | None) -> JsonObject:
    payload: JsonObject = {"temperature": 0.0}
    if path is not None:
        payload = _load_object(path, "external LLM arguments")
    pending: list[Any] = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for key, nested in value.items():
                lowered = str(key).lower()
                if any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS):
                    raise ValueError(
                        "external LLM credentials must be injected through a file descriptor"
                    )
                pending.append(nested)
        elif isinstance(value, list):
            pending.extend(value)
    if "seed" in payload:
        raise ValueError("the tau runner derives and supplies the per-task seed")
    from matric_eval.studies.client_conformance import bounded_external_arguments

    # Validate explicit bounds without changing the frozen study defaults.
    bounded_external_arguments(payload)
    return payload


def _read_secret_fd(fd: int) -> str:
    if fd < 3:
        raise ValueError("external API key descriptor must be 3 or greater")
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            total += len(chunk)
            if total > 16384:
                raise ValueError("external API key descriptor exceeds the size limit")
            chunks.append(chunk)
    finally:
        os.close(fd)
    try:
        secret = b"".join(chunks).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("external API key descriptor is not UTF-8") from exc
    if not secret or "\x00" in secret or "\n" in secret or "\r" in secret:
        raise ValueError("external API key descriptor contains an invalid value")
    return secret


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if any(fragment in str(key).lower() for fragment in SENSITIVE_FRAGMENTS)
                else _redact_sensitive(nested)
            )
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(nested) for nested in value]
    return value


def _knowledge_dependency_evidence() -> JsonObject:
    binaries = {name: shutil.which(name) for name in ("srt", "rg", "bwrap", "socat")}
    missing = [name for name, path in binaries.items() if path is None]
    if missing:
        raise RuntimeError("tau banking sandbox dependencies are missing: " + ", ".join(missing))
    npm = subprocess.run(
        ["npm", "list", "-g", "--json", "@anthropic-ai/sandbox-runtime"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    npm_payload = json.loads(npm.stdout)
    dependencies = npm_payload.get("dependencies") if isinstance(npm_payload, dict) else None
    package = (
        dependencies.get("@anthropic-ai/sandbox-runtime")
        if isinstance(dependencies, dict)
        else None
    )
    npm_version = package.get("version") if isinstance(package, dict) else None
    if npm_version != SANDBOX_RUNTIME_PACKAGE_VERSION:
        raise RuntimeError("sandbox-runtime package version does not match the tau contract")
    rank_bm25_version = importlib.metadata.version("rank-bm25")
    if rank_bm25_version != RANK_BM25_PACKAGE_VERSION:
        raise RuntimeError("rank-bm25 package version does not match the tau contract")

    from tau2.knowledge.sandbox_manager import SandboxManager

    with tempfile.TemporaryDirectory(prefix="tau-sandbox-canary-") as base:
        with SandboxManager(base_temp_dir=base) as sandbox:
            code, stdout, stderr = sandbox.run_command("printf sandbox-canary")
    if code != 0 or stdout != "sandbox-canary" or stderr:
        raise subprocess.CalledProcessError(
            code, "tau banking sandbox execution canary", output=stdout, stderr=stderr
        )
    return {
        "binaries": binaries,
        "sandbox_runtime_npm_version": npm_version,
        "rank_bm25_version": rank_bm25_version,
        "execution_canary": "passed",
    }


def _validate_context_allocation(
    input_tokens: int,
    output_tokens: int,
    context_limit: int,
    safety_margin: int = CONTEXT_SAFETY_MARGIN_TOKENS,
) -> None:
    """Reject a declared request budget that overbooks the model context."""
    values = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "context_limit": context_limit,
        "safety_margin": safety_margin,
    }
    for label, value in values.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"{label} must be a positive integer")
    if safety_margin < 32:
        raise ValueError("context safety margin must be at least 32 tokens")
    combined = input_tokens + output_tokens + safety_margin
    if combined > context_limit:
        raise ValueError(
            f"combined context budget {combined} exceeds context limit {context_limit}"
        )


def _context_budget(context_limit: int, output_tokens: int) -> JsonObject:
    """Reserve output and safety tokens before advertising the input limit."""
    if type(context_limit) is not int or context_limit < 1:
        raise ValueError("context_limit must be a positive integer")
    if type(output_tokens) is not int or output_tokens < 1:
        raise ValueError("output_tokens must be a positive integer")
    input_tokens = context_limit - output_tokens - CONTEXT_SAFETY_MARGIN_TOKENS
    _validate_context_allocation(input_tokens, output_tokens, context_limit)
    return {
        "max_context_tokens": context_limit,
        "max_input_tokens": input_tokens,
        "max_output_tokens": output_tokens,
        "safety_margin_tokens": CONTEXT_SAFETY_MARGIN_TOKENS,
    }


def _agent_args(endpoint: str, sampler: JsonObject, context_limit: int) -> JsonObject:
    context_budget = _context_budget(context_limit, sampler["max_tokens"])
    return {
        "api_base": endpoint,
        "api_key": "EMPTY",
        "temperature": float(sampler["temperature"]),
        "top_p": float(sampler["top_p"]),
        "presence_penalty": float(sampler["presence_penalty"]),
        "max_tokens": context_budget["max_output_tokens"],
        "num_retries": 0,
        "extra_body": {
            "top_k": int(sampler["top_k"]),
            "min_p": float(sampler["min_p"]),
            "repetition_penalty": float(sampler["repetition_penalty"]),
            "chat_template_kwargs": {"enable_thinking": False},
        },
    }


def _server_argument(arguments: list[Any], option: str) -> str:
    if arguments.count(option) != 1:
        raise ValueError(f"server receipt must contain exactly one {option}")
    index = arguments.index(option)
    if index + 1 >= len(arguments):
        raise ValueError(f"server receipt has no value for {option}")
    value = arguments[index + 1]
    if not isinstance(value, str):
        raise ValueError(f"server receipt has a non-string value for {option}")
    return value


def _load_target_counter(
    *,
    server_receipt: JsonObject,
    model_path: Path,
    chat_template: Path,
    runtime: JsonObject,
    transformers_version: str,
    tokenizer_factory: Any = None,
) -> tuple[Any, JsonObject]:
    server_runtime = server_receipt.get("runtime")
    versions = server_runtime.get("versions") if isinstance(server_runtime, dict) else None
    arguments = server_runtime.get("arguments") if isinstance(server_runtime, dict) else None
    if not isinstance(versions, dict) or versions.get("transformers") != transformers_version:
        raise ValueError("server Transformers version does not match the Tau patch contract")
    if not isinstance(arguments, list):
        raise ValueError("server receipt does not contain its effective arguments")
    if server_receipt.get("chat_template_sha256") != runtime.get("chat_template_sha256"):
        raise ValueError("server chat template does not match the model runtime contract")
    if _server_argument(arguments, "--chat-template") != str(chat_template):
        raise ValueError("Tau counter template path differs from the server override")
    if _server_argument(arguments, "--max-model-len") != str(runtime["context_limit"]):
        raise ValueError("server context limit differs from the Tau runtime contract")
    if not arguments or arguments[0] != str(model_path):
        raise ValueError("server receipt model path differs from the Tau tokenizer path")
    required_flags = {"--enable-auto-tool-choice", "--language-model-only"}
    if not required_flags.issubset(set(arguments)):
        raise ValueError("server receipt is missing the sealed tool/reasoning interface")
    if (
        _server_argument(arguments, "--reasoning-parser") != "qwen3"
        or _server_argument(arguments, "--tool-call-parser") != "qwen3_coder"
    ):
        raise ValueError("server receipt uses the wrong tool/reasoning parser")
    return load_attested_tokenizer(
        model_path=model_path,
        chat_template_path=chat_template,
        expected_template_sha256=str(server_receipt["chat_template_sha256"]),
        expected_transformers_version=transformers_version,
        tokenizer_factory=tokenizer_factory,
    )


def _private_path(path: Path, label: str) -> None:
    if not path.is_absolute() or not path.is_relative_to(PRIVATE_ROOT):
        raise ValueError(f"{label} is outside {PRIVATE_ROOT}: {path}")
    if path.exists():
        raise ValueError(f"refusing to overwrite tau evidence: {path}")


def _result_filename(canonical_id: str) -> str:
    digest = hashlib.sha256(canonical_id.encode()).hexdigest()[:20]
    return f"task-{digest}.json"


def _write_private_json(path: Path, payload: Any) -> str:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return _sha256_file(path)


def _context_invalid_failure(exc: TargetContextRuntimeInvalid) -> JsonObject:
    return {
        "owner": "context-runtime",
        "actor": "runner",
        "stage": "context-budget",
        "retryable": False,
        "http_attempted": False,
        "side_effect_retry_attempted": False,
        "exception_chain": exception_chain(exc),
        "context_observation": exc.observation,
    }


def run_tau(args: argparse.Namespace) -> JsonObject:
    if platform.node() != "basilisk":
        raise RuntimeError("tau study execution requires host basilisk")
    _private_path(args.result_dir, "tau result directory")
    _private_path(args.receipt, "tau receipt")
    if importlib.metadata.version("tau2") != TAU_PACKAGE_VERSION:
        raise RuntimeError("installed tau runner version does not match the study contract")
    if _git_revision(args.tau_checkout) != TAU_SOURCE_REVISION:
        raise RuntimeError("tau source checkout revision does not match the study contract")
    patch_contract = load_patch_contract(args.tau_patch_manifest)
    tau_worktree = _tau_worktree_evidence(args.tau_checkout, args.tau_patch_manifest)

    study, model, sampler = _load_protocol(args.protocol, args.model_id)
    runtime = model["runtime"]
    context_budget = _context_budget(runtime["context_limit"], sampler["max_tokens"])
    target_names = {
        args.model_id,
        str(args.model_path),
        f"hosted_vllm/{args.model_id}",
        str(model.get("source", "")),
    }
    if args.nl_evaluator_model in target_names:
        raise ValueError("a target model may not score tau natural-language assertions")
    auxiliary_profile = None
    auxiliary_amendment = None
    if getattr(args, "auxiliary_amendment", None) and not getattr(
        args, "auxiliary_client_profile", None
    ):
        raise ValueError("an auxiliary amendment requires its client profile")
    if getattr(args, "auxiliary_client_profile", None):
        from matric_eval.studies.auxiliary_runtime import load_amendment

        if not args.auxiliary_amendment:
            raise ValueError("an explicit auxiliary amendment is required")
        auxiliary_profile, auxiliary_amendment = load_amendment(
            args.auxiliary_client_profile,
            args.auxiliary_amendment,
            study_id=str(study["id"]),
            protocol_sha256=_sha256_file(args.protocol),
        )
        if (
            args.user_model != auxiliary_profile.model
            or args.nl_evaluator_model != auxiliary_profile.model
        ):
            raise ValueError("external models must match the declared auxiliary amendment")
        if auxiliary_profile.target_model not in target_names:
            raise ValueError("auxiliary amendment target identity does not match this run")
    elif args.user_model != TAU_EXTERNAL_MODEL or args.nl_evaluator_model != TAU_EXTERNAL_MODEL:
        raise ValueError(f"tau external models must use fixed snapshot {TAU_EXTERNAL_MODEL}")
    if os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY must not be exported; use --external-api-key-fd")

    summary = _load_object(args.inputs_summary, "agentic input summary")
    scored_by_domain = _load_object(args.scored_ids, "tau scored IDs")
    scored_ids = _flatten_scored_ids(scored_by_domain)
    artifacts = summary.get("artifacts")
    expected_ids_hash = (
        artifacts.get("tau3-scored-ids.json") if isinstance(artifacts, dict) else None
    )
    if _sha256_file(args.scored_ids) != expected_ids_hash:
        raise ValueError("tau scored ID hash does not match the agentic input summary")
    scored_samples = summary.get("scored_samples")
    if not isinstance(scored_samples, dict) or len(scored_ids) != scored_samples.get("tau3-bench"):
        raise ValueError("tau scored sample count does not match the agentic input summary")
    manifest_sha256 = _verify_manifest(args.manifest, summary, scored_ids, str(study["id"]))
    server_receipt = _load_object(args.server_receipt, "model server receipt")
    if (
        server_receipt.get("study_id") != study["id"]
        or server_receipt.get("model_id") != args.model_id
        or server_receipt.get("protocol_sha256") != summary.get("protocol_sha256")
    ):
        raise ValueError("model server receipt does not match the tau study run")
    target_counter, tokenizer_attestation = _load_target_counter(
        server_receipt=server_receipt,
        model_path=args.model_path,
        chat_template=args.chat_template,
        runtime=runtime,
        transformers_version=patch_contract.transformers_version,
    )
    _validate_endpoint(args.endpoint, args.model_id, args.model_path)

    external_args = _load_external_args(args.external_llm_args)
    if auxiliary_profile is not None:
        from matric_eval.studies.auxiliary_runtime import external_arguments

        declared_args = external_arguments(auxiliary_profile)
        if args.external_llm_args and external_args != declared_args:
            raise ValueError("external arguments do not match the auxiliary profile")
        external_args = declared_args
    agent_args = _agent_args(args.endpoint, sampler, runtime["context_limit"])
    root_seed = int(study["seed"])
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"

    import tau2.evaluator.evaluator_nl_assertions as nl_evaluator
    from tau2.data_model.simulation import TextRunConfig
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.run import get_tasks, run_single_task
    from tau2.utils.llm_utils import scoped_llm_request_guard

    knowledge_dependencies = (
        _knowledge_dependency_evidence() if "banking_knowledge" in scored_by_domain else None
    )

    task_inventory: dict[str, Any] = {}
    for domain, task_ids in scored_by_domain.items():
        tasks = get_tasks(domain, task_split_name="base", task_ids=task_ids)
        task_inventory[domain] = {task.id: task for task in tasks}
        if set(task_inventory[domain]) != set(task_ids):
            raise RuntimeError(f"official tau task loader omitted selected IDs for {domain}")

    external_api_key = (
        _read_secret_fd(args.external_api_key_fd) if auxiliary_profile is None else None
    )
    runtime_external_args = dict(external_args)
    if external_api_key is not None:
        runtime_external_args["api_key"] = external_api_key

    args.result_dir.mkdir(parents=True, exist_ok=False)
    args.result_dir.chmod(0o750)
    started = time.time()
    records: list[JsonObject] = []
    terminations: Counter[str] = Counter()
    analytic_statuses: Counter[str] = Counter()
    status = AdapterStatus(args.model_id, "tau3-bench")
    for canonical_id in scored_ids:
        status.start(canonical_id)
        domain, task_id = canonical_id.split(":", 1)
        seed = _generation_seed(root_seed, canonical_id)
        task = task_inventory[domain][task_id]
        config = TextRunConfig(
            domain=domain,
            task_set_name=domain,
            task_split_name="base",
            task_ids=[task_id],
            num_trials=1,
            agent="llm_agent",
            user="user_simulator",
            llm_agent=f"hosted_vllm/{args.model_id}",
            llm_args_agent=dict(agent_args),
            llm_user=args.user_model,
            llm_args_user=dict(runtime_external_args),
            max_steps=200,
            max_errors=10,
            timeout=None,
            max_concurrency=1,
            workers=0,
            seed=seed,
            log_level="ERROR",
            verbose_logs=False,
            max_retries=0,
            auto_resume=False,
            auto_review=False,
            hallucination_retries=0,
            retrieval_config="alltools" if domain == "banking_knowledge" else None,
        )
        nl_evaluator.DEFAULT_LLM_NL_ASSERTIONS = args.nl_evaluator_model
        nl_evaluator.DEFAULT_LLM_NL_ASSERTIONS_ARGS = {
            **runtime_external_args,
            "seed": seed,
        }
        task_started = time.time()
        target_guard = TargetContextGuard(
            target_model=f"hosted_vllm/{args.model_id}",
            budget=context_budget,
            count_tokens=target_counter,
        )
        try:
            auxiliary_scope: AbstractContextManager[None] = nullcontext()
            if auxiliary_profile is not None:
                import tau2.utils.llm_utils as tau_llm

                from matric_eval.studies.auxiliary_runtime import scoped_auxiliary_client

                auxiliary_scope = scoped_auxiliary_client(
                    tau_llm, auxiliary_profile, args.result_dir / "auxiliary-client", seed=seed
                )
            with auxiliary_scope, scoped_llm_request_guard(target_guard):
                simulation = run_single_task(
                    config,
                    task,
                    seed=seed,
                    evaluation_type=EvaluationType.ALL,
                    verbose_logs=False,
                    auto_review=False,
                )
        except TargetContextRuntimeInvalid as exc:
            output_path = args.result_dir / _result_filename(canonical_id)
            failure = _context_invalid_failure(exc)
            raw_payload = _redact_sensitive(
                {
                    "schema_version": "1",
                    "canonical_id": canonical_id,
                    "generation_seed": seed,
                    "analytic_status": "invalid",
                    "official_reward": None,
                    "official_termination_reason": None,
                    "partial_trace": {"target_request": target_guard.last_request},
                    "failure_attribution": failure,
                }
            )
            if external_api_key and external_api_key in json.dumps(raw_payload, sort_keys=True):
                raise RuntimeError("external API key escaped invalid evidence redaction")
            raw_sha256 = _write_private_json(output_path, raw_payload)
            status.result(
                canonical_id,
                reward=None,
                valid=False,
                reason="context_runtime_invalid",
                native_failure=failure,
                evidence_uri=str(output_path),
                evidence_sha256=raw_sha256,
            )
            analytic_statuses["invalid"] += 1
            records.append(
                {
                    "canonical_id": canonical_id,
                    "generation_seed": seed,
                    "reward": None,
                    "termination_reason": None,
                    "analytic_status": "invalid",
                    "failure_attribution": failure,
                    "duration_seconds": time.time() - task_started,
                    "fresh_attempt_count": 1,
                    "recovered_attempt_count": 0,
                    "total_attempt_count": 1,
                    "raw_result_file": output_path.name,
                    "raw_result_sha256": raw_sha256,
                }
            )
            continue
        if simulation.seed != seed:
            raise RuntimeError(f"tau did not retain the declared seed for {canonical_id}")
        output_path = args.result_dir / _result_filename(canonical_id)
        raw_payload = _redact_sensitive(simulation.model_dump(mode="json"))
        if external_api_key and external_api_key in json.dumps(raw_payload, sort_keys=True):
            raise RuntimeError("external API key escaped simulation evidence redaction")
        raw_sha256 = _write_private_json(output_path, raw_payload)
        termination = str(
            getattr(simulation.termination_reason, "value", simulation.termination_reason)
        )
        terminations[termination] += 1
        analytic_statuses["valid"] += 1
        reward = simulation.reward_info.reward if simulation.reward_info is not None else None
        status.result(
            canonical_id,
            reward=reward,
            valid=True,
            reason=None,
            evidence_uri=str(output_path),
            evidence_sha256=raw_sha256,
        )
        records.append(
            {
                "canonical_id": canonical_id,
                "generation_seed": seed,
                "reward": reward,
                "termination_reason": termination,
                "analytic_status": "valid",
                "failure_attribution": None,
                "duration_seconds": time.time() - task_started,
                "fresh_attempt_count": 1,
                "recovered_attempt_count": 0,
                "total_attempt_count": 1,
                "raw_result_file": output_path.name,
                "raw_result_sha256": raw_sha256,
            }
        )

    rewards = [float(record["reward"]) for record in records if record["reward"] is not None]
    receipt: JsonObject = {
        "schema_version": "1",
        "study_id": study["id"],
        "protocol_sha256": summary["protocol_sha256"],
        "manifest_sha256": manifest_sha256,
        "model_id": args.model_id,
        "model_source": model["source"],
        "model_revision": model["checkpoint_revision"],
        "server_receipt_sha256": _sha256_file(args.server_receipt),
        "runner": {
            "package": "tau2",
            "version": TAU_PACKAGE_VERSION,
            "source_revision": TAU_SOURCE_REVISION,
            "source_worktree": tau_worktree,
            "source_patch_manifest_sha256": _sha256_file(args.tau_patch_manifest),
            "python": platform.python_version(),
            "matric_eval_revision": _git_revision(Path(__file__).resolve().parents[1]),
            "api": "tau2.run.run_single_task",
            "evaluation_type": "all",
        },
        "execution": {
            "num_trials": 1,
            "max_steps": 200,
            "max_errors": 10,
            "timeout_seconds": None,
            "concurrency": 1,
            "workers": 0,
            "retries": 0,
            "hallucination_retries": 0,
            "banking_retrieval_config": "alltools",
            "banking_knowledge_dependencies": knowledge_dependencies,
            "external_credential_transport": "inherited-file-descriptor",
            "context_budget": context_budget,
            "context_budget_enforcement": "exact-serialized-target-pre-http",
            "tokenizer_attestation": tokenizer_attestation,
            "target_thinking_mode_requested": "disabled",
            "target_transport_retries": 0,
        },
        "sampler": sampler,
        "user_simulator": {"model": args.user_model, "arguments": external_args},
        "auxiliary_amendment": auxiliary_amendment,
        "nl_assertion_evaluator": {
            "model": args.nl_evaluator_model,
            "arguments": {**external_args, "seed": "per-task-generation-seed"},
        },
        "scored_samples": len(records),
        "scored_results": records,
        "reward_count": len(rewards),
        "reward_mean": sum(rewards) / len(rewards) if rewards else None,
        "analytic_status_counts": dict(sorted(analytic_statuses.items())),
        "termination_counts": dict(sorted(terminations.items())),
        "execution_seconds": time.time() - started,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    _write_private_json(args.receipt, receipt)
    runtime_external_args.clear()
    external_api_key = ""
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18083/v1")
    parser.add_argument("--tau-checkout", type=Path, required=True)
    parser.add_argument("--tau-patch-manifest", type=Path, default=DEFAULT_TAU_PATCH_MANIFEST)
    parser.add_argument("--chat-template", type=Path, required=True)
    parser.add_argument("--inputs-summary", type=Path, required=True)
    parser.add_argument("--scored-ids", type=Path, required=True)
    parser.add_argument("--user-model", required=True)
    parser.add_argument("--nl-evaluator-model", required=True)
    parser.add_argument("--external-llm-args", type=Path)
    parser.add_argument("--auxiliary-client-profile", type=Path)
    parser.add_argument("--auxiliary-amendment", type=Path)
    parser.add_argument("--external-api-key-fd", type=int, default=3)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    receipt = run_tau(build_parser().parse_args(argv))
    print(
        json.dumps(
            {
                "study_id": receipt["study_id"],
                "model_id": receipt["model_id"],
                "scored_samples": receipt["scored_samples"],
                "reward_mean": receipt["reward_mean"],
                "termination_counts": receipt["termination_counts"],
                "execution_seconds": receipt["execution_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(adapter_main(main))
