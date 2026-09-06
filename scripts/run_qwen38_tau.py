#!/usr/bin/env python3
"""Run and officially score the manifest-locked tau3-bench pilot."""

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
from pathlib import Path
from typing import Any, Sequence

import yaml

TAU_PACKAGE_VERSION = "1.0.1"
TAU_SOURCE_REVISION = "672227c6b6676edc20d57ea53b7000262aae77b9"
SANDBOX_RUNTIME_PACKAGE_VERSION = "0.0.23"
RANK_BM25_PACKAGE_VERSION = "0.2.2"
PRIVATE_ROOT = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
ALLOWED_TAU_WORKTREE_CHANGES = {"uv.lock"}
JsonObject = dict[str, Any]


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


def _tau_worktree_evidence(checkout: Path) -> JsonObject:
    status = subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain=v1", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    changed_paths = sorted(line[3:].strip() for line in status.splitlines() if len(line) >= 4)
    unexpected = sorted(set(changed_paths) - ALLOWED_TAU_WORKTREE_CHANGES)
    if unexpected:
        raise RuntimeError(
            "tau source checkout has modified tracked source outside the recorded lockfile: "
            + ", ".join(unexpected)
        )
    diff = subprocess.run(
        ["git", "-C", str(checkout), "diff", "--binary", "--", *changed_paths],
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout
    return {
        "tracked_changes": changed_paths,
        "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
    }


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
    manifest = _load_object(manifest_path, "pilot manifest")
    canonical = dict(manifest)
    declared_hash = canonical.pop("manifest_sha256", None)
    actual_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared_hash != actual_hash or summary.get("manifest_sha256") != actual_hash:
        raise ValueError("pilot manifest hash does not match the agentic input summary")
    if manifest.get("study_id") != study_id or manifest.get("cohort") != "pilot":
        raise ValueError("tau runner requires the declared pilot manifest")
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
        raise ValueError("tau scored IDs do not exactly match the pilot manifest")
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
    sensitive_fragments = ("key", "token", "secret", "password", "credential")
    pending: list[Any] = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for key, nested in value.items():
                lowered = str(key).lower()
                if any(fragment in lowered for fragment in sensitive_fragments):
                    raise ValueError(
                        "external LLM credentials must be injected through the environment"
                    )
                pending.append(nested)
        elif isinstance(value, list):
            pending.extend(value)
    if "seed" in payload:
        raise ValueError("the tau runner derives and supplies the per-task seed")
    return payload


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
        raise RuntimeError("tau banking sandbox execution canary failed")
    return {
        "binaries": binaries,
        "sandbox_runtime_npm_version": npm_version,
        "rank_bm25_version": rank_bm25_version,
        "execution_canary": "passed",
    }


def _agent_args(endpoint: str, sampler: JsonObject) -> JsonObject:
    return {
        "api_base": endpoint,
        "api_key": "EMPTY",
        "temperature": float(sampler["temperature"]),
        "top_p": float(sampler["top_p"]),
        "presence_penalty": float(sampler["presence_penalty"]),
        "max_tokens": int(sampler["max_tokens"]),
        "extra_body": {
            "top_k": int(sampler["top_k"]),
            "min_p": float(sampler["min_p"]),
            "repetition_penalty": float(sampler["repetition_penalty"]),
        },
    }


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


def run_tau(args: argparse.Namespace) -> JsonObject:
    if platform.node() != "basilisk":
        raise RuntimeError("tau study execution requires host basilisk")
    _private_path(args.result_dir, "tau result directory")
    _private_path(args.receipt, "tau receipt")
    if importlib.metadata.version("tau2") != TAU_PACKAGE_VERSION:
        raise RuntimeError("installed tau runner version does not match the study contract")
    if _git_revision(args.tau_checkout) != TAU_SOURCE_REVISION:
        raise RuntimeError("tau source checkout revision does not match the study contract")
    tau_worktree = _tau_worktree_evidence(args.tau_checkout)

    study, model, sampler = _load_protocol(args.protocol, args.model_id)
    target_names = {
        args.model_id,
        str(args.model_path),
        f"hosted_vllm/{args.model_id}",
        str(model.get("source", "")),
    }
    if args.nl_evaluator_model in target_names:
        raise ValueError("a target model may not score tau natural-language assertions")
    if not args.user_model.strip() or not args.nl_evaluator_model.strip():
        raise ValueError("tau external model identifiers must be non-empty exact snapshots")
    for env_name in args.required_secret_env:
        if not os.environ.get(env_name):
            raise RuntimeError(
                f"required credential environment variable is unavailable: {env_name}"
            )

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
    _validate_endpoint(args.endpoint, args.model_id, args.model_path)

    external_args = _load_external_args(args.external_llm_args)
    agent_args = _agent_args(args.endpoint, sampler)
    root_seed = int(study["seed"])
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"

    import tau2.evaluator.evaluator_nl_assertions as nl_evaluator
    from tau2.data_model.simulation import TextRunConfig
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.run import get_tasks, run_single_task

    knowledge_dependencies = (
        _knowledge_dependency_evidence() if "banking_knowledge" in scored_by_domain else None
    )

    task_inventory: dict[str, Any] = {}
    for domain, task_ids in scored_by_domain.items():
        tasks = get_tasks(domain, task_split_name="base", task_ids=task_ids)
        task_inventory[domain] = {task.id: task for task in tasks}
        if set(task_inventory[domain]) != set(task_ids):
            raise RuntimeError(f"official tau task loader omitted selected IDs for {domain}")

    args.result_dir.mkdir(parents=True, exist_ok=False)
    args.result_dir.chmod(0o750)
    started = time.time()
    records: list[JsonObject] = []
    terminations: Counter[str] = Counter()
    for canonical_id in scored_ids:
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
            llm_args_user=dict(external_args),
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
        nl_evaluator.DEFAULT_LLM_NL_ASSERTIONS_ARGS = {**external_args, "seed": seed}
        task_started = time.time()
        simulation = run_single_task(
            config,
            task,
            seed=seed,
            evaluation_type=EvaluationType.ALL,
            verbose_logs=False,
            auto_review=False,
        )
        if simulation.seed != seed:
            raise RuntimeError(f"tau did not retain the declared seed for {canonical_id}")
        output_path = args.result_dir / _result_filename(canonical_id)
        raw_sha256 = _write_private_json(output_path, simulation.model_dump(mode="json"))
        termination = str(
            getattr(simulation.termination_reason, "value", simulation.termination_reason)
        )
        terminations[termination] += 1
        reward = simulation.reward_info.reward if simulation.reward_info is not None else None
        records.append(
            {
                "canonical_id": canonical_id,
                "generation_seed": seed,
                "reward": reward,
                "termination_reason": termination,
                "duration_seconds": time.time() - task_started,
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
        },
        "sampler": sampler,
        "user_simulator": {"model": args.user_model, "arguments": external_args},
        "nl_assertion_evaluator": {
            "model": args.nl_evaluator_model,
            "arguments": {**external_args, "seed": "per-task-generation-seed"},
        },
        "scored_samples": len(records),
        "scored_results": records,
        "reward_count": len(rewards),
        "reward_mean": sum(rewards) / len(rewards) if rewards else None,
        "termination_counts": dict(sorted(terminations.items())),
        "execution_seconds": time.time() - started,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    _write_private_json(args.receipt, receipt)
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
    parser.add_argument("--inputs-summary", type=Path, required=True)
    parser.add_argument("--scored-ids", type=Path, required=True)
    parser.add_argument("--user-model", required=True)
    parser.add_argument("--nl-evaluator-model", required=True)
    parser.add_argument("--external-llm-args", type=Path)
    parser.add_argument("--required-secret-env", action="append", default=[])
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
    raise SystemExit(main())
